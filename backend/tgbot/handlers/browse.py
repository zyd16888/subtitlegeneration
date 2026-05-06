"""
媒体浏览和搜索处理（/browse, /search）
"""
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    season_list_keyboard,
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


async def _reply_text(query, text: str, reply_markup=None) -> None:
    """
    安全地回复文本：如果当前消息是 photo 则 delete + send，否则 edit。
    """
    try:
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.get_bot().send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"_reply_text 回退 send_message: {e}")
        await query.get_bot().send_message(
            chat_id=query.message.chat_id, text=text, reply_markup=reply_markup,
        )


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


def _parse_search_flags(args: list[str]) -> tuple[str, dict]:
    """
    把 /search 参数中的 --flag 抽取为过滤选项，剩余拼成关键词。

    支持的 flag：
      --no-sub / --no-subs  仅显示无字幕媒体
      --has-sub             仅显示有字幕媒体
      --movie               仅电影
      --series              仅剧集
    """
    keyword_parts: list[str] = []
    opts: dict = {}
    for token in args:
        low = token.lower()
        if low in ("--no-sub", "--no-subs", "--nosub"):
            opts["has_subtitles"] = False
        elif low in ("--has-sub", "--with-sub"):
            opts["has_subtitles"] = True
        elif low == "--movie":
            opts["item_type"] = "Movie"
        elif low == "--series":
            opts["item_type"] = "Series"
        else:
            keyword_parts.append(token)
    return " ".join(keyword_parts).strip(), opts


@require_auth
async def search_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """搜索媒体。

    用法:
      /search 关键词
      /search 关键词 --no-sub        # 仅无字幕
      /search 关键词 --has-sub       # 仅有字幕
      /search 关键词 --movie         # 仅电影
      /search 关键词 --series        # 仅剧集
    """
    if not context.args:
        await update.message.reply_text(
            "用法: /search 关键词 [--no-sub|--has-sub|--movie|--series]"
        )
        return

    keyword, opts = _parse_search_flags(list(context.args))
    if not keyword:
        await update.message.reply_text("请输入搜索关键词")
        return

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
                item_type=opts.get("item_type"),
                has_subtitles=opts.get("has_subtitles"),
            )

        flag_desc = []
        if opts.get("item_type") == "Movie":
            flag_desc.append("仅电影")
        elif opts.get("item_type") == "Series":
            flag_desc.append("仅剧集")
        if opts.get("has_subtitles") is False:
            flag_desc.append("无字幕")
        elif opts.get("has_subtitles") is True:
            flag_desc.append("有字幕")
        flag_str = f"（{' · '.join(flag_desc)}）" if flag_desc else ""

        if not items:
            await update.message.reply_text(
                f"没有找到与 \"{keyword}\" 相关的媒体{flag_str}"
            )
            return

        text = f"🔍 搜索 \"{keyword}\"{flag_str} 找到 {total} 个结果：\n"
        buttons = []
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


@require_auth
async def recent_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """最近添加的媒体。"""
    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            await update.message.reply_text("❌ Emby 服务未配置")
            return

        accessible_ids = _get_accessible_ids(config)
        async with EmbyConnector(emby_url, emby_api_key) as emby:
            items, total = await emby.get_media_items(
                limit=10, offset=0,
                accessible_library_ids=accessible_ids,
                sort_by="DateCreated", sort_order="Descending",
            )

        if not items:
            await update.message.reply_text("最近没有新增媒体")
            return

        text = f"🆕 最近添加（{total} 项）\n"
        buttons = []
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
        logger.error(f"最近添加查询异常: {e}")
        await update.message.reply_text("❌ 获取最近添加失败")
    finally:
        db.close()


