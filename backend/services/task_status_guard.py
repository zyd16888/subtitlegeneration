"""
任务状态守卫逻辑。
"""
import logging
import os
from typing import Callable, Optional

from config.time_utils import ensure_utc, utc_now
from models.task import Task as TaskModel
from models.task import TaskStatus

logger = logging.getLogger(__name__)


def skip_if_terminal_task(
    task_id: str,
    task_manager,
    run_async: Callable,
) -> Optional[dict]:
    """已取消/已完成/已失败的任务直接跳过，避免重复投递覆盖终态。"""
    try:
        existing = run_async(task_manager.get_task(task_id))
        if existing and existing.status in (
            TaskStatus.CANCELLED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        ):
            logger.info(f"[{task_id}] 任务状态为 {existing.status.value}，跳过执行")
            return {
                "task_id": task_id,
                "status": existing.status.value,
                "skipped": True,
            }
    except Exception as exc:
        logger.warning(f"[{task_id}] 入口状态检查失败，继续执行: {exc}")
    return None


def ensure_task_leaves_processing(
    task_id: str,
    subtitle_path: Optional[str],
    session_factory: Callable,
) -> None:
    """任务退出时兜底修正仍停留在 PROCESSING/PENDING 的状态。"""
    try:
        safety_db = session_factory()
        try:
            row = safety_db.query(TaskModel).filter(TaskModel.id == task_id).first()
            if row is None or row.status not in (
                TaskStatus.PROCESSING,
                TaskStatus.PENDING,
            ):
                return

            if subtitle_path and os.path.exists(subtitle_path):
                row.status = TaskStatus.COMPLETED
                row.progress = 100
                row.completed_at = utc_now()
                if row.started_at:
                    started = ensure_utc(row.started_at)
                    completed = ensure_utc(row.completed_at)
                    row.processing_time = (completed - started).total_seconds()
                logger.warning(
                    f"[{task_id}] 安全网：任务退出时状态仍为 {row.status.value}，"
                    f"检测到字幕文件已生成，强制标记为 COMPLETED"
                )
            else:
                row.status = TaskStatus.FAILED
                row.completed_at = utc_now()
                if not row.error_message:
                    row.error_message = "任务异常退出，未生成字幕文件"
                logger.warning(
                    f"[{task_id}] 安全网：任务退出时状态仍为 {row.status.value}，"
                    f"未检测到字幕文件，强制标记为 FAILED"
                )
            safety_db.commit()
        finally:
            safety_db.close()
    except Exception as exc:
        logger.error(f"[{task_id}] 安全网状态修正失败: {exc}", exc_info=True)
