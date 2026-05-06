"""
字幕任务阶段编排器。
"""
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from services.subtitle_asr_pipeline import (
    filter_asr_segments,
    process_language_detection,
    transcribe_audio,
)
from services.subtitle_audio_pipeline import prepare_audio
from services.subtitle_output_pipeline import (
    generate_subtitle_files,
    write_subtitles_to_emby,
)
from services.subtitle_search_pipeline import try_external_subtitle
from services.subtitle_task_startup import start_subtitle_task
from services.subtitle_text_pipeline import translate_subtitles
from services.task_lifecycle import cleanup_task_work_dir, mark_task_completed
from services.task_result_persister import format_step_log

logger = logging.getLogger(__name__)


@dataclass
class SubtitleTaskRequest:
    """字幕任务请求参数。"""

    task_id: str
    media_item_id: str
    video_path: str
    library_id: Optional[str] = None
    path_mapping_index: Optional[int] = None
    asr_engine: Optional[str] = None
    asr_model_id: Optional[str] = None
    translation_service: Optional[str] = None
    openai_model: Optional[str] = None
    source_language: Optional[str] = None
    target_languages: Optional[List[str]] = None
    keep_source_subtitle: Optional[bool] = None


@dataclass
class SubtitleTaskRunResult:
    """字幕任务运行结果。"""

    subtitle_path: str