@require_auth
async def no_subs_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """无字幕媒体快捷列表（按最近添加排序）。"""
    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            await update.message.reply_text("❌ Emby 服务未配置")
            return

        accessible_ids = _get_accessible_ids(config)
        async with EmbyConnector(emby_url, emby_api_key) as emby:
            items, total = await emby.get_media_items(
                limit=10, offset=0,
                accessible_library_ids=accessible_ids,
                sort_by="DateCreated", sort_order="Descending",
                has_subtitles=False,
            )

        if not items:
            await update.message.reply_text("没有无字幕媒体 🎉")
            return

        text = f"❌ 无字幕媒体（{total} 项）\n"
        buttons = []
        for item in items:
            icon = "🎬" if item.type == "Movie" else "📺"
            buttons.append([
                InlineKeyboardButton(
                    f"{icon} {item.name}",
                    callback_data=f"b:d:{item.id}",
                )
            ])

        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"无字幕查询异常: {e}")
        await update.message.reply_text("❌ 获取无字幕媒体失败")
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
                await _reply_text(query, "暂无可访问的媒体库")
                return
            await _reply_text(
                query, "📁 选择媒体库：",
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

    if data.startswith("b:se:"):
        # 某一季的集列表
        rest = data[5:]
        parts = rest.rsplit(":", 1)
        if len(parts) < 2:
            return
        try:
            page = int(parts[1])
        except ValueError:
            page = 0
        # parts[0] 形如 "{series_id}:{season_key}"，可能 series_id 含冒号
        head_parts = parts[0].rsplit(":", 1)
        if len(head_parts) < 2:
            return
        series_id, season_key = head_parts
        await _show_season_episodes(query, series_id, season_key, page)
        return

    if data.startswith("b:s:"):
        # 季列表（剧集入口）
        series_id = data[4:]
        # 兼容旧格式 b:s:{id}:{page}：剥离尾部数字
        if ":" in series_id:
            series_id = series_id.split(":", 1)[0]
        await _show_seasons(query, series_id)
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
            await _reply_text(query, "❌ 无权访问该内容")
            return

        async with EmbyConnector(emby_url, emby_api_key) as emby:
            items, total = await emby.get_media_items(
                library_id=lib_id,
                limit=PAGE_SIZE,
                offset=page * PAGE_SIZE,
                accessible_library_ids=accessible_ids,
            )

        if not items:
            await _reply_text(query, "此媒体库暂无内容")
            return

        await _reply_text(
            query,
            f"📺 媒体列表 (第 {page + 1} 页，共 {total} 项)：",
            reply_markup=media_list_keyboard(items, lib_id, page, total, PAGE_SIZE),
        )
    except Exception as e:
        logger.error(f"显示媒体列表异常: {e}")
    finally:
        db.close()


def _group_episodes_by_season(
    episodes: list,
) -> tuple[list[tuple[int, int]], dict[str, list]]:
    """
    把集列表按季分组。

    Returns:
        (seasons_summary, by_season)
        seasons_summary: [(season_number, count), ...] 升序，None/0 表示特别篇
        by_season: {"1": [ep, ep, ...], "0": [...]} 集按 episode_number 升序
    """
    by_season: dict[str, list] = {}
    for ep in episodes:
        season = ep.season_number
        key = "0" if (season is None or season == 0) else str(int(season))
        by_season.setdefault(key, []).append(ep)

    # 集内排序
    for eps in by_season.values():
        eps.sort(key=lambda e: (
            e.episode_number if e.episode_number is not None else 9999
        ))

    # 季列表升序，特别篇放最后
    keys_sorted = sorted(
        by_season.keys(),
        key=lambda k: (1 if k == "0" else 0, int(k) if k != "0" else 0),
    )
    summary = [
        (None if k == "0" else int(k), len(by_season[k]))
        for k in keys_sorted
    ]
    return summary, by_season


async def _fetch_series_episodes_safe(query, series_id: str) -> Optional[list]:
    """加载剧集，同时做访问控制。返回 None 表示已发回错误消息。"""
    db = SessionLocal()
    try:
        emby_url, emby_api_key, config = await _get_emby(db)
        if not emby_url:
            return None

        accessible_ids = _get_accessible_ids(config)
        async with EmbyConnector(emby_url, emby_api_key) as emby:
            if accessible_ids is not None:
                series = await emby.get_media_item(series_id)
                if not await emby.is_item_accessible(series, accessible_ids):
                    logger.warning(
                        f"TG 访问控制拒绝: user={query.from_user.id} series_id={series_id}"
                    )
                    await _reply_text(query, "❌ 无权访问该内容")
                    return None
            return await emby.get_series_episodes(series_id)
    finally:
        db.close()


async def _show_seasons(query, series_id: str) -> None:
    """显示某剧集下的季列表（仅一季时直接跳到集列表）。"""
    try:
        episodes = await _fetch_series_episodes_safe(query, series_id)
        if episodes is None:
            return
        if not episodes:
            await _reply_text(query, "此剧集暂无内容")
            return

        summary, _ = _group_episodes_by_season(episodes)

        # 只有单季时直接跳过季列表
        if len(summary) == 1:
            season_num = summary[0][0]
            season_key = "0" if season_num is None else str(season_num)
            await _show_season_episodes(query, series_id, season_key, 0)
            return

        await _reply_text(
            query,
            f"📺 剧集结构（共 {len(summary)} 季 / {len(episodes)} 集）：",
            reply_markup=season_list_keyboard(series_id, summary),
        )
    except Exception as e:
        logger.error(f"显示季列表异常: {e}")


async def _show_season_episodes(
    query, series_id: str, season_key: str, page: int,
) -> None:
    """显示某季的集列表（分页）。"""
    try:
        episodes = await _fetch_series_episodes_safe(query, series_id)
        if episodes is None:
            return
        if not episodes:
            await _reply_text(query, "此剧集暂无内容")
            return

        _, by_season = _group_episodes_by_season(episodes)
        season_episodes = by_season.get(season_key, [])
        if not season_episodes:
            await _reply_text(query, "该季暂无内容")
            return

        if season_key == "0":
            label = "特别篇"
        else:
            label = f"第 {int(season_key)} 季"

        await _reply_text(
            query,
            f"📺 {label}（共 {len(season_episodes)} 集，第 {page + 1} 页）",
            reply_markup=episode_list_keyboard(season_episodes, series_id, season_key, page),
        )
    except Exception as e:
        logger.error(f"显示该季集列表异常: {e}")


async def _show_media_detail(query, item_id: str) -> None:
    """显示媒体详情（带封面图）"""
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
                await _reply_text(query, "❌ 无权访问该内容")
                return

            # 获取封面图；Episode 优先使用 Series 图片
            image_item_id = item_id
            if item.type == "Episode" and item.image_url and "/api/images/" in item.image_url:
                # image_url 格式: /api/images/{series_id}/Primary
                parts = item.image_url.split("/")
                idx = parts.index("images") + 1
                if idx < len(parts):
                    image_item_id = parts[idx]
            image_bytes = await emby.get_image_bytes(image_item_id)

        sub_status = "✅ 有字幕" if item.has_subtitles else "❌ 无字幕"
        type_label = {"Movie": "电影", "Episode": "剧集", "Series": "剧集"}.get(
            item.type, item.type
        )
        caption = f"📺 {item.name}\n\n类型: {type_label}\n字幕: {sub_status}"

        if item.type == "Series":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 查看剧集", callback_data=f"b:s:{item_id}")],
                [InlineKeyboardButton("🔙 返回", callback_data="b:back")],
            ])
        else:
            keyboard = media_detail_keyboard(item_id)

        chat_id = query.message.chat_id
        # 删除旧消息，发送新的带封面图的消息
        try:
            await query.message.delete()
        except Exception:
            pass

        if image_bytes:
            await query.get_bot().send_photo(
                chat_id=chat_id,
                photo=image_bytes,
                caption=caption,
                reply_markup=keyboard,
            )
        else:
            await query.get_bot().send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=keyboard,
            )
    except Exception as e:
        logger.error(f"显示媒体详情异常: {e}")
    finally:
        db.close()


def register(app: Application) -> None:
    """注册浏览相关 handlers"""
    app.add_handler(CommandHandler("browse", browse_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("recent", recent_command))
    app.add_handler(CommandHandler("no_subs", no_subs_command))
    app.add_handler(CallbackQueryHandler(browse_callback, pattern=r"^b:|^noop$"))
