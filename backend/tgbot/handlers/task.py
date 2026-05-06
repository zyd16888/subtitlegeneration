"""
任务管理处理（创建、查看、取消、重试）
"""
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
from services.emby_connector import EmbyConnector
from services.task_manager import TaskManager
from tasks.subtitle_tasks import generate_subtitle_task
from tgbot.middleware import require_auth
from tgbot.services.user_service import (
    check_user_quota,
    get_or_create_user,
    increment_daily_task_count,
)
from tgbot.utils import format_task_status, short_id

logger = logging.getLogger(__name__)


async def _create_subtitle_task(
    user_telegram_id: int,
    media_item_id: str,
    context: ContextTypes.DEFAULT_TYPE,
    source_language_override: Optional[str] = None,
) -> tuple[bool, str]:
    """创建字幕生成任务，返回 (成功, 消息)。

    source_language_override: 用户在提交时显式选择的源语言；None 时跟随全局配置。
    """
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

        effective_source_language = source_language_override or config.source_language

        # 创建任务
        task_manager = TaskManager(db)
        task = await task_manager.create_task(
            media_item_id=media_item_id,
            media_item_title=media_item.name,
            video_path=audio_url,
            asr_engine=config.asr_engine,
            asr_model_id=getattr(config, "asr_model_id", None),
            translation_service=config.translation_service,
            source_language=effective_source_language,
            target_language=config.target_language,
            telegram_user_id=user.telegram_id,
            telegram_username=user.telegram_username,
            telegram_display_name=user.telegram_display_name,
            emby_username=user.emby_username,
        )

        # 用户偏好覆盖全局：/config 设置过的字段优先生效
        from tgbot.handlers.config import _resolve_effective
        effective_target_languages, effective_keep_source = _resolve_effective(user, config)
        # 防止源语言出现在目标语言里（例如 /config 选了 ja 作目标，又显式选 ja 作源）
        if effective_source_language:
            effective_target_languages = [
                code for code in effective_target_languages
                if code != effective_source_language
            ] or effective_target_languages

        task.extra_info = {
            "target_languages": effective_target_languages,
            "keep_source_subtitle": bool(effective_keep_source),
        }
        if source_language_override:
            task.extra_info["source_language_override"] = source_language_override
        db.commit()

        # 提交 Celery 任务：把生效后的偏好显式传给 worker（避免 worker 端只读全局配置）
        generate_subtitle_task.apply_async(
            kwargs=dict(
                task_id=task.id,
                media_item_id=media_item_id,
                video_path=audio_url,
                asr_engine=config.asr_engine,
                asr_model_id=getattr(config, "asr_model_id", None),
                translation_service=config.translation_service,
                source_language=effective_source_language,
                target_languages=effective_target_languages,
                keep_source_subtitle=bool(effective_keep_source),
            ),
            task_id=task.id,
        )

        # 增加配额计数
        increment_daily_task_count(db, user)

        lang_hint = (
            f"\n源语言: {source_language_override}（手动选择）"
            if source_language_override else ""
        )
        return True, (
            f"✅ 任务已创建\n\n"
            f"📺 {media_item.name}\n"
            f"🆔 {short_id(task.id)}\n"
            f"状态: {format_task_status(task.status.value)}"
            f"{lang_hint}"
        )

    except Exception as e:
        logger.error(f"创建任务异常: {e}")
        return False, f"❌ 创建任务失败: {str(e)}"
    finally:
        db.close()


async def task_create_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """处理 "生成字幕" 按钮回调（默认全局源语言）"""
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


async def task_create_lang_pick_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """t:cl:{media_id} — 弹出源语言选择键盘。"""
    from tgbot.keyboards import source_language_picker_keyboard

    query = update.callback_query
    media_item_id = query.data[5:]  # t:cl:{media_id}

    db = SessionLocal()
    try:
        config = await ConfigManager(db).get_config()
        current_lang = config.source_language
    finally:
        db.close()

    await query.answer()
    try:
        await query.edit_message_reply_markup(
            reply_markup=source_language_picker_keyboard(
                "create", media_item_id, current_lang=current_lang,
            ),
        )
    except Exception as e:
        logger.warning(f"显示源语言选择键盘失败: {e}")


