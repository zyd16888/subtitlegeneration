"""
字幕生成 Celery 任务

协调音频提取、ASR、翻译、字幕生成、Emby 回写的完整流程
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
from typing import Dict, List, Optional
from celery import Task

from .celery_app import celery_app
from models.task import TaskStatus
from services.emby_connector import EmbyConnector
from services.asr_factory import (
    detect_language,
    get_asr_engine,
    resolve_vad_model_path,
    resolve_model_by_language,
)
from services.path_mapping import apply_path_mapping
from services.subtitle_pipeline import (
    filter_asr_segments,
    prepare_audio,
    prepare_task_runtime,
    process_language_detection,
    transcribe_audio,
    translate_subtitles,
)
from services.subtitle_generator import SubtitleGenerator
from services.task_manager import TaskManager
from services.config_manager import ConfigManager
from services.task_log_capture import TaskLogCapture
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
_apply_path_mapping = apply_path_mapping


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
    db = SessionLocal()
    task_manager = TaskManager(db)
    config_manager = ConfigManager(db)
    audio_path = None
    subtitle_path = None  # finally 安全网用，跟踪是否生成了字幕文件

    # ── 防止已取消/已完成的任务被重新执行 ────────────────────────────
    # task_acks_late=True 场景下，worker 重启时 broker 会重新投递未确认的消息，
    # 必须在入口处检查数据库状态，避免覆盖 CANCELLED / COMPLETED / FAILED。
    try:
        existing = _run_async(task_manager.get_task(task_id))
        if existing and existing.status in (
            TaskStatus.CANCELLED, TaskStatus.COMPLETED, TaskStatus.FAILED,
        ):
            logger.info(
                f"[{task_id}] 任务状态为 {existing.status.value}，跳过执行"
            )
            db.close()
            return {"task_id": task_id, "status": existing.status.value, "skipped": True}
    except Exception as e:
        logger.warning(f"[{task_id}] 入口状态检查失败，继续执行: {e}")

    # 挂载任务日志捕获器，将处理过程中的所有 logging 输出收集起来供前端展示
    log_capture = TaskLogCapture()
    root_logger = logging.getLogger()
    root_logger.addHandler(log_capture)
    if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
        # 确保 INFO 级别能流到 handler；不修改原有 level 行为以外的设置
        log_capture.setLevel(logging.INFO)

    def _persist_logs_extra(extra: dict) -> dict:
        """合并日志快照到 extra_info 更新载荷"""
        merged = dict(extra) if extra else {}
        merged["logs"] = log_capture.snapshot()
        return merged

    def _mark_step_start(stage: str) -> None:
        # 保留占位以兼容下面调用，无副作用
        pass

    def _format_step_log(stage: str, summary: str) -> str:
        return summary

    def _persist_step_logs(step_logs: dict) -> None:
        _run_async(task_manager.update_task_result(
            task_id,
            extra_info=_persist_logs_extra({"step_logs": step_logs}),
        ))

    def _persist_asr_result(segment_count: int, step_logs: dict) -> None:
        _run_async(task_manager.update_task_result(
            task_id,
            segment_count=segment_count,
            extra_info=_persist_logs_extra({"step_logs": step_logs}),
        ))

    try:
        config = _run_async(config_manager.get_config())
        runtime = prepare_task_runtime(
            config,
            task_id=task_id,
            session_factory=SessionLocal,
            asr_engine=asr_engine,
            asr_model_id=asr_model_id,
            translation_service=translation_service,
            openai_model=openai_model,
            source_language=source_language,
            target_languages=target_languages,
            keep_source_subtitle=keep_source_subtitle,
        )
        config = runtime.config
        source_lang = runtime.source_lang
        resolved_target_langs = runtime.resolved_target_langs
        primary_target_lang = runtime.primary_target_lang
        keep_source = runtime.keep_source
        translation_source_lang = runtime.translation_source_lang
        reporter = runtime.reporter

        # 持久化阶段配置到 extra_info，供前端动态渲染处理流程
        _run_async(task_manager.update_task_result(
            task_id,
            extra_info={
                "stage_weights": {k: list(v) for k, v in reporter._stages.items()},
            },
        ))

        _run_async(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 0))
        logger.info(f"开始处理任务 {task_id}: {video_path}")
        logger.info(
            f"[{task_id}] 配置: ASR={config.asr_engine}, model_id={config.asr_model_id}, "
            f"翻译={config.translation_service}, 语言={source_lang}->{resolved_target_langs}"
        )

        # 为每个任务创建独立的工作目录，保留所有中间产物
        task_work_dir = os.path.join(config.temp_dir, "tasks", task_id)
        os.makedirs(task_work_dir, exist_ok=True)
        logger.info(f"[{task_id}] 任务工作目录: {task_work_dir}")

        # 用于收集每个步骤的详细日志
        step_logs = {}
        skipped_steps = []

        _mark_step_start("audio")
        if getattr(config, "enable_denoise", False):
            _mark_step_start("denoise")
        audio_result = prepare_audio(
            task_id=task_id,
            video_path=video_path,
            task_work_dir=task_work_dir,
            config=config,
            reporter=reporter,
            step_logs=step_logs,
            run_async=_run_async,
            persist_step_logs=_persist_step_logs,
            format_step_log=_format_step_log,
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
            persist_step_logs=_persist_step_logs,
            format_step_log=_format_step_log,
        )
        source_lang = language_result.source_lang
        translation_source_lang = language_result.translation_source_lang
        step_logs = language_result.step_logs

        _mark_step_start("asr")
        asr_result = transcribe_audio(
            task_id=task_id,
            config=config,
            audio_path=audio_path,
            task_work_dir=task_work_dir,
            source_lang=source_lang,
            reporter=reporter,
            step_logs=step_logs,
            run_async=_run_async,
            persist_asr_result=_persist_asr_result,
            format_step_log=_format_step_log,
        )
        segments = asr_result.segments
        step_logs = asr_result.step_logs

        filter_result = filter_asr_segments(
            task_id=task_id,
            config=config,
            segments=segments,
            source_lang=source_lang,
            step_logs=step_logs,
            persist_asr_result=_persist_asr_result,
            format_step_log=_format_step_log,
        )
        segments = filter_result.segments
        step_logs = filter_result.step_logs

        # 3. 翻译文本（支持多目标语言）
        _mark_step_start("translation")
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
            format_step_log=_format_step_log,
        )
        per_lang_segments = translation_result.per_lang_segments
        emit_langs = translation_result.emit_langs
        step_logs = translation_result.step_logs
        skipped_steps = translation_result.skipped_steps
        _run_async(task_manager.update_task_result(
            task_id,
            extra_info=_persist_logs_extra({
                "step_logs": step_logs,
                "skipped_steps": skipped_steps,
                "target_languages": list(resolved_target_langs),
                "keep_source_subtitle": keep_source,
            }),
        ))

        # 4. 生成字幕文件（每种语言一份）
        _mark_step_start("subtitle")
        reporter.report("subtitle", 0.0)
        logger.info(f"[{task_id}] 步骤 4/5: 生成字幕文件")
        subtitle_generator = SubtitleGenerator()

        # subtitle_paths: 按语言顺序记录 (lang, path)
        subtitle_paths: Dict[str, str] = {}
        subtitle_info_lines: List[str] = []
        for lang_code in emit_langs:
            segs = per_lang_segments.get(lang_code, [])
            if not segs:
                logger.warning(f"[{task_id}] 语言 {lang_code} 无字幕段，跳过生成")
                continue
            path = subtitle_generator.generate_srt(
                segs, video_path, lang_code, output_dir=task_work_dir
            )
            subtitle_paths[lang_code] = path
            size_kb = os.path.getsize(path) / 1024 if os.path.exists(path) else 0
            logger.info(f"[{task_id}] 字幕文件生成完成: {path}")
            subtitle_info_lines.append(
                f"  - {lang_code}: {path} ({size_kb:.1f} KB, {len(segs)} 段)"
            )

        if not subtitle_paths:
            raise RuntimeError("未能生成任何字幕文件")

        # 主字幕路径：primary_target_lang 对应那一份；不存在时用 emit_langs 第 0 个
        subtitle_path = subtitle_paths.get(primary_target_lang) or subtitle_paths[emit_langs[0]]

        reporter.report("subtitle", 1.0)
        step_logs["subtitle"] = _format_step_log(
            "subtitle",
            "生成字幕文件:\n" + "\n".join(subtitle_info_lines),
        )
        _run_async(task_manager.update_task_result(
            task_id,
            subtitle_path=subtitle_path,
            extra_info=_persist_logs_extra({
                "step_logs": step_logs,
                "subtitles": [
                    {"lang": lc, "path": p}
                    for lc, p in subtitle_paths.items()
                ],
            }),
        ))

        # 5. 复制字幕到视频目录 + 刷新 Emby
        _mark_step_start("emby")
        reporter.report("emby", 0.0)
        logger.info(f"[{task_id}] 步骤 5/6: 复制字幕到视频目录")
        emby_log_lines = []
        emby_copy_skipped = False
        if config.emby_url and config.emby_api_key:

            async def get_video_real_path():
                async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                    return await emby.get_media_file_path(media_item_id)

            # 获取视频在 Emby 服务器上的真实路径
            try:
                emby_video_path = _run_async(get_video_real_path())
                logger.info(f"[{task_id}] Emby 视频真实路径: {emby_video_path}")
                emby_log_lines.append(f"Emby 视频路径: {emby_video_path}")
            except Exception as e:
                logger.warning(f"[{task_id}] 获取视频真实路径失败: {e}，跳过字幕文件复制")
                emby_video_path = None
                emby_log_lines.append(f"获取视频路径失败: {e}")
                emby_copy_skipped = True

            if emby_video_path and config.path_mappings:
                local_video_path = apply_path_mapping(
                    emby_video_path,
                    config.path_mappings,
                    path_mapping_index=path_mapping_index,
                    library_id=library_id,
                )
                if local_video_path:
                    emby_log_lines.append(f"本地映射路径: {local_video_path}")
                    if not os.path.exists(local_video_path):
                        logger.error(
                            f"[{task_id}] 本地视频文件不存在: {local_video_path}，"
                            f"请检查路径映射配置是否正确 (Emby 路径: {emby_video_path})"
                        )
                        emby_log_lines.append(f"本地视频文件不存在，路径映射可能配置错误")
                        raise RuntimeError(
                            f"本地视频文件不存在: {local_video_path}，"
                            f"请检查路径映射配置 (Emby 路径: {emby_video_path})"
                        )
                    # 每种语言复制一份字幕到视频目录
                    video_basename = os.path.splitext(os.path.basename(local_video_path))[0]
                    video_dir = os.path.dirname(local_video_path)

                    for lang_code, src_path in subtitle_paths.items():
                        target_srt = os.path.join(video_dir, f"{video_basename}.{lang_code}.srt")
                        try:
                            shutil.copy2(src_path, target_srt)
                            logger.info(
                                f"[{task_id}] 字幕文件已复制 [{lang_code}]: "
                                f"{src_path} → {target_srt}"
                            )
                            emby_log_lines.append(f"字幕已复制 [{lang_code}]: {target_srt}")
                        except Exception as e:
                            logger.error(
                                f"[{task_id}] 复制字幕文件失败 [{lang_code}]: {e}",
                                exc_info=True,
                            )
                            raise RuntimeError(
                                f"复制字幕文件到视频目录失败 [{lang_code}]: {e}"
                            )
                else:
                    logger.warning(
                        f"[{task_id}] 路径映射未匹配，Emby 路径: {emby_video_path}，"
                        f"已配置 {len(config.path_mappings)} 条映射规则，跳过复制"
                    )
                    emby_log_lines.append(
                        f"路径映射未匹配 (已配置 {len(config.path_mappings)} 条规则)，跳过复制"
                    )
                    emby_copy_skipped = True
            elif emby_video_path and not config.path_mappings:
                logger.warning(f"[{task_id}] 未配置路径映射规则，跳过字幕文件复制到视频目录")
                emby_log_lines.append("未配置路径映射规则，跳过复制")
                emby_copy_skipped = True

            # 6. 刷新 Emby 元数据
            logger.info(f"[{task_id}] 步骤 6/6: 刷新 Emby 元数据")

            async def refresh_emby():
                async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                    return await emby.refresh_metadata(media_item_id)

            success = _run_async(refresh_emby())
            if success:
                logger.info(f"[{task_id}] Emby 元数据刷新成功")
                emby_log_lines.append("Emby 元数据刷新: 成功")
            else:
                logger.warning(f"[{task_id}] Emby 元数据刷新失败，但字幕文件已生成")
                emby_log_lines.append("Emby 元数据刷新: 失败")
        else:
            logger.warning(f"[{task_id}] 未配置 Emby 连接，跳过字幕回写")
            emby_log_lines.append("未配置 Emby 连接，跳过回写")

        step_logs["emby"] = _format_step_log("emby", "\n".join(emby_log_lines))
        # 判断 Emby 回写是否实质性跳过（未配置 Emby / 获取路径失败 / 路径映射未匹配或未配置）
        if not (config.emby_url and config.emby_api_key) or emby_copy_skipped:
            skipped_steps.append("emby")
        _run_async(task_manager.update_task_result(task_id, extra_info=_persist_logs_extra({"step_logs": step_logs, "skipped_steps": skipped_steps})))

        reporter.report("emby", 1.0)
        _run_async(task_manager.update_task_status(task_id, TaskStatus.COMPLETED, 100))
        # 任务完成后再写一次，捕获完成日志
        _run_async(task_manager.update_task_result(task_id, extra_info=_persist_logs_extra({})))
        logger.info(f"[{task_id}] 任务完成")

        # 按配置决定是否清理临时文件
        if config.cleanup_temp_files_on_success:
            try:
                shutil.rmtree(task_work_dir)
                logger.info(f"[{task_id}] 临时文件已清理: {task_work_dir}")
            except Exception as e:
                logger.warning(f"[{task_id}] 清理临时文件失败: {e}")

        return {"task_id": task_id, "status": "completed", "subtitle_path": subtitle_path}

    except Exception as e:
        error_message = str(e)
        logger.error(f"[{task_id}] 任务失败: {error_message}", exc_info=True)
        _run_async(
            task_manager.update_task_status(task_id, TaskStatus.FAILED, error_message=error_message)
        )
        # 失败时也持久化捕获到的日志，便于排查
        try:
            _run_async(task_manager.update_task_result(task_id, extra_info=_persist_logs_extra({})))
        except Exception:
            pass
        raise

    finally:
        # ── 安全网：保证任务一定离开 PROCESSING 状态 ─────────────────
        # 重新读取一次 DB（用独立 session 避免被前面的异常污染），
        # 如果发现状态仍是 PROCESSING/PENDING，根据 subtitle_path 是否
        # 已生成强制改成 COMPLETED 或 FAILED。这一层兜底独立于上面所有
        # 逻辑，无论 asyncio loop / SQLite 锁 / 第三方库出什么状况，
        # 任务都不会再卡在 95%。
        try:
            from models.task import Task as _TaskModel
            safety_db = SessionLocal()
            try:
                row = safety_db.query(_TaskModel).filter(_TaskModel.id == task_id).first()
                if row is not None and row.status in (TaskStatus.PROCESSING, TaskStatus.PENDING):
                    from config.time_utils import utc_now
                    if subtitle_path and os.path.exists(subtitle_path):
                        row.status = TaskStatus.COMPLETED
                        row.progress = 100
                        row.completed_at = utc_now()
                        if row.started_at:
                            from config.time_utils import ensure_utc
                            started = ensure_utc(row.started_at)
                            completed = ensure_utc(row.completed_at)
                            row.processing_time = (completed - started).total_seconds()
                        logger.warning(
                            f"[{task_id}] 安全网：任务退出时状态仍为 {row.status.value}，"
                            f"检测到字幕文件已生成，强制标记为 COMPLETED"
                        )
                    else:
                        row.status = TaskStatus.FAILED
                        row.completed_at = utc_now()
                        if not row.error_message:
                            row.error_message = "任务异常退出，未生成字幕文件"
                        logger.warning(
                            f"[{task_id}] 安全网：任务退出时状态仍为 {row.status.value}，"
                            f"未检测到字幕文件，强制标记为 FAILED"
                        )
                    safety_db.commit()
            finally:
                safety_db.close()
        except Exception as e:
            logger.error(f"[{task_id}] 安全网状态修正失败: {e}", exc_info=True)

        # 卸载日志捕获器
        try:
            root_logger.removeHandler(log_capture)
        except Exception:
            pass
        # 中间产物保留在 task_work_dir 中，不清理，方便调试
        try:
            db.close()
        except Exception:
            pass
