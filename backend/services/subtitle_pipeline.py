"""
字幕生成流水线准备逻辑。
"""
import logging
import os
import json
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from services.asr_factory import detect_language, get_asr_engine, resolve_model_by_language
from services.audio_denoiser import denoise_audio
from services.audio_extractor import AudioExtractor
from services.progress_reporter import TaskProgressReporter
from services.segment_filter import filter_filler_segments
from services.subtitle_generator import SubtitleSegment
from services.subtitle_translation import (
    build_source_segments,
    resolve_target_languages,
    translate_to_multi_targets,
)
from services.translation_factory import get_translation_service

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


@dataclass
class LanguageDetectionResult:
    """语言检测阶段输出。"""

    source_lang: str
    translation_source_lang: str
    step_logs: dict


@dataclass
class AsrTranscriptionResult:
    """ASR 转录阶段输出。"""

    segments: list
    step_logs: dict


@dataclass
class SegmentFilterResult:
    """ASR 段落过滤阶段输出。"""

    segments: list
    step_logs: dict


@dataclass
class SubtitleTranslationResult:
    """字幕翻译阶段输出。"""

    per_lang_segments: Dict[str, List[SubtitleSegment]]
    emit_langs: List[str]
    translation_skipped: bool
    step_logs: dict
    skipped_steps: List[str]


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


def process_language_detection(
    task_id: str,
    config,
    audio_path: str,
    source_lang: str,
    translation_source_lang: str,
    reporter: TaskProgressReporter,
    step_logs: dict,
    persist_step_logs: Callable[[dict], None],
    format_step_log: Callable[[str, str], str],
) -> LanguageDetectionResult:
    """执行可选 LID 语言检测，并更新 ASR 模型/源语言。"""
    if not (config.enable_language_detection and config.lid_model_id):
        return LanguageDetectionResult(
            source_lang=source_lang,
            translation_source_lang=translation_source_lang,
            step_logs=step_logs,
        )

    reporter.report("lid", 0.0)
    logger.info(f"[{task_id}] 步骤 1.8: 音频语言检测 (LID)")
    try:
        detected_lang = detect_language(config, audio_path)
        if detected_lang:
            logger.info(f"[{task_id}] 检测到音频语言: {detected_lang}")
            resolved_model_id, resolved_source_lang = resolve_model_by_language(
                detected_lang,
                config.asr_language_model_map,
                config.asr_model_id,
            )
            if resolved_model_id and resolved_model_id != config.asr_model_id:
                logger.info(
                    f"[{task_id}] 按语言映射切换 ASR 模型: "
                    f"{config.asr_model_id} → {resolved_model_id}"
                )
                config.asr_model_id = resolved_model_id
            if resolved_source_lang:
                source_lang = resolved_source_lang
                if translation_source_lang != "auto":
                    translation_source_lang = resolved_source_lang
                logger.info(f"[{task_id}] 源语言更新为: {source_lang}")
            step_logs["lid"] = format_step_log(
                "lid",
                (
                    f"检测语言: {detected_lang}\n"
                    f"ASR 模型: {config.asr_model_id}\n"
                    f"源语言: {source_lang}"
                ),
            )
        else:
            logger.info(f"[{task_id}] 语言检测未返回结果，使用默认配置")
            step_logs["lid"] = format_step_log("lid", "未检测到语言，使用默认配置")
    except Exception as exc:
        logger.warning(
            f"[{task_id}] 语言检测失败，使用默认配置: {exc}",
            exc_info=True,
        )
        step_logs["lid"] = format_step_log("lid", f"检测失败: {exc}，使用默认配置")

    reporter.report("lid", 1.0)
    persist_step_logs(step_logs)
    return LanguageDetectionResult(
        source_lang=source_lang,
        translation_source_lang=translation_source_lang,
        step_logs=step_logs,
    )