async def task_create_with_lang_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """t:cs:{media_id}:{lang} — 用指定源语言创建任务。"""
    from tgbot.keyboards import SOURCE_LANGUAGE_CODES

    query = update.callback_query
    rest = query.data[5:]  # t:cs:{media_id}:{lang}
    if ":" not in rest:
        await query.answer("❌ 参数错误", show_alert=True)
        return

    media_item_id, lang = rest.rsplit(":", 1)
    if lang not in SOURCE_LANGUAGE_CODES:
        await query.answer("❌ 不支持的源语言", show_alert=True)
        return

    await query.answer(text=f"⏳ 用 {lang} 创建任务…")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"移除按钮失败: {e}")

    success, msg = await _create_subtitle_task(
        update.effective_user.id, media_item_id, context,
        source_language_override=lang,
    )
    await query.message.reply_text(msg)


async def _query_user_tasks(
    db, telegram_id: int, filter_kind: str, page: int,
) -> tuple[list[Task], int]:
    """按过滤档位和页码查询用户任务，返回 (tasks, total)。"""
    from tgbot.views.task_view import filter_to_statuses, PAGE_SIZE

    base = db.query(Task).filter(Task.telegram_user_id == telegram_id)
    statuses = filter_to_statuses(filter_kind)
    if statuses is not None:
        base = base.filter(Task.status.in_(statuses))

    total = base.count()
    tasks = (
        base.order_by(Task.created_at.desc())
        .limit(PAGE_SIZE)
        .offset(page * PAGE_SIZE)
        .all()
    )
    return tasks, total


async def _get_user_quota(db, user) -> tuple[int, int]:
    """返回 (daily_count, daily_limit)。"""
    from tgbot.services.user_service import get_daily_task_count

    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    daily_count = get_daily_task_count(db, user)
    daily_limit = (
        user.daily_task_limit
        if user.daily_task_limit is not None
        else config.telegram_daily_task_limit
    )
    return daily_count, daily_limit


@require_auth
async def tasks_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """查看我的任务列表（交互式分页 + 状态过滤）"""
    from tgbot.views.task_view import FILTER_ALL, render_task_list

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        tasks, total = await _query_user_tasks(db, user.telegram_id, FILTER_ALL, 0)
        daily_count, daily_limit = await _get_user_quota(db, user)

        text, keyboard = render_task_list(
            tasks, total, FILTER_ALL, 0, daily_count, daily_limit,
        )
        await update.message.reply_text(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"查看任务列表异常: {e}")
        await update.message.reply_text("❌ 获取任务列表失败")
    finally:
        db.close()


@require_auth
async def task_info_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """查看任务详情：/task_info 短码"""
    from tgbot.views.task_view import render_task_detail

    if not context.args:
        await update.message.reply_text("用法: /task_info 任务ID短码")
        return

    task_short_id = context.args[0]
    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
            Task.telegram_user_id == user.telegram_id,
        ).first()

        if not task:
            await update.message.reply_text("❌ 未找到任务，请检查 ID")
            return

        text, keyboard = render_task_detail(task)
        await update.message.reply_text(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"查看任务详情异常: {e}")
        await update.message.reply_text("❌ 获取任务详情失败")
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
            Task.telegram_user_id == user.telegram_id,
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
            from tgbot.services import audit as audit_service
            audit_service.record(
                db, update.effective_user.id, "cancel", target_id=task.id,
            )
            db.commit()
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
            Task.telegram_user_id == user.telegram_id,
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

        # 保留原任务 extra_info 中的多语言/字幕快照，重试时透传给 worker
        original_extra = dict(task.extra_info) if task.extra_info else {}
        snapshot_target_languages = original_extra.get("target_languages")
        snapshot_keep_source = original_extra.get("keep_source_subtitle")

        # 创建新任务（task_manager.retry_task 已复制基础字段和 telegram_user_id）
        task_manager = TaskManager(db)
        new_task = await task_manager.retry_task(task.id)
        if new_task:
            # 完整复制原 extra_info（清掉一次性的通知/重试状态字段）
            carry_over = {
                k: v for k, v in original_extra.items()
                if k not in ("telegram_notified", "notification_failed_count", "current_stage")
            }
            new_task.extra_info = carry_over
            from tgbot.services import audit as audit_service
            audit_service.record(
                db, update.effective_user.id, "retry",
                target_id=new_task.id,
                payload={"original_task_id": task.id},
            )
            db.commit()
            increment_daily_task_count(db, user)

            # 提交 Celery，传入快照避免取到变化后的全局配置
            generate_subtitle_task.apply_async(
                kwargs=dict(
                    task_id=new_task.id,
                    media_item_id=new_task.media_item_id,
                    video_path=new_task.video_path,
                    asr_engine=new_task.asr_engine,
                    asr_model_id=new_task.asr_model_id,
                    translation_service=new_task.translation_service,
                    source_language=new_task.source_language,
                    target_languages=snapshot_target_languages,
                    keep_source_subtitle=snapshot_keep_source,
                ),
                task_id=new_task.id,
            )

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


