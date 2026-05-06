"""
字幕文件下载与编码归一化。

输入：RankedHit（已经过元信息层级语言判定）+ 保存目录
流程：
  1. HTTP GET 拉取原始字节
  2. chardet 探测编码 → 解码为 UTF-8 文本
  3. 如果元信息未判出语言（或显式要求验证），用文本内容做 L3 检测
  4. 写入 {save_dir}/{video_basename}.{lang_code}.{ext}（UTF-8 无 BOM）
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

import httpx

from .lang_sniffer import (
    decode_subtitle_bytes,
    detect_from_content,
    extract_text_from_ass,
    extract_text_from_srt,
)
from .types import DownloadedSubtitle, LanguageResolution, LanguageSource, RankedHit

logger = logging.getLogger(__name__)


DEFAULT_DOWNLOAD_TIMEOUT = 15.0
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB 字幕已极端，超过视为异常


class SubtitleDownloadError(Exception):
    """字幕下载或解码失败。"""


_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename_part(value: str) -> str:
    """把任意字符串处理成可作为文件名片段的形式。"""
    if not value:
        return ""
    cleaned = _INVALID_FS_CHARS.sub("_", value).strip(" .")
    return cleaned or ""


def build_subtitle_filename(
    video_basename: str,
    language: LanguageResolution,
    ext: str,
) -> str:
    """构造保存文件名：{basename}.{lang_code}.{ext}。

    - 未知语言用 "unknown"
    - lang_code 自身不带 "."、"/"、空格
    - 扩展名小写
    """
    safe_base = _safe_filename_part(video_basename) or "subtitle"
    code = language.code or "unknown"
    safe_code = _safe_filename_part(code) or "unknown"
    safe_ext = (ext or "srt").strip(" .").lower() or "srt"
    return f"{safe_base}.{safe_code}.{safe_ext}"


async def download_and_resolve(
    ranked: RankedHit,
    save_dir: str,
    video_basename: str,
    *,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
    force_content_detection: bool = False,
) -> DownloadedSubtitle:
    """下载字幕、解码为 UTF-8、必要时做内容语言检测、写盘。"""
    hit = ranked.hit
    if not hit.url:
        raise SubtitleDownloadError("字幕条目缺少 URL")

    os.makedirs(save_dir, exist_ok=True)

    # 1. 下载
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(hit.url)
            resp.raise_for_status()
            raw = resp.content
    except httpx.HTTPError as exc:
        raise SubtitleDownloadError(f"下载字幕失败: {exc}") from exc

    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise SubtitleDownloadError(
            f"字幕文件过大: {len(raw)} bytes (上限 {MAX_DOWNLOAD_BYTES})"
        )

    if not raw.strip():
        raise SubtitleDownloadError("字幕文件为空")

    # 2. 解码为 UTF-8 文本
    text = decode_subtitle_bytes(raw)
    if not text.strip():
        raise SubtitleDownloadError("字幕文件解码后为空")

    is_ass = (hit.ext or "").lower() == "ass"

    # 3. 语言判定：元信息够用就直接用；否则做 L3
    language = ranked.language
    needs_content = (
        force_content_detection
        or language.code is None
        or language.source == LanguageSource.UNKNOWN
    )
    if needs_content:
        sample_text = (
            extract_text_from_ass(text) if is_ass else extract_text_from_srt(text)
        )
        content_resolution = detect_from_content(sample_text)
        # 元信息和内容相互验证
        language = _merge_resolutions(language, content_resolution)

    # 4. 写盘
    filename = build_subtitle_filename(video_basename, language, hit.ext)
    target_path = os.path.join(save_dir, filename)
    try:
        with open(target_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        raise SubtitleDownloadError(f"写入字幕文件失败: {exc}") from exc

    file_size = os.path.getsize(target_path)
    logger.info(
        f"字幕已下载: {hit.url} → {target_path} "
        f"(lang={language.code} src={language.source.value} size={file_size}B)"
    )

    return DownloadedSubtitle(
        local_path=target_path,
        language=language,
        ext=(hit.ext or "srt").lower(),
        source_url=hit.url,
        file_size=file_size,
    )


def _merge_resolutions(
    meta: LanguageResolution,
    content: LanguageResolution,
) -> LanguageResolution:
    """合并元信息层级与内容层级判定结果。

    优先策略：
      - 元信息已识别且内容也识别 → 优先元信息，置信度取较高者
      - 元信息未识别但内容识别 → 用内容
      - 内容识别为双语 → 透传双语标记
      - 都未识别 → unknown
    """
    if meta.code and content.code:
        # 二者一致：拉满置信度
        if meta.code == content.code:
            return LanguageResolution(
                code=meta.code,
                source=meta.source,
                confidence=max(meta.confidence, content.confidence, 0.95),
                is_bilingual=meta.is_bilingual or content.is_bilingual,
                secondary_code=meta.secondary_code or content.secondary_code,
            )
        # 不一致：信任置信度更高的；置信度差不多则信元信息（API/文件名比启发式更稳）
        if content.confidence > meta.confidence + 0.1:
            return content
        return LanguageResolution(
            code=meta.code,
            source=meta.source,
            confidence=meta.confidence,
            is_bilingual=meta.is_bilingual,
            secondary_code=meta.secondary_code or content.code,
        )
    if meta.code:
        return meta
    if content.code:
        return content
    return LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=0.0)
