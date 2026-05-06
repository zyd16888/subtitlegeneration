"""
InlineKeyboard 构建函数
"""
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


SOURCE_LANGUAGE_CHOICES: list[tuple[str, str]] = [
    ("ja", "日语"),
    ("en", "English"),
    ("zh", "中文"),
    ("ko", "한국어"),
    ("yue", "粤语"),
]
SOURCE_LANGUAGE_CODES: set[str] = {code for code, _ in SOURCE_LANGUAGE_CHOICES}


def library_list_keyboard(
    libraries: list,
) -> InlineKeyboardMarkup:
    """构建媒体库列表键盘"""
    buttons = []
    for lib in libraries:
        buttons.append([
            InlineKeyboardButton(
                f"📁 {lib.name}",
                callback_data=f"b:l:{lib.id}",
            )
        ])
    return InlineKeyboardMarkup(buttons)


def media_list_keyboard(
    items: list,
    lib_id: str,
    page: int,
    total: int,
    page_size: int = 5,
) -> InlineKeyboardMarkup:
    """构建媒体项列表键盘（分页）"""
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

    # 分页按钮
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 上一页", callback_data=f"b:m:{lib_id}:{page - 1}"))
    if (page + 1) * page_size < total:
        nav.append(InlineKeyboardButton("下一页 ▶", callback_data=f"b:m:{lib_id}:{page + 1}"))
    if nav:
        buttons.append(nav)

    # 返回按钮
    buttons.append([InlineKeyboardButton("🔙 返回媒体库", callback_data="b:back")])

    return InlineKeyboardMarkup(buttons)


def season_list_keyboard(
    series_id: str,
    seasons: list[tuple[int, int]],
) -> InlineKeyboardMarkup:
    """
    构建季列表键盘。

    Args:
        series_id: 剧集 ID
        seasons: [(season_number, episode_count), ...] 按季编号升序
    """
    buttons = []
    for season_num, count in seasons:
        if season_num is None or season_num == 0:
            label = f"🗂 特别篇 ({count} 集)"
            season_key = "0"
        else:
            label = f"🗂 第 {season_num} 季 ({count} 集)"
            season_key = str(season_num)
        buttons.append([
            InlineKeyboardButton(
                label,
                callback_data=f"b:se:{series_id}:{season_key}:0",
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 返回", callback_data="b:back")])
    return InlineKeyboardMarkup(buttons)


def episode_list_keyboard(
    episodes: list,
    series_id: str,
    season_key: str,
    page: int,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    """构建某一季的剧集列表键盘"""
    buttons = []
    start = page * page_size
    page_episodes = episodes[start:start + page_size]

    for ep in page_episodes:
        sub_icon = " ✅" if ep.has_subtitles else ""
        # 在已限定季的视图下，直接展示集编号 + 名称尾段，文字更短
        if ep.episode_number is not None:
            display = f"E{ep.episode_number:02d}"
            tail = ep.name.split(" ")[-1] if ep.name else ""
            if tail and tail != display:
                display = f"{display} · {tail}"
            label = f"📺 {display}{sub_icon}"
        else:
            label = f"📺 {ep.name}{sub_icon}"
        buttons.append([
            InlineKeyboardButton(
                label,
                callback_data=f"b:d:{ep.id}",
            )
        ])

    # 分页
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            "◀ 上一页",
            callback_data=f"b:se:{series_id}:{season_key}:{page - 1}",
        ))
    if start + page_size < len(episodes):
        nav.append(InlineKeyboardButton(
            "下一页 ▶",
            callback_data=f"b:se:{series_id}:{season_key}:{page + 1}",
        ))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("🔙 返回剧集", callback_data=f"b:s:{series_id}"),
    ])

    return InlineKeyboardMarkup(buttons)


def media_detail_keyboard(media_item_id: str) -> InlineKeyboardMarkup:
    """构建媒体详情键盘（含生成字幕按钮）"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 生成字幕", callback_data=f"t:c:{media_item_id}")],
        [InlineKeyboardButton("🌐 选源语言生成", callback_data=f"t:cl:{media_item_id}")],
        [InlineKeyboardButton("🔙 返回", callback_data="b:back")],
    ])


def confirm_task_keyboard(media_item_id: str) -> InlineKeyboardMarkup:
    """构建任务确认键盘（内联搜索选中后使用）"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 确认生成", callback_data=f"t:c:{media_item_id}"),
            InlineKeyboardButton("❌ 取消", callback_data="noop"),
        ],
        [InlineKeyboardButton("🌐 选源语言生成", callback_data=f"t:cl:{media_item_id}")],
    ])


def source_language_picker_keyboard(
    action: str,
    target: str,
    current_lang: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """构建源语言选择键盘。

    Args:
        action: "create" 或 "retry"
        target: 媒体 ID（create）或任务短码（retry）
        current_lang: 当前/原任务的源语言，用于在按钮上加 ✓ 标记
    """
    if action == "create":
        submit_prefix = "t:cs:"
        back_callback = f"b:d:{target}"
    elif action == "retry":
        submit_prefix = "to:rs:"
        back_callback = f"td:{target}"
    else:
        raise ValueError(f"未知 action: {action}")

    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for code, label in SOURCE_LANGUAGE_CHOICES:
        marker = "✓ " if code == current_lang else ""
        pair.append(InlineKeyboardButton(
            f"{marker}{label}",
            callback_data=f"{submit_prefix}{target}:{code}",
        ))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    rows.append([InlineKeyboardButton("🔙 返回", callback_data=back_callback)])
    return InlineKeyboardMarkup(rows)


def notification_settings_keyboard(
    notify_complete: bool, notify_failure: bool
) -> InlineKeyboardMarkup:
    """通知设置键盘"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅' if notify_complete else '❌'} 完成通知",
            callback_data="s:nc",
        )],
        [InlineKeyboardButton(
            f"{'✅' if notify_failure else '❌'} 失败通知",
            callback_data="s:nf",
        )],
    ])
