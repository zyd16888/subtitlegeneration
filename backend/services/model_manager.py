"""
ASR 模型管理服务

提供动态模型注册表（从 GitHub API 获取）、下载、进度跟踪和跨平台路径管理。
"""

import json
import logging
import re
import shutil
import tarfile
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("subtitle_service.model_manager")


# ── 支持的语言 ──────────────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "ru": "Русский",
    "pt": "Português",
    "it": "Italiano",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "ar": "العربية",
    "yue": "粤语",
}

# Whisper 多语言列表
_WHISPER_LANGUAGES = ["ja", "en", "zh", "ko", "fr", "de", "es", "ru", "pt", "it", "th", "vi", "ar"]

# 语言推断映射（模型名称片段 → 语言代码列表）
_LANGUAGE_PATTERNS: List[Tuple[str, List[str]]] = [
    ("bilingual-zh-en", ["zh", "en"]),
    ("multi-zh-hans", ["zh"]),
    ("-zh-en-", ["zh", "en"]),
    ("-zh-", ["zh"]),
    ("-en-", ["en"]),
    ("-ja-", ["ja"]),
    ("reazonspeech", ["ja"]),
    ("-korean-", ["ko"]),
    ("-fr-", ["fr"]),
    ("-de-", ["de"]),
    ("-es-", ["es"]),
    ("-ru-", ["ru"]),
    ("-pt-", ["pt"]),
    ("-it-", ["it"]),
    ("-thai-", ["th"]),
    ("-vi-", ["vi"]),
    ("-ar-", ["ar"]),
    ("-cantonese-", ["yue"]),
    ("gigaspeech", ["en"]),
]

# 不兼容的模型关键词（当前引擎不支持）
_INCOMPATIBLE_KEYWORDS = [
    "paraformer", "sensevoice", "nemo", "tdnn", "wenet", "telespeech",
    "moonshine",
]

# 非 ASR 资产关键词
_NON_ASR_KEYWORDS = [
    "native-lib", "speaker", "tts", "punctuation", "keyword",
    "kws-", "audio-tagging", "fire-red-asr",
]

# VAD 模型关键词
_VAD_KEYWORDS = ["vad"]


# ── 下载状态 ────────────────────────────────────────────────────────────────