def _is_task_owner_or_admin(task: Task, tg_user_id: int, admin_ids: list[int]) -> bool:
    """判断当前 TG 用户是否有权操作该任务"""
    if task.telegram_user_id is not None and int(task.telegram_user_id) == int(tg_user_id):
        return True
    if int(tg_user_id) in admin_ids:
        return True
    return False


async def _safe_edit_text(query, text, reply_markup=None) -> None:
    """安全修改消息文本：photo 消息不能 edit_message_text，回退到删除+发新消息。"""
    try:
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.get_bot().send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning("_safe_edit_text 回退 send_message: %s", e)
        try:
            await query.get_bot().send_message(
                chat_id=query.message.chat_id, text=text, reply_markup=reply_markup,
            )
        except Exception:
            pass


async def _op_cancel(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    task_short_id: str,
) -> None:
    """取消任务的统一 helper（供新旧 callback 共用）。"""
    tg_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    db = SessionLocal()
    try:
        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
        ).first()

        if not task:
            await query.answer("❌ 任务不存在", show_alert=True)
            return

        if not _is_task_owner_or_admin(task, tg_user_id, admin_ids):
            logger.warning(
                "TG 取消任务越权: tg_user=%s task=%s owner=%s",
                tg_user_id, task.id, task.telegram_user_id,
            )
            await query.answer("❌ 无权操作此任务", show_alert=True)
            return

        await query.answer()
        if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            task_manager = TaskManager(db)
            await task_manager.cancel_task(task.id)
            from tgbot.services import audit as audit_service
            audit_service.record(
                db, tg_user_id, "cancel", target_id=task.id,
            )
            db.commit()
            await _safe_edit_text(
                query,
                f"✅ 已取消: {task.media_item_title or short_id(task.id)}",
            )
        else:
            await _safe_edit_text(query, "❌ 无法取消此任务")
    finally:
        db.close()


async def _op_retry(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    update: Update,
    task_short_id: str,
    source_language_override: Optional[str] = None,
) -> None:
    """重试任务的统一 helper。

    source_language_override: 用户在重试时显式选择的源语言；None 时沿用原任务的 source_language。
    """
    tg_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    db = SessionLocal()
    try:
        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
        ).first()

        if not task:
            await query.answer("❌ 任务不存在", show_alert=True)
            return

        if not _is_task_owner_or_admin(task, tg_user_id, admin_ids):
            logger.warning(
                "TG 重试任务越权: tg_user=%s task=%s owner=%s",
                tg_user_id, task.id, task.telegram_user_id,
            )
            await query.answer("❌ 无权操作此任务", show_alert=True)
            return

        if task.status != TaskStatus.FAILED:
            await query.answer("❌ 只能重试失败的任务", show_alert=True)
            return

        await query.answer(text="⏳ 正在创建重试任务…")

        user = get_or_create_user(db, update.effective_user)

        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        quota_msg = check_user_quota(
            db, user,
            config.telegram_daily_task_limit,
            config.telegram_max_concurrent_per_user,
        )
        if quota_msg:
            await _safe_edit_text(query, f"❌ {quota_msg}")
            return

        original_extra = dict(task.extra_info) if task.extra_info else {}
        snapshot_target_languages = original_extra.get("target_languages")
        snapshot_keep_source = original_extra.get("keep_source_subtitle")

        task_manager = TaskManager(db)
        new_task = await task_manager.retry_task(task.id)
        if not new_task:
            await _safe_edit_text(query, "❌ 重试失败")
            return

        # 显式覆盖源语言（优先于复制自原任务的 new_task.source_language）
        if source_language_override:
            new_task.source_language = source_language_override
            # 防止源语言出现在目标语言里
            if snapshot_target_languages:
                filtered = [
                    code for code in snapshot_target_languages
                    if code != source_language_override
                ]
                if filtered:
                    snapshot_target_languages = filtered

        carry_over = {
            k: v for k, v in original_extra.items()
            if k not in ("telegram_notified", "notification_failed_count", "current_stage")
        }
        if source_language_override:
            carry_over["source_language_override"] = source_language_override
            carry_over["target_languages"] = snapshot_target_languages
        new_task.extra_info = carry_over
        from tgbot.services import audit as audit_service
        audit_service.record(
            db, tg_user_id, "retry",
            target_id=new_task.id,
            payload={
                "original_task_id": task.id,
                "source_language_override": source_language_override,
            },
        )
        db.commit()
        increment_daily_task_count(db, user)

        generate_subtitle_task.apply_async(
            kwargs=dict(
                task_id=new_task.id,
                media_item_id=new_task.media_item_id,
                video_path=new_task.video_path,
                asr_engine=new_task.asr_engine,
                asr_model_id=new_task.asr_model_id,
                translation_service=new_task.translation_service,
                source_language=new_task.source_language,
                target_languages=snapshot_target_languages,
                keep_source_subtitle=snapshot_keep_source,
            ),
            task_id=new_task.id,
        )

        lang_hint = (
            f"\n源语言: {source_language_override}（手动选择）"
            if source_language_override else ""
        )
        await _safe_edit_text(
            query,
            f"🔄 重试任务已创建\n"
            f"📺 {new_task.media_item_title}\n"
            f"🆔 {short_id(new_task.id)}"
            f"{lang_hint}",
        )
    except Exception as e:
        logger.error("TG 重试任务异常: %s", e)
        try:
            await _safe_edit_text(query, "❌ 重试失败")
        except Exception:
            pass
    finally:
        db.close()


