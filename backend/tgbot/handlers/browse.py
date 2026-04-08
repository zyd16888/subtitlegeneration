"""
媒体浏览和搜索处理（/browse, /search）
"""
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from models.base import SessionLocal
from services.config_manager import ConfigManager
from services.emby_connector import EmbyConnector
from tgbot.keyboards import (
    episode_list_keyboard,
    library_list_keyboard,
    media_detail_keyboard,
    media_list_keyboard,
)
from tgbot.middleware import require_auth

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


async def _get_emby(db) -> tuple:
    """获取 Emby 配置"""
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    if not config.emby_url or not config.emby_api_key:
        return None, None, config
    return config.emby_url, config.emby_api_key, config


def _get_accessible_ids(config):
    """
    获取可访问媒体库 ID 列表。
    空列表或 None 返回 None（表示允许所有，向后兼容）。
    """
    ids = getattr(config, "telegram_accessible_libraries", None)
    if not ids:
        return None
    return list(ids)


@require_auth
async def browse_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """浏览媒体库列表"""
    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            await update.message.reply_text("❌ Emby 服务未配置")
            return

        accessible_ids = _get_accessible_ids(config)
        async with EmbyConnector(emby_url, emby_api_key) as emby:
            libraries = await emby.get_libraries(accessible_library_ids=accessible_ids)

        if not libraries:
            await update.message.reply_text("暂无可访问的媒体库")
            return

        await update.message.reply_text(
            "📁 选择媒体库：",
            reply_markup=library_list_keyboard(libraries),
        )
    except Exception as e:
        logger.error(f"浏览媒体库异常: {e}")
        await update.message.reply_text("❌ 获取媒体库失败")
    finally:
        db.close()


@require_auth
async def search_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """搜索媒体"""
    if not context.args:
        await update.message.reply_text("用法: /search 关键词")
        return

    keyword = " ".join(context.args)

    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            await update.message.reply_text("❌ Emby 服务未配置")
            return

        accessible_ids = _get_accessible_ids(config)
        async with EmbyConnector(emby_url, emby_api_key) as emby:
            items, total = await emby.get_media_items(
                search=keyword, limit=10, offset=0,
                accessible_library_ids=accessible_ids,
            )

        if not items:
            await update.message.reply_text(f"没有找到与 \"{keyword}\" 相关的媒体")
            return

        text = f"🔍 搜索 \"{keyword}\" 找到 {total} 个结果：\n"
        buttons = []
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        for item in items:
            icon = "🎬" if item.type == "Movie" else "📺"
            sub_icon = " ✅" if item.has_subtitles else ""
            buttons.append([
                InlineKeyboardButton(
                    f"{icon} {item.name}{sub_icon}",
                    callback_data=f"b:d:{item.id}",
                )
            ])

        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"搜索异常: {e}")
        await update.message.reply_text("❌ 搜索失败")
    finally:
        db.close()


async def browse_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理浏览相关的回调"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "b:back":
        # 返回媒体库列表
        db = SessionLocal()
        try:
            emby_url, emby_api_key, config = await _get_emby(db)
            if not emby_url:
                return

            accessible_ids = _get_accessible_ids(config)
            async with EmbyConnector(emby_url, emby_api_key) as emby:
                libraries = await emby.get_libraries(accessible_library_ids=accessible_ids)

            if not libraries:
                await query.edit_message_text("暂无可访问的媒体库")
                return
            await query.edit_message_text(
                "📁 选择媒体库：",
                reply_markup=library_list_keyboard(libraries),
            )
        except Exception as e:
            logger.error(f"返回媒体库异常: {e}")
        finally:
            db.close()
        return

    if data.startswith("b:l:"):
        # 浏览某个媒体库
        lib_id = data[4:]
        await _show_library_items(query, lib_id, 0)
        return

    if data.startswith("b:m:"):
        # 媒体列表翻页
        parts = data[4:].rsplit(":", 1)
        lib_id = parts[0]
        page = int(parts[1]) if len(parts) > 1 else 0
        await _show_library_items(query, lib_id, page)
        return

    if data.startswith("b:s:"):
        # 剧集列表翻页
        parts = data[4:].rsplit(":", 1)
        series_id = parts[0]
        page = int(parts[1]) if len(parts) > 1 else 0
        await _show_episodes(query, series_id, page)
        return

    if data.startswith("b:d:"):
        # 媒体详情
        item_id = data[4:]
        await _show_media_detail(query, item_id)
        return

    if data == "noop":
        return


