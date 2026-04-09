"""
任务管理处理（创建、查看、取消、重试）
"""
import logging

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
from services.emby_connector import EmbyConnector
from services.task_manager import TaskManager
from tasks.subtitle_tasks import generate_subtitle_task
from tgbot.keyboards import task_detail_keyboard
from tgbot.middleware import require_auth
from tgbot.services.user_service import (
    check_user_quota,
    get_or_create_user,
    increment_daily_task_count,
)
from tgbot.utils import (
    format_duration,
    format_progress,
    format_task_status,
    format_time_ago,
    short_id,
)

logger = logging.getLogger(__name__)


async def _create_subtitle_task(
    user_telegram_id: int, media_item_id: str, context: ContextTypes.DEFAULT_TYPE
) -> tuple[bool, str]:
    """创建字幕生成任务，返回 (成功, 消息)"""
    db = SessionLocal()
    try:
        # 获取用户
        from tgbot.services.user_service import get_user_by_telegram_id
        user = get_user_by_telegram_id(db, user_telegram_id)
        if not user:
            return False, "用户未找到"

        # 获取配置
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        # 配额检查
        quota_msg = check_user_quota(
            db, user,
            config.telegram_daily_task_limit,
            config.telegram_max_concurrent_per_user,
        )
        if quota_msg:
            return False, f"❌ {quota_msg}"

        # 系统全局并发检查
        active_count = db.query(Task).filter(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])
        ).count()
        if active_count >= config.max_concurrent_tasks:
            return False, "❌ 系统繁忙，请稍后重试"

        # 获取媒体信息
        if not config.emby_url or not config.emby_api_key:
            return False, "❌ Emby 服务未配置"

        accessible_ids = config.telegram_accessible_libraries or None
        async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
            media_item = await emby.get_media_item(media_item_id)
            if not await emby.is_item_accessible(media_item, accessible_ids):
                logger.warning(
                    f"TG 任务创建访问控制拒绝: user={user_telegram_id} item_id={media_item_id}"
                )
                return False, "❌ 无权访问该内容"
            audio_url = await emby.get_audio_stream_url(media_item_id)

        # 创建任务
        task_manager = TaskManager(db)
        task = await task_manager.create_task(
            media_item_id=media_item_id,
            media_item_title=media_item.name,
            video_path=audio_url,
            asr_engine=config.asr_engine,
            asr_model_id=getattr(config, "asr_model_id", None),
            translation_service=config.translation_service,
            source_language=config.source_language,
            target_language=config.target_language,
            telegram_user_id=user.telegram_id,
            telegram_username=user.telegram_username,
            telegram_display_name=user.telegram_display_name,
            emby_username=user.emby_username,
        )

        # 记录来源 + 多语言信息（保留用于兼容性和重试恢复）
        effective_target_languages = (
            list(config.target_languages) if config.target_languages else [config.target_language]
        )
        task.extra_info = {
            "telegram_user_id": user_telegram_id,
            "target_languages": effective_target_languages,
            "keep_source_subtitle": bool(config.keep_source_subtitle),
        }
        db.commit()

        # 提交 Celery 任务（TG 任务统一走全局配置）
        generate_subtitle_task.delay(
            task_id=task.id,
            media_item_id=media_item_id,
            video_path=audio_url,
            asr_engine=config.asr_engine,
            translation_service=config.translation_service,
            source_language=config.source_language,
            target_languages=None,  # 使用全局配置
            keep_source_subtitle=None,  # 使用全局配置
        )

        # 增加配额计数
        increment_daily_task_count(db, user)

        return True, (
            f"✅ 任务已创建\n\n"
            f"📺 {media_item.name}\n"
            f"🆔 {short_id(task.id)}\n"
            f"状态: {format_task_status(task.status.value)}"
        )

    except Exception as e:
        logger.error(f"创建任务异常: {e}")
        return False, f"❌ 创建任务失败: {str(e)}"
    finally:
        db.close()


async def task_create_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理 "生成字幕" 按钮回调"""
    query = update.callback_query
    # 立即 toast 反馈，避免用户感觉无响应
    await query.answer(text="⏳ 正在创建任务…")

    media_item_id = query.data[4:]  # t:c:{media_item_id}

    # 立即移除按钮，防止重复点击产生重复任务（对 photo 和 text 消息都合法）
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"移除按钮失败: {e}")

    success, msg = await _create_subtitle_task(
        update.effective_user.id, media_item_id, context
    )

    # 以新消息回复结果，兼容原消息为 photo 的情况
    # （Telegram 不允许把 photo 消息 edit 成 text 消息）
    await query.message.reply_text(msg)


@require_auth
async def tasks_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """查看我的任务列表"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)

        # 查询该用户的任务
        tasks = db.query(Task).filter(
            Task.extra_info.contains(f'"telegram_user_id": {user.telegram_id}'),
        ).order_by(Task.created_at.desc()).limit(10).all()

        if not tasks:
            await update.message.reply_text("你还没有任务记录")
            return

        # 获取配额信息
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        from tgbot.services.user_service import get_daily_task_count
        daily_count = get_daily_task_count(db, user)
        daily_limit = (
            user.daily_task_limit
            if user.daily_task_limit is not None
            else config.telegram_daily_task_limit
        )

        lines = ["📋 我的任务\n"]
        for i, task in enumerate(tasks, 1):
            status = format_task_status(
                task.status.value if isinstance(task.status, TaskStatus) else task.status
            )
            title = task.media_item_title or "未知"
            if len(title) > 25:
                title = title[:24] + "…"

            extra = ""
            if task.status == TaskStatus.PROCESSING:
                extra = f" {format_progress(task.progress)}"
            elif task.status == TaskStatus.COMPLETED:
                extra = f" {format_time_ago(task.completed_at)}"
            elif task.status == TaskStatus.FAILED:
                stage = task.error_stage or ""
                extra = f" ({stage})" if stage else ""

            lines.append(f"{i}. {status} {title}{extra}")

        lines.append(f"\n今日配额: {daily_count}/{daily_limit}")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"查看任务列表异常: {e}")
        await update.message.reply_text("❌ 获取任务列表失败")
    finally:
        db.close()


