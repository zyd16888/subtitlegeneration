"""
字幕任务前置：尝试通过迅雷字幕 API 直接拿到现成字幕。

命中条件（必须全部满足）：
  - 用 media_item_title 搜到候选
  - rank 后每个目标语言都有 score >= subtitle_search_min_score 的命中
  - 所有命中字幕成功下载并应用到视频目录

满足以上条件 → 跳过 ASR/翻译/字幕生成阶段，直接 mark_completed。
任何步骤失败 → 返回 None，上层继续走 ASR 管线。
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from services.subtitle_search import AppliedSubtitle, DownloadedSubtitle, RankedHit
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
from services.subtitle_search.lang_sniffer import sniff_url_language
from services.subtitle_search.query_builder import build_search_queries
from services.subtitle_search.ranker import pick_best_per_language, rank_hits, score_hit

logger = logging.getLogger(__name__)


@dataclass
class ExternalSubtitleResult:
    """外部字幕命中后的结果。"""

    applied: List[AppliedSubtitle]
    query: str
    matched_languages: List[str]
    ranked_summary: List[dict] = field(default_factory=list)  # 持久化用的轻量摘要


async def _sniff_unknown_in_pipeline(
    ranked: list,
    target_languages: List[str],
    media_duration_ms: Optional[int],
    timeout: float,
    max_sniff: int = 8,
) -> list:
    """对 ranked 中前 max_sniff 条 language.code is None 的候选并发嗅探。

    与手动模式 _sniff_unknown_languages 的逻辑一致；这里再写一份是为了避免
    pipeline 模块依赖 api 模块。
    """
    from services.subtitle_search.types import RankedHit

    indices = [i for i, r in enumerate(ranked) if r.language.code is None][:max_sniff]
    if not indices:
        return ranked

    sem = asyncio.Semaphore(5)

    async def _one(idx: int):
        async with sem:
            r = ranked[idx]
            return idx, await sniff_url_language(r.hit.url, r.hit.ext, timeout=timeout)

    results = await asyncio.gather(*[_one(i) for i in indices])

    new_ranked = list(ranked)
    changed = False
    for idx, resolution in results:
        if resolution is None or resolution.code is None:
            continue
        old = new_ranked[idx]
        new_ranked[idx] = RankedHit(
            hit=old.hit,
            language=resolution,
            score=old.score,
            duration_match=old.duration_match,
            score_breakdown=old.score_breakdown,
        )
        changed = True

    if not changed:
        return ranked

    rescored = [
        score_hit(r.hit, r.language, target_languages, media_duration_ms)
        for r in new_ranked
    ]
    rescored.sort(key=lambda r: r.score, reverse=True)
    return rescored


async def _download_all(
    picks: Dict[str, RankedHit],
    save_dir: str,
    timeout: float,
) -> Tuple[List[DownloadedSubtitle], List[str]]:
    """并发下载每个目标语言对应的字幕。

    返回 (成功列表, 失败语言列表)。
    """
    if not picks:
        return [], []

    async def _one(target: str, ranked: RankedHit) -> Tuple[str, Optional[DownloadedSubtitle], Optional[str]]:
        try:
            downloaded = await download_and_resolve(
                ranked,
                save_dir=save_dir,
                video_basename="search",  # 临时名；applier 会重命名
                timeout=timeout,
                # 元信息已要求语言匹配，可跳过强制内容检测以节省时间
                force_content_detection=False,
            )
            return target, downloaded, None
        except SubtitleDownloadError as exc:
            return target, None, str(exc)
        except Exception as exc:
            logger.warning(f"下载字幕异常 target={target}: {exc}", exc_info=True)
            return target, None, str(exc)

    results = await asyncio.gather(*[_one(t, r) for t, r in picks.items()])

    successes: List[DownloadedSubtitle] = []
    failures: List[str] = []
    for target, downloaded, err in results:
        if downloaded is None:
            failures.append(f"{target}({err})")
        else:
            successes.append(downloaded)
    return successes, failures


def try_external_subtitle(
    *,
    task_id: str,
    media_item_id: str,
    media_item_title: Optional[str],
    config,
    resolved_target_langs: List[str],
    library_id: Optional[str],
    path_mapping_index: Optional[int],
    task_work_dir: str,
    reporter,
    step_logs: dict,
    skipped_steps: List[str],
    run_async: Callable,
    persist_step_logs: Callable[[dict], None],
    format_step_log: Callable[[str, str], str],
) -> Optional[ExternalSubtitleResult]:
    """前置阶段：尝试外部字幕。命中返回结果，未命中返回 None。

    保持与其它 pipeline 阶段一致的同步接口；内部异步操作通过 run_async 串接。
    """
    reporter.report("search", 0.0)
    log_lines: List[str] = []

    if not config.path_mappings:
        log_lines.append("未配置路径映射规则，跳过外部字幕检索")
        step_logs["search"] = format_step_log("search", "\n".join(log_lines))
        skipped_steps.append("search")
        persist_step_logs(step_logs)
        reporter.report("search", 1.0)
        return None

    queries = build_search_queries(media_item_title or "")
    if not queries:
        log_lines.append("无媒体标题，跳过外部字幕检索")
        step_logs["search"] = format_step_log("search", "\n".join(log_lines))
        skipped_steps.append("search")
        persist_step_logs(step_logs)
        reporter.report("search", 1.0)
        return None

    timeout = float(getattr(config, "subtitle_search_timeout", 5) or 5)
    min_score = float(getattr(config, "subtitle_search_min_score", 0.7) or 0.7)
    log_lines.append(f"候选查询: {queries}")
    log_lines.append(f"目标语言: {', '.join(resolved_target_langs)}")
    log_lines.append(f"命中阈值: {min_score:.2f}")

    # 1. 拉媒体时长用于评分
    media_duration_ms: Optional[int] = None
    if config.emby_url and config.emby_api_key:
        try:
            from services.emby_connector import EmbyConnector

            async def _fetch_duration():
                async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                    return await emby.get_media_duration_ms(media_item_id)

            media_duration_ms = run_async(_fetch_duration())
        except Exception as exc:
            logger.warning(f"[{task_id}] 获取媒体时长失败，跳过时长加权: {exc}")

    # 2-3. 按候选查询顺序尝试：API → rank → 嗅探未识别 → 严格匹配
    client = XunleiSubtitleClient(timeout=timeout)
    selected_query: Optional[str] = None
    qualified: Dict[str, RankedHit] = {}

    for query in queries:
        log_lines.append(f"--- 尝试 query: {query!r} ---")
        try:
            hits = run_async(client.search(query))
        except SubtitleSearchError as exc:
            log_lines.append(f"  API 调用失败: {exc}")
            continue
        log_lines.append(f"  API 返回候选: {len(hits)} 条")
        if not hits:
            continue

        # 不强制语言匹配，让未识别项进入 ranker
        ranked = rank_hits(
            hits,
            target_languages=resolved_target_langs,
            media_duration_ms=media_duration_ms,
            require_target_match=False,
        )
        # 对 top-N 未识别项做内容嗅探，可能涨到目标语言
        ranked = run_async(
            _sniff_unknown_in_pipeline(
                ranked, resolved_target_langs, media_duration_ms, timeout
            )
        )

        picks = pick_best_per_language(ranked, resolved_target_langs)
        for lang, r in picks.items():
            log_lines.append(
                f"  最佳[{lang}]: score={r.score:.2f} ext={r.hit.ext} "
                f"src={r.language.source.value} name={r.hit.name}"
            )

        attempt_qualified = {
            lang: r for lang, r in picks.items() if r.score >= min_score
        }
        missing = [lang for lang in resolved_target_langs if lang not in attempt_qualified]
        if not missing:
            selected_query = query
            qualified = attempt_qualified
            log_lines.append(f"  ✓ 所有目标语言均达阈值，选用此 query")
            break
        log_lines.append(f"  ✗ 未达阈值: {', '.join(missing)}")

    if selected_query is None:
        log_lines.append("所有候选查询均未命中 → 走 ASR")
        step_logs["search"] = format_step_log("search", "\n".join(log_lines))
        skipped_steps.append("search")
        persist_step_logs(step_logs)
        reporter.report("search", 1.0)
        return None

    query = selected_query  # 后续日志/报告用

    # 4. 全部目标语言都命中：下载到 task_work_dir/search/
    save_dir = os.path.join(task_work_dir, "search")
    os.makedirs(save_dir, exist_ok=True)
    reporter.report("search", 0.4)
    downloaded, failures = run_async(_download_all(qualified, save_dir, timeout))
    if failures:
        log_lines.append(f"下载失败: {', '.join(failures)} → 走 ASR")
        step_logs["search"] = format_step_log("search", "\n".join(log_lines))
        skipped_steps.append("search")
        persist_step_logs(step_logs)
        reporter.report("search", 1.0)
        return None

    log_lines.append(f"下载成功: {len(downloaded)} 个语言")
    reporter.report("search", 0.7)

    # 5. 应用到视频目录 + Emby 刷新
    applied: List[AppliedSubtitle] = []
    try:
        for sub in downloaded:
            async def _apply(sub=sub):
                return await apply_downloaded_subtitle(
                    sub,
                    media_item_id,
                    emby_url=config.emby_url,
                    emby_api_key=config.emby_api_key,
                    path_mappings=config.path_mappings,
                    library_id=library_id,
                    path_mapping_index=path_mapping_index,
                    refresh_metadata=True,
                )

            applied.append(run_async(_apply()))
    except SubtitleApplyError as exc:
        log_lines.append(f"字幕应用失败: {exc} → 走 ASR")
        step_logs["search"] = format_step_log("search", "\n".join(log_lines))
        skipped_steps.append("search")
        persist_step_logs(step_logs)
        reporter.report("search", 1.0)
        return None
    except Exception as exc:
        logger.error(f"[{task_id}] 字幕应用异常: {exc}", exc_info=True)
        log_lines.append(f"字幕应用异常: {exc} → 走 ASR")
        step_logs["search"] = format_step_log("search", "\n".join(log_lines))
        skipped_steps.append("search")
        persist_step_logs(step_logs)
        reporter.report("search", 1.0)
        return None

    log_lines.append(
        "已应用语言: "
        + ", ".join(f"{a.language.code or '?'} → {os.path.basename(a.target_path)}" for a in applied)
    )
    step_logs["search"] = format_step_log("search", "\n".join(log_lines))
    persist_step_logs(step_logs)
    reporter.report("search", 1.0)

    ranked_summary = [
        {
            "lang": lang,
            "score": round(r.score, 3),
            "ext": r.hit.ext,
            "name": r.hit.name,
            "url": r.hit.url,
        }
        for lang, r in qualified.items()
    ]

    return ExternalSubtitleResult(
        applied=applied,
        query=query,
        matched_languages=[a.language.code for a in applied if a.language.code],
        ranked_summary=ranked_summary,
    )
