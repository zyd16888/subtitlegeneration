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
from services.subtitle_task_runner import SubtitleTaskRequest, SubtitleTaskRunner
from services.task_status_guard import (
    ensure_task_leaves_processing,
    skip_if_terminal_task,
)
from services.task_lifecycle import mark_task_failed
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
    subtitle_path = None  # finally 安全网用，跟踪是否生成了字幕文件
    context = create_task_execution_context(task_id, SessionLocal, _run_async)
    task_manager = context.task_manager
    result_persister = context.result_persister

    # ── 防止已取消/已完成的任务被重新执行 ────────────────────────────
    # task_acks_late=True 场景下，worker 重启时 broker 会重新投递未确认的消息，
    # 必须在入口处检查数据库状态，避免覆盖 CANCELLED / COMPLETED / FAILED。
    skipped_result = skip_if_terminal_task(task_id, task_manager, _run_async)
    if skipped_result:
        context.close()
        return skipped_result

    try:
        request = SubtitleTaskRequest(
            task_id=task_id,
            media_item_id=media_item_id,
            video_path=video_path,
            library_id=library_id,
            path_mapping_index=path_mapping_index,
            asr_engine=asr_engine,
            asr_model_id=asr_model_id,
            translation_service=translation_service,
            openai_model=openai_model,
            source_language=source_language,
            target_languages=target_languages,
            keep_source_subtitle=keep_source_subtitle,
        )
        runner = SubtitleTaskRunner(request, context, _run_async)
        run_result = runner.run()
        subtitle_path = run_result.subtitle_path

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
