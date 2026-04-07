"""
文本格式化和工具函数
"""
from datetime import datetime
from typing import Optional

from config.time_utils import utc_now, ensure_utc


def format_duration(seconds: Optional[float]) -> str:
    """格式化时长"""
    if seconds is None:
        return "未知"
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    if minutes > 0:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def format_progress(progress: int) -> str:
    """格式化进度条"""
    filled = progress // 10
    empty = 10 - filled
    return f"[{'█' * filled}{'░' * empty}] {progress}%"


def format_task_status(status: str) -> str:
    """格式化任务状态"""
    status_map = {
        "pending": "🕐 排队中",
        "processing": "⏳ 处理中",
        "completed": "✅ 已完成",
        "failed": "❌ 失败",
        "cancelled": "🚫 已取消",
    }
    return status_map.get(status, status)


def format_time_ago(dt: Optional[datetime]) -> str:
    """格式化时间为 'x 分钟前' 形式"""
    if dt is None:
        return "未知"

    now = utc_now()
    diff = now - ensure_utc(dt)
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "刚刚"
    elif seconds < 3600:
        return f"{seconds // 60}分钟前"
    elif seconds < 86400:
        return f"{seconds // 3600}小时前"
    else:
        return f"{seconds // 86400}天前"


def truncate(text: str, max_len: int = 30) -> str:
    """截断文本"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def short_id(task_id: str) -> str:
    """任务 ID 短码"""
    return task_id[:8]
