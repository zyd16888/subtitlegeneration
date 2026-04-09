"""
任务进度上报器

把各处理阶段的内部进度（fraction 0..1）映射到全局百分比并写入 tasks 表，
带节流（≥1% 或 ≥1s 间隔），线程安全，可被 ASR 工作线程和翻译协程同时调用。

写库走独立同步 session，不依赖任何 asyncio loop，避免与主任务的 ORM session 抢锁。
"""
import logging
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from sqlalchemy import update

from models.task import Task

logger = logging.getLogger(__name__)


# 全局阶段权重表：与 subtitle_tasks.py 原硬编码节点保持一致
# 必须按顺序排列，end 单调递增
DEFAULT_STAGE_WEIGHTS: Dict[str, Tuple[int, int]] = {
    "audio": (0, 20),
    "asr": (20, 60),
    "translation": (60, 90),
    "subtitle": (90, 95),
    "emby": (95, 100),
}


class TaskProgressReporter:
    """
    线程安全的任务进度上报器。

    用法：
        reporter = TaskProgressReporter(task_id, SessionLocal)
        reporter.report("audio", 1.0)              # → 写 progress=20
        cb = reporter.for_stage("asr")
        cb(0.5)                                     # → 写 progress=40
        reporter.report("asr", 1.0)                 # → 写 progress=60

    节流策略：
        - 同一百分比、距上次写库 <1s 跳过
        - fraction == 0 / 1 强制写一次（保证关键节点不丢）
    """

    # 节流参数
    MIN_INTERVAL_SECONDS = 1.0
    MIN_PERCENT_DELTA = 1

    def __init__(
        self,
        task_id: str,
        session_factory,
        stage_weights: Optional[Dict[str, Tuple[int, int]]] = None,
    ):
        """
        Args:
            task_id: 任务 ID
            session_factory: SQLAlchemy session 工厂（通常是 SessionLocal）
            stage_weights: 自定义阶段权重表，None 时使用 DEFAULT_STAGE_WEIGHTS
        """
        self.task_id = task_id
        self._session_factory = session_factory
        self._stages = stage_weights or DEFAULT_STAGE_WEIGHTS
        self._lock = threading.Lock()
        self._last_pct: int = -1
        self._last_write: float = 0.0
        self._current_stage: Optional[str] = None

    def report(self, stage: str, fraction: float) -> None:
        """
        上报某阶段的内部进度。

        Args:
            stage: 阶段名（必须在 stage_weights 内）
            fraction: 0..1 之间的进度比例（会被截断到合法范围）
        """
        if stage not in self._stages:
            logger.warning(f"[{self.task_id}] 未知进度阶段: {stage}")
            return

        # 截断到 [0, 1]
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0

        start, end = self._stages[stage]
        new_pct = int(start + (end - start) * fraction)
        # 单调递增保护：百分比只前进不回退
        # （多目标语言翻译切换时 done/total 不会回退，但 ASR/翻译边界节点
        #  可能因调用顺序出现轻微抖动，这里兜底）
        force = fraction in (0.0, 1.0)

        write_pct: Optional[int] = None
        with self._lock:
            if new_pct < self._last_pct and not force:
                return

            now = time.monotonic()
            elapsed = now - self._last_write
            delta = abs(new_pct - self._last_pct)

            if not force and delta < self.MIN_PERCENT_DELTA and elapsed < self.MIN_INTERVAL_SECONDS:
                return

            # 即使是 force=True，也要避免重复写同一个值
            if new_pct == self._last_pct and not force:
                return
            if new_pct == self._last_pct and force and elapsed < self.MIN_INTERVAL_SECONDS:
                return

            write_pct = new_pct
            self._last_pct = new_pct
            self._last_write = now
            self._current_stage = stage

        # 锁外执行 DB 写入，避免 SQLite 行锁等待时阻塞 ASR / 翻译线程
        if write_pct is not None:
            self._write_progress(write_pct, stage)

    def for_stage(self, stage: str) -> Callable[[float], None]:
        """
        返回绑定到指定阶段的进度回调闭包。

        给 ASR/翻译这种「只关心自己阶段内 0..1」的代码使用。
        """
        def _cb(fraction: float) -> None:
            self.report(stage, fraction)
        return _cb

    def _write_progress(self, pct: int, stage: str) -> None:
        """直接 UPDATE 一行，不走 ORM refresh，最快路径。"""
        try:
            session = self._session_factory()
            try:
                session.execute(
                    update(Task)
                    .where(Task.id == self.task_id)
                    .values(progress=pct)
                )
                session.commit()
            finally:
                session.close()
        except Exception as e:
            # 进度上报失败不应阻塞主流程
            logger.warning(f"[{self.task_id}] 进度写库失败 ({stage}={pct}%): {e}")
