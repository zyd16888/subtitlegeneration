"""
字幕搜索结果评分与排序。

输入：原始 SearchHit 列表（来自 client.py）+ 可选目标语言/媒体时长
输出：排序后的 RankedHit 列表

评分规则（综合分 0-1，越高越优）：
  - 语言匹配：必填且匹配 target_languages → +0.5；只识别但不匹配 → 0
  - 时长匹配：±5% 满分 0.3，±10% 半分 0.15，未知 0.1，超出 0
  - 扩展名：.srt → +0.1，.ass → +0.05
  - 文件名质量：纯哈希名 → -0.1
  - 双语命中目标语言 → +0.05 加成

去重：同 gcid 仅保留分数最高一条；同语言可保留多条供用户选。
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from .lang_sniffer import is_hash_only_name, resolve_from_metadata
from .types import LanguageResolution, LanguageSource, RankedHit, SearchHit

logger = logging.getLogger(__name__)


def _duration_score(hit_ms: int, media_ms: Optional[int]) -> float:
    """时长子分（0-1）。媒体时长未知时给中性分 0.33（≈ 0.1/0.3）。"""
    if not media_ms or media_ms <= 0:
        return 0.33
    if hit_ms <= 0:
        return 0.0
    diff_ratio = abs(hit_ms - media_ms) / media_ms
    if diff_ratio <= 0.05:
        return 1.0
    if diff_ratio <= 0.10:
        return 0.5
    if diff_ratio <= 0.20:
        return 0.2
    return 0.0


def _ext_score(ext: str) -> float:
    e = (ext or "").lower()
    if e == "srt":
        return 1.0
    if e == "ass":
        return 0.5
    return 0.0


def score_hit(
    hit: SearchHit,
    language: LanguageResolution,
    target_languages: Optional[Iterable[str]],
    media_duration_ms: Optional[int],
) -> RankedHit:
    """对单条 hit 计算综合评分，返回 RankedHit。

    target_languages 为 None / 空列表时不做语言加权（即只看时长 / 扩展名 / 文件名）。
    """
    targets = [code for code in (target_languages or []) if code]
    target_set = {code.lower() for code in targets}

    lang_match = False
    if target_set and language.code:
        lang_match = language.code.lower() in target_set or (
            language.is_bilingual
            and language.secondary_code
            and language.secondary_code.lower() in target_set
        )

    # 子分
    if not target_set:
        # 没指定目标语言：只要识别出语言就给 0.5，未知给 0.2
        lang_subscore = 0.5 if language.code else 0.2
    else:
        if lang_match:
            lang_subscore = 1.0
        elif language.code is None:
            # 未识别语言：给中性子分，避免在元信息层级失败时被腰斩；
            # 真正的判定由内容嗅探（API 端点 sniff_unknown）或下载阶段做
            lang_subscore = 0.4
        else:
            # 识别出来但和目标不匹配
            lang_subscore = 0.0

    duration_subscore = _duration_score(hit.duration_ms, media_duration_ms)
    ext_subscore = _ext_score(hit.ext)
    name_penalty = 0.1 if is_hash_only_name(hit.name) else 0.0
    bilingual_bonus = 0.05 if (lang_match and language.is_bilingual) else 0.0

    # 加权汇总（系数对应方案中 0.5/0.3/0.1 的份额）
    raw = (
        0.5 * lang_subscore
        + 0.3 * duration_subscore
        + 0.1 * ext_subscore
        - name_penalty
        + bilingual_bonus
    )
    score = max(0.0, min(1.0, raw))

    breakdown = {
        "language": round(lang_subscore, 3),
        "duration": round(duration_subscore, 3),
        "extension": round(ext_subscore, 3),
        "hash_name_penalty": round(name_penalty, 3),
        "bilingual_bonus": round(bilingual_bonus, 3),
        "language_match": lang_match,
    }

    return RankedHit(
        hit=hit,
        language=language,
        score=score,
        duration_match=duration_subscore,
        score_breakdown=breakdown,
    )


def rank_hits(
    hits: Iterable[SearchHit],
    *,
    target_languages: Optional[Iterable[str]] = None,
    media_duration_ms: Optional[int] = None,
    require_target_match: bool = False,
) -> List[RankedHit]:
    """评分 + 排序 + 去重。

    Args:
        hits: 来自 client.search() 的原始候选
        target_languages: 期望的目标语言码列表
        media_duration_ms: 媒体时长（毫秒），用于时长匹配评分
        require_target_match: True 时丢弃语言不匹配 / 未识别的条目
                              （自动模式用；手动模式应留 False）
    """
    seen_gcid = set()
    ranked: List[RankedHit] = []

    targets = [code for code in (target_languages or []) if code]

    for hit in hits:
        if hit.gcid and hit.gcid in seen_gcid:
            continue

        # 元信息层级语言识别（不读文件内容；下载阶段才会有内容做 L3）
        meta_lang = resolve_from_metadata(hit.raw_languages, hit.name)
        language = meta_lang or LanguageResolution(
            code=None, source=LanguageSource.UNKNOWN, confidence=0.0
        )

        if require_target_match and targets:
            if not language.code:
                # 未识别的，自动模式下放弃；手动模式不会走到这
                continue
            target_set = {code.lower() for code in targets}
            primary_match = language.code.lower() in target_set
            secondary_match = (
                language.is_bilingual
                and language.secondary_code
                and language.secondary_code.lower() in target_set
            )
            if not (primary_match or secondary_match):
                continue

        ranked_hit = score_hit(hit, language, targets, media_duration_ms)
        ranked.append(ranked_hit)
        if hit.gcid:
            seen_gcid.add(hit.gcid)

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def pick_best_per_language(
    ranked: Iterable[RankedHit],
    target_languages: Iterable[str],
) -> dict:
    """每个目标语言取分数最高的一条，返回 {lang_code: RankedHit}。

    只考虑 RankedHit.language.code 命中目标的（语言识别失败的不参与）。
    用于自动模式下决定要下载哪些条目。
    """
    targets = [code for code in target_languages if code]
    result: dict = {}
    for r in ranked:
        if not r.language.code:
            continue
        for target in targets:
            if r.language.code.lower() != target.lower():
                continue
            existing = result.get(target)
            if existing is None or r.score > existing.score:
                result[target] = r
            break
    return result
