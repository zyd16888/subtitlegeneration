"""
个人偏好配置 /config

允许用户覆盖全局任务配置（仅安全的部分）：
- 目标语言列表（target_languages）
- 是否保留源语言字幕（keep_source_subtitle）

不开放翻译服务/ASR 引擎切换，避免需要 admin 配置才能跑通的"黑盒"。
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from models.base import SessionLocal
from services.config_manager import ConfigManager
from tgbot.middleware import require_auth
from tgbot.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)

# 与 config_manager._SUPPORTED_LANGUAGE_CODES 对齐的可选语言（按常用度排序）
LANG_CHOICES: list[tuple[str, str]] = [
    ("zh", "中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("ru", "Русский"),
    ("pt", "Português"),
    ("it", "Italiano"),
    ("th", "ไทย"),
    ("vi", "Tiếng Việt"),
    ("ar", "العربية"),
    ("yue", "粵語"),
]


def _resolve_effective(user, config) -> tuple[list[str], bool]:
    """
    返回用户的有效（生效）偏好。

    Returns:
        (target_languages, keep_source_subtitle)
    """
    if user.prefer_target_languages:
        target_langs = list(user.prefer_target_languages)
    else:
        target_langs = (
            list(config.target_languages) if config.target_languages
            else [config.target_language]
        )

    if user.prefer_keep_source_subtitle is not None:
        keep = bool(user.prefer_keep_source_subtitle)
    else:
        keep = bool(config.keep_source_subtitle)

    return target_langs, keep


def _render_config(user, config) -> tuple[str, InlineKeyboardMarkup]:
    """渲染 /config 主消息和键盘。"""
    target_langs, keep = _resolve_effective(user, config)

    overridden_langs = user.prefer_target_languages is not None
    overridden_keep = user.prefer_keep_source_subtitle is not None

    src_lang = config.source_language or "ja"

    lines = [
        "⚙️ 任务偏好",
        f"源语言: {src_lang}（全局，无法在此修改）",
        f"目标语言: {' / '.join(target_langs) or '—'} {'(已覆盖)' if overridden_langs else '(全局)'}",
        f"保留源字幕: {'✅ 是' if keep else '❌ 否'} {'(已覆盖)' if overridden_keep else '(全局)'}",
        "",
        "点击语言按钮切换；点击⚪/✅切换保留源字幕。",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    # 把语言按 2 列显示
    pair: list[InlineKeyboardButton] = []
    for code, name in LANG_CHOICES:
        # 不允许把源语言加进 target（avoid self translation）
        if code == src_lang:
            continue
        marker = "✅" if code in target_langs else "⬜"
        pair.append(InlineKeyboardButton(
            f"{marker} {name}",
            callback_data=f"cfg:lang:{code}",
        ))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    # 保留源字幕开关
    rows.append([
        InlineKeyboardButton(
            f"{'✅' if keep else '⚪'} 保留源字幕",
            callback_data="cfg:keep",
        )
    ])

    rows.append([
        InlineKeyboardButton("🔄 重置为全局", callback_data="cfg:reset")
    ])

    return "\n".join(lines), InlineKeyboardMarkup(rows)


@require_auth
async def config_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """显示并修改个人偏好。"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        config = await ConfigManager(db).get_config()
        text, keyboard = _render_config(user, config)
        await update.message.reply_text(text, reply_markup=keyboard)
    finally:
        db.close()


async def config_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理 cfg:* 回调"""
    query = update.callback_query
    data = query.data

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        config = await ConfigManager(db).get_config()

        if data == "cfg:show":
            await query.answer()
        elif data == "cfg:reset":
            user.prefer_target_languages = None
            user.prefer_keep_source_subtitle = None
            db.commit()
            await query.answer("已重置为全局配置")
        elif data == "cfg:keep":
            # None → True → False → None 三段切换
            current = user.prefer_keep_source_subtitle
            global_default = bool(config.keep_source_subtitle)
            if current is None:
                # 当前用全局默认，按钮按下后取相反值并设置覆盖
                user.prefer_keep_source_subtitle = not global_default
            elif current == (not global_default):
                # 已经是反转过的覆盖值，再按一次回到全局
                user.prefer_keep_source_subtitle = None
            else:
                # 已经是和全局相同的覆盖值，则切换为相反
                user.prefer_keep_source_subtitle = not current
            db.commit()
            await query.answer("保留源字幕已更新")
        elif data.startswith("cfg:lang:"):
            code = data[len("cfg:lang:"):]
            src_lang = config.source_language or "ja"
            if code == src_lang:
                await query.answer("不能选择源语言作为目标", show_alert=True)
                return

            current_overridden = user.prefer_target_languages
            if current_overridden is not None:
                target_langs = list(current_overridden)
            else:
                target_langs = (
                    list(config.target_languages) if config.target_languages
                    else [config.target_language]
                )

            if code in target_langs:
                target_langs = [c for c in target_langs if c != code]
            else:
                target_langs.append(code)

            # 空列表保留为覆盖（用户明确想要无目标 = 不翻译，但实际等同于"重置"）；
            # 这里如果空了直接当作"恢复全局"，避免后续 worker 拿到空列表报错
            if not target_langs:
                user.prefer_target_languages = None
            else:
                user.prefer_target_languages = target_langs
            db.commit()
            await query.answer("目标语言已更新")
        else:
            await query.answer()
            return

        # 重新渲染主消息
        # 重新拿 user/config（user.prefer_* 可能刚被改了）
        db.refresh(user)
        text, keyboard = _render_config(user, config)
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            # 例如 message is not modified
            pass
    finally:
        db.close()


def register(app: Application) -> None:
    """注册 /config 相关 handlers"""
    app.add_handler(CommandHandler("config", config_command))
    app.add_handler(CallbackQueryHandler(config_callback, pattern=r"^cfg:"))


__all__ = ["register", "_resolve_effective"]
