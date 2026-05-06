"""
全局错误处理器。

接管 telegram.ext.Application 中未被 handler 自身捕获的异常：
- 完整记录 traceback
- 给当前用户回一句友好提示（避免静默失败）
- 严重错误（PTB 内部 / DB / 第三方异常）记录但不打扰用户多次
"""
import logging
import traceback

from telegram import Update
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def global_error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    PTB 全局错误处理。

    PTB 在 handler 抛异常时调用本函数，update 可能不是 Update（也可能是 None）。
    """
    err = context.error
    if err is None:
        return

    # 网络抖动 / 限流：只记录，不打扰用户（被 messaging 层兜底）
    if isinstance(err, (RetryAfter, TimedOut, NetworkError)):
        logger.warning("Telegram 网络/限流: %s", err)
        return

    # 用户拉黑 / 聊天不存在：记录，不再尝试给该用户回复
    if isinstance(err, Forbidden):
        logger.info("Telegram Forbidden（用户已拉黑或停用）: %s", err)
        return

    # BadRequest 通常是消息已被删除或内容不变（edit_message 等）
    if isinstance(err, BadRequest):
        msg = str(err).lower()
        if "message is not modified" in msg or "message to edit not found" in msg:
            logger.debug("Telegram BadRequest（可忽略）: %s", err)
            return

    # 其他异常：记录完整 traceback
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    logger.error("Bot handler 未捕获异常:\n%s", tb)

    # 尝试给当前用户回一条友好提示
    if isinstance(update, Update):
        try:
            if update.callback_query:
                try:
                    await update.callback_query.answer(
                        "❌ 操作失败，请稍后重试", show_alert=True,
                    )
                except TelegramError:
                    pass
            elif update.effective_message:
                try:
                    await update.effective_message.reply_text(
                        "❌ 操作失败，请稍后重试。问题已记录，请联系管理员。"
                    )
                except TelegramError:
                    pass
        except Exception:
            # 友好回复本身失败也不二次抛出
            pass


def register(application) -> None:
    """注册全局错误处理器。"""
    application.add_error_handler(global_error_handler)


__all__ = ["global_error_handler", "register"]