class SubtitleTaskRunner:
    """按固定阶段编排一次字幕生成任务。"""

    def __init__(
        self,
        request: SubtitleTaskRequest,
        context,
        run_async: Callable,
    ):
        self.request = request
        self.context = context
        self.run_async = run_async

    def _fetch_media_title(self, task_id: str, task_manager) -> Optional[str]:
        """从 DB 拿任务对应的 media_item_title，作为外部字幕搜索关键词。"""
        try:
            task = self.run_async(task_manager.get_task(task_id))
            return task.media_item_title if task else None
        except Exception:
            return None

    def run(self) -> SubtitleTaskRunResult:
        """执行完整字幕生成流水线。"""
        request = self.request
        result_persister = self.context.result_persister
        task_manager = self.context.task_manager
        config_manager = self.context.config_manager

        startup = start_subtitle_task(
            task_id=request.task_id,
            video_path=request.video_path,
            config_manager=config_manager,
            task_manager=task_manager,
            result_persister=result_persister,
            session_factory=self.context.session_factory,
            run_async=self.run_async,
            asr_engine=request.asr_engine,
            asr_model_id=request.asr_model_id,
            translation_service=request.translation_service,
            openai_model=request.openai_model,
            source_language=request.source_language,
            target_languages=request.target_languages,
            keep_source_subtitle=request.keep_source_subtitle,
        )
        config = startup.config
        source_lang = startup.source_lang
        resolved_target_langs = startup.resolved_target_langs
        primary_target_lang = startup.primary_target_lang
        keep_source = startup.keep_source
        translation_source_lang = startup.translation_source_lang
        reporter = startup.reporter
        task_work_dir = startup.task_work_dir

        step_logs = {}
        skipped_steps = []

        # ── 自动外部字幕检索（任务前置） ───────────────────────────────
        # 命中：直接复制并刷新 Emby，跳过 ASR/翻译。
        # 未命中或失败：log 一条记录，继续走原管线。
        if (
            getattr(config, "subtitle_search_enabled", False)
            and getattr(config, "subtitle_search_auto_in_task", False)
        ):
            external_result = try_external_subtitle(
                task_id=request.task_id,
                media_item_id=request.media_item_id,
                media_item_title=self._fetch_media_title(request.task_id, task_manager),
                config=config,
                resolved_target_langs=resolved_target_langs,
                library_id=request.library_id,
                path_mapping_index=request.path_mapping_index,
                task_work_dir=task_work_dir,
                reporter=reporter,
                step_logs=step_logs,
                skipped_steps=skipped_steps,
                run_async=self.run_async,
                persist_step_logs=result_persister.persist_step_logs,
                format_step_log=format_step_log,
            )
            if external_result is not None:
                primary_path = (
                    external_result.applied[0].target_path
                    if external_result.applied
                    else ""
                )
                # 写入 task 字段 + extra_info 摘要
                self.run_async(
                    task_manager.update_task_result(
                        request.task_id,
                        subtitle_path=primary_path,
                    )
                )
                result_persister.update_result(
                    extra_info=result_persister.with_logs({
                        "step_logs": step_logs,
                        "skipped_steps": skipped_steps + ["audio", "asr", "translation", "subtitle"],
                        "subtitle_source": "xunlei_search",
                        "search_query": external_result.query,
                        "matched_languages": external_result.matched_languages,
                        "ranked_summary": external_result.ranked_summary,
                        "subtitles": [
                            {
                                "lang": a.language.code,
                                "path": a.target_path,
                                "ext": a.ext,
                                "source_url": a.source_url,
                            }
                            for a in external_result.applied
                        ],
                        "target_languages": list(resolved_target_langs),
                        "keep_source_subtitle": keep_source,
                    })
                )
                mark_task_completed(
                    task_id=request.task_id,
                    task_manager=task_manager,
                    result_persister=result_persister,
                    run_async=self.run_async,
                )
                cleanup_task_work_dir(
                    task_id=request.task_id,
                    task_work_dir=task_work_dir,
                    cleanup_enabled=config.cleanup_temp_files_on_success,
                )
                logger.info(
                    f"[{request.task_id}] 命中外部字幕，跳过 ASR/翻译: "
                    f"langs={external_result.matched_languages}"
                )
                return SubtitleTaskRunResult(subtitle_path=primary_path)

        audio_result = prepare_audio(
            task_id=request.task_id,
            video_path=request.video_path,
            task_work_dir=task_work_dir,
            config=config,
            reporter=reporter,
            step_logs=step_logs,
            run_async=self.run_async,
            persist_step_logs=result_persister.persist_step_logs,
            format_step_log=format_step_log,
        )
        audio_path = audio_result.audio_path
        step_logs = audio_result.step_logs

        language_result = process_language_detection(
            task_id=request.task_id,
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
            task_id=request.task_id,
            config=config,
            audio_path=audio_path,
            task_work_dir=task_work_dir,
            source_lang=source_lang,
            reporter=reporter,
            step_logs=step_logs,
            run_async=self.run_async,
            persist_asr_result=result_persister.persist_asr_result,
            format_step_log=format_step_log,
        )
        segments = asr_result.segments
        step_logs = asr_result.step_logs

        filter_result = filter_asr_segments(
            task_id=request.task_id,
            config=config,
            segments=segments,
            source_lang=source_lang,
            step_logs=step_logs,
            persist_asr_result=result_persister.persist_asr_result,
            format_step_log=format_step_log,
        )
        segments = filter_result.segments
        step_logs = filter_result.step_logs

        translation_result = translate_subtitles(
            task_id=request.task_id,
            config=config,
            segments=segments,
            source_lang=source_lang,
            translation_source_lang=translation_source_lang,
            resolved_target_langs=resolved_target_langs,
            keep_source=keep_source,
            reporter=reporter,
            step_logs=step_logs,
            skipped_steps=skipped_steps,
            run_async=self.run_async,
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

        subtitle_result = generate_subtitle_files(
            task_id=request.task_id,
            video_path=request.video_path,
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

        emby_result = write_subtitles_to_emby(
            task_id=request.task_id,
            config=config,
            media_item_id=request.media_item_id,
            subtitle_paths=subtitle_paths,
            path_mapping_index=request.path_mapping_index,
            library_id=request.library_id,
            reporter=reporter,
            step_logs=step_logs,
            skipped_steps=skipped_steps,
            run_async=self.run_async,
            format_step_log=format_step_log,
        )
        result_persister.persist_emby_result(
            step_logs=emby_result.step_logs,
            skipped_steps=emby_result.skipped_steps,
        )

        mark_task_completed(
            task_id=request.task_id,
            task_manager=task_manager,
            result_persister=result_persister,
            run_async=self.run_async,
        )
        cleanup_task_work_dir(
            task_id=request.task_id,
            task_work_dir=task_work_dir,
            cleanup_enabled=config.cleanup_temp_files_on_success,
        )

        return SubtitleTaskRunResult(subtitle_path=subtitle_path)
