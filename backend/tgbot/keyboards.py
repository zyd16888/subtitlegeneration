"""
InlineKeyboard 构建函数
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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


def episode_list_keyboard(
    episodes: list,
    series_id: str,
    page: int,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    """构建剧集列表键盘"""
    buttons = []
    start = page * page_size
    page_episodes = episodes[start:start + page_size]

    for ep in page_episodes:
        sub_icon = " ✅" if ep.has_subtitles else ""
        buttons.append([
            InlineKeyboardButton(
                f"📺 {ep.name}{sub_icon}",
                callback_data=f"b:d:{ep.id}",
            )
        ])

    # 分页
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 上一页", callback_data=f"b:s:{series_id}:{page - 1}"))
    if start + page_size < len(episodes):
        nav.append(InlineKeyboardButton("下一页 ▶", callback_data=f"b:s:{series_id}:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔙 返回", callback_data="b:back")])

    return InlineKeyboardMarkup(buttons)


def media_detail_keyboard(media_item_id: str) -> InlineKeyboardMarkup:
    """构建媒体详情键盘（含生成字幕按钮）"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 生成字幕", callback_data=f"t:c:{media_item_id}")],
        [InlineKeyboardButton("🔙 返回", callback_data="b:back")],
    ])


def task_detail_keyboard(task_id: str, status: str) -> InlineKeyboardMarkup:
    """构建任务详情键盘"""
    buttons = []
    if status in ("pending", "processing"):
        buttons.append([
            InlineKeyboardButton("❌ 取消任务", callback_data=f"t:x:{task_id[:8]}")
        ])
    elif status == "failed":
        buttons.append([
            InlineKeyboardButton("🔄 重试", callback_data=f"t:r:{task_id[:8]}")
        ])
    return InlineKeyboardMarkup(buttons)


def confirm_task_keyboard(media_item_id: str) -> InlineKeyboardMarkup:
    """构建任务确认键盘（内联搜索选中后使用）"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 确认生成", callback_data=f"t:c:{media_item_id}"),
            InlineKeyboardButton("❌ 取消", callback_data="noop"),
        ],
    ])


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