async def _show_library_items(query, lib_id: str, page: int) -> None:
    """显示媒体库下的媒体项"""
    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            return

        accessible_ids = _get_accessible_ids(config)
        if accessible_ids is not None and lib_id not in set(accessible_ids):
            logger.warning(
                f"TG 访问控制拒绝: user={query.from_user.id} lib_id={lib_id}"
            )
            await query.edit_message_text("❌ 无权访问该内容")
            return

        async with EmbyConnector(emby_url, emby_api_key) as emby:
            items, total = await emby.get_media_items(
                library_id=lib_id,
                limit=PAGE_SIZE,
                offset=page * PAGE_SIZE,
                accessible_library_ids=accessible_ids,
            )

        if not items:
            await query.edit_message_text("此媒体库暂无内容")
            return

        await query.edit_message_text(
            f"📺 媒体列表 (第 {page + 1} 页，共 {total} 项)：",
            reply_markup=media_list_keyboard(items, lib_id, page, total, PAGE_SIZE),
        )
    except Exception as e:
        logger.error(f"显示媒体列表异常: {e}")
    finally:
        db.close()


async def _show_episodes(query, series_id: str, page: int) -> None:
    """显示剧集列表"""
    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            return

        accessible_ids = _get_accessible_ids(config)
        async with EmbyConnector(emby_url, emby_api_key) as emby:
            # 先校验 series 所属媒体库是否在允许范围
            if accessible_ids is not None:
                series = await emby.get_media_item(series_id)
                if not await emby.is_item_accessible(series, accessible_ids):
                    logger.warning(
                        f"TG 访问控制拒绝: user={query.from_user.id} series_id={series_id}"
                    )
                    await query.edit_message_text("❌ 无权访问该内容")
                    return
            episodes = await emby.get_series_episodes(series_id)

        if not episodes:
            await query.edit_message_text("此剧集暂无内容")
            return

        await query.edit_message_text(
            f"📺 剧集列表 (共 {len(episodes)} 集)：",
            reply_markup=episode_list_keyboard(episodes, series_id, page),
        )
    except Exception as e:
        logger.error(f"显示剧集列表异常: {e}")
    finally:
        db.close()


async def _show_media_detail(query, item_id: str) -> None:
    """显示媒体详情"""
    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            return

        accessible_ids = _get_accessible_ids(config)
        async with EmbyConnector(emby_url, emby_api_key) as emby:
            item = await emby.get_media_item(item_id)
            allowed = (
                accessible_ids is None
                or await emby.is_item_accessible(item, accessible_ids)
            )

        if not allowed:
            logger.warning(
                f"TG 访问控制拒绝: user={query.from_user.id} item_id={item_id}"
            )
            await query.edit_message_text("❌ 无权访问该内容")
            return

        sub_status = "✅ 有字幕" if item.has_subtitles else "❌ 无字幕"
        type_label = {"Movie": "电影", "Episode": "剧集", "Series": "剧集"}.get(
            item.type, item.type
        )

        text = (
            f"📺 {item.name}\n\n"
            f"类型: {type_label}\n"
            f"字幕: {sub_status}\n"
        )

        # 如果是 Series，显示剧集列表
        if item.type == "Series":
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            await query.edit_message_text(
                text + "\n点击下方查看剧集列表：",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 查看剧集", callback_data=f"b:s:{item_id}:0")],
                    [InlineKeyboardButton("🔙 返回", callback_data="b:back")],
                ]),
            )
        else:
            await query.edit_message_text(
                text,
                reply_markup=media_detail_keyboard(item_id),
            )
    except Exception as e:
        logger.error(f"显示媒体详情异常: {e}")
    finally:
        db.close()


def register(app: Application) -> None:
    """注册浏览相关 handlers"""
    app.add_handler(CommandHandler("browse", browse_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(browse_callback, pattern=r"^b:|^noop$"))
