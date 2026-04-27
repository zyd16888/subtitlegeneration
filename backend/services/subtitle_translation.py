"""
字幕翻译辅助流程。
"""
import logging
from typing import Callable, Dict, List, Optional

from services.asr_engine import Segment
from services.subtitle_generator import SubtitleSegment
from services.translation_service import TranslationService

logger = logging.getLogger(__name__)


async def translate_segments(
    segments: List[Segment],
    translation_service: TranslationService,
    source_lang: str = "ja",
    target_lang: str = "zh",
    concurrency: Optional[int] = None,
    context_size: int = 0,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[SubtitleSegment]:
    """并发翻译 ASR 识别的文本片段。"""
    if not segments:
        return []

    texts = [s.text for s in segments]
    results = await translation_service.translate_batch(
        texts,
        source_lang=source_lang,
        target_lang=target_lang,
        concurrency=concurrency,
        all_texts=texts if context_size > 0 else None,
        context_size=context_size,
        progress_cb=progress_cb,
    )

    subtitle_segments: List[SubtitleSegment] = []
    for segment, (translated_text, success) in zip(segments, results):
        subtitle_segments.append(
            SubtitleSegment(
                start=segment.start,
                end=segment.end,
                original_text=segment.text,
                translated_text=translated_text,
                is_translated=success,
            )
        )
    return subtitle_segments


def build_source_segments(segments: List[Segment]) -> List[SubtitleSegment]:
    """构造源语言字幕片段。"""
    return [
        SubtitleSegment(
            start=segment.start,
            end=segment.end,
            original_text=segment.text,
            translated_text=segment.text,
            is_translated=False,
        )
        for segment in segments
    ]


def resolve_target_languages(config, task_override: Optional[List[str]] = None) -> List[str]:
    """解析本次任务要生成的目标语言列表，去重并保持顺序。"""
    if task_override:
        candidates = list(task_override)
    elif getattr(config, "target_languages", None):
        candidates = list(config.target_languages)
    else:
        candidates = [config.target_language]

    seen = set()
    result: List[str] = []
    for code in candidates:
        if not code:
            continue
        code = code.strip()
        if code and code not in seen:
            seen.add(code)
            result.append(code)
    return result


async def translate_to_multi_targets(
    segments: List[Segment],
    translation_service: TranslationService,
    source_lang: str,
    translation_source_lang: str,
    target_langs: List[str],
    concurrency: Optional[int] = None,
    context_size: int = 0,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Dict[str, List[SubtitleSegment]]:
    """按语言维度串行翻译到多个目标语言。"""
    translate_langs = [
        lang for lang in target_langs
        if not (source_lang == lang and translation_source_lang != "auto")
    ]
    total_segs = len(segments) * len(translate_langs) if translate_langs else 0
    completed_segs = 0

    def _per_lang_cb(done: int, total: int) -> None:
        nonlocal completed_segs
        if progress_cb and total_segs > 0:
            fraction = min(0.99, (completed_segs + done) / total_segs)
            progress_cb(fraction)

    results: Dict[str, List[SubtitleSegment]] = {}
    for target_lang in target_langs:
        if source_lang == target_lang and translation_source_lang != "auto":
            logger.info(
                f"目标语言 {target_lang} 与源语言相同，跳过翻译直接使用 ASR 原文"
            )
            results[target_lang] = build_source_segments(segments)
            continue

        logger.info(f"开始翻译到 {target_lang}")
        results[target_lang] = await translate_segments(
            segments,
            translation_service,
            source_lang=translation_source_lang,
            target_lang=target_lang,
            concurrency=concurrency,
            context_size=context_size,
            progress_cb=_per_lang_cb,
        )
        completed_segs += len(segments)
    return results
