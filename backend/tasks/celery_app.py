"""
Celery 应用配置

配置 Celery 应用，使用 Redis 作为消息代理和结果存储
"""
import logging

from celery import Celery
from config.settings import settings

logger = logging.getLogger(__name__)


def _load_worker_concurrency(default: int = 2) -> int:
    """从数据库读取 max_concurrent_tasks 作为 worker 并发数。

    在 celery_app 模块导入时调用（worker 启动前），失败则回退到默认值。
    修改 UI 配置后需要重启 worker 才能生效。
    """
    try:
        from models.base import SessionLocal
        from models.config import SystemConfig

        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == "max_concurrent_tasks").first()
            if row and row.value:
                value = int(str(row.value).strip('"'))
                if 1 <= value <= 16:
                    return value
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"读取 max_concurrent_tasks 失败，使用默认值 {default}: {e}")
    return default


_worker_concurrency = _load_worker_concurrency()

# 创建 Celery 应用实例
celery_app = Celery(
    "subtitle_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["tasks.subtitle_tasks"]
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化格式
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # 时区设置
    timezone="UTC",
    enable_utc=True,
    
    # 结果过期时间（7天）
    result_expires=7 * 24 * 60 * 60,
    
    # 任务结果配置
    result_backend_transport_options={
        "master_name": "mymaster",
    },
    
    # 任务执行配置
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    task_soft_time_limit=3300,  # 55分钟软超时
    
    # Worker 配置
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    # 并发数来自 UI 设置页（数据库 max_concurrent_tasks 字段），修改后需重启 worker
    worker_concurrency=_worker_concurrency,
    # 池类型：threads 跨平台可用（Windows 无 prefork）；ffmpeg/翻译/sherpa 混合负载适合线程池
    worker_pool="threads",
    
    # 任务路由
    task_routes={
        "backend.tasks.subtitle_tasks.*": {"queue": "subtitle_generation"},
        "tasks.subtitle_tasks.*": {"queue": "subtitle_generation"},
    },
    
    # 任务优先级
    task_default_priority=5,
    
    # 重试配置
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# 自动发现任务
celery_app.autodiscover_tasks(["tasks"])
