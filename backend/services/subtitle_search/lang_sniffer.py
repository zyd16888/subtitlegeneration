"""
字幕语言识别多层级流水线。

判定级联（按优先级）：
  L1  API languages 字段 → 名称映射表
  L2  文件名正则提取（zh-TW、English、简体...）
  L3  字幕内容检测（chardet 解码 + 文本剥离 + langdetect）
  L4  unknown 兜底

所有出口归一化为项目使用的语言码：
  zh / zh-Hant / en / ja / ko / fr / de / es / ru / pt / it / th / vi / ar
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List, Optional, Tuple

from .types import LanguageResolution, LanguageSource

logger = logging.getLogger(__name__)


# ── 归一化目标语言码集合（与 config_manager._SUPPORTED_LANGUAGE_CODES 对齐）────
_NORMALIZED_CODES = {
    "zh", "zh-Hant", "en", "ja", "ko", "fr", "de", "es", "ru",
    "pt", "it", "th", "vi", "ar", "yue",
}


# ── L1：API languages 字段映射 ──────────────────────────────────────────────
# 单字段值 → 归一化语言码；返回 None 表示该值不足以判定（如 "" / "默认"）
_API_FIELD_MAP = {
    # 中文系
    "简体": "zh",
    "简": "zh",
    "中文": "zh",
    "chs": "zh",
    "chi": "zh",
    "zh": "zh",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "繁体": "zh-Hant",
    "繁": "zh-Hant",
    "cht": "zh-Hant",
    "zh-tw": "zh-Hant",
    "zh-hk": "zh-Hant",
    "zh-hant": "zh-Hant",
    # 英文
    "english": "en",
    "英文": "en",
    "en": "en",
    "eng": "en",
    # 日文
    "japanese": "ja",
    "日文": "ja",
    "日语": "ja",
    "日": "ja",
    "ja": "ja",
    "jp": "ja",
    "jpn": "ja",
    # 韩文
    "korean": "ko",
    "韩文": "ko",
    "ko": "ko",
    "kor": "ko",
    # 其它
    "fr": "fr", "french": "fr", "法语": "fr", "法文": "fr",
    "de": "de", "german": "de", "德语": "de", "德文": "de",
    "es": "es", "spanish": "es", "西班牙语": "es",
    "ru": "ru", "russian": "ru", "俄语": "ru", "俄文": "ru",
    "pt": "pt", "portuguese": "pt",
    "it": "it", "italian": "it",
    "th": "th", "thai": "th",
    "vi": "vi", "vietnamese": "vi",
    "ar": "ar", "arabic": "ar",
}

# 视为"无效语言信息"的占位符
_API_FIELD_PLACEHOLDERS = {"", "默认", "default", "未知", "unknown", "n/a", "none", "其他", "other"}


def _normalize_api_field(value: str) -> Optional[str]:
    """API languages 单值 → 归一化语言码。无法判定返回 None。"""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    key = raw.lower()
    if key in _API_FIELD_PLACEHOLDERS or raw in _API_FIELD_PLACEHOLDERS:
        return None
    return _API_FIELD_MAP.get(key)


# ── L2：文件名正则 ─────────────────────────────────────────────────────────
# 顺序很关键：优先匹配信息量大的 token，再回退到短码
_FILENAME_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # 长形式 / 区域码（区分简繁）
    (re.compile(r"\bzh[-_.]?(?:hant|tw|hk|mo)\b", re.IGNORECASE), "zh-Hant"),
    (re.compile(r"\bzh[-_.]?(?:hans|cn|sg)\b", re.IGNORECASE), "zh"),
    (re.compile(r"\b(?:cht|chinese[-_.]?traditional|tc|big5)\b", re.IGNORECASE), "zh-Hant"),
    (re.compile(r"\b(?:chs|chinese[-_.]?simplified|sc|gb)\b", re.IGNORECASE), "zh"),
    (re.compile(r"繁體|繁体|正體|正体"), "zh-Hant"),
    (re.compile(r"简體|简体|簡體"), "zh"),
    (re.compile(r"中文"), "zh"),
    # 英文
    (re.compile(r"\b(?:english|eng|en)\b", re.IGNORECASE), "en"),
    (re.compile(r"英文|英语"), "en"),
    # 日文
    (re.compile(r"\b(?:japanese|jpn|jp|ja)\b", re.IGNORECASE), "ja"),
    (re.compile(r"日文|日语|日語"), "ja"),
    # 韩文
    (re.compile(r"\b(?:korean|kor|ko)\b", re.IGNORECASE), "ko"),
    (re.compile(r"韩文|韩语|韓文|韓語"), "ko"),
    # 其它
    (re.compile(r"\b(?:french|fra|fr)\b", re.IGNORECASE), "fr"),
    (re.compile(r"\b(?:german|deu|ger|de)\b", re.IGNORECASE), "de"),
    (re.compile(r"\b(?:spanish|spa|esp|es)\b", re.IGNORECASE), "es"),
    (re.compile(r"\b(?:russian|rus|ru)\b", re.IGNORECASE), "ru"),
    (re.compile(r"\b(?:portuguese|por|pt)\b", re.IGNORECASE), "pt"),
    (re.compile(r"\b(?:italian|ita|it)\b", re.IGNORECASE), "it"),
    (re.compile(r"\b(?:thai|tha|th)\b", re.IGNORECASE), "th"),
    (re.compile(r"\b(?:vietnamese|vie|vi)\b", re.IGNORECASE), "vi"),
    (re.compile(r"\b(?:arabic|ara|ar)\b", re.IGNORECASE), "ar"),
]

# 检测双语文件名（中日 / 中英 双轨）
_BILINGUAL_HINTS = re.compile(
    r"双语|雙語|中日|中英|中韩|中韓|chs[-_.]?eng|chs[-_.]?jpn|cht[-_.]?eng|"
    r"bilingual|dual",
    re.IGNORECASE,
)

# 纯 hash 文件名（40 位十六进制，例如 34E0CD5C5CD75008A57786B32375B913113E9396.srt）
_HASH_NAME_RE = re.compile(r"^[0-9a-fA-F]{32,64}$")


def is_hash_only_name(filename: str) -> bool:
    """判断文件名（不含扩展名）是否纯哈希。"""
    if not filename:
        return False
    stem = filename.rsplit(".", 1)[0]
    return bool(_HASH_NAME_RE.match(stem))


def _detect_from_filename(filename: str) -> List[str]:
    """从文件名抽取所有命中的语言码（按 _FILENAME_PATTERNS 顺序，去重）。"""
    if not filename:
        return []
    seen = set()
    result: List[str] = []
    for pattern, code in _FILENAME_PATTERNS:
        if pattern.search(filename) and code not in seen:
            seen.add(code)
            result.append(code)
    return result


# ── L3：字幕内容检测 ───────────────────────────────────────────────────────
_SRT_TIMESTAMP_RE = re.compile(r"-->")
_SRT_TAG_RE = re.compile(r"<[^>]+>")           # <i>, <b>, <font>
_ASS_STYLE_RE = re.compile(r"\{[^}]*\}")        # {\b1\i1}
_ASS_DIALOGUE_PREFIX = re.compile(r"^Dialogue\s*:", re.IGNORECASE)


def extract_text_from_srt(content: str, max_lines: int = 200) -> str:
    """剥离 SRT 时间戳/序号/HTML 标签，返回纯文本。"""
    out: List[str] = []
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if _SRT_TIMESTAMP_RE.search(s):
            continue
        if s.isdigit():
            continue
        s = _SRT_TAG_RE.sub("", s)
        s = s.replace("\\N", " ").replace("\\h", " ")
        if s:
            out.append(s)
        if len(out) >= max_lines:
            break
    return "\n".join(out)


def extract_text_from_ass(content: str, max_lines: int = 200) -> str:
    """从 ASS 的 [Events] 段提取 Dialogue 行的文本字段。"""
    out: List[str] = []
    in_events = False
    format_fields: List[str] = []
    text_idx: Optional[int] = None

    for line in content.splitlines():
        s = line.rstrip()
        stripped = s.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_events = stripped.lower() == "[events]"
            format_fields = []
            text_idx = None
            continue
        if not in_events:
            continue
        if stripped.lower().startswith("format:"):
            format_fields = [
                f.strip().lower() for f in stripped.split(":", 1)[1].split(",")
            ]
            try:
                text_idx = format_fields.index("text")
            except ValueError:
                text_idx = None
            continue
        if not _ASS_DIALOGUE_PREFIX.match(stripped):
            continue
        # Dialogue 各字段以逗号分隔，最后一个字段是 Text，可能本身含逗号 → split 时限制
        body = stripped.split(":", 1)[1] if ":" in stripped else ""
        # 默认 Text 是最后一个字段；ASS 标准 Format 共 9 列，Text 永远在最后
        if text_idx is None or text_idx < 0:
            split_count = 9
        else:
            split_count = max(1, len(format_fields))
        parts = body.split(",", split_count - 1)
        if len(parts) < split_count:
            text = parts[-1] if parts else ""
        else:
            text = parts[split_count - 1]
        text = _ASS_STYLE_RE.sub("", text)
        text = text.replace("\\N", " ").replace("\\h", " ").strip()
        if text:
            out.append(text)
        if len(out) >= max_lines:
            break
    return "\n".join(out)


def decode_subtitle_bytes(raw: bytes) -> str:
    """探测字节流编码并解码为 str。失败时回退 utf-8 + errors=replace。"""
    if not raw:
        return ""
    # 显式去掉 BOM，避免 chardet 干扰
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
    encoding = None
    try:
        import chardet  # type: ignore

        result = chardet.detect(raw[:65536])
        encoding = (result or {}).get("encoding")
    except ImportError:
        logger.debug("chardet 未安装，跳过编码探测")
    candidates: List[str] = []
    if encoding:
        candidates.append(encoding)
    candidates.extend(["utf-8", "utf-8-sig", "gb18030", "big5", "shift_jis", "euc-kr"])
    seen = set()
    for enc in candidates:
        norm = (enc or "").lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_langdetect(code: str) -> Optional[str]:
    """langdetect 输出 → 项目语言码。"""
    if not code:
        return None
    c = code.lower()
    if c == "zh-cn":
        return "zh"
    if c == "zh-tw":
        return "zh-Hant"
    if c == "zh":
        return "zh"
    if c in _NORMALIZED_CODES:
        return c
    if c.split("-")[0] in _NORMALIZED_CODES:
        return c.split("-")[0]
    return None


def _heuristic_chinese_variant(text: str) -> Optional[str]:
    """简体/繁体启发式：用常见简繁差异字判别。

    仅在 langdetect 检测到 zh 但分不清简繁时使用。
    """
    if not text:
        return None
    trad_markers = "繁體國這個說沒會學寫應為來時實當點還麼讓內無條經產給後從現開傳給響"
    simp_markers = "国这个说没会学写应为来时实当点还么让内无条经产给后从现开传响"
    trad_count = sum(1 for ch in text if ch in trad_markers)
    simp_count = sum(1 for ch in text if ch in simp_markers)
    if trad_count == simp_count == 0:
        return None
    return "zh-Hant" if trad_count > simp_count else "zh"


def detect_from_content(text: str) -> LanguageResolution:
    """对剥离后的纯文本做语言识别。"""
    if not text or not text.strip():
        return LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=0.0)

    sample = text[:5000]
    try:
        from langdetect import DetectorFactory, detect_langs  # type: ignore

        DetectorFactory.seed = 0
        results = detect_langs(sample)
    except ImportError:
        logger.debug("langdetect 未安装，无法做内容语言检测")
        return LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=0.0)
    except Exception as exc:
        logger.debug(f"langdetect 失败: {exc}")
        return LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=0.0)

    if not results:
        return LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=0.0)

    top = results[0]
    top_code = _normalize_langdetect(getattr(top, "lang", ""))
    top_prob = float(getattr(top, "prob", 0.0))

    # 中文需要进一步区分简繁
    if top_code == "zh":
        variant = _heuristic_chinese_variant(sample)
        if variant:
            top_code = variant

    # 双语判定：top-2 都 ≥ 0.3 且语言不同
    secondary_code: Optional[str] = None
    is_bilingual = False
    if len(results) >= 2:
        second = results[1]
        sec_code = _normalize_langdetect(getattr(second, "lang", ""))
        sec_prob = float(getattr(second, "prob", 0.0))
        if (
            top_prob >= 0.3
            and sec_prob >= 0.3
            and sec_code
            and sec_code != top_code
        ):
            is_bilingual = True
            secondary_code = sec_code

    if top_prob < 0.85 and not is_bilingual:
        # 不够自信：标记 unknown，但保留概率以便上层展示
        return LanguageResolution(
            code=None,
            source=LanguageSource.UNKNOWN,
            confidence=top_prob,
        )
    if not top_code:
        return LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=top_prob)

    return LanguageResolution(
        code=top_code,
        source=LanguageSource.CONTENT,
        confidence=top_prob,
        is_bilingual=is_bilingual,
        secondary_code=secondary_code,
    )


# ── 顶层组合 ───────────────────────────────────────────────────────────────


def resolve_from_metadata(
    raw_languages: Iterable[str],
    filename: str,
) -> Optional[LanguageResolution]:
    """L1 + L2：仅靠元信息判定；不足以判定时返回 None。"""
    # L1：API languages 字段
    api_codes: List[str] = []
    for raw in raw_languages or []:
        code = _normalize_api_field(raw)
        if code and code not in api_codes:
            api_codes.append(code)

    # L2：文件名
    name_codes = _detect_from_filename(filename)

    # 合并：API 字段优先，文件名补充
    combined: List[str] = []
    for code in api_codes + name_codes:
        if code not in combined:
            combined.append(code)

    if not combined:
        return None

    bilingual_hint = bool(_BILINGUAL_HINTS.search(filename or ""))
    is_bilingual = bilingual_hint or len(combined) >= 2
    primary = combined[0]
    secondary = combined[1] if len(combined) >= 2 else None

    source = LanguageSource.API_FIELD if api_codes else LanguageSource.FILENAME
    confidence = 0.95 if api_codes else 0.85

    return LanguageResolution(
        code=primary,
        source=source,
        confidence=confidence,
        is_bilingual=is_bilingual,
        secondary_code=secondary,
    )


def resolve_language(
    raw_languages: Iterable[str],
    filename: str,
    content: Optional[str] = None,
    is_ass: bool = False,
) -> LanguageResolution:
    """完整流水线：先元信息再内容。content 为 None 时只走 L1+L2。"""
    meta = resolve_from_metadata(raw_languages, filename)
    if meta is not None:
        return meta

    if content is None:
        return LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=0.0)

    text = extract_text_from_ass(content) if is_ass else extract_text_from_srt(content)
    return detect_from_content(text)
