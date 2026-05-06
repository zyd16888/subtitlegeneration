"""
Telegram 消息发送的安全包装层。

主要解决两件事：
1. RetryAfter（API 限流）：捕获并按 retry_after 等待后重试。
2. 短暂网络错误（NetworkError / TimedOut）：指数退避重试。

只用于 bot 主动给用户/管理员发消息的路径，不接管 reply_text 等响应路径
（响应路径的失败由 add_error_handler 统一兜底）。
"""
import asyncio
import logging
from typing import Any, Optional

from telegram.error import RetryAfter, TimedOut, NetworkError, TelegramError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0


async def _call_with_retry(
    label: str,
    coro_factory,
) -> Any:
    """
    通用重试封装。

    Args:
        label: 操作名（出错日志用）
        coro_factory: 无参函数，每次调用返回一个新的 awaitable
    """
    backoff = INITIAL_BACKOFF_SECONDS
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except RetryAfter as e:
            wait = float(getattr(e, "retry_after", backoff))
            logger.warning(
                "%s 触发 RetryAfter，等待 %.1fs 后重试（第 %d/%d）",
                label, wait, attempt, MAX_RETRIES,
            )
            await asyncio.sleep(wait + 0.5)
            last_exc = e
        except (TimedOut, NetworkError) as e:
            logger.warning(
                "%s 网络抖动 %s，%.1fs 后重试（第 %d/%d）",
                label, type(e).__name__, backoff, attempt, MAX_RETRIES,
            )
            await asyncio.sleep(backoff)
            backoff *= 2
            last_exc = e
        except TelegramError as e:
            # 其他 Telegram 错误（聊天封禁、用户拉黑等）不重试
            logger.warning("%s Telegram 错误，不重试: %s", label, e)
            raise

    if last_exc is not None:
        logger.error("%s 重试 %d 次仍失败: %s", label, MAX_RETRIES, last_exc)
        raise last_exc
    return None


async def send_message_safe(bot, chat_id: int, text: str, **kwargs) -> Any:
    """带 RetryAfter 处理的 send_message。"""
    return await _call_with_retry(
        f"send_message(chat_id={chat_id})",
        lambda: bot.send_message(chat_id=chat_id, text=text, **kwargs),
    )


async def send_document_safe(bot, chat_id: int, document, **kwargs) -> Any:
    """带 RetryAfter 处理的 send_document。"""
    return await _call_with_retry(
        f"send_document(chat_id={chat_id})",
        lambda: bot.send_document(chat_id=chat_id, document=document, **kwargs),
    )
