"""
字幕生成 Celery 任务

协调音频提取、ASR、翻译、字幕生成、Emby 回写的完整流程
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import List, Optional
from celery import Task

from .celery_app import celery_app
from services.asr_factory import (
    detect_language,
    get_asr_engine,
    resolve_vad_model_path,
    resolve_model_by_language,
)
from services.subtitle_pipeline import (
    filter_asr_segments,
    generate_subtitle_files,
    prepare_audio,
    process_language_detection,
    transcribe_audio,
    translate_subtitles,
    write_subtitles_to_emby,
)
from services.subtitle_task_startup import start_subtitle_task
from services.task_result_persister import format_step_log
from services.task_status_guard import (
    ensure_task_leaves_processing,
    skip_if_terminal_task,
)
from services.task_lifecycle import (
    cleanup_task_work_dir,
    mark_task_completed,
    mark_task_failed,
)
from services.task_execution_context import create_task_execution_context
from models.base import SessionLocal

logger = logging.getLogger(__name__)


# ── 线程本地的持久 event loop ────────────────────────────────────────
# 多线程 worker 池下，反复 _run_async() 会不停建毁 loop，对 httpx /
# SQLAlchemy 等持久化资源极不友好（偶发卡死、连接池泄漏）。
# 这里给每个 worker 线程绑定一个长期存活的 loop，全程复用。
_thread_local = threading.local()


def _run_async(coro):
    """在当前线程的持久 event loop 上同步执行一个协程。"""
    loop = getattr(_thread_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _thread_local.loop = loop
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class SubtitleGenerationTask(Task):
    """字幕生成任务基类，支持任务状态跟踪"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}")
        logger.error(f"Exception info: {einfo}")


_resolve_vad_model_path = resolve_vad_model_path
_detect_language = detect_language
_resolve_model_by_language = resolve_model_by_language
_get_asr_engine = get_asr_engine


