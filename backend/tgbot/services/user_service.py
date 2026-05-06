"""
Telegram 用户 CRUD 和配额管理
"""
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from telegram import User as TgUser

from config.time_utils import utc_now, to_local
from tgbot.models import TelegramUser

logger = logging.getLogger(__name__)


def get_or_create_user(db: Session, tg_user: TgUser) -> TelegramUser:
    """获取或创建 Telegram 用户记录"""
    user = db.query(TelegramUser).filter(
        TelegramUser.telegram_id == tg_user.id
    ).first()

    if user is None:
        user = TelegramUser(
            telegram_id=tg_user.id,
            telegram_username=tg_user.username,
            telegram_display_name=tg_user.full_name,
            created_at=utc_now(),
            last_active_at=utc_now(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"新建 Telegram 用户: {tg_user.id} ({tg_user.full_name})")
    else:
        # 更新基本信息
        user.telegram_username = tg_user.username
        user.telegram_display_name = tg_user.full_name
        db.commit()

    return user


def get_user_by_telegram_id(
    db: Session, telegram_id: int
) -> Optional[TelegramUser]:
    """通过 Telegram ID 获取用户"""
    return db.query(TelegramUser).filter(
        TelegramUser.telegram_id == telegram_id
    ).first()


def get_all_active_users(db: Session) -> list[TelegramUser]:
    """获取所有活跃且已绑定 Emby 的用户"""
    return db.query(TelegramUser).filter(
        TelegramUser.is_active == True,
        TelegramUser.emby_user_id.isnot(None),
    ).all()


def get_all_users(db: Session) -> list[TelegramUser]:
    """获取所有用户"""
    return db.query(TelegramUser).all()


def get_daily_task_count(db: Session, user: TelegramUser) -> int:
    """获取用户今日任务数，按本地时区（Asia/Shanghai）自动重置跨天计数"""
    today_local = to_local(utc_now()).date()
    reset_local_date = (
        to_local(user.daily_count_reset_at).date()
        if user.daily_count_reset_at is not None
        else None
    )

    if reset_local_date != today_local:
        user.daily_task_count = 0
        user.daily_count_reset_at = utc_now()
        db.commit()

    return user.daily_task_count


def increment_daily_task_count(db: Session, user: TelegramUser) -> None:
    """增加用户今日任务计数"""
    get_daily_task_count(db, user)  # 确保计数已重置
    user.daily_task_count += 1
    db.commit()


def check_user_quota(
    db: Session,
    user: TelegramUser,
    global_daily_limit: int,
    global_max_concurrent: int,
) -> Optional[str]:
    """
    检查用户配额，返回 None 表示通过，否则返回拒绝原因

    Args:
        db: 数据库 session
        user: 用户
        global_daily_limit: 全局每日限制
        global_max_concurrent: 全局每用户并发限制
    """
    from models.task import Task, TaskStatus

    # 1. 用户是否被封禁
    if not user.is_active:
        return "你的账号已被停用"

    # 2. 用户是否已绑定 Emby
    if not user.emby_user_id:
        return "请先 /login 绑定 Emby 账号"

    # 3. 检查每用户并发限制
    active_count = db.query(Task).filter(
        Task.telegram_user_id == user.telegram_id,
        Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
    ).count()

    if active_count >= global_max_concurrent:
        return f"你当前有 {active_count} 个任务在进行中，请等待完成后再提交"

    # 4. 检查每日限制
    daily_limit = user.daily_task_limit if user.daily_task_limit is not None else global_daily_limit
    daily_count = get_daily_task_count(db, user)

    if daily_count >= daily_limit:
        return f"今日任务配额已用完 ({daily_count}/{daily_limit})，请明天再试"

    return None


def get_users_by_filter(db: Session, kind: str) -> list[TelegramUser]:
    """
    按 broadcast 定向条件返回用户列表。

    kind:
      "active-7d" - 最近 7 天活跃且未被封禁（默认推荐）
      "bound"     - 已绑定 Emby 且未被封禁
      "admins"    - 管理员（is_admin=True）
      "all"       - 所有未被封禁的用户
    """
    base = db.query(TelegramUser).filter(TelegramUser.is_active == True)

    if kind == "active-7d":
        cutoff = utc_now() - timedelta(days=7)
        return base.filter(TelegramUser.last_active_at >= cutoff).all()
    if kind == "bound":
        return base.filter(TelegramUser.emby_user_id.isnot(None)).all()
    if kind == "admins":
        return base.filter(TelegramUser.is_admin == True).all()
    if kind == "all":
        return base.all()

    raise ValueError(f"未知的广播过滤条件: {kind}")


def search_users(
    db: Session, keyword: str, page: int, page_size: int,
) -> tuple[list[TelegramUser], int]:
    """
    按关键词模糊匹配用户（telegram_username / display_name / emby_username / telegram_id）。

    Returns:
        (users, total)
    """
    base = db.query(TelegramUser)
    if keyword:
        kw_like = f"%{keyword}%"
        base = base.filter(
            or_(
                TelegramUser.telegram_username.ilike(kw_like),
                TelegramUser.telegram_display_name.ilike(kw_like),
                TelegramUser.emby_username.ilike(kw_like),
                # telegram_id 是数字，也允许整体匹配
                TelegramUser.telegram_id == _try_int(keyword),
            )
        )
    total = base.count()
    users = (
        base.order_by(TelegramUser.created_at.desc())
        .limit(page_size)
        .offset(page * page_size)
        .all()
    )
    return users, total


def _try_int(s: str) -> int:
    """安全把字符串转 int，失败返回 0（不会匹配真实 telegram_id）。"""
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def get_user_task_stats(db: Session, telegram_id: int) -> dict:
    """
    返回用户的任务统计摘要。

    Returns:
        {
          "total": int, "completed": int, "failed": int,
          "cancelled": int, "active": int,
          "success_rate": float | None,  # 终结任务（completed+failed+cancelled）中 completed 比例
          "avg_processing_seconds": float | None,
          "last_7d": int,
        }
    """
    from models.task import Task, TaskStatus

    base = db.query(Task).filter(Task.telegram_user_id == telegram_id)

    total = base.count()
    completed = base.filter(Task.status == TaskStatus.COMPLETED).count()
    failed = base.filter(Task.status == TaskStatus.FAILED).count()
    cancelled = base.filter(Task.status == TaskStatus.CANCELLED).count()
    active = base.filter(
        Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])
    ).count()

    finished = completed + failed + cancelled
    success_rate = (completed / finished) if finished > 0 else None

    avg_seconds = (
        db.query(func.avg(Task.processing_time))
        .filter(
            Task.telegram_user_id == telegram_id,
            Task.status == TaskStatus.COMPLETED,
            Task.processing_time.isnot(None),
        )
        .scalar()
    )

    seven_days_ago = utc_now() - timedelta(days=7)
    last_7d = base.filter(Task.created_at >= seven_days_ago).count()

    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "cancelled": cancelled,
        "active": active,
        "success_rate": float(success_rate) if success_rate is not None else None,
        "avg_processing_seconds": float(avg_seconds) if avg_seconds is not None else None,
        "last_7d": last_7d,
    }
