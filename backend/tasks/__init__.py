"""Celery 任务模块"""

from .celery_app import celery_app
from .subtitle_tasks import generate_subtitle_task

__all__ = ["celery_app", "generate_subtitle_task"]
