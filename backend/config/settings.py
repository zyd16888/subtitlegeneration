"""
系统配置管理 - 仅基础设施配置
业务配置（Emby、ASR、翻译、VAD等）通过 UI 设置页面管理，持久化在数据库中
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """基础设施配置（从环境变量或 .env 文件加载）"""

    # 应用配置
    app_name: str = "Emby AI 中文字幕生成服务"
    debug: bool = False

    # 认证配置
    auth_enabled: bool = True
    auth_username: str = "admin"
    auth_password: str = "admin123"  # 生产环境请修改
    jwt_secret_key: str = "change-this-to-a-random-secret-key-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 天

    # 数据库配置
    database_url: str = "sqlite:///./subtitle_service.db"

    # Redis 配置
    redis_url: str = "redis://localhost:6379/0"

    # Celery 配置
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # 模型存储目录（为空时使用跨平台默认路径）
    model_storage_dir: str = "./data/models"

    # GitHub Token（可选，用于提高 API 速率限制：匿名 60次/小时 → 认证 5000次/小时）
    github_token: Optional[str] = None

    # 临时文件目录
    temp_dir: str = "./data"

    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/subtitle_service.log"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        protected_namespaces = ('settings_',)
        extra = "ignore"  # 忽略 .env 中已迁移到 UI 配置的旧字段


# 全局配置实例
settings = Settings()