@require_auth
async def cancel_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """取消任务"""
    if not context.args:
        await update.message.reply_text("用法: /cancel 任务ID短码")
        return

    task_short_id = context.args[0]

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)

        # 查找匹配的任务
        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
            Task.extra_info.contains(f'"telegram_user_id": {user.telegram_id}'),
        ).first()

        if not task:
            await update.message.reply_text("❌ 未找到任务，请检查 ID")
            return

        if task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            await update.message.reply_text(
                f"❌ 任务状态为 {format_task_status(task.status.value)}，无法取消"
            )
            return

        task_manager = TaskManager(db)
        result = await task_manager.cancel_task(task.id)
        if result:
            await update.message.reply_text(
                f"✅ 已取消任务: {task.media_item_title or short_id(task.id)}"
            )
        else:
            await update.message.reply_text("❌ 取消失败")

    except Exception as e:
        logger.error(f"取消任务异常: {e}")
        await update.message.reply_text("❌ 操作失败")
    finally:
        db.close()


@require_auth
async def retry_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """重试失败任务"""
    if not context.args:
        await update.message.reply_text("用法: /retry 任务ID短码")
        return

    task_short_id = context.args[0]

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)

        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
            Task.extra_info.contains(f'"telegram_user_id": {user.telegram_id}'),
        ).first()

        if not task:
            await update.message.reply_text("❌ 未找到任务")
            return

        if task.status != TaskStatus.FAILED:
            await update.message.reply_text("❌ 只能重试失败的任务")
            return

        # 配额检查
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        quota_msg = check_user_quota(
            db, user,
            config.telegram_daily_task_limit,
            config.telegram_max_concurrent_per_user,
        )
        if quota_msg:
            await update.message.reply_text(f"❌ {quota_msg}")
            return

        # 创建新任务
        task_manager = TaskManager(db)
        new_task = await task_manager.retry_task(task.id)
        if new_task:
            new_task.extra_info = {"telegram_user_id": user.telegram_id}
            db.commit()
            increment_daily_task_count(db, user)
            await update.message.reply_text(
                f"🔄 重试任务已创建\n"
                f"📺 {new_task.media_item_title}\n"
                f"🆔 {short_id(new_task.id)}"
            )
        else:
            await update.message.reply_text("❌ 重试失败")

    except Exception as e:
        logger.error(f"重试任务异常: {e}")
        await update.message.reply_text("❌ 操作失败")
    finally:
        db.close()


async def task_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理任务相关的回调（取消、重试）"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("t:x:"):
        # 取消任务
        task_short_id = data[4:]
        db = SessionLocal()
        try:
            task = db.query(Task).filter(
                Task.id.like(f"{task_short_id}%"),
            ).first()
            if task and task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                task_manager = TaskManager(db)
                await task_manager.cancel_task(task.id)
                await query.edit_message_text(
                    f"✅ 已取消: {task.media_item_title or short_id(task.id)}"
                )
            else:
                await query.edit_message_text("❌ 无法取消此任务")
        finally:
            db.close()

    elif data.startswith("t:r:"):
        # 重试任务 - 简化处理，发送提示
        task_short_id = data[4:]
        await query.edit_message_text(
            f"请使用命令: /retry {task_short_id}"
        )


@require_auth
async def settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """通知设置"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        from tgbot.keyboards import notification_settings_keyboard

        await update.message.reply_text(
            "⚙️ 通知设置\n\n"
            "点击切换通知开关：",
            reply_markup=notification_settings_keyboard(
                user.notify_on_complete, user.notify_on_failure
            ),
        )
    finally:
        db.close()


async def settings_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理通知设置回调"""
    query = update.callback_query
    await query.answer()

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)

        if query.data == "s:nc":
            user.notify_on_complete = not user.notify_on_complete
        elif query.data == "s:nf":
            user.notify_on_failure = not user.notify_on_failure

        db.commit()

        from tgbot.keyboards import notification_settings_keyboard

        await query.edit_message_reply_markup(
            reply_markup=notification_settings_keyboard(
                user.notify_on_complete, user.notify_on_failure
            ),
        )
    finally:
        db.close()


def register(app: Application) -> None:
    """注册任务相关 handlers"""
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(task_create_callback, pattern=r"^t:c:"))
    app.add_handler(CallbackQueryHandler(task_callback, pattern=r"^t:[xr]:"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^s:n[cf]$"))