class DownloadStatus(str, Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadProgress:
    model_id: str
    progress: int = 0  # 0-100
    status: DownloadStatus = DownloadStatus.IDLE
    error: Optional[str] = None


# ── ModelRegistry ─────────────────────────────────────────────────────────

class ModelRegistry:
    """动态模型注册表，从 GitHub API 获取并缓存到本地 JSON"""

    CACHE_FILE = "model_cache.json"
    CACHE_TTL = 3600 * 6  # 6 小时
    GITHUB_API_URL = (
        "https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/asr-models"
    )

    def __init__(self, models_dir: Path, github_token: Optional[str] = None):
        self.models_dir = models_dir
        self.cache_path = models_dir / self.CACHE_FILE
        self.github_token = github_token
        self._lock = threading.Lock()

    def get_models(self, force_refresh: bool = False) -> Dict[str, dict]:
        """获取模型列表（优先读缓存，过期或强制刷新则从 GitHub 拉取）"""
        if not force_refresh:
            cached = self._read_cache()
            if cached is not None:
                asr_count = sum(1 for m in cached.values() if m.get("category") != "vad")
                vad_count = len(cached) - asr_count
                print(f"[model_manager] 缓存命中: {len(cached)} 个模型 (ASR={asr_count}, VAD={vad_count})")
                if asr_count == 0:
                    print("[model_manager] 缓存中无 ASR 模型，强制刷新")
                else:
                    return cached
            else:
                print("[model_manager] 缓存未命中（不存在或已过期），将从 GitHub 获取")

        try:
            models = self._fetch_from_github()
            self._write_cache(models)
            asr_count = sum(1 for m in models.values() if m.get("category") != "vad")
            print(f"[model_manager] 模型列表已更新: {len(models)} 个模型 (ASR={asr_count})")
            return models
        except Exception as e:
            print(f"[model_manager] 获取失败: {type(e).__name__}: {e}")
            cached = self._read_cache(ignore_ttl=True)
            if cached is not None:
                print("[model_manager] 使用过期缓存作为回退")
                return cached
            return {}

    def refresh(self) -> Dict[str, dict]:
        """强制从 GitHub 刷新模型列表"""
        return self.get_models(force_refresh=True)

    # ── GitHub API ──

    # 本地 JSON 文件路径（GitHub 访问失败时的备用）
    LOCAL_MODELS_JSON = Path(__file__).parent.parent.parent / "models_registry.json"

    def _fetch_from_github(self) -> Dict[str, dict]:
        """从 GitHub Releases API 获取并解析模型列表，失败时回退到本地 JSON 文件"""
        from config.settings import settings as app_settings

        print(f"[model_manager] 正在从 GitHub 获取模型列表: {self.GITHUB_API_URL}")
        logger.info(f"正在从 GitHub 获取模型列表: {self.GITHUB_API_URL}")

        # 尝试从 GitHub 获取
        try:
            headers = {"Accept": "application/vnd.github.v3+json"}
            github_token = self.github_token or app_settings.github_token
            if github_token:
                headers["Authorization"] = f"token {github_token}"
                logger.debug("使用 GitHub Token 认证请求")

            resp = httpx.get(
                self.GITHUB_API_URL,
                headers=headers,
                timeout=30.0,
            )
            if resp.status_code == 403:
                body = resp.text[:200]
                logger.warning(f"GitHub API 返回 403: {body}")
                if "rate limit" in body.lower():
                    logger.warning("GitHub API 速率限制！可在 .env 中设置 GITHUB_TOKEN 提高限额（匿名 60次/小时 → 认证 5000次/小时）")
                raise httpx.HTTPStatusError(
                    f"GitHub API 403: {body[:100]}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            release = resp.json()
            assets = release.get("assets", [])
            logger.info(f"GitHub 返回 {len(assets)} 个 assets")

            models: Dict[str, dict] = {}
            skipped_reasons: Dict[str, int] = {}
            for asset in assets:
                parsed = self._parse_asset(asset)
                if parsed:
                    model_id = parsed.pop("id")
                    models[model_id] = parsed
                else:
                    asset_name = asset.get("name", "unknown")
                    reason = self._skip_reason(asset_name)
                    skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

            asr_count = sum(1 for m in models.values() if m.get("category") != "vad")
            vad_count = len(models) - asr_count
            logger.info(f"从 GitHub 解析到 {len(models)} 个模型 (ASR={asr_count}, VAD={vad_count})")
            if skipped_reasons:
                logger.info(f"跳过的 assets: {skipped_reasons}")

            if asr_count == 0 and len(assets) > 0:
                # 打印前5个 asset 名称帮助排查
                sample = [a.get("name", "?") for a in assets[:5]]
                logger.warning(f"GitHub 有 {len(assets)} 个 assets 但解析出 0 个 ASR 模型! 前5个: {sample}")

            # 保存到本地文件作为缓存
            self._save_models_cache(models)

            return models

        except Exception as e:
            print(f"[model_manager] GitHub 请求异常: {type(e).__name__}: {e}")
            logger.warning(f"从 GitHub 获取模型列表失败: {type(e).__name__}: {e}")

            # 回退到本地 JSON 文件
            return self._fetch_from_local_json()
    
    def _fetch_from_local_json(self) -> Dict[str, dict]:
        """从本地 JSON 文件加载模型列表（GitHub 不可用时使用）"""
        if not self.LOCAL_MODELS_JSON.exists():
            logger.warning(f"本地模型注册文件不存在: {self.LOCAL_MODELS_JSON}，回退到内置模型列表")
            return self._get_builtin_models()

        try:
            data = json.loads(self.LOCAL_MODELS_JSON.read_text(encoding="utf-8"))

            # 兼容两种格式：
            # 1) _save_models_cache 写入的已解析格式: {"models": {id: meta, ...}}
            # 2) 原始 GitHub release 格式: {"assets": [{name, size, ...}, ...]}
            if "models" in data and isinstance(data["models"], dict):
                models = data["models"]
                logger.info(f"从本地缓存加载 {len(models)} 个模型（已解析格式）")
                return models

            assets = data.get("assets", [])
            models: Dict[str, dict] = {}
            for asset in assets:
                parsed = self._parse_asset(asset)
                if parsed:
                    model_id = parsed.pop("id")
                    models[model_id] = parsed

            logger.info(f"从本地缓存解析到 {len(models)} 个兼容模型（原始 assets 格式）")
            return models

        except Exception as e:
            logger.warning(f"从本地缓存加载失败: {e}，使用内置模型列表")
            return self._get_builtin_models()
    
    def _save_models_cache(self, models: Dict[str, dict]) -> None:
        """保存模型列表到本地 JSON 文件（GitHub 不可用时的备份）"""
        try:
            cache_data = {
                "fetched_at": time.time(),
                "count": len(models),
                "models": models,
            }
            self.LOCAL_MODELS_JSON.parent.mkdir(parents=True, exist_ok=True)
            self.LOCAL_MODELS_JSON.write_text(
                json.dumps(cache_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"保存模型缓存失败: {e}")
    
    def _get_builtin_models(self) -> Dict[str, dict]:
        """获取内置的预定义模型列表（仅 VAD，ASR 需从 GitHub 获取）"""
        logger.warning("GitHub 和本地缓存均不可用，仅返回内置 VAD 模型")
        return {
            "silero_vad": {
                "name": "Silero VAD",
                "type": "vad",
                "model_type": "silero_vad",
                "category": "vad",
                "languages": [],
                "size": "~2MB",
                "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
                "archive_dir": "silero_vad",
                "download_count": 0,
            },
            "silero_vad_v4": {
                "name": "Silero VAD V4",
                "type": "vad",
                "model_type": "silero_vad",
                "category": "vad",
                "languages": [],
                "size": "~2MB",
                "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad_v4.onnx",
                "archive_dir": "silero_vad_v4",
                "download_count": 0,
            },
            "silero_vad_v5": {
                "name": "Silero VAD V5",
                "type": "vad",
                "model_type": "silero_vad",
                "category": "vad",
                "languages": [],
                "size": "~2MB",
                "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad_v5.onnx",
                "archive_dir": "silero_vad_v5",
                "download_count": 0,
            },
            "ten-vad": {
                "name": "Tencent VAD",
                "type": "vad",
                "model_type": "ten_vad",
                "category": "vad",
                "languages": [],
                "size": "~3MB",
                "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/ten-vad.onnx",
                "archive_dir": "ten-vad",
                "download_count": 0,
            },
        }

    def _parse_asset(self, asset: dict) -> Optional[dict]:
        """从 GitHub asset 解析模型元数据，不兼容的返回 None"""
        name: str = asset.get("name", "")
        name_lower = name.lower()
        size_bytes = asset.get("size", 0)
        size_str = self._format_size(size_bytes)
        download_url = asset.get("browser_download_url", "")

        # 检查是否 VAD 模型（可以是 .onnx 直接文件或 .tar.bz2 压缩包）
        is_vad_onnx = name_lower.endswith(".onnx") and any(kw in name_lower for kw in _VAD_KEYWORDS)
        is_vad_archive = name.endswith(".tar.bz2") and any(kw in name_lower for kw in _VAD_KEYWORDS)

        if is_vad_onnx or is_vad_archive:
            # VAD 模型处理
            if is_vad_onnx:
                model_id = name[:-len(".onnx")]  # 直接是 .onnx 文件
                archive_dir = model_id
                # 生成可读的显示名称
                display_name = " ".join(p.capitalize() for p in model_id.replace("_", "-").split("-") if p)
            else:
                model_id = name[len("sherpa-onnx-"):-len(".tar.bz2")]
                archive_dir = name[:-len(".tar.bz2")]
                display_name = self._make_display_name(model_id, "vad", [])

            return {
                "id": model_id,
                "name": display_name,
                "type": "vad",
                "model_type": "silero_vad",
                "category": "vad",
                "languages": [],
                "size": size_str,
                "url": download_url,
                "archive_dir": archive_dir,
                "download_count": asset.get("download_count", 0),
            }

        # 非 VAD 模型：只处理 tar.bz2
        if not name.endswith(".tar.bz2"):
            return None

        # 必须以 sherpa-onnx- 开头
        if not name.startswith("sherpa-onnx-"):
            return None

        # 排除非 ASR 资产
        for kw in _NON_ASR_KEYWORDS:
            if kw in name_lower:
                return None

        # 去掉前缀 "sherpa-onnx-" 和后缀 ".tar.bz2"
        stem = name[len("sherpa-onnx-"):-len(".tar.bz2")]
        archive_dir = name[:-len(".tar.bz2")]
        model_id = self._make_model_id(stem)

        # 排除不兼容 ASR 模型
        for kw in _INCOMPATIBLE_KEYWORDS:
            if kw in name_lower:
                return None

        engine_type, model_type = self._infer_engine_and_model_type(stem)
        languages = self._infer_languages(stem, model_type)

        return {
            "id": model_id,
            "name": self._make_display_name(stem, model_type, languages),
            "type": engine_type,
            "model_type": model_type,
            "category": "asr",
            "languages": languages,
            "size": size_str,
            "url": download_url,
            "archive_dir": archive_dir,
            "download_count": asset.get("download_count", 0),
        }

    @staticmethod
    def _skip_reason(name: str) -> str:
        """返回 asset 被跳过的原因分类（用于调试日志）"""
        name_lower = name.lower()
        if any(kw in name_lower for kw in _VAD_KEYWORDS):
            return "vad(已收录)"
        if name_lower.endswith(".onnx"):
            return "非tar.bz2(.onnx)"
        if not name.endswith(".tar.bz2"):
            return f"非tar.bz2({name.rsplit('.', 1)[-1] if '.' in name else 'no-ext'})"
        if not name.startswith("sherpa-onnx-"):
            return "无sherpa-onnx前缀"
        for kw in _NON_ASR_KEYWORDS:
            if kw in name_lower:
                return f"非ASR({kw})"
        for kw in _INCOMPATIBLE_KEYWORDS:
            if kw in name_lower:
                return f"不兼容({kw})"
        return "未知原因"

    # ── 名称推断 ──

    @staticmethod
    def _infer_engine_and_model_type(stem: str) -> Tuple[str, str]:
        """从 stem 推断 (engine_type, model_type)"""
        s = stem.lower()
        if s.startswith("streaming-"):
            return ("online", "transducer")
        if "whisper" in s:
            return ("offline", "whisper")
        return ("offline", "transducer")

    @staticmethod
    def _infer_languages(stem: str, model_type: str) -> List[str]:
        """从 stem 推断语言列表"""
        s = stem.lower()
        # Whisper 系列默认多语言
        if model_type == "whisper":
            return list(_WHISPER_LANGUAGES)

        for pattern, langs in _LANGUAGE_PATTERNS:
            if pattern in s:
                return langs

        return ["unknown"]

    @staticmethod
    def _make_model_id(stem: str) -> str:
        """从 stem 生成简洁的 model_id"""
        # 去掉日期后缀 如 -2023-02-20, -2024-08-01
        cleaned = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", stem)
        return cleaned

    @staticmethod
    def _make_display_name(stem: str, model_type: str, languages: List[str]) -> str:
        """生成用于展示的模型名称"""
        parts = stem.split("-")
        # 首字母大写处理
        name = " ".join(p.capitalize() for p in parts if not re.match(r"^\d{4}$", p))
        # 限制长度
        if len(name) > 60:
            name = name[:57] + "..."
        return name

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """将字节数转为可读字符串"""
        if size_bytes <= 0:
            return "unknown"
        if size_bytes < 1024 * 1024:
            return f"~{size_bytes // 1024}KB"
        if size_bytes < 1024 * 1024 * 1024:
            return f"~{size_bytes // (1024 * 1024)}MB"
        return f"~{size_bytes / (1024 * 1024 * 1024):.1f}GB"

    # ── 缓存 ──

    def _read_cache(self, ignore_ttl: bool = False) -> Optional[Dict[str, dict]]:
        """读取缓存，过期返回 None"""
        with self._lock:
            if not self.cache_path.exists():
                return None
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                cached_at = data.get("cached_at", 0)
                if not ignore_ttl and (time.time() - cached_at) > self.CACHE_TTL:
                    return None
                return data.get("models", {})
            except (json.JSONDecodeError, KeyError):
                return None

    def _write_cache(self, models: Dict[str, dict]):
        """写入缓存"""
        with self._lock:
            self.models_dir.mkdir(parents=True, exist_ok=True)
            data = {"cached_at": time.time(), "models": models}
            self.cache_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )


# ── ModelManager ────────────────────────────────────────────────────────────

# 全局下载进度表
_download_progress: Dict[str, DownloadProgress] = {}
_download_lock = threading.Lock()


class ModelManager:
    """ASR 模型管理器：注册表查询、下载、删除、路径管理"""

    MODEL_META_FILE = "model_meta.json"

    def __init__(self, models_dir: Optional[str] = None, github_token: Optional[str] = None):
        self.models_dir = Path(models_dir) if models_dir else self._default_models_dir()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.github_token = github_token
        self.registry = ModelRegistry(self.models_dir, github_token=github_token)

    # ── 跨平台默认目录 ──

    @staticmethod
    def _default_models_dir() -> Path:
        backend_dir = Path(__file__).resolve().parent.parent
        return backend_dir / "models_data"

    # ── 查询 ──

    def list_models(self, active_model_id: Optional[str] = None) -> List[dict]:
        """返回所有 ASR 模型及其安装状态（排除 VAD 模型）"""
        registry_models = self.registry.get_models()
        seen_ids: set = set()
        result = []

        # 1) 注册表中的模型
        for model_id, meta in registry_models.items():
            if meta.get("category") == "vad":
                continue
            seen_ids.add(model_id)
            installed = self._is_installed(model_id)
            result.append({
                "id": model_id,
                "name": meta.get("name", model_id),
                "type": meta.get("type", "offline"),
                "model_type": meta.get("model_type", "transducer"),
                "languages": meta.get("languages", []),
                "size": meta.get("size", "unknown"),
                "installed": installed,
                "active": model_id == active_model_id,
                "download_count": meta.get("download_count", 0),
            })

        # 2) 扫描本地已安装但不在注册表中的模型
        local_added = 0
        if self.models_dir.exists():
            for sub in self.models_dir.iterdir():
                if not sub.is_dir() or sub.name in seen_ids:
                    continue
                meta_path = sub / self.MODEL_META_FILE
                if not meta_path.exists():
                    continue
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if meta.get("category") == "vad":
                    continue
                model_id = sub.name
                result.append({
                    "id": model_id,
                    "name": meta.get("name", model_id),
                    "type": meta.get("type", "offline"),
                    "model_type": meta.get("model_type", "transducer"),
                    "languages": meta.get("languages", []),
                    "size": meta.get("size", "unknown"),
                    "installed": True,
                    "active": model_id == active_model_id,
                    "download_count": meta.get("download_count", 0),
                })
                local_added += 1
        if local_added:
            print(f"[model_manager] 从本地磁盘补充 {local_added} 个不在注册表中的已安装模型")

        result.sort(key=lambda m: (not m["installed"], -m.get("download_count", 0)))
        return result

    def list_vad_models(self, active_vad_model_id: Optional[str] = None) -> List[dict]:
        """返回所有 VAD 模型及其安装状态"""
        registry_models = self.registry.get_models()
        seen_ids: set = set()
        result = []

        for model_id, meta in registry_models.items():
            if meta.get("category") != "vad":
                continue
            seen_ids.add(model_id)
            installed = self._is_installed_vad(model_id)
            result.append({
                "id": model_id,
                "name": meta.get("name", model_id),
                "type": "vad",
                "model_type": meta.get("model_type", "silero_vad"),
                "languages": [],
                "size": meta.get("size", "unknown"),
                "installed": installed,
                "active": model_id == active_vad_model_id,
                "download_count": meta.get("download_count", 0),
            })

        # 扫描本地已安装但不在注册表中的 VAD 模型
        if self.models_dir.exists():
            for sub in self.models_dir.iterdir():
                if not sub.is_dir() or sub.name in seen_ids:
                    continue
                meta_path = sub / self.MODEL_META_FILE
                if not meta_path.exists():
                    continue
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if meta.get("category") != "vad":
                    continue
                model_id = sub.name
                result.append({
                    "id": model_id,
                    "name": meta.get("name", model_id),
                    "type": "vad",
                    "model_type": meta.get("model_type", "silero_vad"),
                    "languages": [],
                    "size": meta.get("size", "unknown"),
                    "installed": True,
                    "active": model_id == active_vad_model_id,
                    "download_count": meta.get("download_count", 0),
                })

        result.sort(key=lambda m: (not m["installed"], -m.get("download_count", 0)))
        return result

    def get_model_meta(self, model_id: str) -> Optional[dict]:
        """获取模型元数据（优先从已安装的 model_meta.json 读取）"""
        meta_path = self.models_dir / model_id / self.MODEL_META_FILE
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        # 回退到注册表
        registry_models = self.registry.get_models()
        return registry_models.get(model_id)

    def get_model_path(self, model_id: str) -> Optional[Path]:
        """返回已安装模型的目录路径"""
        model_dir = self.models_dir / model_id
        if model_dir.exists():
            return model_dir
        return None

    def get_model_file_paths(self, model_id: str) -> Optional[Dict[str, str]]:
        """返回模型各文件的绝对路径"""
        model_dir = self.get_model_path(model_id)
        if not model_dir:
            return None
        meta = self.get_model_meta(model_id)
        if not meta or "files" not in meta:
            return None
        paths = {}
        for key, filename in meta["files"].items():
            full_path = model_dir / filename
            if full_path.exists():
                paths[key] = str(full_path)
        return paths if paths else None

    def _is_installed(self, model_id: str) -> bool:
        """检查模型是否已完整安装（有 model_meta.json 且文件齐全）"""
        model_dir = self.models_dir / model_id
        if not model_dir.exists():
            return False
        meta_path = model_dir / self.MODEL_META_FILE
        if not meta_path.exists():
            # 旧模型兼容：尝试自动生成 meta
            return self._try_generate_meta(model_id)
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            files = meta.get("files", {})
            for filename in files.values():
                if not (model_dir / filename).exists():
                    return False
            return bool(files)
        except (json.JSONDecodeError, OSError):
            return False

    def _is_installed_vad(self, model_id: str) -> bool:
        """检查 VAD 模型是否已安装"""
        model_dir = self.models_dir / model_id
        if not model_dir.exists():
            return False
        meta_path = model_dir / self.MODEL_META_FILE
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                model_file = meta.get("files", {}).get("model", "")
                return bool(model_file and (model_dir / model_file).exists())
            except (json.JSONDecodeError, OSError):
                return False
        # 没有 meta，检查是否有 .onnx 文件
        vad_files = self._auto_detect_vad_files(model_dir)
        return bool(vad_files)

    @staticmethod
    def _auto_detect_vad_files(model_dir: Path) -> Dict[str, str]:
        """检测 VAD 模型目录中的 .onnx 文件"""
        onnx_files = list(model_dir.glob("*.onnx"))
        for f in onnx_files:
            if "vad" in f.name.lower():
                return {"model": f.name}
        if len(onnx_files) == 1:
            return {"model": onnx_files[0].name}
        return {}

    def _try_generate_meta(self, model_id: str) -> bool:
        """为旧版安装的模型自动生成 model_meta.json"""
        model_dir = self.models_dir / model_id
        file_map = self._auto_detect_files(model_dir)
        if not file_map:
            return False

        # 从注册表获取额外信息
        registry_models = self.registry.get_models()
        reg_meta = registry_models.get(model_id, {})

        # 推断模型类型
        if "whisper" in model_id.lower():
            engine_type, model_type = "offline", "whisper"
        elif model_id.startswith("streaming-"):
            engine_type, model_type = "online", "transducer"
        else:
            engine_type, model_type = "offline", "transducer"

        meta = {
            "type": reg_meta.get("type", engine_type),
            "model_type": reg_meta.get("model_type", model_type),
            "languages": reg_meta.get("languages", ["unknown"]),
            "files": file_map,
        }
        try:
            meta_path = model_dir / self.MODEL_META_FILE
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info(f"为旧模型 {model_id} 自动生成 model_meta.json")
            return True
        except OSError:
            return False

    # ── 文件自动检测 ──

    @staticmethod
    def _auto_detect_files(model_dir: Path) -> Dict[str, str]:
        """扫描模型目录，自动匹配 encoder/decoder/joiner/tokens 文件"""
        file_map: Dict[str, str] = {}

        onnx_files = list(model_dir.glob("*.onnx"))
        txt_files = list(model_dir.glob("*.txt"))

        for f in onnx_files:
            name_lower = f.name.lower()
            if "encoder" in name_lower and "encoder" not in file_map:
                file_map["encoder"] = f.name
            elif "decoder" in name_lower and "decoder" not in file_map:
                file_map["decoder"] = f.name
            elif "joiner" in name_lower and "joiner" not in file_map:
                file_map["joiner"] = f.name

        for f in txt_files:
            name_lower = f.name.lower()
            if "tokens" in name_lower and "tokens" not in file_map:
                file_map["tokens"] = f.name

        # 最少需要 encoder + decoder + tokens
        if all(k in file_map for k in ("encoder", "decoder", "tokens")):
            return file_map
        return {}

    # ── 下载 ──

    def start_download(self, model_id: str) -> DownloadProgress:
        """启动后台下载线程"""
        registry_models = self.registry.get_models()
        if model_id not in registry_models:
            return DownloadProgress(
                model_id=model_id,
                status=DownloadStatus.FAILED,
                error="未知模型，请先刷新模型列表",
            )

        with _download_lock:
            existing = _download_progress.get(model_id)
            if existing and existing.status == DownloadStatus.DOWNLOADING:
                return existing

            progress = DownloadProgress(model_id=model_id, status=DownloadStatus.DOWNLOADING)
            _download_progress[model_id] = progress

        thread = threading.Thread(
            target=self._download_worker,
            args=(model_id, registry_models[model_id]),
            daemon=True,
        )
        thread.start()
        return progress

    def get_download_progress(self, model_id: str) -> DownloadProgress:
        """查询下载进度"""
        with _download_lock:
            return _download_progress.get(
                model_id,
                DownloadProgress(model_id=model_id, status=DownloadStatus.IDLE),
            )

    # 下载重试配置
    DOWNLOAD_MAX_RETRIES = 5
    DOWNLOAD_RETRY_BASE_DELAY = 3  # 秒
    DOWNLOAD_CHUNK_SIZE = 1024 * 256  # 256KB
    DOWNLOAD_TIMEOUT = 120.0  # 单次连接超时

    def _download_with_resume(self, model_id: str, url: str, tmp_file: Path) -> None:
        """带断点续传和重试的文件下载"""
        total = 0
        for attempt in range(1, self.DOWNLOAD_MAX_RETRIES + 1):
            downloaded = tmp_file.stat().st_size if tmp_file.exists() else 0
            headers = {}
            if downloaded > 0:
                headers["Range"] = f"bytes={downloaded}-"
                logger.info(f"模型 {model_id} 第 {attempt} 次尝试，从 {downloaded} 字节处续传")
            else:
                logger.info(f"模型 {model_id} 第 {attempt} 次尝试，从头下载")

            try:
                timeout = httpx.Timeout(self.DOWNLOAD_TIMEOUT, read=self.DOWNLOAD_TIMEOUT)
                with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=timeout) as resp:
                    # 如果服务器不支持 Range 返回 200，需要重新下载
                    if downloaded > 0 and resp.status_code == 200:
                        logger.warning(f"模型 {model_id} 服务器不支持断点续传，重新下载")
                        downloaded = 0
                        tmp_file.unlink(missing_ok=True)

                    resp.raise_for_status()

                    if resp.status_code == 206:
                        # 部分内容，从 content-range 获取总大小
                        cr = resp.headers.get("content-range", "")
                        total = int(cr.split("/")[-1]) if "/" in cr else 0
                    else:
                        total = int(resp.headers.get("content-length", 0))

                    if total > 0:
                        logger.info(f"模型 {model_id} 文件总大小: {total} 字节")

                    mode = "ab" if downloaded > 0 and resp.status_code == 206 else "wb"
                    with open(tmp_file, mode) as f:
                        for chunk in resp.iter_bytes(chunk_size=self.DOWNLOAD_CHUNK_SIZE):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = min(int(downloaded / total * 90), 90)
                            else:
                                pct = 50
                            self._set_progress(model_id, pct, DownloadStatus.DOWNLOADING)

                # 下载完成后校验文件大小
                actual_size = tmp_file.stat().st_size
                if total > 0 and actual_size < total:
                    raise httpx.ReadError(
                        f"文件不完整: 已下载 {actual_size}/{total} 字节"
                    )

                logger.info(f"模型 {model_id} 下载完成，共 {actual_size} 字节")
                return  # 成功

            except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError,
                    httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout,
                    ConnectionError, OSError) as e:
                current_size = tmp_file.stat().st_size if tmp_file.exists() else 0
                logger.warning(
                    f"模型 {model_id} 下载中断 (第 {attempt}/{self.DOWNLOAD_MAX_RETRIES} 次): "
                    f"{type(e).__name__}: {e}，已下载 {current_size} 字节"
                )
                if attempt >= self.DOWNLOAD_MAX_RETRIES:
                    raise RuntimeError(
                        f"下载失败，已重试 {self.DOWNLOAD_MAX_RETRIES} 次: {e}"
                    ) from e
                delay = self.DOWNLOAD_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.info(f"模型 {model_id} 将在 {delay} 秒后重试...")
                self._set_progress(model_id,
                    min(int(current_size / max(total, 1) * 90), 90) if total > 0 else 50,
                    DownloadStatus.DOWNLOADING)
                time.sleep(delay)

    def _download_worker(self, model_id: str, meta: dict):
        """后台下载 + 解压 + 自动检测文件 + 写入 meta"""
        url = meta["url"]
        target_dir = self.models_dir / model_id
        is_vad = meta.get("category") == "vad"
        
        # VAD 模型（.onnx 文件）不需要解压
        if is_vad and url.endswith(".onnx"):
            tmp_file = self.models_dir / f"{model_id}.tmp.onnx"
        else:
            tmp_file = self.models_dir / f"{model_id}.tmp.tar.bz2"
        
        extract_tmp = self.models_dir / f"_extract_{model_id}"

        try:
            # 带断点续传和重试的流式下载
            logger.info(f"开始下载模型 {model_id}: {url}")
            self._download_with_resume(model_id, url, tmp_file)

            # 清理旧目录
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            # VAD .onnx 文件直接移动，不需要解压
            if is_vad and url.endswith(".onnx"):
                logger.info(f"模型 {model_id} 是直接的 .onnx 文件，直接移动到目标目录")
                onnx_file = tmp_file.name.replace(".tmp.onnx", ".onnx")
                # 从 URL 获取文件名
                import os
                onnx_filename = os.path.basename(url)
                shutil.move(str(tmp_file), str(target_dir / onnx_filename))
                
                # 写入 meta
                file_map = {"model": onnx_filename}
                model_meta = {
                    "type": "vad",
                    "model_type": "silero_vad",
                    "category": "vad",
                    "languages": [],
                    "files": file_map,
                    "name": meta.get("name", model_id),
                    "size": meta.get("size", "unknown"),
                }
                (target_dir / self.MODEL_META_FILE).write_text(
                    json.dumps(model_meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                self._set_progress(model_id, 100, DownloadStatus.COMPLETED)
                logger.info(f"VAD 模型 {model_id} 安装完成: {target_dir / onnx_filename}")
                return

            logger.info(f"模型 {model_id} 下载完成，开始解压...")
            self._set_progress(model_id, 91, DownloadStatus.EXTRACTING)

            if extract_tmp.exists():
                shutil.rmtree(extract_tmp)
            extract_tmp.mkdir(parents=True)

            # 解压到临时目录
            with tarfile.open(tmp_file, "r:bz2") as tar:
                tar.extractall(path=extract_tmp)

            # 找到包含模型文件的目录
            source_dir = self._find_model_dir(extract_tmp, is_vad=is_vad)

            if source_dir is None:
                contents = list(extract_tmp.rglob("*"))[:30]
                content_list = "\n".join(str(p.relative_to(extract_tmp)) for p in contents)
                raise RuntimeError(
                    f"解压后找不到模型文件（需要 *encoder*.onnx + *decoder*.onnx + *tokens*.txt）\n"
                    f"解压内容:\n{content_list}"
                )

            # 移动到目标目录
            logger.info(f"模型 {model_id}: 从 {source_dir} 移动到 {target_dir}")
            shutil.move(str(source_dir), str(target_dir))

            # 自动检测文件并写入 meta
            is_vad = meta.get("category") == "vad"
            if is_vad:
                file_map = self._auto_detect_vad_files(target_dir)
                if not file_map:
                    raise RuntimeError("VAD 模型文件检测失败：找不到 .onnx 文件")
            else:
                file_map = self._auto_detect_files(target_dir)
                if not file_map:
                    raise RuntimeError("模型文件自动检测失败：缺少必要的 encoder/decoder/tokens 文件")

            model_meta = {
                "type": meta.get("type", "offline"),
                "model_type": meta.get("model_type", "transducer"),
                "category": meta.get("category", "asr"),
                "languages": meta.get("languages", []),
                "files": file_map,
                "name": meta.get("name", model_id),
                "size": meta.get("size", "unknown"),
            }
            meta_path = target_dir / self.MODEL_META_FILE
            meta_path.write_text(
                json.dumps(model_meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            self._set_progress(model_id, 100, DownloadStatus.COMPLETED)
            logger.info(f"模型 {model_id} 安装完成: {target_dir}")

        except Exception as e:
            logger.error(f"模型 {model_id} 下载/安装失败: {e}", exc_info=True)
            self._set_progress(model_id, 0, DownloadStatus.FAILED, str(e))
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
        finally:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            if extract_tmp.exists():
                shutil.rmtree(extract_tmp, ignore_errors=True)

    def _find_model_dir(self, extract_root: Path, is_vad: bool = False) -> Optional[Path]:
        """在解压目录中搜索包含模型文件的目录"""

        def has_model_files(d: Path) -> bool:
            if is_vad:
                return bool(self._auto_detect_vad_files(d))
            return bool(self._auto_detect_files(d))

        # 策略1: 直接在解压根目录
        if has_model_files(extract_root):
            return extract_root

        # 策略2: 一级子目录
        for child in extract_root.iterdir():
            if child.is_dir() and has_model_files(child):
                return child

        # 策略3: 二级子目录
        for child in extract_root.iterdir():
            if child.is_dir():
                for grandchild in child.iterdir():
                    if grandchild.is_dir() and has_model_files(grandchild):
                        return grandchild

        return None

    def _set_progress(self, model_id: str, progress: int, status: DownloadStatus, error: str = None):
        with _download_lock:
            _download_progress[model_id] = DownloadProgress(
                model_id=model_id,
                progress=progress,
                status=status,
                error=error,
            )

    # ── 删除 ──

    def delete_model(self, model_id: str) -> bool:
        """删除已下载的模型文件"""
        model_dir = self.models_dir / model_id
        if model_dir.exists():
            shutil.rmtree(model_dir)
            with _download_lock:
                _download_progress.pop(model_id, None)
            logger.info(f"模型 {model_id} 已删除")
            return True
        return False