@celery_app.task(
    bind=True,
    base=SubtitleGenerationTask,
    name="backend.tasks.subtitle_tasks.generate_subtitle_task",
    max_retries=3,
    default_retry_delay=60,
)
def generate_subtitle_task(
    self,
    task_id: str,
    media_item_id: str,
    video_path: str,
    asr_engine: str = None,
    asr_model_id: str = None,
    translation_service: str = None,
    openai_model: str = None,
    library_id: str = None,
    path_mapping_index: int = None,
    source_language: str = None,
    target_languages: Optional[List[str]] = None,
    keep_source_subtitle: Optional[bool] = None,
):
    """
    字幕生成主任务

    1. 提取音频 (20%)
    1.8 语言检测（可选）
    2. 语音识别 (60%)
    3. 翻译文本 (90%)
    4. 生成字幕文件 (95%)
    5. 回写 Emby (100%)

    Args:
        asr_model_id: 任务级 ASR 模型覆盖；None 时使用 config.asr_model_id
        target_languages: 任务级多目标语言覆盖；None 时使用 config.target_languages
        keep_source_subtitle: 任务级源语言字幕开关；None 时使用 config.keep_source_subtitle
    """
    audio_path = None
    subtitle_path = None  # finally 安全网用，跟踪是否生成了字幕文件
    context = create_task_execution_context(task_id, SessionLocal, _run_async)
    task_manager = context.task_manager
    config_manager = context.config_manager
    result_persister = context.result_persister

    # ── 防止已取消/已完成的任务被重新执行 ────────────────────────────
    # task_acks_late=True 场景下，worker 重启时 broker 会重新投递未确认的消息，
    # 必须在入口处检查数据库状态，避免覆盖 CANCELLED / COMPLETED / FAILED。
    skipped_result = skip_if_terminal_task(task_id, task_manager, _run_async)
    if skipped_result:
        context.close()
        return skipped_result

    try:
        startup = start_subtitle_task(
            task_id=task_id,
            video_path=video_path,
            config_manager=config_manager,
            task_manager=task_manager,
            result_persister=result_persister,
            session_factory=SessionLocal,
            run_async=_run_async,
            asr_engine=asr_engine,
            asr_model_id=asr_model_id,
            translation_service=translation_service,
            openai_model=openai_model,
            source_language=source_language,
            target_languages=target_languages,
            keep_source_subtitle=keep_source_subtitle,
        )
        config = startup.config
        source_lang = startup.source_lang
        resolved_target_langs = startup.resolved_target_langs
        primary_target_lang = startup.primary_target_lang
        keep_source = startup.keep_source
        translation_source_lang = startup.translation_source_lang
        reporter = startup.reporter
        task_work_dir = startup.task_work_dir

        # 用于收集每个步骤的详细日志
        step_logs = {}
        skipped_steps = []

        audio_result = prepare_audio(
            task_id=task_id,
            video_path=video_path,
            task_work_dir=task_work_dir,
            config=config,
            reporter=reporter,
            step_logs=step_logs,
            run_async=_run_async,
            persist_step_logs=result_persister.persist_step_logs,
            format_step_log=format_step_log,
        )
        audio_path = audio_result.audio_path
        step_logs = audio_result.step_logs

        language_result = process_language_detection(
            task_id=task_id,
            config=config,
            audio_path=audio_path,
            source_lang=source_lang,
            translation_source_lang=translation_source_lang,
            reporter=reporter,
            step_logs=step_logs,
            persist_step_logs=result_persister.persist_step_logs,
            format_step_log=format_step_log,
        )
        source_lang = language_result.source_lang
        translation_source_lang = language_result.translation_source_lang
        step_logs = language_result.step_logs

        asr_result = transcribe_audio(
            task_id=task_id,
            config=config,
            audio_path=audio_path,
            task_work_dir=task_work_dir,
            source_lang=source_lang,
            reporter=reporter,
            step_logs=step_logs,
            run_async=_run_async,
            persist_asr_result=result_persister.persist_asr_result,
            format_step_log=format_step_log,
        )
        segments = asr_result.segments
        step_logs = asr_result.step_logs

        filter_result = filter_asr_segments(
            task_id=task_id,
            config=config,
            segments=segments,
            source_lang=source_lang,
            step_logs=step_logs,
            persist_asr_result=result_persister.persist_asr_result,
            format_step_log=format_step_log,
        )
        segments = filter_result.segments
        step_logs = filter_result.step_logs

        # 3. 翻译文本（支持多目标语言）
        translation_result = translate_subtitles(
            task_id=task_id,
            config=config,
            segments=segments,
            source_lang=source_lang,
            translation_source_lang=translation_source_lang,
            resolved_target_langs=resolved_target_langs,
            keep_source=keep_source,
            reporter=reporter,
            step_logs=step_logs,
            skipped_steps=skipped_steps,
            run_async=_run_async,
            format_step_log=format_step_log,
        )
        per_lang_segments = translation_result.per_lang_segments
        emit_langs = translation_result.emit_langs
        step_logs = translation_result.step_logs
        skipped_steps = translation_result.skipped_steps
        result_persister.persist_translation_result(
            step_logs=step_logs,
            skipped_steps=skipped_steps,
            target_languages=resolved_target_langs,
            keep_source_subtitle=keep_source,
        )

        # 4. 生成字幕文件（每种语言一份）
        subtitle_result = generate_subtitle_files(
            task_id=task_id,
            video_path=video_path,
            task_work_dir=task_work_dir,
            per_lang_segments=per_lang_segments,
            emit_langs=emit_langs,
            primary_target_lang=primary_target_lang,
            reporter=reporter,
            step_logs=step_logs,
            format_step_log=format_step_log,
        )
        subtitle_path = subtitle_result.subtitle_path
        subtitle_paths = subtitle_result.subtitle_paths
        step_logs = subtitle_result.step_logs
        result_persister.persist_subtitle_result(
            subtitle_path=subtitle_path,
            subtitle_paths=subtitle_paths,
            step_logs=step_logs,
        )

        # 5. 复制字幕到视频目录 + 刷新 Emby
        emby_result = write_subtitles_to_emby(
            task_id=task_id,
            config=config,
            media_item_id=media_item_id,
            subtitle_paths=subtitle_paths,
            path_mapping_index=path_mapping_index,
            library_id=library_id,
            reporter=reporter,
            step_logs=step_logs,
            skipped_steps=skipped_steps,
            run_async=_run_async,
            format_step_log=format_step_log,
        )
        step_logs = emby_result.step_logs
        skipped_steps = emby_result.skipped_steps
        result_persister.persist_emby_result(
            step_logs=step_logs,
            skipped_steps=skipped_steps,
        )
        mark_task_completed(
            task_id=task_id,
            task_manager=task_manager,
            result_persister=result_persister,
            run_async=_run_async,
        )

        # 按配置决定是否清理临时文件
        cleanup_task_work_dir(
            task_id=task_id,
            task_work_dir=task_work_dir,
            cleanup_enabled=config.cleanup_temp_files_on_success,
        )

        return {"task_id": task_id, "status": "completed", "subtitle_path": subtitle_path}

    except Exception as e:
        mark_task_failed(
            task_id=task_id,
            exc=e,
            task_manager=task_manager,
            result_persister=result_persister,
            run_async=_run_async,
        )
        raise

    finally:
        # ── 安全网：保证任务一定离开 PROCESSING 状态 ─────────────────
        # 重新读取一次 DB（用独立 session 避免被前面的异常污染），
        # 如果发现状态仍是 PROCESSING/PENDING，根据 subtitle_path 是否
        # 已生成强制改成 COMPLETED 或 FAILED。这一层兜底独立于上面所有
        # 逻辑，无论 asyncio loop / SQLite 锁 / 第三方库出什么状况，
        # 任务都不会再卡在 95%。
        ensure_task_leaves_processing(task_id, subtitle_path, SessionLocal)

        context.close()
