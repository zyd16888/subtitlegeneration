"""
Telegram Bot 操作审计：用同一个会话写入 telegram_audit_log。

设计原则：
- 调用方共享 db session，audit 不自己开 session（避免事务交错）。
- audit 只 add，不 commit；commit 由调用方负责（保持原子性）。
- 失败仅记录 warning，不抛异常打断主流程。
"""
import logging
from typing import Optional, Any

from sqlalchemy.orm import Session

from tgbot.models import TelegramAuditLog

logger = logging.getLogger(__name__)


def record(
    db: Session,
    tg_user_id: int,
    action: str,
    target_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """
    写一条审计记录到当前 session（不自动 commit）。
    """
    try:
        entry = TelegramAuditLog(
            tg_user_id=int(tg_user_id),
            action=action,
            target_id=str(target_id) if target_id is not None else None,
            payload=payload or None,
        )
        db.add(entry)
    except Exception as e:
        logger.warning("写审计日志失败 (action=%s, user=%s): %s", action, tg_user_id, e)


def query(
    db: Session,
    action: Optional[str] = None,
    tg_user_id: Optional[int] = None,
    limit: int = 20,
) -> list[TelegramAuditLog]:
    """查询审计日志，按时间倒序。"""
    base = db.query(TelegramAuditLog)
    if action:
        base = base.filter(TelegramAuditLog.action == action)
    if tg_user_id is not None:
        base = base.filter(TelegramAuditLog.tg_user_id == tg_user_id)
    return base.order_by(TelegramAuditLog.ts.desc()).limit(limit).all()


__all__ = ["record", "query"]
