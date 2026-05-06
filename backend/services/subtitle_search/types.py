"""
字幕搜索模块共享数据类型。

集中放在这里避免循环依赖：client → ranker → applier 都引用这些类型。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class LanguageSource(str, Enum):
    """语言判定来源，便于上游展示和审计。"""

    API_FIELD = "api_field"          # API languages 字段直接给出
    FILENAME = "filename"             # 从文件名正则提取
    CONTENT = "content"               # 通过文件内容检测
    UNKNOWN = "unknown"               # 全部失败


@dataclass
class SearchHit:
    """API 原始返回的一条字幕记录。"""

    gcid: str
    cid: str
    url: str
    ext: str                  # srt / ass / 其它
    name: str                 # 文件名（可能是哈希、可能含语言信息）
    duration_ms: int          # API 的 duration 字段；经验值是毫秒
    raw_languages: List[str] = field(default_factory=list)  # API languages 字段原值
    extra_name: Optional[str] = None  # API extra_name，例如 "（网友上传）"
    source: int = 0
    score: int = 0
    fingerprintf_score: int = 0


@dataclass
class LanguageResolution:
    """对一条字幕的语言判定结果。"""

    code: Optional[str]              # 归一化语言码，如 "zh" / "zh-Hant" / "en" / "ja"；None 表示未知
    source: LanguageSource           # 判定来源
    confidence: float = 0.0          # 0-1，UNKNOWN 时为 0
    is_bilingual: bool = False       # 双语字幕（zh+ja 之类）
    secondary_code: Optional[str] = None  # 双语时的副语言


@dataclass
class RankedHit:
    """打分后的字幕候选，含归一化语言信息。"""

    hit: SearchHit
    language: LanguageResolution
    score: float                     # 综合评分 0-1
    duration_match: float = 0.0      # 时长匹配子分 0-1
    score_breakdown: dict = field(default_factory=dict)


@dataclass
class DownloadedSubtitle:
    """已下载到本地（task_work_dir）的字幕文件。"""

    local_path: str                  # 已写入磁盘的 UTF-8 文件路径
    language: LanguageResolution
    ext: str                         # srt / ass
    source_url: str
    file_size: int                   # 字节数


@dataclass
class AppliedSubtitle:
    """已应用到视频目录的字幕文件。"""

    media_item_id: str
    language: LanguageResolution
    ext: str
    target_path: str                 # 复制到视频目录后的最终路径
    emby_refreshed: bool
    source_url: str
