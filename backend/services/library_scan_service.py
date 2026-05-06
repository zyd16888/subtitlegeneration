"""
媒体库批量字幕扫描服务。

针对单个 Emby 媒体库下的所有媒体项，逐个调用迅雷字幕 API：
  - 命中且达阈值 → 下载并落盘到视频目录、刷 Emby
  - 未命中 / 字幕已存在（按配置）→ 跳过
  - 失败 → 记录到 report，继续下一项

整个扫描作为一个 Celery 任务存在，进度即"已处理项 / 总项数"。
取消通过周期检查 Task.status 实现，命中 CANCELLED 即中止并写入部分报告。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional

from sqlalchemy import update

from models.task import Task, TaskStatus
from services.emby_connector import EmbyConnector, MediaItem
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
from services.subtitle_search.ranker import pick_best_per_language, rank_hits

logger = logging.getLogger(__name__)


@dataclass
class LibraryScanRequest:
    """库扫描参数。"""

    library_id: str
    target_languages: Optional[List[str]] = None  # None 时使用 config.target_languages
    skip_if_has_subtitle: bool = True             # 媒体项已有字幕则跳过
    max_items: int = 0                            # 0 = 不限
    concurrency: int = 3                          # 并发处理项数量
    item_type: Optional[str] = None               # 可选：仅扫某类型（Movie / Episode）


@dataclass
class LibraryScanItemReport:
    """单个媒体项的扫描结果。"""

    media_item_id: str
    name: str
    outcome: str  # applied | no_match | skipped_already_has_subtitle | error | cancelled
    languages: List[str] = field(default_factory=list)
    score: Optional[float] = None
    error: Optional[str] = None


@dataclass
class LibraryScanReport:
    """整库扫描汇总报告。"""

    library_id: str
    library_name: str
    target_languages: List[str]
    skip_if_has_subtitle: bool
    scanned_total: int = 0
    applied: int = 0
    no_match: int = 0
    skipped_already_has_subtitle: int = 0
    errors: int = 0
    cancelled: bool = False
    halted_reason: Optional[str] = None
    items: List[LibraryScanItemReport] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ── 内部工具 ────────────────────────────────────────────────────────────────


async def _enumerate_library_items(
    emby: EmbyConnector,
    library_id: str,
    item_type: Optional[str],
    limit_total: int,
) -> List[MediaItem]:
    """分页拉取整个库的媒体项。"""
    items: List[MediaItem] = []
    page_size = 200
    offset = 0
    while True:
        page, total = await emby.get_media_items(
            library_id=library_id,
            item_type=item_type,
            limit=page_size,
            offset=offset,
        )
        items.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
        if limit_total > 0 and len(items) >= limit_total:
            items = items[:limit_total]
            break
    return items


def _check_cancelled(session_factory, task_id: str) -> bool:
    """读 DB 检查任务是否被外部取消。"""
    try:
        session = session_factory()
        try:
            row = session.query(Task).filter(Task.id == task_id).first()
            return bool(row and row.status == TaskStatus.CANCELLED)
        finally:
            session.close()
    except Exception:
        return False


def _write_progress(
    session_factory,
    task_id: str,
    progress: int,
    extra_info_patch: Optional[dict] = None,
) -> None:
    """直接 UPDATE 进度 + 可选 extra_info 增量。"""
    try:
        session = session_factory()
        try:
            if extra_info_patch is not None:
                row = session.query(Task).filter(Task.id == task_id).first()
                if row:
                    merged = dict(row.extra_info) if row.extra_info else {}
                    merged.update(extra_info_patch)
                    row.extra_info = merged
                    row.progress = progress
                    session.commit()
            else:
                session.execute(
                    update(Task).where(Task.id == task_id).values(progress=progress)
                )
                session.commit()
        finally:
            session.close()
    except Exception as exc:
        logger.warning(f"[{task_id}] 库扫描进度写库失败: {exc}")


# ── 主流程 ──────────────────────────────────────────────────────────────────


async def run_library_scan(
    request: LibraryScanRequest,
    task_id: str,
    config,
    session_factory: Callable,
) -> LibraryScanReport:
    """执行整库扫描。返回最终 report。"""
    if not config.emby_url or not config.emby_api_key:
        raise RuntimeError("Emby 未配置，无法扫描")
    if not config.path_mappings:
        raise RuntimeError("未配置路径映射规则，无法将字幕落盘到视频目录")

    target_languages = list(request.target_languages or config.target_languages or [config.target_language])
    target_languages = [code for code in target_languages if code]
    if not target_languages:
        raise RuntimeError("未指定任何目标语言")

    timeout = float(getattr(config, "subtitle_search_timeout", 5) or 5)
    min_score = float(getattr(config, "subtitle_search_min_score", 0.7) or 0.7)
    concurrency = max(1, min(int(request.concurrency or 3), 10))

    report = LibraryScanReport(
        library_id=request.library_id,
        library_name="",
        target_languages=target_languages,
        skip_if_has_subtitle=request.skip_if_has_subtitle,
    )

    async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
        # 拿库名
        try:
            libraries = await emby.get_libraries()
            for lib in libraries:
                if lib.id == request.library_id:
                    report.library_name = lib.name
                    break
        except Exception as exc:
            logger.warning(f"[{task_id}] 获取库列表失败（不致命）: {exc}")

        # 列举媒体项
        _write_progress(
            session_factory, task_id, 1,
            extra_info_patch={"task_type": "library_subtitle_scan"},
        )
        try:
            items = await _enumerate_library_items(
                emby, request.library_id, request.item_type, request.max_items
            )
        except Exception as exc:
            raise RuntimeError(f"列举媒体项失败: {exc}") from exc

        report.scanned_total = len(items)
        logger.info(
            f"[{task_id}] 库扫描开始 library={request.library_id} "
            f"items={len(items)} targets={target_languages} concurrency={concurrency}"
        )

        if not items:
            return report

        client = XunleiSubtitleClient(timeout=timeout)
        sem = asyncio.Semaphore(concurrency)
        completed = 0
        completed_lock = asyncio.Lock()
        consecutive_errors = 0
        consecutive_lock = asyncio.Lock()
        last_persist_at = time.monotonic()
        cancelled_event = asyncio.Event()

        async def _process_one(item: MediaItem) -> LibraryScanItemReport:
            nonlocal consecutive_errors
            item_report = LibraryScanItemReport(
                media_item_id=item.id,
                name=item.name,
                outcome="error",
            )
            if cancelled_event.is_set():
                item_report.outcome = "cancelled"
                return item_report

            async with sem:
                if cancelled_event.is_set():
                    item_report.outcome = "cancelled"
                    return item_report

                # 1. 跳过已有字幕的（按配置）
                if request.skip_if_has_subtitle and item.has_subtitles:
                    item_report.outcome = "skipped_already_has_subtitle"
                    return item_report

                # 2. 调 API
                try:
                    media_duration_ms = await emby.get_media_duration_ms(item.id)
                except Exception:
                    media_duration_ms = None

                try:
                    hits = await client.search(item.name)
                    async with consecutive_lock:
                        consecutive_errors = 0
                except SubtitleSearchError as exc:
                    item_report.error = str(exc)
                    async with consecutive_lock:
                        consecutive_errors += 1
                        if consecutive_errors >= 5:
                            cancelled_event.set()
                            report.halted_reason = (
                                "API 连续失败 5 次，扫描中止以避免被封"
                            )
                    return item_report

                # 3. 评分（严格匹配）
                ranked = rank_hits(
                    hits,
                    target_languages=target_languages,
                    media_duration_ms=media_duration_ms,
                    require_target_match=True,
                )
                picks = pick_best_per_language(ranked, target_languages)
                qualified = {
                    lang: r for lang, r in picks.items() if r.score >= min_score
                }
                if not qualified:
                    item_report.outcome = "no_match"
                    return item_report

                # 4. 下载到临时目录（每项独立目录便于清理）
                staging = tempfile.mkdtemp(prefix=f"libscan_{item.id}_")
                try:
                    downloaded_list = []
                    download_failed = False
                    for lang, ranked_hit in qualified.items():
                        try:
                            downloaded = await download_and_resolve(
                                ranked_hit,
                                save_dir=staging,
                                video_basename="search",
                                timeout=timeout,
                                force_content_detection=False,
                            )
                            downloaded_list.append(downloaded)
                        except SubtitleDownloadError as exc:
                            item_report.error = f"下载{lang}失败: {exc}"
                            download_failed = True
                            break
                    if download_failed:
                        return item_report

                    # 5. 应用每个字幕
                    applied_codes: List[str] = []
                    best_score = max(r.score for r in qualified.values())
                    for sub in downloaded_list:
                        try:
                            applied = await apply_downloaded_subtitle(
                                sub,
                                item.id,
                                emby_url=config.emby_url,
                                emby_api_key=config.emby_api_key,
                                path_mappings=config.path_mappings,
                                library_id=request.library_id,
                                refresh_metadata=True,
                            )
                            if applied.language.code:
                                applied_codes.append(applied.language.code)
                        except SubtitleApplyError as exc:
                            item_report.error = f"应用失败: {exc}"
                            return item_report
                        except ValueError as exc:
                            item_report.error = f"媒体项错误: {exc}"
                            return item_report

                    item_report.outcome = "applied"
                    item_report.languages = applied_codes
                    item_report.score = round(best_score, 3)
                    return item_report
                finally:
                    shutil.rmtree(staging, ignore_errors=True)

        async def _runner():
            nonlocal completed, last_persist_at
            tasks_pending = []
            for item in items:
                tasks_pending.append(asyncio.create_task(_process_one(item)))

            for fut in asyncio.as_completed(tasks_pending):
                try:
                    item_report = await fut
                except Exception as exc:
                    logger.error(f"[{task_id}] 扫描项异常: {exc}", exc_info=True)
                    item_report = LibraryScanItemReport(
                        media_item_id="?",
                        name="?",
                        outcome="error",
                        error=str(exc),
                    )
                report.items.append(item_report)

                if item_report.outcome == "applied":
                    report.applied += 1
                elif item_report.outcome == "no_match":
                    report.no_match += 1
                elif item_report.outcome == "skipped_already_has_subtitle":
                    report.skipped_already_has_subtitle += 1
                elif item_report.outcome == "cancelled":
                    pass  # 不计入失败
                else:
                    report.errors += 1

                async with completed_lock:
                    completed += 1
                    pct = 1 + int(completed / len(items) * 98)  # 1..99 留 100 给收尾

                # 周期性外部取消检查 + 进度持久化（每 ~3 秒或每 5 项）
                now = time.monotonic()
                should_persist = (now - last_persist_at) > 3.0 or completed % 5 == 0
                if _check_cancelled(session_factory, task_id):
                    cancelled_event.set()
                    report.cancelled = True
                    if not report.halted_reason:
                        report.halted_reason = "用户取消"
                if should_persist:
                    last_persist_at = now
                    _write_progress(
                        session_factory, task_id, pct,
                        extra_info_patch={
                            "task_type": "library_subtitle_scan",
                            "scan_report": _serializable_report(report),
                        },
                    )

                if cancelled_event.is_set():
                    # 取消后取消其余 pending 任务
                    for t in tasks_pending:
                        if not t.done():
                            t.cancel()
                    break

        await _runner()

    logger.info(
        f"[{task_id}] 库扫描完成 applied={report.applied} no_match={report.no_match} "
        f"skipped={report.skipped_already_has_subtitle} errors={report.errors} "
        f"cancelled={report.cancelled}"
    )
    return report


def _serializable_report(report: LibraryScanReport) -> dict:
    """转换为可 JSON 序列化的 dict（asdict 已能处理 dataclass，仅做防御性 round-trip）。"""
    try:
        d = report.to_dict()
        json.dumps(d)
        return d
    except Exception:
        # 兜底：丢弃 items 详情，只保留摘要
        return {
            "library_id": report.library_id,
            "library_name": report.library_name,
            "target_languages": report.target_languages,
            "scanned_total": report.scanned_total,
            "applied": report.applied,
            "no_match": report.no_match,
            "skipped_already_has_subtitle": report.skipped_already_has_subtitle,
            "errors": report.errors,
            "cancelled": report.cancelled,
            "halted_reason": report.halted_reason,
        }
