"""
字幕生成流水线兼容导出。

具体阶段实现已拆分到更小的模块：
- subtitle_runtime
- subtitle_audio_pipeline
- subtitle_asr_pipeline
- subtitle_text_pipeline
- subtitle_output_pipeline
"""
from services.subtitle_asr_pipeline import (
    AsrTranscriptionResult,
    LanguageDetectionResult,
    SegmentFilterResult,
    filter_asr_segments,
    process_language_detection,
    transcribe_audio,
)
from services.subtitle_audio_pipeline import AudioPreparationResult, prepare_audio
from services.subtitle_output_pipeline import (
    EmbyWritebackResult,
    SubtitleGenerationResult,
    generate_subtitle_files,
    write_subtitles_to_emby,
)
from services.subtitle_runtime import (
    SubtitleTaskRuntime,
    create_progress_reporter,
    create_task_work_dir,
    prepare_task_runtime,
)
from services.subtitle_text_pipeline import SubtitleTranslationResult, translate_subtitles

__all__ = [
    "AsrTranscriptionResult",
    "AudioPreparationResult",
    "EmbyWritebackResult",
    "LanguageDetectionResult",
    "SegmentFilterResult",
    "SubtitleGenerationResult",
    "SubtitleTaskRuntime",
    "SubtitleTranslationResult",
    "create_progress_reporter",
    "create_task_work_dir",
    "filter_asr_segments",
    "generate_subtitle_files",
    "prepare_audio",
    "prepare_task_runtime",
    "process_language_detection",
    "transcribe_audio",
    "translate_subtitles",
    "write_subtitles_to_emby",
]
