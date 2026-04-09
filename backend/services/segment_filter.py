"""ASR 段落过滤器 — 过滤纯语气词/感叹词段落，减少无意义翻译，节省 token。

在 ASR 识别完成后、翻译前调用。仅对纯语气词段落生效，
包含实际内容的段落即使夹杂语气词也会保留。
"""
import logging
import re
from typing import List, Set, Tuple

from services.asr_engine import Segment

logger = logging.getLogger(__name__)

# ── 内置默认语气词表（按语言） ──────────────────────────────────────
# 仅当段落文本完全由这些词（+ 标点/空白）组成时才会被过滤

DEFAULT_FILLER_WORDS = {
    "ja": [
        # 感叹/惊讶
        "あ", "ああ", "あー", "あぁ", "あっ",
        "え", "えー", "えぇ", "えっ",
        "お", "おー", "おお", "おっ",
        "わ", "わあ", "わー",
        # 思考/犹豫
        "うん", "うーん", "ん", "んー", "んん",
        "えと", "えっと", "あの", "あのー", "その", "そのー",
        "まあ", "まー",
        # 应答
        "はい", "ええ", "うん",
        "ふん", "ふーん", "へえ", "へー",
        "ほう", "ほー",
        # 语气助词（单独出现时）
        "ね", "ねえ", "な", "なあ", "なー",
        "さ", "さあ", "さー",
        # 叹息/呼气
        "はあ", "はぁ", "ふう", "ふぅ",
    ],
}


def get_default_fillers(lang: str) -> List[str]:
    """返回指定语言的内置默认语气词列表。"""
    return list(DEFAULT_FILLER_WORDS.get(lang, []))


# ── 标点/空白正则 ───────────────────────────────────────────────────
_PUNCT_WS_RE = re.compile(r'[\s、。，,.!?！？…─\-ー〜~♪♫☆★\u3000]+')


def _is_filler(text: str, fillers_sorted: List[str]) -> bool:
    """判断文本是否完全由语气词 + 标点/空白组成。

    Args:
        text: 待检测文本
        fillers_sorted: 按长度降序排列的语气词列表（最长优先贪心匹配）
    """
    cleaned = _PUNCT_WS_RE.sub('', text).strip()
    if not cleaned:
        return True  # 纯标点/空白

    remaining = cleaned
    while remaining:
        matched = False
        for filler in fillers_sorted:
            if remaining.startswith(filler):
                remaining = remaining[len(filler):]
                matched = True
                break
        if not matched:
            return False
    return True


def filter_filler_segments(
    segments: List[Segment],
    source_lang: str = "ja",
    custom_fillers: List[str] | None = None,
    enabled: bool = True,
) -> Tuple[List[Segment], int]:
    """过滤纯语气词段落。

    Args:
        segments: ASR 识别结果段落列表
        source_lang: 源语言代码（用于选择内置词表）
        custom_fillers: 用户自定义语气词（与内置列表合并）
        enabled: 总开关，False 时直接返回原列表

    Returns:
        (过滤后的段落列表, 被移除的段落数)
    """
    if not enabled or not segments:
        return segments, 0

    # 合并内置 + 自定义词表，去重
    builtin = DEFAULT_FILLER_WORDS.get(source_lang, [])
    extra = custom_fillers or []
    all_fillers: Set[str] = set(builtin) | set(extra)

    if not all_fillers:
        return segments, 0

    # 按长度降序排列，保证最长优先匹配
    fillers_sorted = sorted(all_fillers, key=len, reverse=True)

    result: List[Segment] = []
    removed = 0
    for seg in segments:
        if _is_filler(seg.text, fillers_sorted):
            removed += 1
            logger.debug(
                "过滤语气词段落: [%.2f-%.2f] %s", seg.start, seg.end, seg.text
            )
        else:
            result.append(seg)

    return result, removed
