"""
任务相关 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from models.base import get_db
from models.task import Task, TaskStatus
from services.task_manager import TaskManager
from services.emby_connector import EmbyConnector
from services.config_manager import ConfigManager
from tasks.subtitle_tasks import generate_subtitle_task

router = APIRouter(prefix="/api", tags=["tasks"])


class TaskConfigRequest(BaseModel):
    """单个任务配置"""
    media_item_id: str
    asr_engine: Optional[str] = None
    translation_service: Optional[str] = None
    openai_model: Optional[str] = None


class CreateTaskRequest(BaseModel):
    """创建任务请求模型"""
    media_item_ids: Optional[List[str]] = None  # 批量创建，使用全局配置
    tasks: Optional[List[TaskConfigRequest]] = None  # 单独配置每个任务


class TaskResponse(BaseModel):
    """任务响应模型"""
    id: str
    media_item_id: str
    media_item_title: Optional[str] = None
    video_path: Optional[str] = None
    status: TaskStatus
    progress: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True


class PaginatedTaskResponse(BaseModel):
    """分页任务响应模型"""
    items: List[TaskResponse]
    total: int
    limit: int
    offset: int


async def get_emby_connector(db: Session = Depends(get_db)) -> EmbyConnector:
    """获取 Emby 连接器实例"""
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    
    if not config.emby_url or not config.emby_api_key:
        raise HTTPException(
            status_code=400,
            detail="Emby 连接未配置"
        )
    
    return EmbyConnector(config.emby_url, config.emby_api_key)


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
    created_tasks = []
    
    try:
        async with emby:
            # 处理批量创建（使用全局配置）
            if request.media_item_ids:
                for media_item_id in request.media_item_ids:
                    # 获取媒体项信息
                    try:
                        media_item = await emby.get_media_item(media_item_id)
                        video_path = await emby.get_media_file_path(media_item_id)
                    except Exception as e:
                        raise HTTPException(
                            status_code=404,
                            detail=f"获取媒体项 {media_item_id} 失败: {str(e)}"
                        )
                    
                    # 创建任务
                    task = await task_manager.create_task(
                        media_item_id=media_item_id,
                        media_item_title=media_item.name,
                        video_path=video_path
                    )
                    
                    # 提交 Celery 任务（使用全局配置）
                    generate_subtitle_task.delay(
                        task_id=task.id,
                        media_item_id=media_item_id,
                        video_path=video_path
                    )
                    
                    created_tasks.append(TaskResponse.model_validate(task))
            
            # 处理单独配置的任务
            if request.tasks:
                for task_config in request.tasks:
                    # 获取媒体项信息
                    try:
                        media_item = await emby.get_media_item(task_config.media_item_id)
                        video_path = await emby.get_media_file_path(task_config.media_item_id)
                    except Exception as e:
                        raise HTTPException(
                            status_code=404,
                            detail=f"获取媒体项 {task_config.media_item_id} 失败: {str(e)}"
                        )
                    
                    # 创建任务
                    task = await task_manager.create_task(
                        media_item_id=task_config.media_item_id,
                        media_item_title=media_item.name,
                        video_path=video_path
                    )
                    
                    # 提交 Celery 任务（使用自定义配置）
                    generate_subtitle_task.delay(
                        task_id=task.id,
                        media_item_id=task_config.media_item_id,
                        video_path=video_path,
                        asr_engine=task_config.asr_engine,
                        translation_service=task_config.translation_service,
                        openai_model=task_config.openai_model
                    )
                    
                    created_tasks.append(TaskResponse.model_validate(task))
        
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
        # 获取任务列表
        tasks = await task_manager.list_tasks(
            status=status,
            limit=limit,
            offset=offset
        )
        
        # 获取总数（需要单独查询）
        all_tasks = await task_manager.list_tasks(status=status, limit=10000, offset=0)
        total = len(all_tasks)
        
        return PaginatedTaskResponse(
            items=[TaskResponse.model_validate(task) for task in tasks],
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取任务列表失败: {str(e)}"
        )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    获取任务详情
    
    Args:
        task_id: 任务 ID
        
    Returns:
        任务详情
    """
    task_manager = TaskManager(db)
    
    try:
        task = await task_manager.get_task(task_id)
        
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=f"任务 {task_id} 不存在"
            )
        
        return TaskResponse.model_validate(task)
        
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
        return TaskResponse.model_validate(task)
        
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
            video_path=new_task.video_path
        )
        
        return TaskResponse.model_validate(new_task)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"重试任务失败: {str(e)}"
        )