async def _op_retry_lang_pick(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    task_short_id: str,
) -> None:
    """to:rl:{sid} — 显示重试时的源语言选择键盘。"""
    from tgbot.keyboards import source_language_picker_keyboard

    tg_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    db = SessionLocal()
    try:
        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
        ).first()

        if not task:
            await query.answer("❌ 任务不存在", show_alert=True)
            return

        if not _is_task_owner_or_admin(task, tg_user_id, admin_ids):
            await query.answer("❌ 无权操作此任务", show_alert=True)
            return

        if task.status != TaskStatus.FAILED:
            await query.answer("❌ 只能重试失败的任务", show_alert=True)
            return

        await query.answer()
        try:
            await query.edit_message_reply_markup(
                reply_markup=source_language_picker_keyboard(
                    "retry", short_id(task.id), current_lang=task.source_language,
                ),
            )
        except Exception as e:
            logger.warning(f"显示重试源语言键盘失败: {e}")
    finally:
        db.close()


async def _op_download(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    task_short_id: str,
    lang: Optional[str] = None,
) -> None:
    """下载字幕文件的统一 helper。"""
    import os

    tg_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    db = SessionLocal()
    try:
        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
        ).first()

        if not task:
            await query.answer("❌ 任务不存在", show_alert=True)
            return

        if not _is_task_owner_or_admin(task, tg_user_id, admin_ids):
            logger.warning(
                "TG 下载字幕越权: tg_user=%s task=%s owner=%s",
                tg_user_id, task.id, task.telegram_user_id,
            )
            await query.answer("❌ 无权操作此任务", show_alert=True)
            return

        if task.status != TaskStatus.COMPLETED:
            await query.answer("❌ 任务尚未完成", show_alert=True)
            return

        # 选择字幕文件路径
        target_path: Optional[str] = None
        target_lang_label = lang or (task.target_language or "")
        if lang:
            for sub in (task.extra_info or {}).get("subtitles") or []:
                if isinstance(sub, dict) and sub.get("lang") == lang:
                    target_path = sub.get("path")
                    break
        else:
            target_path = task.subtitle_path
            if not target_path:
                # 单一下载按钮但只有多语言列表时取第一个
                subs = (task.extra_info or {}).get("subtitles") or []
                if subs and isinstance(subs[0], dict):
                    target_path = subs[0].get("path")
                    target_lang_label = subs[0].get("lang", target_lang_label)

        if not target_path or not os.path.exists(target_path):
            await query.answer("❌ 字幕文件不存在或已被清理", show_alert=True)
            return

        await query.answer(text="📤 正在发送字幕…")

        # 文件名：使用源文件名 + 语言后缀
        try:
            base_name = os.path.basename(target_path)
        except Exception:
            base_name = f"{short_id(task.id)}.srt"

        try:
            with open(target_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=f,
                    filename=base_name,
                    caption=f"📺 {task.media_item_title or '字幕'}"
                            + (f" · {target_lang_label}" if target_lang_label else ""),
                )
        except Exception as e:
            logger.error("发送字幕文件失败: %s", e)
            try:
                await query.message.reply_text(f"❌ 发送字幕失败: {e}")
            except Exception:
                pass
    finally:
        db.close()


async def task_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """旧 callback（t:x:、t:r:）兼容入口，统一走 helper。"""
    query = update.callback_query
    data = query.data
    if data.startswith("t:x:"):
        await _op_cancel(query, context, data[4:])
    elif data.startswith("t:r:"):
        await _op_retry(query, context, update, data[4:])


