"""
媒体库批量字幕扫描 Celery 任务。

与字幕生成任务共享 worker 池，通过 task_routes 进入同一队列。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import List, Optional

from celery import Task

from .celery_app import celery_app
from config.time_utils import utc_now
from models.base import SessionLocal
from models.task import Task as TaskModel
from models.task import TaskStatus
from services.config_manager import ConfigManager
from services.library_scan_service import (
    LibraryScanRequest,
    _serializable_report,
    run_library_scan,
)
from services.task_status_guard import skip_if_terminal_task

logger = logging.getLogger(__name__)


# 复用线程本地 event loop，与 subtitle_tasks 一致
_thread_local = threading.local()


def _run_async(coro):
    loop = getattr(_thread_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _thread_local.loop = loop
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _mark_status(
    task_id: str,
    status: TaskStatus,
    error_message: Optional[str] = None,
    progress: Optional[int] = None,
    extra_info_patch: Optional[dict] = None,
) -> None:
    """同步更新任务状态字段（避开异步 task_manager 与守卫机制）。"""
    db = SessionLocal()
    try:
        row = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not row:
            return
        row.status = status
        if progress is not None:
            row.progress = progress
        if status == TaskStatus.PROCESSING and not row.started_at:
            row.started_at = utc_now()
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            row.completed_at = utc_now()
            if row.started_at:
                row.processing_time = (row.completed_at - row.started_at).total_seconds()
        if error_message is not None:
            row.error_message = error_message
        if extra_info_patch is not None:
            merged = dict(row.extra_info) if row.extra_info else {}
            merged.update(extra_info_patch)
            row.extra_info = merged
        db.commit()
    finally:
        db.close()


class LibraryScanTask(Task):
    """库扫描 Celery 任务基类，附带统一的失败回调。"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"[{task_id}] 库扫描任务失败: {exc}\n{einfo}")


@celery_app.task(
    bind=True,
    base=LibraryScanTask,
    name="backend.tasks.library_scan_tasks.scan_library_task",
    max_retries=0,
)
def scan_library_task(
    self,
    task_id: str,
    library_id: str,
    target_languages: Optional[List[str]] = None,
    skip_if_has_subtitle: bool = True,
    max_items: int = 0,
    concurrency: int = 3,
    item_type: Optional[str] = None,
):
    """库扫描主任务。"""
    # 终态任务不重复执行
    db = SessionLocal()
    try:
        task_manager_get = lambda tid: db.query(TaskModel).filter(TaskModel.id == tid).first()
        existing = task_manager_get(task_id)
        if existing and existing.status in (
            TaskStatus.CANCELLED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        ):
            logger.info(f"[{task_id}] 库扫描任务状态为 {existing.status.value}，跳过")
            return {"task_id": task_id, "status": existing.status.value, "skipped": True}
    finally:
        db.close()

    # 标记进入 PROCESSING
    _mark_status(
        task_id,
        TaskStatus.PROCESSING,
        progress=0,
        extra_info_patch={"task_type": "library_subtitle_scan"},
    )

    try:
        # 加载配置
        cfg_db = SessionLocal()
        try:
            config = _run_async(ConfigManager(cfg_db).get_config())
        finally:
            cfg_db.close()

        request = LibraryScanRequest(
            library_id=library_id,
            target_languages=list(target_languages) if target_languages else None,
            skip_if_has_subtitle=skip_if_has_subtitle,
            max_items=max_items,
            concurrency=concurrency,
            item_type=item_type,
        )

        report = _run_async(
            run_library_scan(
                request=request,
                task_id=task_id,
                config=config,
                session_factory=SessionLocal,
            )
        )

        report_dict = _serializable_report(report)
        if report.cancelled:
            _mark_status(
                task_id,
                TaskStatus.CANCELLED,
                progress=100,
                extra_info_patch={"scan_report": report_dict},
            )
            return {"task_id": task_id, "status": "cancelled", "report": report_dict}

        _mark_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100,
            extra_info_patch={"scan_report": report_dict},
        )
        return {"task_id": task_id, "status": "completed", "report": report_dict}

    except Exception as exc:
        logger.error(f"[{task_id}] 库扫描任务异常: {exc}", exc_info=True)
        _mark_status(
            task_id,
            TaskStatus.FAILED,
            error_message=str(exc),
            progress=100,
        )
        raise
