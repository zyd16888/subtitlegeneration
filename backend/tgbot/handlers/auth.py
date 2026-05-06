"""
Emby 账号验证处理（/login, /logout）
"""
import logging

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from models.base import SessionLocal
from tgbot.middleware import require_auth, update_last_active
from tgbot.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)

# ConversationHandler 状态
USERNAME, PASSWORD = range(2)


async def login_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """开始登录流程"""
    await update_last_active(update)

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        if user.emby_user_id:
            await update.message.reply_text(
                f"你已绑定 Emby 账号: {user.emby_username}\n"
                f"如需重新绑定，请先 /logout"
            )
            return ConversationHandler.END
    finally:
        db.close()

    await update.message.reply_text(
        "请输入你的 Emby 用户名：\n\n"
        "输入 /cancel 取消登录"
    )
    return USERNAME


async def receive_username(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """接收 Emby 用户名"""
    context.user_data["emby_username"] = update.message.text.strip()
    await update.message.reply_text("请输入你的 Emby 密码：")
    return PASSWORD


async def receive_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """接收密码并验证"""
    password = update.message.text
    username = context.user_data.get("emby_username", "")

    # 尝试删除包含密码的消息
    try:
        await update.message.delete()
    except Exception:
        pass

    # 从配置获取 Emby URL 和 API Key
    from services.config_manager import ConfigManager

    db = SessionLocal()
    try:
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()
        emby_url = config.emby_url
        emby_api_key = config.emby_api_key

        if not emby_url or not emby_api_key:
            await update.message.reply_text("❌ Emby 服务未配置，请联系管理员")
            return ConversationHandler.END

        # 调用 Emby AuthenticateByName
        auth_header = (
            'MediaBrowser Client="SubtitleBot", '
            f'Device="Telegram", '
            f'DeviceId="tg-{update.effective_user.id}", '
            f'Version="1.0"'
        )

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{emby_url.rstrip('/')}/Users/AuthenticateByName",
                headers={
                    "X-Emby-Authorization": auth_header,
                    "Content-Type": "application/json",
                },
                json={"Username": username, "Pw": password},
            )

        if response.status_code == 200:
            data = response.json()
            emby_user_id = data.get("User", {}).get("Id", "")
            emby_username = data.get("User", {}).get("Name", username)

            # 保存绑定信息
            user = get_or_create_user(db, update.effective_user)
            user.emby_user_id = emby_user_id
            user.emby_username = emby_username
            from tgbot.services import audit as audit_service
            audit_service.record(
                db, update.effective_user.id, "login",
                target_id=emby_user_id,
                payload={"emby_username": emby_username},
            )
            db.commit()

            await update.effective_chat.send_message(
                f"✅ 绑定成功！\n\n"
                f"Emby 用户: {emby_username}\n\n"
                f"现在你可以：\n"
                f"• 使用内联搜索查找媒体\n"
                f"• /browse 浏览媒体库\n"
                f"• /tasks 查看任务"
            )
        else:
            error_msg = "用户名或密码错误"
            if response.status_code == 401:
                error_msg = "用户名或密码错误"
            elif response.status_code >= 500:
                error_msg = "Emby 服务器错误，请稍后重试"

            await update.effective_chat.send_message(
                f"❌ 验证失败: {error_msg}\n\n"
                f"请重新 /login 尝试"
            )

    except httpx.TimeoutException:
        await update.effective_chat.send_message(
            "❌ 连接 Emby 服务器超时，请稍后重试"
        )
    except Exception as e:
        logger.error(f"Emby 认证异常: {e}")
        await update.effective_chat.send_message(
            "❌ 验证过程出错，请稍后重试"
        )
    finally:
        db.close()

    # 清理用户数据
    context.user_data.pop("emby_username", None)
    return ConversationHandler.END


async def cancel_login(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """取消登录"""
    context.user_data.pop("emby_username", None)
    await update.message.reply_text("登录已取消")
    return ConversationHandler.END


@require_auth
async def logout_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """解绑 Emby 账号"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        old_name = user.emby_username
        old_emby_id = user.emby_user_id
        user.emby_user_id = None
        user.emby_username = None
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "logout",
            target_id=old_emby_id,
            payload={"emby_username": old_name},
        )
        db.commit()

        await update.message.reply_text(
            f"已解绑 Emby 账号: {old_name}\n"
            f"使用 /login 重新绑定"
        )
    finally:
        db.close()


def register(app: Application) -> None:
    """注册认证相关 handlers"""
    login_handler = ConversationHandler(
        entry_points=[CommandHandler("login", login_command)],
        states={
            USERNAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_username
                )
            ],
            PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_password
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_login)],
        conversation_timeout=120,
    )

    app.add_handler(login_handler)
    app.add_handler(CommandHandler("logout", logout_command))
