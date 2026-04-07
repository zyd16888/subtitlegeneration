"""
任务相关 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, AsyncGenerator
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from config.time_utils import ensure_utc
from models.base import get_db
from models.task import Task, TaskStatus
from services.task_manager import TaskManager
from services.emby_connector import EmbyConnector
from services.config_manager import ConfigManager
from tasks.subtitle_tasks import generate_subtitle_task
from services.auth import require_auth

router = APIRouter(prefix="/api", tags=["tasks"], dependencies=[Depends(require_auth)])


# ── 请求模型 ────────────────────────────────────────────────────────────────

class TaskConfigRequest(BaseModel):
    """单个任务配置"""
    media_item_id: str
    asr_engine: Optional[str] = None
    translation_service: Optional[str] = None
    openai_model: Optional[str] = None
    path_mapping_index: Optional[int] = None  # 指定路径映射规则索引
    source_language: Optional[str] = None  # 语音识别语言，覆盖全局配置


class CreateTaskRequest(BaseModel):
    """创建任务请求模型"""
    media_item_ids: Optional[List[str]] = None  # 批量创建，使用全局配置
    tasks: Optional[List[TaskConfigRequest]] = None  # 单独配置每个任务
    library_id: Optional[str] = None  # 当前浏览的媒体库 ID（用于路径映射匹配）


# ── 响应模型 ────────────────────────────────────────────────────────────────

class TaskResponse(BaseModel):
    """任务响应模型"""
    id: str
    media_item_id: str
    media_item_title: Optional[str] = None
    video_path: Optional[str] = None
    
    # 状态信息
    status: TaskStatus
    progress: int = Field(description="任务进度 (0-100)")
    
    # 时间信息
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_time: Optional[float] = Field(None, description="处理耗时（秒）")
    
    # 错误信息
    error_message: Optional[str] = None
    error_stage: Optional[str] = Field(None, description="错误发生的阶段")
    
    # 配置信息
    asr_engine: Optional[str] = None
    asr_model_id: Optional[str] = None
    translation_service: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    
    # 结果信息
    subtitle_path: Optional[str] = None
    segment_count: Optional[int] = Field(None, description="识别的字幕段落数")
    audio_duration: Optional[float] = Field(None, description="音频时长（秒）")
    
    class Config:
        from_attributes = True


class TaskDetailResponse(TaskResponse):
    """任务详情响应模型（包含更多细节）"""
    extra_info: Optional[dict] = Field(None, description="扩展信息")
    
    # 计算字段
    wait_time: Optional[float] = Field(None, description="等待时间（秒）")
    
    def __init__(self, **data):
        super().__init__(**data)
        # 计算等待时间
        if self.started_at and self.created_at:
            self.wait_time = (self.started_at - self.created_at).total_seconds()


class PaginatedTaskResponse(BaseModel):
    """分页任务响应模型"""
    items: List[TaskResponse]
    total: int
    limit: int
    offset: int


# ── 辅助函数 ────────────────────────────────────────────────────────────────

async def get_emby_connector(db: Session = Depends(get_db)) -> AsyncGenerator[EmbyConnector, None]:
    """获取 Emby 连接器实例（自动关闭，防止连接泄漏）"""
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    
    if not config.emby_url or not config.emby_api_key:
        raise HTTPException(
            status_code=400,
            detail="Emby 连接未配置"
        )
    
    connector = EmbyConnector(config.emby_url, config.emby_api_key)
    try:
        yield connector
    finally:
        await connector.close()


def task_to_response(task: Task) -> TaskResponse:
    """将 Task 模型转换为响应模型"""
    return TaskResponse(
        id=task.id,
        media_item_id=task.media_item_id,
        media_item_title=task.media_item_title,
        video_path=task.video_path,
        status=task.status,
        progress=task.progress,
        created_at=ensure_utc(task.created_at),
        started_at=ensure_utc(task.started_at),
        completed_at=ensure_utc(task.completed_at),
        processing_time=task.processing_time,
        error_message=task.error_message,
        error_stage=task.error_stage,
        asr_engine=task.asr_engine,
        asr_model_id=task.asr_model_id,
        translation_service=task.translation_service,
        source_language=task.source_language,
        target_language=task.target_language,
        subtitle_path=task.subtitle_path,
        segment_count=task.segment_count,
        audio_duration=task.audio_duration,
    )


# ── API 端点 ────────────────────────────────────────────────────────────────

@router.post("/tasks", response_model=List[TaskResponse])
async def create_tasks(
    request: CreateTaskRequest,
    db: Session = Depends(get_db),
    emby: EmbyConnector = Depends(get_emby_connector)
):
    """
    创建字幕生成任务（支持批量）
    
    支持两种模式：
    1. media_item_ids: 批量创建，使用全局配置
    2. tasks: 为每个任务单独配置 ASR 引擎和翻译服务
    
    Args:
        request: 包含媒体项 ID 列表或任务配置列表的请求
        
    Returns:
        创建的任务列表
    """
    if not request.media_item_ids and not request.tasks:
        raise HTTPException(
            status_code=400,
            detail="必须提供 media_item_ids 或 tasks"
        )
    
    task_manager = TaskManager(db)
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    created_tasks = []
    
    try:
        # 处理批量创建（使用全局配置）
        if request.media_item_ids:
            for media_item_id in request.media_item_ids:
                # 获取媒体项信息
                try:
                    media_item = await emby.get_media_item(media_item_id)
                    # 使用音频流 URL 而不是物理路径（支持远程 Emby）
                    audio_url = await emby.get_audio_stream_url(media_item_id)
                except ValueError as e:
                    # 媒体项不存在或没有路径
                    raise HTTPException(
                        status_code=404,
                        detail=str(e)
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"获取媒体项 {media_item_id} 失败: {str(e)}"
                    )
                
                # 创建任务（记录配置信息）
                task = await task_manager.create_task(
                    media_item_id=media_item_id,
                    media_item_title=media_item.name,
                    video_path=audio_url,
                    asr_engine=config.asr_engine,
                    asr_model_id=config.asr_model_id,
                    translation_service=config.translation_service,
                    source_language=config.source_language,
                    target_language=config.target_language,
                )
                
                # 提交 Celery 任务（使用全局配置）
                generate_subtitle_task.delay(
                    task_id=task.id,
                    media_item_id=media_item_id,
                    video_path=audio_url,
                    library_id=request.library_id,
                    source_language=None,  # 使用全局配置的语言
                )

                created_tasks.append(task_to_response(task))

        # 处理单独配置的任务
        if request.tasks:
            for task_config in request.tasks:
                # 获取媒体项信息
                try:
                    media_item = await emby.get_media_item(task_config.media_item_id)
                    # 使用音频流 URL 而不是物理路径（支持远程 Emby）
                    audio_url = await emby.get_audio_stream_url(task_config.media_item_id)
                except ValueError as e:
                    # 媒体项不存在或没有路径
                    raise HTTPException(
                        status_code=404,
                        detail=str(e)
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"获取媒体项 {task_config.media_item_id} 失败: {str(e)}"
                    )

                # 确定使用的配置
                task_asr_engine = task_config.asr_engine or config.asr_engine
                task_translation_service = task_config.translation_service or config.translation_service
                task_source_language = task_config.source_language or config.source_language

                # 创建任务
                task = await task_manager.create_task(
                    media_item_id=task_config.media_item_id,
                    media_item_title=media_item.name,
                    video_path=audio_url,
                    asr_engine=task_asr_engine,
                    asr_model_id=config.asr_model_id,
                    translation_service=task_translation_service,
                    source_language=task_source_language,
                    target_language=config.target_language,
                )

                # 提交 Celery 任务（使用自定义配置）
                generate_subtitle_task.delay(
                    task_id=task.id,
                    media_item_id=task_config.media_item_id,
                    video_path=audio_url,
                    asr_engine=task_config.asr_engine,
                    translation_service=task_config.translation_service,
                    openai_model=task_config.openai_model,
                    library_id=request.library_id,
                    path_mapping_index=task_config.path_mapping_index,
                    source_language=task_config.source_language,
                )
                
                created_tasks.append(task_to_response(task))
        
        return created_tasks
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"创建任务失败: {str(e)}"
        )


@router.get("/tasks", response_model=PaginatedTaskResponse)
async def get_tasks(
    status: Optional[TaskStatus] = Query(None, description="任务状态筛选"),
    limit: int = Query(100, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: Session = Depends(get_db)
):
    """
    获取任务列表
    
    Args:
        status: 可选的状态筛选
        limit: 每页返回的数量
        offset: 分页偏移量
        
    Returns:
        分页的任务列表
    """
    task_manager = TaskManager(db)
    
    try:
        # 获取任务列表（同时返回总数，避免二次全量查询）
        tasks, total = await task_manager.list_tasks(
            status=status,
            limit=limit,
            offset=offset
        )
        
        return PaginatedTaskResponse(
            items=[task_to_response(task) for task in tasks],
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取任务列表失败: {str(e)}"
        )


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    获取任务详情
    
    Args:
        task_id: 任务 ID
        
    Returns:
        任务详情（包含更多细节）
    """
    task_manager = TaskManager(db)
    
    try:
        task = await task_manager.get_task(task_id)
        
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=f"任务 {task_id} 不存在"
            )
        
        created_at_utc = ensure_utc(task.created_at)
        started_at_utc = ensure_utc(task.started_at)
        completed_at_utc = ensure_utc(task.completed_at)

        # 计算等待时间
        wait_time = None
        if started_at_utc and created_at_utc:
            wait_time = (started_at_utc - created_at_utc).total_seconds()

        return TaskDetailResponse(
            id=task.id,
            media_item_id=task.media_item_id,
            media_item_title=task.media_item_title,
            video_path=task.video_path,
            status=task.status,
            progress=task.progress,
            created_at=created_at_utc,
            started_at=started_at_utc,
            completed_at=completed_at_utc,
            processing_time=task.processing_time,
            error_message=task.error_message,
            error_stage=task.error_stage,
            asr_engine=task.asr_engine,
            asr_model_id=task.asr_model_id,
            translation_service=task.translation_service,
            source_language=task.source_language,
            target_language=task.target_language,
            subtitle_path=task.subtitle_path,
            segment_count=task.segment_count,
            audio_duration=task.audio_duration,
            extra_info=task.extra_info,
            wait_time=wait_time,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取任务详情失败: {str(e)}"
        )


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    取消任务
    
    只能取消处于 PENDING 或 PROCESSING 状态的任务
    
    Args:
        task_id: 任务 ID
        
    Returns:
        更新后的任务
    """
    task_manager = TaskManager(db)
    
    try:
        success = await task_manager.cancel_task(task_id)
        
        if not success:
            task = await task_manager.get_task(task_id)
            if task is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"任务 {task_id} 不存在"
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"任务 {task_id} 无法取消（当前状态: {task.status}）"
                )
        
        # 获取更新后的任务
        task = await task_manager.get_task(task_id)
        return task_to_response(task)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"取消任务失败: {str(e)}"
        )


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    重试失败的任务
    
    创建一个新任务，复制原任务的媒体项信息
    
    Args:
        task_id: 原任务 ID
        
    Returns:
        新创建的任务
    """
    task_manager = TaskManager(db)
    
    try:
        new_task = await task_manager.retry_task(task_id)
        
        if new_task is None:
            task = await task_manager.get_task(task_id)
            if task is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"任务 {task_id} 不存在"
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"任务 {task_id} 无法重试（当前状态: {task.status}）"
                )
        
        # 提交 Celery 任务
        generate_subtitle_task.delay(
            task_id=new_task.id,
            media_item_id=new_task.media_item_id,
            video_path=new_task.video_path,
            asr_engine=new_task.asr_engine,
            translation_service=new_task.translation_service,
            source_language=new_task.source_language,
        )
        
        return task_to_response(new_task)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"重试任务失败: {str(e)}"
        )
