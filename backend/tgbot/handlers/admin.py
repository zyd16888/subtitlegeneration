"""
管理员命令处理
"""
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from models.base import SessionLocal
from models.task import Task, TaskStatus
from services.config_manager import ConfigManager
from services.task_manager import TaskManager
from tgbot.middleware import require_admin
from tgbot.services.user_service import (
    get_all_users,
    get_daily_task_count,
    get_user_by_telegram_id,
)
from tgbot.utils import format_task_status, format_time_ago, short_id

logger = logging.getLogger(__name__)


@require_admin
async def admin_stats(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """系统统计"""
    db = SessionLocal()
    try:
        task_manager = TaskManager(db)
        stats = await task_manager.get_statistics()

        users = get_all_users(db)
        total_users = len(users)
        bound_users = sum(1 for u in users if u.emby_user_id)
        banned_users = sum(1 for u in users if not u.is_active)

        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        queued_or_running_tasks = db.query(Task).filter(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])
        ).count()

        await update.message.reply_text(
            f"📊 系统状态\n\n"
            f"任务统计:\n"
            f"  🕐 排队中: {stats.pending}\n"
            f"  ⏳ 处理中: {stats.processing}\n"
            f"  ✅ 已完成: {stats.completed}\n"
            f"  ❌ 已失败: {stats.failed}\n"
            f"  🚫 已取消: {stats.cancelled}\n\n"
            f"Bot 用户:\n"
            f"  👥 总用户: {total_users}\n"
            f"  ✅ 已绑定: {bound_users}\n"
            f"  🚫 已封禁: {banned_users}\n\n"
            f"执行并发: {stats.processing}/{config.max_concurrent_tasks}\n"
            f"队列占用: {queued_or_running_tasks}"
        )
    except Exception as e:
        logger.error(f"获取统计异常: {e}")
        await update.message.reply_text("❌ 获取统计失败")
    finally:
        db.close()


@require_admin
async def admin_tasks(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """查看所有任务"""
    status_filter = context.args[0] if context.args else None

    db = SessionLocal()
    try:
        query = db.query(Task).order_by(Task.created_at.desc())
        if status_filter:
            try:
                status = TaskStatus(status_filter)
                query = query.filter(Task.status == status)
            except ValueError:
                await update.message.reply_text(
                    f"无效状态，可选: {', '.join(s.value for s in TaskStatus)}"
                )
                return

        tasks = query.limit(15).all()

        if not tasks:
            await update.message.reply_text("没有任务记录")
            return

        lines = ["📋 所有任务\n"]
        for i, task in enumerate(tasks, 1):
            status_str = format_task_status(
                task.status.value if isinstance(task.status, TaskStatus) else task.status
            )
            title = task.media_item_title or "未知"
            if len(title) > 20:
                title = title[:19] + "…"

            # 获取来源用户
            info = task.extra_info or {}
            tg_id = info.get("telegram_user_id", "")
            source = f" [TG:{tg_id}]" if tg_id else " [Web]"

            lines.append(
                f"{i}. {status_str} {title} ({short_id(task.id)}){source}"
            )

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"查看所有任务异常: {e}")
        await update.message.reply_text("❌ 获取任务失败")
    finally:
        db.close()


@require_admin
async def admin_users(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """查看所有 Bot 用户"""
    db = SessionLocal()
    try:
        users = get_all_users(db)
        if not users:
            await update.message.reply_text("没有注册用户")
            return

        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        lines = [f"👥 Bot 用户列表 (共 {len(users)} 人)\n"]
        for u in users:
            name = u.telegram_username or u.telegram_display_name or str(u.telegram_id)
            if u.telegram_username:
                name = f"@{name}"

            emby = f"Emby:{u.emby_username}" if u.emby_user_id else "未绑定"
            status = "已封禁" if not u.is_active else "活跃"
            admin_badge = " 👑" if u.is_admin else ""

            daily_count = get_daily_task_count(db, u)
            daily_limit = u.daily_task_limit or config.telegram_daily_task_limit

            lines.append(
                f"• {name} ({emby}) - {status}{admin_badge}\n"
                f"  ID: {u.telegram_id} | 今日: {daily_count}/{daily_limit}"
            )

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"查看用户列表异常: {e}")
        await update.message.reply_text("❌ 获取用户列表失败")
    finally:
        db.close()


