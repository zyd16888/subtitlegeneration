"""
把已下载的字幕落盘到视频目录并刷新 Emby 元数据。

复用项目既有的 path_mapping + EmbyConnector 流程，与
`subtitle_output_pipeline._copy_subtitles_to_video_dir` 行为对齐，
但额外支持 .ass 等非 .srt 扩展名。
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

from services.emby_connector import EmbyConnector
from services.path_mapping import apply_path_mapping

from .downloader import build_subtitle_filename
from .types import AppliedSubtitle, DownloadedSubtitle

logger = logging.getLogger(__name__)


class SubtitleApplyError(Exception):
    """字幕应用失败（路径映射缺失、视频文件不存在、复制失败等）。"""


async def apply_downloaded_subtitle(
    downloaded: DownloadedSubtitle,
    media_item_id: str,
    *,
    emby_url: Optional[str],
    emby_api_key: Optional[str],
    path_mappings: list,
    library_id: Optional[str] = None,
    path_mapping_index: Optional[int] = None,
    refresh_metadata: bool = True,
) -> AppliedSubtitle:
    """把已下载到本地的字幕复制到视频目录，并按需刷新 Emby。"""
    if not emby_url or not emby_api_key:
        raise SubtitleApplyError("Emby 未配置，无法定位视频路径")

    if not path_mappings:
        raise SubtitleApplyError("未配置路径映射规则，无法将字幕落盘到视频目录")

    if not os.path.exists(downloaded.local_path):
        raise SubtitleApplyError(f"已下载字幕不存在: {downloaded.local_path}")

    # 1. 拿视频物理路径 + 路径映射
    async with EmbyConnector(emby_url, emby_api_key) as emby:
        emby_video_path = await emby.get_media_file_path(media_item_id)
        local_video_path = apply_path_mapping(
            emby_video_path,
            path_mappings,
            path_mapping_index=path_mapping_index,
            library_id=library_id,
        )
        if not local_video_path:
            raise SubtitleApplyError(
                f"路径映射未匹配，Emby 路径: {emby_video_path}"
            )
        if not os.path.exists(local_video_path):
            raise SubtitleApplyError(
                f"本地视频文件不存在: {local_video_path}（请检查路径映射）"
            )

        # 2. 复制
        video_basename = os.path.splitext(os.path.basename(local_video_path))[0]
        video_dir = os.path.dirname(local_video_path)
        target_filename = build_subtitle_filename(
            video_basename, downloaded.language, downloaded.ext
        )
        target_path = os.path.join(video_dir, target_filename)

        try:
            shutil.copy2(downloaded.local_path, target_path)
        except OSError as exc:
            raise SubtitleApplyError(f"复制字幕到视频目录失败: {exc}") from exc

        logger.info(
            f"字幕已应用 [media={media_item_id} lang={downloaded.language.code}]: "
            f"{downloaded.local_path} → {target_path}"
        )

        # 3. 刷新 Emby
        emby_refreshed = False
        if refresh_metadata:
            try:
                emby_refreshed = bool(await emby.refresh_metadata(media_item_id))
            except Exception as exc:
                logger.warning(
                    f"刷新 Emby 元数据失败（字幕已落盘）: media={media_item_id} err={exc}"
                )
                emby_refreshed = False

    return AppliedSubtitle(
        media_item_id=media_item_id,
        language=downloaded.language,
        ext=downloaded.ext,
        target_path=target_path,
        emby_refreshed=emby_refreshed,
        source_url=downloaded.source_url,
    )
