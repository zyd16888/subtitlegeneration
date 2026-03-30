"""
系统配置管理
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """系统配置"""
    
    # 应用配置
    app_name: str = "Emby AI 中文字幕生成服务"
    debug: bool = False
    
    # 数据库配置
    database_url: str = "sqlite:///./subtitle_service.db"
    
    # Redis 配置
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery 配置
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # Emby 配置
    emby_url: Optional[str] = None
    emby_api_key: Optional[str] = None
    
    # ASR 配置
    asr_engine: str = "sherpa-onnx"  # sherpa-onnx 或 cloud
    asr_model_path: Optional[str] = None
    asr_model_id: Optional[str] = None
    cloud_asr_url: Optional[str] = None
    cloud_asr_api_key: Optional[str] = None

    # 语言配置
    source_language: str = "ja"
    target_language: str = "zh"

    # 模型存储目录（为空时使用跨平台默认路径）
    model_storage_dir: Optional[str] = None

    # 翻译服务配置
    translation_service: str = "openai"  # openai, deepseek, local
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    deepseek_api_key: Optional[str] = None
    local_llm_url: Optional[str] = None
    
    # 任务配置
    max_concurrent_tasks: int = 2
    temp_dir: str = "/tmp/subtitle_service"
    
    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/subtitle_service.log"
    log_rotation: str = "1 day"
    log_retention: str = "30 days"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局配置实例
settings = Settings()