async def task_action_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """新命名空间 to:* 任务操作回调。"""
    from tgbot.views.task_view import (
        FILTER_ALL,
        render_task_list,
    )

    query = update.callback_query
    data = query.data

    if data.startswith("to:x:"):
        await _op_cancel(query, context, data[5:])
        return

    if data.startswith("to:rl:"):
        await _op_retry_lang_pick(query, context, data[6:])
        return

    if data.startswith("to:rs:"):
        from tgbot.keyboards import SOURCE_LANGUAGE_CODES
        rest = data[6:]
        if ":" not in rest:
            await query.answer("❌ 参数错误", show_alert=True)
            return
        sid, lang = rest.rsplit(":", 1)
        if lang not in SOURCE_LANGUAGE_CODES:
            await query.answer("❌ 不支持的源语言", show_alert=True)
            return
        await _op_retry(query, context, update, sid, source_language_override=lang)
        return

    if data.startswith("to:r:"):
        await _op_retry(query, context, update, data[5:])
        return

    if data.startswith("to:dl:"):
        rest = data[6:]
        # 形如 {short_id} 或 {short_id}:{lang}
        if ":" in rest:
            short, lang = rest.split(":", 1)
        else:
            short, lang = rest, None
        await _op_download(query, context, short, lang)
        return

    if data.startswith("to:back:"):
        rest = data[8:]
        # 形如 {filter}:{page}
        try:
            filter_kind, page_str = rest.split(":", 1)
            page = int(page_str)
        except (ValueError, IndexError):
            filter_kind, page = FILTER_ALL, 0

        await query.answer()
        db = SessionLocal()
        try:
            user = get_or_create_user(db, update.effective_user)
            tasks, total = await _query_user_tasks(db, user.telegram_id, filter_kind, page)
            daily_count, daily_limit = await _get_user_quota(db, user)
            text, keyboard = render_task_list(
                tasks, total, filter_kind, page, daily_count, daily_limit,
            )
            await _safe_edit_text(query, text, reply_markup=keyboard)
        finally:
            db.close()
        return


async def task_list_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """tl:{filter}:{page} 列表分页/过滤切换。"""
    from tgbot.views.task_view import FILTER_ALL, render_task_list

    query = update.callback_query
    data = query.data
    rest = data[3:]
    try:
        filter_kind, page_str = rest.split(":", 1)
        page = int(page_str)
    except (ValueError, IndexError):
        filter_kind, page = FILTER_ALL, 0

    await query.answer()
    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        tasks, total = await _query_user_tasks(db, user.telegram_id, filter_kind, page)
        daily_count, daily_limit = await _get_user_quota(db, user)
        text, keyboard = render_task_list(
            tasks, total, filter_kind, page, daily_count, daily_limit,
        )
        await _safe_edit_text(query, text, reply_markup=keyboard)
    finally:
        db.close()


async def task_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """td:{short_id} 进入任务详情。"""
    from tgbot.views.task_view import render_task_detail

    query = update.callback_query
    task_short_id = query.data[3:]

    db = SessionLocal()
    try:
        user = get_or_create_user(db, update.effective_user)
        admin_ids = context.bot_data.get("admin_ids", [])

        task = db.query(Task).filter(
            Task.id.like(f"{task_short_id}%"),
        ).first()

        if not task:
            await query.answer("❌ 任务不存在", show_alert=True)
            return

        if not _is_task_owner_or_admin(task, user.telegram_id, admin_ids):
            await query.answer("❌ 无权查看此任务", show_alert=True)
            return

        await query.answer()
        text, keyboard = render_task_detail(task)
        await _safe_edit_text(query, text, reply_markup=keyboard)
    finally:
        db.close()


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
    app.add_handler(CommandHandler("task_info", task_info_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CommandHandler("settings", settings_command))

    # 创建任务（媒体详情按钮 + 内联确认）
    app.add_handler(CallbackQueryHandler(task_create_callback, pattern=r"^t:c:"))
    # 创建任务时选源语言
    app.add_handler(CallbackQueryHandler(task_create_lang_pick_callback, pattern=r"^t:cl:"))
    app.add_handler(CallbackQueryHandler(task_create_with_lang_callback, pattern=r"^t:cs:"))

    # 旧命名空间兼容（历史按钮）
    app.add_handler(CallbackQueryHandler(task_callback, pattern=r"^t:[xr]:"))

    # 新命名空间：任务列表 / 详情 / 操作
    app.add_handler(CallbackQueryHandler(task_list_callback, pattern=r"^tl:"))
    app.add_handler(CallbackQueryHandler(task_detail_callback, pattern=r"^td:"))
    app.add_handler(CallbackQueryHandler(task_action_callback, pattern=r"^to:"))

    app.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^s:n[cf]$"))
