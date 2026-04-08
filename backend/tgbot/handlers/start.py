"""
/start 和 /help 命令处理

/start 同时处理 deep-link 参数：
  /start sub_{media_id} — 从内联搜索结果跳转，确认生成字幕
"""
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from tgbot.middleware import update_last_active

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /start 命令，包括 deep-link 参数"""
    await update_last_active(update)

    # 检查 deep-link 参数: /start sub_{media_id}
    if context.args and len(context.args) == 1 and context.args[0].startswith("sub_"):
        media_item_id = context.args[0][4:]  # 去掉 "sub_" 前缀
        await _handle_subtitle_deeplink(update, context, media_item_id)
        return

    user = update.effective_user
    await update.message.reply_text(
        f"你好 {user.first_name}！\n\n"
        f"我是 Emby AI 字幕生成机器人，可以帮你为视频生成中文字幕。\n\n"
        f"使用方法：\n"
        f"1. /login - 绑定你的 Emby 账号\n"
        f"2. @{context.bot.username} 关键词 - 内联搜索媒体\n"
        f"3. /browse - 浏览媒体库\n"
        f"4. /search 关键词 - 搜索媒体\n"
        f"5. /tasks - 查看我的任务\n\n"
        f"输入 /help 查看所有命令。"
    )


async def _handle_subtitle_deeplink(
    update: Update, context: ContextTypes.DEFAULT_TYPE, media_item_id: str
) -> None:
    """处理从内联搜索跳转过来的字幕生成请求"""
    from models.base import SessionLocal
    from services.config_manager import ConfigManager
    from services.emby_connector import EmbyConnector
    from tgbot.keyboards import confirm_task_keyboard
    from tgbot.services.user_service import get_or_create_user

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)

        # 检查是否已绑定
        if not user.emby_user_id:
            await update.message.reply_text(
                "请先使用 /login 绑定 Emby 账号后再生成字幕"
            )
            return

        if not user.is_active:
            await update.message.reply_text("❌ 你的账号已被停用")
            return

        # 获取媒体信息
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        if not config.emby_url or not config.emby_api_key:
            await update.message.reply_text("❌ Emby 服务未配置，请联系管理员")
            return

        accessible_ids = config.telegram_accessible_libraries or None
        async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
            media_item = await emby.get_media_item(media_item_id)

        if not EmbyConnector.is_item_accessible(media_item, accessible_ids):
            logger.warning(
                f"TG deeplink 访问控制拒绝: user={update.effective_user.id} item_id={media_item_id}"
            )
            await update.message.reply_text("❌ 无权访问该内容")
            return

        sub_status = "✅ 有字幕" if media_item.has_subtitles else "❌ 无字幕"
        type_label = {"Movie": "电影", "Episode": "剧集", "Series": "剧集"}.get(
            media_item.type, media_item.type
        )

        await update.message.reply_text(
            f"📺 {media_item.name}\n"
            f"类型: {type_label}\n"
            f"字幕: {sub_status}\n\n"
            f"确认为此媒体生成字幕？",
            reply_markup=confirm_task_keyboard(media_item_id),
        )

    except Exception as e:
        logger.error(f"处理字幕 deep-link 异常: {e}")
        await update.message.reply_text("❌ 获取媒体信息失败，请稍后重试")
    finally:
        db.close()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /help 命令"""
    await update_last_active(update)
    await update.message.reply_text(
        "📖 命令列表\n\n"
        "🔐 账号\n"
        "/login - 绑定 Emby 账号\n"
        "/logout - 解绑 Emby 账号\n"
        "/me - 查看个人信息\n\n"
        "🔍 搜索\n"
        f"@{context.bot.username} 关键词 - 内联搜索\n"
        "/search 关键词 - 搜索媒体\n"
        "/browse - 浏览媒体库\n\n"
        "📋 任务\n"
        "/tasks - 我的任务列表\n"
        "/cancel ID - 取消任务\n"
        "/retry ID - 重试失败任务\n\n"
        "⚙️ 设置\n"
        "/settings - 通知偏好\n"
    )


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /me 命令，显示个人信息"""
    await update_last_active(update)

    from tgbot.services.user_service import get_or_create_user
    from models.base import SessionLocal

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        if user.emby_user_id:
            emby_info = f"✅ 已绑定: {user.emby_username}"
        else:
            emby_info = "❌ 未绑定（请 /login）"

        daily_limit = user.daily_task_limit
        if daily_limit is None:
            from services.config_manager import ConfigManager
            cm = ConfigManager(db)
            config = await cm.get_config()
            daily_limit = config.telegram_daily_task_limit

        from tgbot.services.user_service import get_daily_task_count
        daily_count = get_daily_task_count(db, user)

        await update.message.reply_text(
            f"👤 个人信息\n\n"
            f"Telegram: @{user.telegram_username or '无'}\n"
            f"Emby: {emby_info}\n"
            f"今日任务: {daily_count}/{daily_limit}\n"
            f"管理员: {'是' if user.is_admin else '否'}\n"
        )
    finally:
        db.close()


def register(app: Application) -> None:
    """注册 start/help handlers"""
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("me", me_command))
