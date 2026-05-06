"""
外部字幕搜索集成（迅雷字幕 API）。

按职责拆分为：
- client：访问第三方 API
- ranker：结果过滤与评分
- lang_sniffer：多层级语言识别（API 字段 → 文件名 → 内容）
- downloader：下载并归一化编码
- applier：把字幕落盘到视频目录并刷新 Emby

上层调用方包含：
- 手动 API（api/subtitle_search.py）
- 任务前置自动检索（services/subtitle_search_pipeline.py）
- 库批量扫描（tasks/library_scan_tasks.py）
"""
from .types import (
    SearchHit,
    RankedHit,
    LanguageResolution,
    LanguageSource,
    DownloadedSubtitle,
    AppliedSubtitle,
)

__all__ = [
    "SearchHit",
    "RankedHit",
    "LanguageResolution",
    "LanguageSource",
    "DownloadedSubtitle",
    "AppliedSubtitle",
]
