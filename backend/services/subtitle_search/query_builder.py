"""
搜索关键词构造。

Emby 媒体标题往往很长（"ADN-351 周末限定 夫妇交换 妻子被其他人插入的夜 希岛爱里,加藤あやの"），
直接用整串作 query 命中率低。这里按优先级生成几个候选 query，pipeline 按顺序尝试。

优先级：
  1. AV 番号（ADN-351 / NSFS-061）—— 短串、信号最强
  2. 原始标题
  3. 剥离常见噪声（年份、画质、释放组等）后的标题
  4. 剧集类标题去掉 SxxExx 取剧名
"""
from __future__ import annotations

import re
from typing import List

# 主流番号格式：2-7 个 ASCII 字母 + 可选连字符 + 2-6 位数字
# 例：ADN-351 / NSFS-061 / JUE-001 / FC2-PPV-1234567
# 用 lookaround 而非 \b，避免中文紧贴英文时（如"周末ADN-351"）边界失效。
_AV_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z]{2,7})[-_]?(\d{2,6})(?![A-Za-z0-9])"
)

# SxxExx 剧集模式
_SERIES_EP_RE = re.compile(r"^(.+?)\s+S\d{1,2}E\d{1,3}\s*$", re.IGNORECASE)

# 视频/释放组常见噪声标签
_NOISE_RE = re.compile(
    r"\s*[\[\(]?(?:1080p|720p|2160p|4K|UHD|HDR|BluRay|BDRip|WEB[-_.]?DL|WEBRip|"
    r"HEVC|x264|x265|H\.?264|H\.?265|AAC|FLAC|DTS|REMUX|REPACK)[\]\)]?\b.*",
    re.IGNORECASE,
)

# 年份噪声：(2023) / [2023] / .2023.
_YEAR_RE = re.compile(r"\s*[\[\(\.]?(?:19|20)\d{2}[\]\)\.]?\s*")


def extract_av_codes(title: str) -> List[str]:
    """从标题中抽取番号候选。

    保持出现顺序，去重，统一大写。
    "ADN-351 ..." → ["ADN-351"]
    "Movie ABC123" → ["ABC-123"]（自动补连字符）
    """
    if not title:
        return []
    seen = set()
    result: List[str] = []
    for letters, digits in _AV_CODE_RE.findall(title):
        normalized = f"{letters.upper()}-{digits}"
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def build_search_queries(title: str) -> List[str]:
    """生成用于搜索的候选 query 列表，按优先级排序，去重。"""
    if not title:
        return []
    raw = title.strip()
    if not raw:
        return []

    queries: List[str] = []

    def _push(value: str) -> None:
        v = (value or "").strip()
        if v and v not in queries:
            queries.append(v)

    # 1. 番号（最强信号）
    for code in extract_av_codes(raw):
        _push(code)

    # 2. 原标题
    _push(raw)

    # 3. 去 SxxExx 取剧集主名
    series_match = _SERIES_EP_RE.match(raw)
    if series_match:
        _push(series_match.group(1))

    # 4. 剥噪声
    cleaned = _NOISE_RE.sub("", raw)
    cleaned = _YEAR_RE.sub(" ", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    _push(cleaned)

    return queries


__all__ = ["extract_av_codes", "build_search_queries"]
