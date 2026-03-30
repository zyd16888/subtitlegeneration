"""
Celery 应用配置

配置 Celery 应用，使用 Redis 作为消息代理和结果存储
"""
from celery import Celery
from config.settings import settings

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
    
    # 任务路由
    task_routes={
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
