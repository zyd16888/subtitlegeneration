"""
字幕文本翻译阶段。
"""
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List

from services.progress_reporter import TaskProgressReporter
from services.subtitle_generator import SubtitleSegment
from services.subtitle_translation import build_source_segments, translate_to_multi_targets
from services.translation_factory import get_translation_service

logger = logging.getLogger(__name__)


@dataclass
class SubtitleTranslationResult:
    """字幕翻译阶段输出。"""

    per_lang_segments: Dict[str, List[SubtitleSegment]]
    emit_langs: List[str]
    translation_skipped: bool
    step_logs: dict
    skipped_steps: List[str]


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
