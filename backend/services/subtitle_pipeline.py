"""
字幕生成流水线准备逻辑。
"""
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from services.progress_reporter import TaskProgressReporter
from services.subtitle_translation import resolve_target_languages

logger = logging.getLogger(__name__)


@dataclass
class SubtitleTaskRuntime:
    """单次字幕任务运行时配置。"""

    config: object
    source_lang: str
    resolved_target_langs: List[str]
    primary_target_lang: str
    keep_source: bool
    translation_source_lang: str
    reporter: TaskProgressReporter


def prepare_task_runtime(
    config,
    task_id: str,
    session_factory: Callable,
    asr_engine: Optional[str] = None,
    asr_model_id: Optional[str] = None,
    translation_service: Optional[str] = None,
    openai_model: Optional[str] = None,
    source_language: Optional[str] = None,
    target_languages: Optional[List[str]] = None,
    keep_source_subtitle: Optional[bool] = None,
) -> SubtitleTaskRuntime:
    """应用任务级覆盖，并构造本次任务的运行时配置。"""
    if asr_engine:
        config.asr_engine = asr_engine
    if asr_model_id:
        config.asr_model_id = asr_model_id
    if translation_service:
        config.translation_service = translation_service
    if openai_model:
        config.openai_model = openai_model

    source_lang = source_language if source_language else config.source_language
    resolved_target_langs = resolve_target_languages(config, target_languages)
    primary_target_lang = (
        resolved_target_langs[0] if resolved_target_langs else config.target_language
    )
    keep_source = (
        keep_source_subtitle
        if keep_source_subtitle is not None
        else bool(getattr(config, "keep_source_subtitle", False))
    )

    translation_source_lang = source_lang
    if getattr(config, "source_language_detection", None) == "auto":
        translation_source_lang = "auto"
        logger.info(f"[{task_id}] 源语言检测模式: auto（翻译服务将自动检测语言）")
    else:
        logger.info(f"[{task_id}] 源语言检测模式: fixed（使用配置的语言: {source_lang}）")

    logger.info(
        f"[{task_id}] 使用语音识别语言: {source_lang} "
        f"(任务指定: {source_language}, 全局: {config.source_language})"
    )
    logger.info(
        f"[{task_id}] 翻译源语言: {translation_source_lang}, "
        f"目标语言: {resolved_target_langs}"
    )
    if keep_source:
        logger.info(f"[{task_id}] 启用源语言字幕保留: {source_lang}")

    return SubtitleTaskRuntime(
        config=config,
        source_lang=source_lang,
        resolved_target_langs=resolved_target_langs,
        primary_target_lang=primary_target_lang,
        keep_source=keep_source,
        translation_source_lang=translation_source_lang,
        reporter=create_progress_reporter(task_id, config, session_factory),
    )


def create_progress_reporter(
    task_id: str,
    config,
    session_factory: Callable,
) -> TaskProgressReporter:
    """根据可选处理阶段创建进度上报器。"""
    has_denoise = getattr(config, "enable_denoise", False)
    has_lid = bool(config.enable_language_detection and config.lid_model_id)

    if has_denoise and has_lid:
        return TaskProgressReporter(task_id, session_factory, stage_weights={
            "audio": (0, 13),
            "denoise": (13, 22),
            "lid": (22, 25),
            "asr": (25, 60),
            "translation": (60, 90),
            "subtitle": (90, 95),
            "emby": (95, 100),
        })
    if has_denoise:
        return TaskProgressReporter(task_id, session_factory, stage_weights={
            "audio": (0, 15),
            "denoise": (15, 25),
            "asr": (25, 60),
            "translation": (60, 90),
            "subtitle": (90, 95),
            "emby": (95, 100),
        })
    if has_lid:
        return TaskProgressReporter(task_id, session_factory, stage_weights={
            "audio": (0, 18),
            "lid": (18, 22),
            "asr": (22, 60),
            "translation": (60, 90),
            "subtitle": (90, 95),
            "emby": (95, 100),
        })
    return TaskProgressReporter(task_id, session_factory)
