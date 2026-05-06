"""
字幕搜索 API（迅雷字幕 API 集成）。

提供两个端点：
  GET  /api/subtitle-search          搜索字幕（可选 media_item_id 用于时长加权）
  POST /api/subtitle-search/apply    下载选中的字幕并复制到视频目录、刷新 Emby
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.base import get_db
from services.auth import require_auth
from services.config_manager import ConfigManager
from services.emby_connector import EmbyConnector
from services.subtitle_search import (
    DownloadedSubtitle,
    LanguageResolution,
    LanguageSource,
    RankedHit,
)
from services.subtitle_search.applier import (
    SubtitleApplyError,
    apply_downloaded_subtitle,
)
from services.subtitle_search.client import (
    SubtitleSearchError,
    XunleiSubtitleClient,
)
from services.subtitle_search.downloader import (
    SubtitleDownloadError,
    download_and_resolve,
)
from services.subtitle_search.ranker import rank_hits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["subtitle_search"], dependencies=[Depends(require_auth)])


# ── 响应/请求模型 ──────────────────────────────────────────────────────────


class LanguageInfo(BaseModel):
    code: Optional[str] = None
    source: str = "unknown"
    confidence: float = 0.0
    is_bilingual: bool = False
    secondary_code: Optional[str] = None


class SubtitleSearchResultDTO(BaseModel):
    gcid: str
    cid: str
    url: str
    ext: str
    name: str
    duration_ms: int
    raw_languages: List[str] = Field(default_factory=list)
    extra_name: Optional[str] = None
    language: LanguageInfo
    score: float
    duration_match: float
    score_breakdown: dict


class SubtitleSearchResponse(BaseModel):
    query: str
    media_duration_ms: Optional[int] = None
    target_languages: List[str] = Field(default_factory=list)
    items: List[SubtitleSearchResultDTO]


class SubtitleApplyRequest(BaseModel):
    media_item_id: str
    url: str
    ext: str
    name: Optional[str] = None
    raw_languages: List[str] = Field(default_factory=list)
    library_id: Optional[str] = None
    path_mapping_index: Optional[int] = None
    # 用户手动覆盖：若指定，跳过自动语言识别（含内容检测）
    force_language: Optional[str] = None


class SubtitleApplyResponse(BaseModel):
    media_item_id: str
    target_path: str
    ext: str
    language: LanguageInfo
    emby_refreshed: bool
    source_url: str
    file_size: int


# ── 工具函数 ────────────────────────────────────────────────────────────────


def _language_to_dto(language: LanguageResolution) -> LanguageInfo:
    return LanguageInfo(
        code=language.code,
        source=language.source.value if isinstance(language.source, LanguageSource) else str(language.source),
        confidence=round(float(language.confidence), 3),
        is_bilingual=language.is_bilingual,
        secondary_code=language.secondary_code,
    )


def _ranked_to_dto(ranked: RankedHit) -> SubtitleSearchResultDTO:
    hit = ranked.hit
    return SubtitleSearchResultDTO(
        gcid=hit.gcid,
        cid=hit.cid,
        url=hit.url,
        ext=hit.ext,
        name=hit.name,
        duration_ms=hit.duration_ms,
        raw_languages=hit.raw_languages,
        extra_name=hit.extra_name,
        language=_language_to_dto(ranked.language),
        score=round(float(ranked.score), 3),
        duration_match=round(float(ranked.duration_match), 3),
        score_breakdown=ranked.score_breakdown,
    )


async def _get_search_config(db: Session):
    """加载配置并校验字幕搜索开关已启用。"""
    config = await ConfigManager(db).get_config()
    if not config.subtitle_search_enabled:
        raise HTTPException(status_code=400, detail="字幕搜索功能未启用，请先在设置中开启")
    return config


# ── 端点 ────────────────────────────────────────────────────────────────────


@router.get("/subtitle-search", response_model=SubtitleSearchResponse)
async def search_subtitles(
    query: str = Query(..., min_length=1, description="搜索关键词，如电影名、剧集 SxxExx 或番号"),
    media_item_id: Optional[str] = Query(None, description="可选：用于获取媒体时长以加权"),
    db: Session = Depends(get_db),
):
    """搜索字幕候选（不下载）。

    - 当配置启用时才可用。
    - 提供 media_item_id 时会读取 Emby 媒体时长，用于评分加权。
    - 返回结果按综合分数倒序排列；语言识别失败的条目仍会返回（手动模式由用户挑）。
    """
    config = await _get_search_config(db)

    media_duration_ms: Optional[int] = None
    if media_item_id and config.emby_url and config.emby_api_key:
        try:
            async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                media_duration_ms = await emby.get_media_duration_ms(media_item_id)
        except Exception as exc:
            logger.warning(f"获取媒体时长失败，跳过时长加权: {exc}")

    client = XunleiSubtitleClient(timeout=float(config.subtitle_search_timeout))
    try:
        hits = await client.search(query)
    except SubtitleSearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    ranked = rank_hits(
        hits,
        target_languages=list(config.target_languages or [config.target_language]),
        media_duration_ms=media_duration_ms,
        require_target_match=False,
    )

    return SubtitleSearchResponse(
        query=query,
        media_duration_ms=media_duration_ms,
        target_languages=list(config.target_languages or [config.target_language]),
        items=[_ranked_to_dto(r) for r in ranked],
    )


@router.post("/subtitle-search/apply", response_model=SubtitleApplyResponse)
async def apply_subtitle(
    request: SubtitleApplyRequest,
    db: Session = Depends(get_db),
):
    """下载选中的字幕，落盘到视频目录并刷新 Emby 元数据。

    - force_language 非空时跳过自动语言识别，按指定语言归档。
    - 路径映射缺失或视频文件不存在时返回 400。
    """
    config = await _get_search_config(db)

    if not config.path_mappings:
        raise HTTPException(status_code=400, detail="未配置路径映射规则，无法将字幕落盘到视频目录")

    # 构造 RankedHit（apply 阶段不再重新评分，只需要 hit + 元信息层级语言）
    from services.subtitle_search.lang_sniffer import resolve_from_metadata
    from services.subtitle_search.types import RankedHit, SearchHit

    if request.force_language:
        forced_language = LanguageResolution(
            code=request.force_language,
            source=LanguageSource.API_FIELD,
            confidence=1.0,
        )
        meta_language = forced_language
    else:
        meta_language = resolve_from_metadata(
            request.raw_languages, request.name or ""
        ) or LanguageResolution(code=None, source=LanguageSource.UNKNOWN, confidence=0.0)

    hit = SearchHit(
        gcid="",
        cid="",
        url=request.url,
        ext=(request.ext or "srt").lower(),
        name=request.name or "",
        duration_ms=0,
        raw_languages=list(request.raw_languages or []),
    )
    ranked = RankedHit(hit=hit, language=meta_language, score=1.0)

    # 临时下载目录：不污染任务工作目录，应用成功后立即清理
    staging_dir = tempfile.mkdtemp(prefix="subtitle_search_")
    downloaded: Optional[DownloadedSubtitle] = None
    try:
        try:
            downloaded = await download_and_resolve(
                ranked,
                save_dir=staging_dir,
                video_basename="downloaded",
                force_content_detection=request.force_language is None,
            )
        except SubtitleDownloadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        # 用户强制语言时，覆盖 downloader 内部可能跑过的内容检测结果
        if request.force_language:
            downloaded = DownloadedSubtitle(
                local_path=downloaded.local_path,
                language=LanguageResolution(
                    code=request.force_language,
                    source=LanguageSource.API_FIELD,
                    confidence=1.0,
                ),
                ext=downloaded.ext,
                source_url=downloaded.source_url,
                file_size=downloaded.file_size,
            )

        try:
            applied = await apply_downloaded_subtitle(
                downloaded,
                request.media_item_id,
                emby_url=config.emby_url,
                emby_api_key=config.emby_api_key,
                path_mappings=config.path_mappings,
                library_id=request.library_id,
                path_mapping_index=request.path_mapping_index,
                refresh_metadata=True,
            )
        except SubtitleApplyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            logger.error(f"字幕应用失败: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"字幕应用失败: {exc}")

        return SubtitleApplyResponse(
            media_item_id=applied.media_item_id,
            target_path=applied.target_path,
            ext=applied.ext,
            language=_language_to_dto(applied.language),
            emby_refreshed=applied.emby_refreshed,
            source_url=applied.source_url,
            file_size=downloaded.file_size,
        )
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass
