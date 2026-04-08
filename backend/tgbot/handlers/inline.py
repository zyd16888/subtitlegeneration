"""
Telegram Inline Query 处理（内联搜索）

用户在 Bot 私聊中输入 @botname 关键词搜索 Emby 媒体库，
选中后直接在私聊展示确认按钮。

安全限制：仅允许在 Bot 私聊中使用内联搜索，群聊中不响应，
避免泄露 Emby 媒体库内容给非授权用户。
"""
import logging
import uuid

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.ext import (
    Application,
    ChosenInlineResultHandler,
    ContextTypes,
    InlineQueryHandler,
)

from models.base import SessionLocal
from services.config_manager import ConfigManager
from services.emby_connector import EmbyConnector
from tgbot.services.user_service import get_user_by_telegram_id

logger = logging.getLogger(__name__)


async def inline_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理内联搜索请求，仅允许私聊"""
    query = update.inline_query.query.strip()
    offset = int(update.inline_query.offset) if update.inline_query.offset else 0

    # 安全限制：仅允许在 Bot 私聊中使用
    # chat_type 可能为 "sender"(私聊发起者)、"private"、"group"、"supergroup"、"channel"
    # 也可能为 None（部分客户端不发送此字段）
    chat_type = update.inline_query.chat_type
    if chat_type and chat_type not in ("sender", "private"):
        await update.inline_query.answer(
            [
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="请在 Bot 私聊中使用内联搜索",
                    description="出于安全考虑，内联搜索仅支持私聊",
                    input_message_content=InputTextMessageContent(
                        message_text="内联搜索仅支持在 Bot 私聊中使用"
                    ),
                )
            ],
            cache_time=60,
            is_personal=True,
        )
        return

    if not query:
        await update.inline_query.answer(
            [], cache_time=5, is_personal=True
        )
        return

    # 验证用户身份
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, update.effective_user.id)
        if not user or not user.emby_user_id or not user.is_active:
            await update.inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title="请先绑定 Emby 账号",
                        description="在 Bot 私聊中发送 /login",
                        input_message_content=InputTextMessageContent(
                            message_text="请先在 Bot 私聊中使用 /login 绑定 Emby 账号"
                        ),
                    )
                ],
                cache_time=5,
                is_personal=True,
            )
            return

        # 搜索 Emby 媒体
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        if not config.emby_url or not config.emby_api_key:
            return

        accessible_ids = config.telegram_accessible_libraries or None
        page_size = 20
        async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
            items, total = await emby.get_media_items(
                search=query,
                limit=page_size,
                offset=offset,
                accessible_library_ids=accessible_ids,
            )

        bot_username = context.bot.username

        # 构建搜索结果
        results = []
        for item in items:
            sub_status = "✅ 有字幕" if item.has_subtitles else "❌ 无字幕"
            type_label = {"Movie": "电影", "Episode": "剧集", "Series": "剧集"}.get(
                item.type, item.type
            )
            description = f"{type_label} | {sub_status}"

            # 私聊中选中后直接发送，附带 deep-link 按钮确认创建任务
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🎯 生成字幕",
                    url=f"https://t.me/{bot_username}?start=sub_{item.id}",
                )]
            ])

            result = InlineQueryResultArticle(
                id=item.id,
                title=item.name,
                description=description,
                thumbnail_url=item.image_url if item.image_url else None,
                input_message_content=InputTextMessageContent(
                    message_text=f"📺 {item.name}\n类型: {type_label}\n字幕: {sub_status}",
                ),
                reply_markup=reply_markup,
            )
            results.append(result)

        next_offset = str(offset + page_size) if offset + page_size < total else ""

        await update.inline_query.answer(
            results,
            cache_time=30,
            is_personal=True,
            next_offset=next_offset,
        )

    except Exception as e:
        logger.error(f"内联搜索异常: {e}")
    finally:
        db.close()


async def chosen_inline_result(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    处理用户选中的内联搜索结果（日志记录）。

    需要在 BotFather 中 /setinlinefeedback 开启才会触发。
    主路径是通过 deep-link 按钮 (/start sub_{media_id}) 跳转私聊。
    """
    result = update.chosen_inline_result
    media_item_id = result.result_id

    logger.info(
        f"用户 {update.effective_user.id} 内联选中媒体: {media_item_id}"
    )


def register(app: Application) -> None:
    """注册内联搜索 handlers"""
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result))
