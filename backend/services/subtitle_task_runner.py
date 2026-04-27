"""
字幕任务阶段编排器。
"""
from dataclasses import dataclass
from typing import Callable, List, Optional

from models.base import SessionLocal
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
from services.subtitle_task_startup import start_subtitle_task
from services.subtitle_text_pipeline import translate_subtitles
from services.task_lifecycle import cleanup_task_work_dir, mark_task_completed
from services.task_result_persister import format_step_log


@dataclass
class SubtitleTaskRunResult:
    """字幕任务运行结果。"""

    subtitle_path: str


class SubtitleTaskRunner:
    """按固定阶段编排一次字幕生成任务。"""

    def __init__(
        self,
        task_id: str,
        media_item_id: str,
        video_path: str,
        context,
        run_async: Callable,
        library_id: Optional[str] = None,
        path_mapping_index: Optional[int] = None,
        asr_engine: Optional[str] = None,
        asr_model_id: Optional[str] = None,
        translation_service: Optional[str] = None,
        openai_model: Optional[str] = None,
        source_language: Optional[str] = None,
        target_languages: Optional[List[str]] = None,
        keep_source_subtitle: Optional[bool] = None,
    ):
        self.task_id = task_id
        self.media_item_id = media_item_id
        self.video_path = video_path
        self.context = context
        self.run_async = run_async
        self.library_id = library_id
        self.path_mapping_index = path_mapping_index
        self.asr_engine = asr_engine
        self.asr_model_id = asr_model_id
        self.translation_service = translation_service
        self.openai_model = openai_model
        self.source_language = source_language
        self.target_languages = target_languages
        self.keep_source_subtitle = keep_source_subtitle

    def run(self) -> SubtitleTaskRunResult:
        """执行完整字幕生成流水线。"""
        result_persister = self.context.result_persister
        task_manager = self.context.task_manager
        config_manager = self.context.config_manager

        startup = start_subtitle_task(
            task_id=self.task_id,
            video_path=self.video_path,
            config_manager=config_manager,
            task_manager=task_manager,
            result_persister=result_persister,
            session_factory=SessionLocal,
            run_async=self.run_async,
            asr_engine=self.asr_engine,
            asr_model_id=self.asr_model_id,
            translation_service=self.translation_service,
            openai_model=self.openai_model,
            source_language=self.source_language,
            target_languages=self.target_languages,
            keep_source_subtitle=self.keep_source_subtitle,
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

        audio_result = prepare_audio(
            task_id=self.task_id,
            video_path=self.video_path,
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
            task_id=self.task_id,
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
            task_id=self.task_id,
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
            task_id=self.task_id,
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
            task_id=self.task_id,
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
            task_id=self.task_id,
            video_path=self.video_path,
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
            task_id=self.task_id,
            config=config,
            media_item_id=self.media_item_id,
            subtitle_paths=subtitle_paths,
            path_mapping_index=self.path_mapping_index,
            library_id=self.library_id,
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
            task_id=self.task_id,
            task_manager=task_manager,
            result_persister=result_persister,
            run_async=self.run_async,
        )
        cleanup_task_work_dir(
            task_id=self.task_id,
            task_work_dir=task_work_dir,
            cleanup_enabled=config.cleanup_temp_files_on_success,
        )

        return SubtitleTaskRunResult(subtitle_path=subtitle_path)
