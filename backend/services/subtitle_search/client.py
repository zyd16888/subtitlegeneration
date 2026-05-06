"""
迅雷字幕搜索 API 客户端。

API: GET http://api-shoulei-ssl.xunlei.com/oracle/subtitle?name=<query>
返回 JSON：{"code": 0, "data": [{...}], "result": "ok"}
"""
import asyncio
import logging
from typing import List, Optional

import httpx

from .types import SearchHit

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://api-shoulei-ssl.xunlei.com/oracle/subtitle"
DEFAULT_TIMEOUT = 5.0
DEFAULT_RETRIES = 1


class SubtitleSearchError(Exception):
    """字幕搜索 API 调用失败。"""


class XunleiSubtitleClient:
    """异步迅雷字幕搜索客户端。"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.retries = max(0, retries)

    async def search(self, query: str) -> List[SearchHit]:
        """搜索给定关键词，返回原始候选列表（未排序、未过滤）。"""
        if not query or not query.strip():
            return []

        params = {"name": query.strip()}
        last_exc: Optional[Exception] = None

        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(self.base_url, params=params)
                    resp.raise_for_status()
                    payload = resp.json()
                return self._parse_payload(payload)
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    # 指数退避：200ms, 400ms ...
                    await asyncio.sleep(0.2 * (2 ** attempt))
                    continue
                logger.warning(
                    f"字幕搜索失败 query={query!r} attempts={attempt + 1}: {exc}"
                )
                raise SubtitleSearchError(f"字幕搜索失败: {exc}") from exc

        # 理论不可达
        raise SubtitleSearchError(f"字幕搜索失败: {last_exc}")

    @staticmethod
    def _parse_payload(payload: dict) -> List[SearchHit]:
        """把 API 返回 JSON 解析为 SearchHit 列表，不做过滤。"""
        if not isinstance(payload, dict):
            return []
        if payload.get("code") != 0:
            logger.debug(f"字幕搜索 API 返回非 0 code: {payload.get('code')}")
            return []

        data = payload.get("data") or []
        hits: List[SearchHit] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or ""
            if not url:
                continue
            try:
                hits.append(
                    SearchHit(
                        gcid=str(item.get("gcid") or ""),
                        cid=str(item.get("cid") or ""),
                        url=url,
                        ext=str(item.get("ext") or "").lower(),
                        name=str(item.get("name") or ""),
                        duration_ms=int(item.get("duration") or 0),
                        raw_languages=[
                            str(lang) for lang in (item.get("languages") or []) if lang is not None
                        ],
                        extra_name=item.get("extra_name"),
                        source=int(item.get("source") or 0),
                        score=int(item.get("score") or 0),
                        fingerprintf_score=int(item.get("fingerprintf_score") or 0),
                    )
                )
            except (TypeError, ValueError) as exc:
                logger.debug(f"忽略一条无法解析的字幕条目: {exc}, item={item}")
        return hits
