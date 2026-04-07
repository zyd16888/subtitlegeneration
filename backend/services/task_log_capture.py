"""
任务日志捕获器

在 Celery 任务执行期间挂载到 root logger，捕获所有 logging 输出，
便于持久化到 Task.extra_info["logs"] 供前端展示。
"""
import logging
from datetime import datetime
from typing import List, Dict, Any


class TaskLogCapture(logging.Handler):
    """捕获日志记录到内存列表，按任务隔离使用"""

    def __init__(self, max_entries: int = 2000, level: int = logging.INFO):
        super().__init__(level=level)
        self.max_entries = max_entries
        self.records: List[Dict[str, Any]] = []
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            }
            self.records.append(entry)
            # 防止日志爆炸：超出上限时丢弃最早的，保留最近的记录
            if len(self.records) > self.max_entries:
                drop = len(self.records) - self.max_entries
                self.records = self.records[drop:]
        except Exception:
            # 日志处理器自身不应抛异常
            pass

    def snapshot(self) -> List[Dict[str, Any]]:
        """返回当前日志的浅拷贝，用于持久化"""
        return list(self.records)
