"""
任务完成通知服务（JobQueue 轮询）
"""
import logging
from datetime import timedelta

from sqlalchemy.orm.attributes import flag_modified
from telegram.ext import CallbackContext

from config.time_utils import utc_now
from models.base import SessionLocal
from models.task import Task, TaskStatus
from tgbot.services.user_service import get_user_by_telegram_id
from tgbot.utils import format_duration

logger = logging.getLogger(__name__)

# 只扫描最近 7 天内完成的任务，避免长跑时全表扫描
NOTIFICATION_LOOKBACK_DAYS = 7
# 单条通知最多重试次数（瞬时网络/限流场景）
MAX_NOTIFICATION_RETRIES = 3


async def check_task_notifications(context: CallbackContext) -> None:
    """
    定期检查已完成/失败的任务，发送通知给创建者。
    由 JobQueue.run_repeating 每 30 秒调用。
    """
    db = SessionLocal()
    try:
        cutoff = utc_now() - timedelta(days=NOTIFICATION_LOOKBACK_DAYS)
        # 查找最近时间窗口内已完成或失败、未通知、有 TG 来源的任务
        tasks = db.query(Task).filter(
            Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED]),
            Task.telegram_user_id.isnot(None),
            Task.completed_at >= cutoff,
        ).all()

        for task in tasks:
            tg_id = task.telegram_user_id
            info = dict(task.extra_info) if task.extra_info else {}

            # 跳过：已通知 / 已超过最大重试次数
            if info.get("telegram_notified"):
                continue
            failed_count = int(info.get("notification_failed_count", 0))
            if failed_count >= MAX_NOTIFICATION_RETRIES:
                # 记录最终失败状态
                info["telegram_notified"] = True
                info["notification_giveup"] = True
                task.extra_info = info
                flag_modified(task, "extra_info")
                continue

            # 检查用户通知偏好
            user = get_user_by_telegram_id(db, tg_id)
            if not user:
                # 标记已通知避免重复查询
                info["telegram_notified"] = True
                task.extra_info = info
                flag_modified(task, "extra_info")
                continue

            should_notify = False
            if task.status == TaskStatus.COMPLETED and user.notify_on_complete:
                should_notify = True
            elif task.status == TaskStatus.FAILED and user.notify_on_failure:
                should_notify = True

            sent_ok = True
            if should_notify:
                try:
                    msg = _format_notification(task)
                    keyboard = _build_notification_keyboard(task)
                    from tgbot.services.messaging import send_message_safe
                    await send_message_safe(
                        context.bot, tg_id, msg, reply_markup=keyboard,
                    )
                except Exception as e:
                    sent_ok = False
                    logger.warning(
                        "发送通知失败 (tg_id=%s task=%s, 第 %d/%d 次): %s",
                        tg_id, task.id, failed_count + 1, MAX_NOTIFICATION_RETRIES, e,
                    )

            if sent_ok:
                # 标记已通知
                info["telegram_notified"] = True
            else:
                # 失败累计计数，下一轮再试
                info["notification_failed_count"] = failed_count + 1

            task.extra_info = info
            flag_modified(task, "extra_info")

        db.commit()

    except Exception as e:
        logger.error(f"通知检查异常: {e}")
    finally:
        db.close()


def mark_pending_notifications_as_sent() -> int:
    """
    在 Bot 启动时调用一次：把"早于 (now - 7d) 但仍未标记 telegram_notified 的旧任务"
    一次性标记为已通知，避免长时间停机后启动时批量发通知造成消息风暴。

    Returns:
        被标记的任务数量
    """
    db = SessionLocal()
    try:
        cutoff = utc_now() - timedelta(days=NOTIFICATION_LOOKBACK_DAYS)
        stale_tasks = db.query(Task).filter(
            Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED]),
            Task.telegram_user_id.isnot(None),
            Task.completed_at < cutoff,
        ).all()

        marked = 0
        for task in stale_tasks:
            info = dict(task.extra_info) if task.extra_info else {}
            if info.get("telegram_notified"):
                continue
            info["telegram_notified"] = True
            info["notification_skipped_stale"] = True
            task.extra_info = info
            flag_modified(task, "extra_info")
            marked += 1

        if marked:
            db.commit()
            logger.info("启动时标记 %d 条历史任务为已通知（避免风暴）", marked)
        return marked
    except Exception as e:
        logger.error("启动时标记历史通知异常: %s", e)
        return 0
    finally:
        db.close()


def _format_notification(task: Task) -> str:
    """格式化通知消息"""
    from tgbot.services.error_hints import classify

    title = task.media_item_title or "未知媒体"

    if task.status == TaskStatus.COMPLETED:
        parts = [
            f"✅ 字幕生成完成\n",
            f"📺 {title}",
        ]
        if task.processing_time:
            parts.append(f"⏱ 耗时 {format_duration(task.processing_time)}")
        if task.segment_count:
            parts.append(f"📝 识别 {task.segment_count} 条字幕")
        if task.translation_service:
            parts.append(f"🌐 翻译: {task.translation_service}")
        parts.append(f"\n字幕已自动上传至 Emby。")
        return "\n".join(parts)

    elif task.status == TaskStatus.FAILED:
        parts = [
            f"❌ 字幕生成失败\n",
            f"📺 {title}",
        ]
        reason, suggestion = classify(task.error_stage, task.error_message)
        parts.append(f"❗ {reason}")
        parts.append(f"💡 {suggestion}")
        if task.error_message:
            error_msg = task.error_message
            if len(error_msg) > 100:
                error_msg = error_msg[:97] + "..."
            parts.append(f"💬 {error_msg}")
        return "\n".join(parts)

    return f"任务 {task.id[:8]} 状态更新: {task.status}"


def _build_notification_keyboard(task: Task):
    """构造通知附带的内联键盘。"""
    from tgbot.views.task_view import (
        render_completion_notification_keyboard,
        render_failure_notification_keyboard,
    )

    if task.status == TaskStatus.COMPLETED:
        return render_completion_notification_keyboard(task)
    if task.status == TaskStatus.FAILED:
        return render_failure_notification_keyboard(task)
    return None