@require_admin
async def admin_ban(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """封禁用户"""
    if not context.args:
        await update.message.reply_text("用法: /admin_ban Telegram_ID")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("请输入有效的 Telegram ID（数字）")
        return

    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, target_id)
        if not user:
            await update.message.reply_text("❌ 用户未找到")
            return

        user.is_active = False
        db.commit()

        # 取消该用户的所有待处理任务
        pending_tasks = db.query(Task).filter(
            Task.extra_info.contains(f'"telegram_user_id": {target_id}'),
            Task.status.in_([TaskStatus.PENDING]),
        ).all()

        task_manager = TaskManager(db)
        for task in pending_tasks:
            await task_manager.cancel_task(task.id)

        name = user.telegram_username or str(user.telegram_id)
        await update.message.reply_text(
            f"🚫 已封禁用户 @{name}\n"
            f"已取消 {len(pending_tasks)} 个待处理任务"
        )
    finally:
        db.close()


@require_admin
async def admin_unban(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """解封用户"""
    if not context.args:
        await update.message.reply_text("用法: /admin_unban Telegram_ID")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("请输入有效的 Telegram ID")
        return

    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, target_id)
        if not user:
            await update.message.reply_text("❌ 用户未找到")
            return

        user.is_active = True
        db.commit()

        name = user.telegram_username or str(user.telegram_id)
        await update.message.reply_text(f"✅ 已解封用户 @{name}")
    finally:
        db.close()


@require_admin
async def admin_set_limit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """设置用户个人配额"""
    if len(context.args) < 2:
        await update.message.reply_text("用法: /admin_set_limit Telegram_ID 每日上限")
        return

    try:
        target_id = int(context.args[0])
        limit = int(context.args[1])
        if limit < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("请输入有效的参数")
        return

    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, target_id)
        if not user:
            await update.message.reply_text("❌ 用户未找到")
            return

        user.daily_task_limit = limit
        db.commit()

        name = user.telegram_username or str(user.telegram_id)
        await update.message.reply_text(
            f"✅ 用户 @{name} 的每日配额已设为 {limit}"
        )
    finally:
        db.close()


@require_admin
async def admin_reset_limit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """重置用户为全局默认配额"""
    if not context.args:
        await update.message.reply_text("用法: /admin_reset_limit Telegram_ID")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("请输入有效的 Telegram ID")
        return

    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, target_id)
        if not user:
            await update.message.reply_text("❌ 用户未找到")
            return

        user.daily_task_limit = None
        db.commit()

        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        name = user.telegram_username or str(user.telegram_id)
        await update.message.reply_text(
            f"✅ 用户 @{name} 已恢复全局默认配额 ({config.telegram_daily_task_limit})"
        )
    finally:
        db.close()


@require_admin
async def admin_cancel_all(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """取消所有待处理任务"""
    db = SessionLocal()
    try:
        pending_tasks = db.query(Task).filter(
            Task.status == TaskStatus.PENDING,
        ).all()

        if not pending_tasks:
            await update.message.reply_text("没有待处理的任务")
            return

        task_manager = TaskManager(db)
        count = 0
        for task in pending_tasks:
            if await task_manager.cancel_task(task.id):
                count += 1

        await update.message.reply_text(f"✅ 已取消 {count} 个待处理任务")
    except Exception as e:
        logger.error(f"批量取消异常: {e}")
        await update.message.reply_text("❌ 操作失败")
    finally:
        db.close()


@require_admin
async def admin_broadcast(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """广播消息给所有活跃用户"""
    if not context.args:
        await update.message.reply_text("用法: /admin_broadcast 消息内容")
        return

    message_text = " ".join(context.args)

    db = SessionLocal()
    try:
        from tgbot.services.user_service import get_all_active_users
        users = get_all_active_users(db)

        sent = 0
        failed = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 管理员通知\n\n{message_text}",
                )
                sent += 1
            except Exception:
                failed += 1

        await update.message.reply_text(
            f"✅ 广播完成: 发送 {sent} 成功, {failed} 失败"
        )
    except Exception as e:
        logger.error(f"广播异常: {e}")
        await update.message.reply_text("❌ 广播失败")
    finally:
        db.close()


def register(app: Application, admin_ids: list[int]) -> None:
    """注册管理员命令 handlers"""
    app.add_handler(CommandHandler("stat", admin_stats))
    app.add_handler(CommandHandler("task", admin_tasks))
    app.add_handler(CommandHandler("user", admin_users))
    app.add_handler(CommandHandler("ban", admin_ban))
    app.add_handler(CommandHandler("unban", admin_unban))
    app.add_handler(CommandHandler("set_limit", admin_set_limit))
    app.add_handler(CommandHandler("reset_limit", admin_reset_limit))
    app.add_handler(CommandHandler("cancel_all", admin_cancel_all))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
