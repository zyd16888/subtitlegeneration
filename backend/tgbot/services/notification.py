"""
任务完成通知服务（JobQueue 轮询）
"""
import logging

from sqlalchemy.orm.attributes import flag_modified
from telegram.ext import CallbackContext

from models.base import SessionLocal
from models.task import Task, TaskStatus
from tgbot.services.user_service import get_user_by_telegram_id
from tgbot.utils import format_duration

logger = logging.getLogger(__name__)


async def check_task_notifications(context: CallbackContext) -> None:
    """
    定期检查已完成/失败的任务，发送通知给创建者。
    由 JobQueue.run_repeating 每 30 秒调用。
    """
    db = SessionLocal()
    try:
        # 查找已完成或失败但未通知的任务
        tasks = db.query(Task).filter(
            Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED]),
            Task.extra_info.isnot(None),
        ).all()

        for task in tasks:
            info = task.extra_info or {}
            tg_id = info.get("telegram_user_id")

            # 跳过：无 telegram 来源、已通知
            if not tg_id or info.get("telegram_notified"):
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

            if should_notify:
                try:
                    msg = _format_notification(task)
                    await context.bot.send_message(
                        chat_id=tg_id, text=msg
                    )
                except Exception as e:
                    logger.warning(f"发送通知失败 (tg_id={tg_id}): {e}")

            # 标记已通知
            info["telegram_notified"] = True
            task.extra_info = info
            flag_modified(task, "extra_info")

        db.commit()

    except Exception as e:
        logger.error(f"通知检查异常: {e}")
    finally:
        db.close()


def _format_notification(task: Task) -> str:
    """格式化通知消息"""
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
        if task.error_stage:
            parts.append(f"❗ 阶段: {task.error_stage}")
        if task.error_message:
            error_msg = task.error_message
            if len(error_msg) > 100:
                error_msg = error_msg[:97] + "..."
            parts.append(f"💬 {error_msg}")
        parts.append(f"\n使用 /retry {task.id[:8]} 重试")
        return "\n".join(parts)

    return f"任务 {task.id[:8]} 状态更新: {task.status}"
