"""
统计相关 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from config.time_utils import ensure_utc
from models.base import get_db
from models.task import Task, TaskStatus
from services.task_manager import TaskManager
from services.config_manager import ConfigManager
from services.emby_connector import EmbyConnector
from services.auth import require_auth

router = APIRouter(prefix="/api", tags=["stats"], dependencies=[Depends(require_auth)])


class TaskStatisticsResponse(BaseModel):
    """任务统计响应模型"""
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    cancelled: int


class RecentTaskResponse(BaseModel):
    """最近任务响应模型"""
    id: str
    media_item_title: Optional[str] = None
    status: TaskStatus
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SystemStatusResponse(BaseModel):
    """系统状态响应模型"""
    emby_connected: bool
    emby_message: str
    asr_configured: bool
    asr_message: str
    translation_configured: bool
    translation_message: str


class StatisticsResponse(BaseModel):
    """统计信息响应模型"""
    task_statistics: TaskStatisticsResponse
    recent_tasks: List[RecentTaskResponse]
    system_status: SystemStatusResponse


@router.get("/stats", response_model=StatisticsResponse)
async def get_statistics(db: Session = Depends(get_db)):
    """
    获取系统统计信息
    
    包括：
    - 任务统计（总数、各状态数量）
    - 最近完成的任务
    - 系统状态（Emby、ASR、翻译服务连接状态）
    
    Returns:
        统计信息对象
    """
    task_manager = TaskManager(db)
    config_manager = ConfigManager(db)
    
    try:
        # 1. 获取任务统计
        task_stats = await task_manager.get_statistics()
        task_statistics = TaskStatisticsResponse(
            total=task_stats.total,
            pending=task_stats.pending,
            processing=task_stats.processing,
            completed=task_stats.completed,
            failed=task_stats.failed,
            cancelled=task_stats.cancelled
        )
        
        # 2. 获取最近完成的任务（最多 10 个）
        completed_tasks, _ = await task_manager.list_tasks(
            status=TaskStatus.COMPLETED,
            limit=10,
            offset=0
        )
        recent_tasks = [
            RecentTaskResponse(
                id=task.id,
                media_item_title=task.media_item_title,
                status=task.status,
                completed_at=ensure_utc(task.completed_at)
            )
            for task in completed_tasks
        ]
        
        # 3. 检查系统状态
        config = await config_manager.get_config()
        
        # 检查 Emby 连接
        emby_connected = False
        emby_message = "未配置"
        if config.emby_url and config.emby_api_key:
            try:
                emby = EmbyConnector(config.emby_url, config.emby_api_key)
                async with emby:
                    emby_connected = await emby.test_connection()
                emby_message = "已连接" if emby_connected else "连接失败"
            except Exception as e:
                emby_message = f"连接失败: {str(e)}"
        
        # 检查 ASR 配置
        asr_configured = False
        asr_message = "未配置"
        if config.asr_engine == "sherpa-onnx":
            if config.asr_model_path:
                asr_configured = True
                asr_message = f"已配置 (sherpa-onnx)"
            else:
                asr_message = "sherpa-onnx 引擎缺少模型路径"
        elif config.asr_engine == "cloud":
            if (
                config.cloud_asr_provider == "groq"
                and config.groq_asr_api_key
                and config.groq_asr_model
                and config.groq_asr_base_url
            ):
                asr_configured = True
                asr_message = f"已配置 (Groq ASR: {config.groq_asr_model})"
            else:
                asr_message = "Groq ASR 缺少 API Key、模型或 Base URL"
        
        # 检查翻译服务配置
        translation_configured = False
        translation_message = "未配置"
        if config.translation_service == "openai":
            if config.openai_api_key:
                translation_configured = True
                translation_message = f"已配置 (OpenAI {config.openai_model})"
            else:
                translation_message = "OpenAI 缺少 API Key"
        elif config.translation_service == "deepseek":
            if config.deepseek_api_key:
                translation_configured = True
                translation_message = "已配置 (DeepSeek)"
            else:
                translation_message = "DeepSeek 缺少 API Key"
        elif config.translation_service == "local":
            if config.local_llm_url:
                translation_configured = True
                translation_message = "已配置 (本地 LLM)"
            else:
                translation_message = "本地 LLM 缺少 API URL"
        elif config.translation_service == "google":
            mode = getattr(config, "google_translate_mode", "free")
            if mode == "free":
                translation_configured = True
                translation_message = "已配置 (Google 免费版)"
            elif mode == "api" and getattr(config, "google_api_key", None):
                translation_configured = True
                translation_message = "已配置 (Google API)"
            else:
                translation_message = "Google API 模式缺少 API Key"
        elif config.translation_service == "microsoft":
            mode = getattr(config, "microsoft_translate_mode", "free")
            if mode == "free":
                translation_configured = True
                translation_message = "已配置 (微软免费版)"
            elif mode == "api" and getattr(config, "microsoft_api_key", None):
                translation_configured = True
                translation_message = "已配置 (微软 API)"
            else:
                translation_message = "微软 API 模式缺少 API Key"
        elif config.translation_service == "baidu":
            if getattr(config, "baidu_app_id", None) and getattr(config, "baidu_secret_key", None):
                translation_configured = True
                translation_message = "已配置 (百度翻译)"
            else:
                translation_message = "百度翻译缺少 APP ID 或 Secret Key"
        elif config.translation_service == "deepl":
            mode = getattr(config, "deepl_mode", "deeplx")
            if mode == "deeplx" and getattr(config, "deeplx_url", None):
                translation_configured = True
                translation_message = "已配置 (DeepLX)"
            elif mode == "api" and getattr(config, "deepl_api_key", None):
                translation_configured = True
                translation_message = "已配置 (DeepL API)"
            else:
                if mode == "deeplx":
                    translation_message = "DeepLX 模式缺少服务地址"
                else:
                    translation_message = "DeepL API 模式缺少 API Key"
        
        system_status = SystemStatusResponse(
            emby_connected=emby_connected,
            emby_message=emby_message,
            asr_configured=asr_configured,
            asr_message=asr_message,
            translation_configured=translation_configured,
            translation_message=translation_message
        )
        
        return StatisticsResponse(
            task_statistics=task_statistics,
            recent_tasks=recent_tasks,
            system_status=system_status
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取统计信息失败: {str(e)}"
        )
