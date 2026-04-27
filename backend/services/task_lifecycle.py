"""
任务生命周期收尾逻辑。
"""
import logging
import shutil
from typing import Callable

from models.task import TaskStatus

logger = logging.getLogger(__name__)


def mark_task_completed(
    task_id: str,
    task_manager,
    result_persister,
    run_async: Callable,
) -> None:
    """标记任务完成，并持久化最后一份日志快照。"""
    run_async(task_manager.update_task_status(task_id, TaskStatus.COMPLETED, 100))
    result_persister.update_result(extra_info=result_persister.with_logs({}))
    logger.info(f"[{task_id}] 任务完成")


def mark_task_failed(
    task_id: str,
    exc: Exception,
    task_manager,
    result_persister,
    run_async: Callable,
) -> None:
    """标记任务失败，并尽量持久化失败时的日志快照。"""
    error_message = str(exc)
    logger.error(f"[{task_id}] 任务失败: {error_message}", exc_info=True)
    run_async(
        task_manager.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_message,
        )
    )
    try:
        result_persister.update_result(extra_info=result_persister.with_logs({}))
    except Exception:
        pass


def cleanup_task_work_dir(
    task_id: str,
    task_work_dir: str,
    cleanup_enabled: bool,
) -> None:
    """按配置清理任务临时目录。"""
    if not cleanup_enabled:
        return

    try:
        shutil.rmtree(task_work_dir)
        logger.info(f"[{task_id}] 临时文件已清理: {task_work_dir}")
    except Exception as exc:
        logger.warning(f"[{task_id}] 清理临时文件失败: {exc}")
