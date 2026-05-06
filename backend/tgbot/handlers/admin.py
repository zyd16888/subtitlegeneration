"""
管理员命令处理
"""
import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

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
from tgbot.utils import format_duration, format_task_status, format_time_ago, short_id

logger = logging.getLogger(__name__)

USER_PAGE_SIZE = 10


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

            # 获取来源用户：优先用任务字段，回退 extra_info（兼容历史数据）
            tg_id = task.telegram_user_id
            if not tg_id:
                tg_id = (task.extra_info or {}).get("telegram_user_id", "")
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


def _render_user_list(
    users, total: int, page: int, keyword: str, daily_limit_default: int,
    db,
):
    """渲染用户列表的文本和分页键盘。"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    title = f"👥 Bot 用户"
    if keyword:
        title += f"（关键词: {keyword}）"
    title += f" · 共 {total} 人"

    if not users:
        return title + "\n\n没有匹配的用户", None

    lines = [title + "\n"]
    for u in users:
        name = u.telegram_username or u.telegram_display_name or str(u.telegram_id)
        if u.telegram_username:
            name = f"@{name}"
        emby = f"Emby:{u.emby_username}" if u.emby_user_id else "未绑定"
        status = "已封禁" if not u.is_active else "活跃"
        admin_badge = " 👑" if u.is_admin else ""
        daily_count = get_daily_task_count(db, u)
        daily_limit = u.daily_task_limit or daily_limit_default
        lines.append(
            f"• {name} ({emby}) - {status}{admin_badge}\n"
            f"  ID: {u.telegram_id} | 今日: {daily_count}/{daily_limit}"
        )

    nav: list = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            "◀ 上一页",
            callback_data=f"au:p:{page - 1}",
        ))
    if (page + 1) * USER_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            "下一页 ▶",
            callback_data=f"au:p:{page + 1}",
        ))
    keyboard = InlineKeyboardMarkup([nav]) if nav else None

    return "\n".join(lines), keyboard


@require_admin
async def admin_users(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """查看 Bot 用户列表（支持分页和关键词搜索）。

    用法:
      /user            - 显示首页
      /user 关键词     - 按用户名/显示名/Emby用户名/Telegram ID 模糊匹配
    """
    from tgbot.services.user_service import search_users

    keyword = " ".join(context.args).strip() if context.args else ""

    db = SessionLocal()
    try:
        users, total = search_users(db, keyword, page=0, page_size=USER_PAGE_SIZE)
        if not users and not keyword:
            await update.message.reply_text("没有注册用户")
            return

        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        # 把当前关键词存到 bot_data，供分页 callback 复用
        context.bot_data.setdefault("admin_user_search", {})
        context.bot_data["admin_user_search"][update.effective_user.id] = keyword

        text, keyboard = _render_user_list(
            users, total, page=0, keyword=keyword,
            daily_limit_default=config.telegram_daily_task_limit,
            db=db,
        )
        await update.message.reply_text(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"查看用户列表异常: {e}")
        await update.message.reply_text("❌ 获取用户列表失败")
    finally:
        db.close()


async def admin_users_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """au:p:{page} 用户列表分页（仅管理员可触发）。"""
    from tgbot.services.user_service import search_users

    query = update.callback_query
    tg_user_id = update.effective_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    db = SessionLocal()
    try:
        # 权限校验：管理员或 DB 中 is_admin
        from tgbot.services.user_service import get_or_create_user
        user = get_or_create_user(db, update.effective_user)
        if not (user.is_admin or tg_user_id in admin_ids):
            await query.answer("❌ 需要管理员权限", show_alert=True)
            return

        try:
            page = int(query.data[len("au:p:"):])
        except ValueError:
            page = 0

        keyword = (
            context.bot_data.get("admin_user_search", {}).get(tg_user_id, "")
        )

        users, total = search_users(db, keyword, page, USER_PAGE_SIZE)
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        await query.answer()
        text, keyboard = _render_user_list(
            users, total, page=page, keyword=keyword,
            daily_limit_default=config.telegram_daily_task_limit,
            db=db,
        )
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=text, reply_markup=keyboard,
            )
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
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "ban", target_id=str(target_id),
        )
        db.commit()

        # 取消该用户的所有待处理任务
        pending_tasks = db.query(Task).filter(
            Task.telegram_user_id == target_id,
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
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "unban", target_id=str(target_id),
        )
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
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "set_limit",
            target_id=str(target_id), payload={"limit": limit},
        )
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
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "reset_limit", target_id=str(target_id),
        )
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

        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "cancel_all",
            payload={"cancelled_count": count},
        )
        db.commit()

        await update.message.reply_text(f"✅ 已取消 {count} 个待处理任务")
    except Exception as e:
        logger.error(f"批量取消异常: {e}")
        await update.message.reply_text("❌ 操作失败")
    finally:
        db.close()


_BROADCAST_FILTER_LABELS = {
    "active-7d": "最近 7 天活跃用户",
    "bound": "已绑定 Emby 的活跃用户",
    "admins": "管理员",
    "all": "所有活跃用户",
}


def _parse_broadcast_args(args: list[str]) -> tuple[str, str]:
    """解析广播 flag，返回 (filter_kind, message)。"""
    filter_kind = "active-7d"
    msg_parts = []
    for token in args:
        low = token.lower()
        if low in ("--active-7d", "--active7d"):
            filter_kind = "active-7d"
        elif low == "--bound":
            filter_kind = "bound"
        elif low == "--admins":
            filter_kind = "admins"
        elif low == "--all":
            filter_kind = "all"
        else:
            msg_parts.append(token)
    return filter_kind, " ".join(msg_parts).strip()


@require_admin
async def admin_broadcast(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """广播消息（支持定向）。

    用法:
      /broadcast 消息                     - 默认 --active-7d
      /broadcast --bound 消息             - 仅已绑定 Emby
      /broadcast --admins 消息            - 仅管理员
      /broadcast --all 消息               - 所有活跃用户
    """
    from tgbot.services.user_service import get_users_by_filter

    if not context.args:
        await update.message.reply_text(
            "用法: /broadcast [--active-7d|--bound|--admins|--all] 消息内容"
        )
        return

    filter_kind, message_text = _parse_broadcast_args(list(context.args))
    if not message_text:
        await update.message.reply_text("❌ 请填写广播内容")
        return

    db = SessionLocal()
    try:
        try:
            users = get_users_by_filter(db, filter_kind)
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
            return

        if not users:
            await update.message.reply_text(
                f"没有符合条件的用户（{_BROADCAST_FILTER_LABELS.get(filter_kind, filter_kind)}）"
            )
            return

        await update.message.reply_text(
            f"📢 准备向 {_BROADCAST_FILTER_LABELS.get(filter_kind, filter_kind)} "
            f"({len(users)} 人) 广播…"
        )

        from tgbot.services.messaging import send_message_safe

        sent = 0
        failed = 0
        for user in users:
            try:
                await send_message_safe(
                    context.bot, user.telegram_id,
                    f"📢 管理员通知\n\n{message_text}",
                )
                sent += 1
            except Exception:
                failed += 1
            # 简单限速，避免触发 Telegram 全局 rate limit
            await asyncio.sleep(0.05)

        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "broadcast",
            payload={
                "filter": filter_kind,
                "recipients": len(users),
                "sent": sent,
                "failed": failed,
                "message": message_text[:200],
            },
        )
        db.commit()

        await update.message.reply_text(
            f"✅ 广播完成: 发送 {sent} 成功, {failed} 失败"
        )
    except Exception as e:
        logger.error(f"广播异常: {e}")
        await update.message.reply_text("❌ 广播失败")
    finally:
        db.close()


@require_admin
async def admin_queue(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """显示当前队列详情（处理中 + 排队中），并估算等待时间。"""
    db = SessionLocal()
    try:
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()
        max_concurrent = max(int(config.max_concurrent_tasks or 1), 1)

        processing = db.query(Task).filter(
            Task.status == TaskStatus.PROCESSING,
        ).order_by(Task.started_at.asc().nullslast()).all()

        pending = db.query(Task).filter(
            Task.status == TaskStatus.PENDING,
        ).order_by(Task.created_at.asc()).limit(15).all()

        # 估算平均耗时（最近 50 个已完成任务）
        recent_completed_times = (
            db.query(Task.processing_time)
            .filter(
                Task.status == TaskStatus.COMPLETED,
                Task.processing_time.isnot(None),
            )
            .order_by(Task.completed_at.desc())
            .limit(50)
            .all()
        )
        times = [row[0] for row in recent_completed_times if row[0]]
        avg_seconds = sum(times) / len(times) if times else None

        lines = [
            f"📊 任务队列",
            f"并发上限: {max_concurrent}",
            f"处理中: {len(processing)} · 排队中: {len(pending)}",
        ]
        if avg_seconds is not None:
            lines.append(f"平均耗时（近 50 个）: {format_duration(avg_seconds)}")

        # 处理中详情
        if processing:
            lines.append("\n⏳ 处理中")
            for i, t in enumerate(processing, 1):
                title = t.media_item_title or "未知"
                if len(title) > 28:
                    title = title[:27] + "…"
                started = format_time_ago(t.started_at) if t.started_at else "—"
                lines.append(
                    f"{i}. {title} ({short_id(t.id)})\n"
                    f"   进度 {t.progress}% · 开始于 {started}"
                )

        # 排队中详情 + 等待估计
        if pending:
            lines.append("\n🕐 排队中（前 15 条）")
            for i, t in enumerate(pending, 1):
                title = t.media_item_title or "未知"
                if len(title) > 28:
                    title = title[:27] + "…"
                # 估计等待 = 队列前面任务数 / 并发 × 平均耗时
                if avg_seconds is not None:
                    ahead = i - 1
                    wait_seconds = (ahead / max_concurrent) * avg_seconds
                    eta = format_duration(wait_seconds)
                    lines.append(
                        f"{i}. {title} ({short_id(t.id)}) · 预计 {eta}"
                    )
                else:
                    lines.append(f"{i}. {title} ({short_id(t.id)})")

        if not processing and not pending:
            lines.append("\n队列为空 ✨")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"查看队列异常: {e}")
        await update.message.reply_text("❌ 获取队列详情失败")
    finally:
        db.close()


@require_admin
async def admin_log(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """查看任务日志：/log 任务ID短码 [--all]

    默认显示最近 30 条；--all 时把完整日志作为文件发送。
    """
    if not context.args:
        await update.message.reply_text("用法: /log 任务ID短码 [--all]")
        return

    show_all = "--all" in context.args
    task_short_id = next(
        (t for t in context.args if not t.startswith("--")),
        "",
    )
    if not task_short_id:
        await update.message.reply_text("用法: /log 任务ID短码 [--all]")
        return

    db = SessionLocal()
    try:
        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
        ).first()
        if not task:
            await update.message.reply_text("❌ 未找到任务")
            return

        info = task.extra_info or {}
        logs = info.get("logs") or []
        if not logs:
            await update.message.reply_text(
                f"任务 {short_id(task.id)} 暂无日志记录"
            )
            return

        if show_all:
            # 把完整日志拼成文本文件发送
            content_lines = [
                f"[{e.get('timestamp', '')}] {e.get('level', '')} "
                f"{e.get('logger', '')} - {e.get('message', '')}"
                for e in logs
            ]
            content = "\n".join(content_lines)
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=content.encode("utf-8"),
                filename=f"task_{short_id(task.id)}_logs.txt",
                caption=f"任务 {task.media_item_title or short_id(task.id)} 完整日志（{len(logs)} 条）",
            )
            return

        # 默认展示最近 30 条
        recent = logs[-30:]
        lines = [
            f"📜 {task.media_item_title or '任务'} 日志（最近 {len(recent)}/{len(logs)} 条）\n"
        ]
        for e in recent:
            level = e.get("level", "")
            msg = e.get("message", "")
            if len(msg) > 200:
                msg = msg[:197] + "…"
            lines.append(f"[{level}] {msg}")
        text = "\n".join(lines)
        # Telegram 单条消息上限约 4096 字符
        if len(text) > 3800:
            text = text[:3800] + "\n…（截断，使用 /log {} --all 查看完整）".format(short_id(task.id))
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"查看任务日志异常: {e}")
        await update.message.reply_text("❌ 获取日志失败")
    finally:
        db.close()


@require_admin
async def admin_promote(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """/promote Telegram_ID - 提升为管理员"""
    if not context.args:
        await update.message.reply_text("用法: /promote Telegram_ID")
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
        if user.is_admin:
            await update.message.reply_text("用户已是管理员")
            return

        user.is_admin = True
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "promote", target_id=str(target_id),
        )
        db.commit()

        # 同步刷新该用户的命令菜单
        try:
            await _refresh_admin_command_menu(context, target_id)
        except Exception as e:
            logger.warning("刷新管理员菜单失败: %s", e)

        name = user.telegram_username or str(user.telegram_id)
        await update.message.reply_text(f"✅ 已提升 @{name} 为管理员")
    finally:
        db.close()


@require_admin
async def admin_demote(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """/demote Telegram_ID - 撤销管理员权限"""
    if not context.args:
        await update.message.reply_text("用法: /demote Telegram_ID")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("请输入有效的 Telegram ID")
        return

    if target_id == update.effective_user.id:
        await update.message.reply_text("❌ 不能撤销自己的管理员权限")
        return

    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, target_id)
        if not user:
            await update.message.reply_text("❌ 用户未找到")
            return
        if not user.is_admin:
            await update.message.reply_text("用户不是管理员")
            return

        user.is_admin = False
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "demote", target_id=str(target_id),
        )
        db.commit()

        try:
            await _refresh_user_command_menu(context, target_id)
        except Exception as e:
            logger.warning("刷新用户菜单失败: %s", e)

        name = user.telegram_username or str(user.telegram_id)
        await update.message.reply_text(f"✅ 已撤销 @{name} 的管理员权限")
    finally:
        db.close()


@require_admin
async def admin_reload_config(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """/reload_config - 不重启 Bot 重新加载配置（admin_ids 等）"""
    db = SessionLocal()
    try:
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        # 重新构建 admin_ids（配置 admin_ids 字符串 + DB 中 is_admin=True 的用户）
        from tgbot.models import TelegramUser

        admin_ids: list[int] = []
        if config.telegram_admin_ids:
            for piece in config.telegram_admin_ids.split(","):
                piece = piece.strip()
                if piece.isdigit():
                    admin_ids.append(int(piece))
        for u in db.query(TelegramUser).filter(TelegramUser.is_admin == True).all():
            if u.telegram_id not in admin_ids:
                admin_ids.append(u.telegram_id)

        old_ids = context.bot_data.get("admin_ids", [])
        context.bot_data["admin_ids"] = admin_ids

        # 同步刷新所有管理员的命令菜单
        try:
            from tgbot.bot import _register_commands
            await _register_commands(context.application, admin_ids)
        except Exception as e:
            logger.warning("重新注册命令失败: %s", e)

        added = set(admin_ids) - set(old_ids)
        removed = set(old_ids) - set(admin_ids)

        from tgbot.services import audit as audit_service
        audit_service.record(
            db, update.effective_user.id, "reload_config",
            payload={
                "added": sorted(added),
                "removed": sorted(removed),
                "admin_count": len(admin_ids),
            },
        )
        db.commit()

        lines = [
            "♻️ 配置已重载",
            f"管理员: {len(admin_ids)} 人",
        ]
        if added:
            lines.append(f"➕ 新增: {', '.join(str(i) for i in added)}")
        if removed:
            lines.append(f"➖ 移除: {', '.join(str(i) for i in removed)}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error("重载配置异常: %s", e)
        await update.message.reply_text("❌ 重载配置失败")
    finally:
        db.close()


def _parse_audit_args(args: list[str]) -> tuple[Optional[str], Optional[int], int]:
    """解析 /audit 参数，返回 (action, user_id, limit)。"""
    action: Optional[str] = None
    user_id: Optional[int] = None
    limit = 20

    i = 0
    while i < len(args):
        token = args[i]
        if token in ("--user", "-u") and i + 1 < len(args):
            try:
                user_id = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        elif token in ("--action", "-a") and i + 1 < len(args):
            action = args[i + 1]
            i += 2
        elif token in ("--limit", "-l") and i + 1 < len(args):
            try:
                limit = max(1, min(100, int(args[i + 1])))
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    return action, user_id, limit


@require_admin
async def admin_audit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """/audit [--user X] [--action Y] [--limit N] - 查询审计日志（管理员）"""
    from tgbot.services import audit as audit_service
    from tgbot.utils import format_time_ago

    action, user_id, limit = _parse_audit_args(list(context.args or []))

    db = SessionLocal()
    try:
        records = audit_service.query(
            db, action=action, tg_user_id=user_id, limit=limit,
        )

        if not records:
            await update.message.reply_text("没有匹配的审计记录")
            return

        title = f"📜 审计日志（最近 {len(records)} 条"
        scope = []
        if action:
            scope.append(f"action={action}")
        if user_id is not None:
            scope.append(f"user={user_id}")
        if scope:
            title += " · " + " · ".join(scope)
        title += "）"

        lines = [title + "\n"]
        for r in records:
            ago = format_time_ago(r.ts)
            target = f" → {r.target_id}" if r.target_id else ""
            payload_str = ""
            if r.payload:
                # 摘要前 80 字
                import json
                try:
                    s = json.dumps(r.payload, ensure_ascii=False)
                except Exception:
                    s = str(r.payload)
                if len(s) > 80:
                    s = s[:77] + "…"
                payload_str = f" {s}"
            lines.append(
                f"[{ago}] tg:{r.tg_user_id} {r.action}{target}{payload_str}"
            )

        text = "\n".join(lines)
        if len(text) > 3800:
            text = text[:3800] + "\n…（截断，请缩小过滤条件）"
        await update.message.reply_text(text)
    except Exception as e:
        logger.error("查询审计日志异常: %s", e)
        await update.message.reply_text("❌ 查询审计日志失败")
    finally:
        db.close()


async def _refresh_admin_command_menu(context: ContextTypes.DEFAULT_TYPE, tg_id: int) -> None:
    """把目标用户提升为管理员后，给 ta 注册管理员命令菜单。"""
    from telegram import BotCommandScopeChat
    from tgbot.bot import _build_user_commands, _build_admin_commands

    user_cmds = _build_user_commands()
    admin_cmds = _build_admin_commands()
    await context.bot.set_my_commands(
        user_cmds + admin_cmds,
        scope=BotCommandScopeChat(chat_id=tg_id),
    )

    # 同步加入 bot_data 中的 admin_ids
    admin_ids = context.bot_data.get("admin_ids", [])
    if tg_id not in admin_ids:
        admin_ids.append(tg_id)
        context.bot_data["admin_ids"] = admin_ids


async def _refresh_user_command_menu(context: ContextTypes.DEFAULT_TYPE, tg_id: int) -> None:
    """把目标用户降级后，把 ta 的命令菜单恢复为普通用户。"""
    from telegram import BotCommandScopeChat
    from tgbot.bot import _build_user_commands

    user_cmds = _build_user_commands()
    await context.bot.set_my_commands(
        user_cmds,
        scope=BotCommandScopeChat(chat_id=tg_id),
    )

    admin_ids = context.bot_data.get("admin_ids", [])
    if tg_id in admin_ids:
        admin_ids.remove(tg_id)
        context.bot_data["admin_ids"] = admin_ids


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

    # P3 新增
    app.add_handler(CommandHandler("queue", admin_queue))
    app.add_handler(CommandHandler("log", admin_log))
    app.add_handler(CommandHandler("promote", admin_promote))
    app.add_handler(CommandHandler("demote", admin_demote))
    app.add_handler(CommandHandler("reload_config", admin_reload_config))

    # P4 新增
    app.add_handler(CommandHandler("audit", admin_audit))

    app.add_handler(CallbackQueryHandler(admin_users_callback, pattern=r"^au:p:"))
