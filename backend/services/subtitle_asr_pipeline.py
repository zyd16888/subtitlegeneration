"""
字幕 ASR 与语言检测阶段。
"""
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

from services.asr_factory import detect_language, get_asr_engine, resolve_model_by_language
from services.progress_reporter import TaskProgressReporter
from services.segment_filter import filter_filler_segments

logger = logging.getLogger(__name__)


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