def transcribe_audio(
    task_id: str,
    config,
    audio_path: str,
    task_work_dir: str,
    source_lang: str,
    reporter: TaskProgressReporter,
    step_logs: dict,
    run_async: Callable,
    persist_asr_result: Callable[[int, dict], None],
    format_step_log: Callable[[str, str], str],
) -> AsrTranscriptionResult:
    """创建 ASR 引擎并转录音频。"""
    reporter.report("asr", 0.0)
    logger.info(f"[{task_id}] 步骤 2/5: 语音识别")
    logger.info(f"[{task_id}] 创建 ASR 引擎...")
    try:
        asr_engine_instance = get_asr_engine(config, source_language=source_lang)
        logger.info(
            f"[{task_id}] ASR 引擎创建成功: {type(asr_engine_instance).__name__}"
        )
    except Exception as exc:
        logger.error(f"[{task_id}] ASR 引擎创建失败: {exc}", exc_info=True)
        raise

    logger.info(f"[{task_id}] 开始转录音频: {audio_path}")
    segments = run_async(
        asr_engine_instance.transcribe(
            audio_path,
            language=source_lang,
            progress_cb=reporter.for_stage("asr"),
        )
    )
    reporter.report("asr", 1.0)
    logger.info(f"[{task_id}] 语音识别完成，识别到 {len(segments)} 个片段")
    step_logs["asr"] = format_step_log(
        "asr",
        (
            f"引擎: {type(asr_engine_instance).__name__}\n"
            f"识别片段数: {len(segments)}\n"
            f"语言: {source_lang}"
        ),
    )
    persist_asr_result(len(segments), step_logs)

    asr_result_path = os.path.join(task_work_dir, "asr_result.json")
    with open(asr_result_path, "w", encoding="utf-8") as file:
        json.dump(
            [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
            file,
            ensure_ascii=False,
            indent=2,
        )
    logger.info(f"[{task_id}] ASR 结果已保存: {asr_result_path}")

    if not segments:
        raise RuntimeError("语音识别未能识别出任何内容，请检查音频是否包含语音或更换 ASR 模型")

    return AsrTranscriptionResult(segments=segments, step_logs=step_logs)


def filter_asr_segments(
    task_id: str,
    config,
    segments: list,
    source_lang: str,
    step_logs: dict,
    persist_asr_result: Callable[[int, dict], None],
    format_step_log: Callable[[str, str], str],
) -> SegmentFilterResult:
    """按配置过滤 ASR 语气词段落。"""
    filter_enabled = getattr(config, "filter_filler_words", True)
    custom_fillers = getattr(config, "custom_filler_words", []) or []
    original_count = len(segments)
    segments, filtered_count = filter_filler_segments(
        segments,
        source_lang=source_lang,
        custom_fillers=custom_fillers,
        enabled=filter_enabled,
    )
    if filtered_count > 0:
        logger.info(
            f"[{task_id}] 已过滤 {filtered_count} 个语气词段落 "
            f"({original_count} → {len(segments)})"
        )
        step_logs["asr"] += (
            f"\n语气词过滤: {filtered_count} 段被移除 "
            f"({original_count} → {len(segments)})"
        )
        step_logs["filler_filter"] = format_step_log(
            "filler_filter",
            f"过滤 {filtered_count} 个语气词段落 ({original_count} → {len(segments)})",
        )
        persist_asr_result(len(segments), step_logs)
    elif filter_enabled:
        logger.info(f"[{task_id}] 语气词过滤已启用，未发现需过滤段落")
        step_logs["filler_filter"] = format_step_log("filler_filter", "未发现需过滤段落")

    if not segments:
        raise RuntimeError("语音识别内容全部为语气词，过滤后无有效字幕段落")

    return SegmentFilterResult(segments=segments, step_logs=step_logs)


def translate_subtitles(
    task_id: str,
    config,
    segments: list,
    source_lang: str,
    translation_source_lang: str,
    resolved_target_langs: List[str],
    keep_source: bool,
    reporter: TaskProgressReporter,
    step_logs: dict,
    skipped_steps: List[str],
    run_async: Callable,
    format_step_log: Callable[[str, str], str],
) -> SubtitleTranslationResult:
    """翻译字幕到目标语言，并按配置追加源语言字幕。"""
    reporter.report("translation", 0.0)
    logger.info(f"[{task_id}] 步骤 3/5: 翻译文本")

    all_targets_equal_source = (
        translation_source_lang != "auto"
        and all(target_lang == source_lang for target_lang in resolved_target_langs)
    )

    per_lang_segments: Dict[str, List[SubtitleSegment]] = {}
    skipped_steps = list(skipped_steps)

    if all_targets_equal_source:
        logger.info(
            f"[{task_id}] 所有目标语言均等于源语言 ({source_lang})，跳过翻译"
        )
        source_subs = build_source_segments(segments)
        for target_lang in resolved_target_langs:
            per_lang_segments[target_lang] = source_subs
        translation_skipped = True
    else:
        if translation_source_lang == "auto":
            logger.info(
                f"[{task_id}] 使用自动语言检测模式翻译到 {resolved_target_langs}"
            )
        translation_service_instance = get_translation_service(config)
        translation_concurrency = getattr(config, "translation_concurrency", None)
        translation_context_size = getattr(config, "translation_context_size", 0) or 0
        logger.info(
            f"[{task_id}] 翻译并发数: "
            f"{translation_concurrency if translation_concurrency else f'默认 ({translation_service_instance.default_concurrency})'}"
        )
        if translation_context_size > 0:
            logger.info(f"[{task_id}] 翻译上下文窗口: 前后各 {translation_context_size} 条")

        per_lang_segments = run_async(
            translate_to_multi_targets(
                segments,
                translation_service_instance,
                source_lang=source_lang,
                translation_source_lang=translation_source_lang,
                target_langs=resolved_target_langs,
                concurrency=translation_concurrency,
                context_size=translation_context_size,
                progress_cb=reporter.for_stage("translation"),
            )
        )
        translation_skipped = False

    emit_langs: List[str] = list(resolved_target_langs)
    if keep_source and source_lang not in per_lang_segments:
        per_lang_segments[source_lang] = build_source_segments(segments)
        emit_langs.append(source_lang)
        logger.info(f"[{task_id}] 追加源语言字幕: {source_lang}")

    reporter.report("translation", 1.0)

    if translation_skipped:
        step_logs["translation"] = format_step_log(
            "translation",
            f"所有目标语言均等于源语言 ({source_lang})，已跳过翻译",
        )
        skipped_steps.append("translation")
    else:
        detection_mode = (
            "自动检测"
            if translation_source_lang == "auto"
            else f"固定 ({translation_source_lang})"
        )
        lines = [
            f"翻译服务: {config.translation_service}",
            f"源语言模式: {detection_mode}",
            f"目标语言: {', '.join(resolved_target_langs)}",
        ]
        for target_lang in resolved_target_langs:
            target_segments = per_lang_segments.get(target_lang, [])
            translated_count = sum(1 for segment in target_segments if segment.is_translated)
            lines.append(
                f"  - {target_lang}: 成功翻译 {translated_count}/{len(target_segments)} 段"
            )
        step_logs["translation"] = format_step_log("translation", "\n".join(lines))

    return SubtitleTranslationResult(
        per_lang_segments=per_lang_segments,
        emit_langs=emit_langs,
        translation_skipped=translation_skipped,
        step_logs=step_logs,
        skipped_steps=skipped_steps,
    )
