"""
字幕生成流水线准备逻辑。
"""
import logging
import os
from dataclasses import dataclass
from typing import Callable, List, Optional

from services.audio_denoiser import denoise_audio
from services.audio_extractor import AudioExtractor
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


@dataclass
class AudioPreparationResult:
    """音频准备阶段输出。"""

    audio_path: str
    step_logs: dict


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


def prepare_audio(
    task_id: str,
    video_path: str,
    task_work_dir: str,
    config,
    reporter: TaskProgressReporter,
    step_logs: dict,
    run_async: Callable,
    persist_step_logs: Callable[[dict], None],
    format_step_log: Callable[[str, str], str],
) -> AudioPreparationResult:
    """提取音频，并按配置执行可选降噪。"""
    reporter.report("audio", 0.0)
    logger.info(f"[{task_id}] 步骤 1/5: 提取音频")
    logger.info(f"[{task_id}] 视频路径: {video_path}")
    audio_extractor = AudioExtractor(task_work_dir)
    try:
        audio_path = run_async(audio_extractor.extract_audio(video_path))
        logger.info(f"[{task_id}] 音频提取成功: {audio_path}")
    except Exception as exc:
        logger.error(f"[{task_id}] 音频提取失败: {exc}", exc_info=True)
        raise

    audio_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
    step_logs["audio"] = format_step_log(
        "audio",
        (
            f"输入: {video_path}\n"
            f"输出: {audio_path}\n"
            f"音频大小: {audio_size / 1024 / 1024:.1f} MB"
        ),
    )
    persist_step_logs(step_logs)
    reporter.report("audio", 1.0)

    if getattr(config, "enable_denoise", False):
        audio_path = _denoise_audio(
            task_id=task_id,
            audio_path=audio_path,
            reporter=reporter,
            step_logs=step_logs,
            run_async=run_async,
            persist_step_logs=persist_step_logs,
            format_step_log=format_step_log,
        )

    return AudioPreparationResult(audio_path=audio_path, step_logs=step_logs)


def _denoise_audio(
    task_id: str,
    audio_path: str,
    reporter: TaskProgressReporter,
    step_logs: dict,
    run_async: Callable,
    persist_step_logs: Callable[[dict], None],
    format_step_log: Callable[[str, str], str],
) -> str:
    reporter.report("denoise", 0.0)
    logger.info(f"[{task_id}] 步骤 1.5: 音频降噪")
    try:
        denoised_path = run_async(denoise_audio(audio_path))
        denoised_size = (
            os.path.getsize(denoised_path)
            if os.path.exists(denoised_path)
            else 0
        )
        logger.info(f"[{task_id}] 降噪完成: {denoised_path}")
        step_logs["denoise"] = format_step_log(
            "denoise",
            (
                f"输入: {audio_path}\n"
                f"输出: {denoised_path}\n"
                f"降噪后大小: {denoised_size / 1024 / 1024:.1f} MB"
            ),
        )
        audio_path = denoised_path
    except Exception as exc:
        logger.warning(
            f"[{task_id}] 降噪失败，使用原始音频继续: {exc}",
            exc_info=True,
        )
        step_logs["denoise"] = format_step_log(
            "denoise",
            f"降噪失败: {exc}，使用原始音频",
        )
    reporter.report("denoise", 1.0)
    persist_step_logs(step_logs)
    return audio_path
