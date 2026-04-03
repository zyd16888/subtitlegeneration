"""
Telegram 用户 CRUD 和配额管理
"""
import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session
from telegram import User as TgUser

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
            created_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
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
    """获取用户今日任务数，自动重置跨天计数"""
    today = date.today()

    if user.daily_count_reset_at is None or user.daily_count_reset_at.date() != today:
        user.daily_task_count = 0
        user.daily_count_reset_at = datetime.utcnow()
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
        Task.extra_info.contains(f'"telegram_user_id": {user.telegram_id}'),
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
