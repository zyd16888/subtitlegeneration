"""
时间工具

统一使用带时区的 aware datetime（存储 UTC，展示由前端按本地时区渲染）。

- utc_now(): 获取当前 UTC 时间（aware）
- ensure_utc(dt): 将 naive datetime 视为 UTC 并附加 tzinfo；aware 则转换到 UTC
- to_local(dt): 转换到本地时区（默认 Asia/Shanghai），用于服务端需按本地日期判断的场景
"""
from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

UTC = timezone.utc
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def utc_now() -> datetime:
    """返回当前 UTC 时间（带 tzinfo）"""
    return datetime.now(UTC)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """保证 datetime 为 aware UTC。

    - None → None
    - naive → 视为 UTC 并附加 tzinfo（历史遗留数据均为 UTC naive）
    - aware → 转换到 UTC
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_local(dt: Optional[datetime]) -> Optional[datetime]:
    """转换到本地时区（Asia/Shanghai）。"""
    if dt is None:
        return None
    return ensure_utc(dt).astimezone(LOCAL_TZ)
