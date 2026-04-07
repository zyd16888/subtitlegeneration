"""
权限检查装饰器
"""
import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config.time_utils import utc_now
from models.base import SessionLocal
from tgbot.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)


async def update_last_active(update: Update) -> None:
    """更新用户最后活跃时间"""
    if not update.effective_user:
        return
    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        user.last_active_at = utc_now()
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


def require_auth(func):
    """装饰器：要求用户已绑定 Emby 账号且未被封禁"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        await update_last_active(update)

        if not update.effective_user:
            return

        db = SessionLocal()
        try:
            user = get_or_create_user(db, update.effective_user)

            if not user.is_active:
                msg = update.message or update.callback_query.message
                if update.callback_query:
                    await update.callback_query.answer("你的账号已被停用", show_alert=True)
                elif msg:
                    await msg.reply_text("❌ 你的账号已被停用，请联系管理员")
                return

            if not user.emby_user_id:
                msg = update.message or update.callback_query.message
                if update.callback_query:
                    await update.callback_query.answer("请先 /login 绑定 Emby 账号", show_alert=True)
                elif msg:
                    await msg.reply_text("请先使用 /login 绑定 Emby 账号")
                return

            context.user_data["db_user"] = user
        finally:
            db.close()

        return await func(update, context, *args, **kwargs)

    return wrapper


def require_admin(func):
    """装饰器：要求管理员权限"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        await update_last_active(update)

        if not update.effective_user:
            return

        db = SessionLocal()
        try:
            user = get_or_create_user(db, update.effective_user)
            admin_ids = context.bot_data.get("admin_ids", [])
            is_admin = user.is_admin or (user.telegram_id in admin_ids)

            if not is_admin:
                if update.message:
                    await update.message.reply_text("❌ 需要管理员权限")
                return

            context.user_data["db_user"] = user
        finally:
            db.close()

        return await func(update, context, *args, **kwargs)

    return wrapper
