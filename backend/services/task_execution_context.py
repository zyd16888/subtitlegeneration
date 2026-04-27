"""
任务执行上下文。
"""
import logging
from dataclasses import dataclass
from typing import Callable

from services.config_manager import ConfigManager
from services.task_log_capture import TaskLogCapture
from services.task_manager import TaskManager
from services.task_result_persister import TaskResultPersister


@dataclass
class TaskExecutionContext:
    """任务执行期间共享的资源。"""

    db: object
    session_factory: Callable
    task_manager: TaskManager
    config_manager: ConfigManager
    log_capture: TaskLogCapture
    root_logger: logging.Logger
    result_persister: TaskResultPersister

    def close(self) -> None:
        """卸载日志捕获器并关闭 DB session。"""
        try:
            self.root_logger.removeHandler(self.log_capture)
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass


def create_task_execution_context(
    task_id: str,
    session_factory: Callable,
    run_async: Callable,
) -> TaskExecutionContext:
    """创建单个任务执行所需的共享资源。"""
    db = session_factory()
    task_manager = TaskManager(db)
    config_manager = ConfigManager(db)

    log_capture = TaskLogCapture()
    root_logger = logging.getLogger()
    root_logger.addHandler(log_capture)
    if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
        # 确保 INFO 级别能流到 handler；不修改原有 level 行为以外的设置
        log_capture.setLevel(logging.INFO)

    result_persister = TaskResultPersister(
        task_id=task_id,
        task_manager=task_manager,
        log_capture=log_capture,
        run_async=run_async,
    )

    return TaskExecutionContext(
        db=db,
        session_factory=session_factory,
        task_manager=task_manager,
        config_manager=config_manager,
        log_capture=log_capture,
        root_logger=root_logger,
        result_persister=result_persister,
    )
