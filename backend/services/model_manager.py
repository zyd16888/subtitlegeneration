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

logger = logging.getLogger(__name__)


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
    "native-lib", "speaker", "tts", "punctuation", "keyword", "vad",
    "kws-", "audio-tagging", "fire-red-asr",
]


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

    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self.cache_path = models_dir / self.CACHE_FILE
        self._lock = threading.Lock()

    def get_models(self, force_refresh: bool = False) -> Dict[str, dict]:
        """获取模型列表（优先读缓存，过期或强制刷新则从 GitHub 拉取）"""
        if not force_refresh:
            cached = self._read_cache()
            if cached is not None:
                return cached

        try:
            models = self._fetch_from_github()
            self._write_cache(models)
            return models
        except Exception as e:
            logger.error(f"从 GitHub 获取模型列表失败: {e}")
            # 回退到过期缓存
            cached = self._read_cache(ignore_ttl=True)
            if cached is not None:
                logger.info("使用过期缓存作为回退")
                return cached
            return {}

    def refresh(self) -> Dict[str, dict]:
        """强制从 GitHub 刷新模型列表"""
        return self.get_models(force_refresh=True)

    # ── GitHub API ──

    def _fetch_from_github(self) -> Dict[str, dict]:
        """从 GitHub Releases API 获取并解析模型列表"""
        logger.info("正在从 GitHub 获取模型列表...")
        resp = httpx.get(
            self.GITHUB_API_URL,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        release = resp.json()
        assets = release.get("assets", [])

        models: Dict[str, dict] = {}
        for asset in assets:
            parsed = self._parse_asset(asset)
            if parsed:
                model_id = parsed.pop("id")
                models[model_id] = parsed

        logger.info(f"从 GitHub 获取到 {len(models)} 个兼容模型")
        return models

    def _parse_asset(self, asset: dict) -> Optional[dict]:
        """从 GitHub asset 解析模型元数据，不兼容的返回 None"""
        name: str = asset.get("name", "")

        # 只处理 tar.bz2
        if not name.endswith(".tar.bz2"):
            return None

        # 必须以 sherpa-onnx- 开头
        if not name.startswith("sherpa-onnx-"):
            return None

        name_lower = name.lower()

        # 排除非 ASR 资产
        for kw in _NON_ASR_KEYWORDS:
            if kw in name_lower:
                return None

        # 排除不兼容模型
        for kw in _INCOMPATIBLE_KEYWORDS:
            if kw in name_lower:
                return None

        # 去掉前缀 "sherpa-onnx-" 和后缀 ".tar.bz2"
        stem = name[len("sherpa-onnx-"):-len(".tar.bz2")]
        # archive_dir 就是去掉 .tar.bz2 的完整文件名
        archive_dir = name[:-len(".tar.bz2")]

        engine_type, model_type = self._infer_engine_and_model_type(stem)
        languages = self._infer_languages(stem, model_type)
        size_bytes = asset.get("size", 0)
        size_str = self._format_size(size_bytes)

        # 生成 model_id: 去掉日期后缀来得到简洁 ID
        model_id = self._make_model_id(stem)

        return {
            "id": model_id,
            "name": self._make_display_name(stem, model_type, languages),
            "type": engine_type,
            "model_type": model_type,
            "languages": languages,
            "size": size_str,
            "url": asset.get("browser_download_url", ""),
            "archive_dir": archive_dir,
            "download_count": asset.get("download_count", 0),
        }

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

    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = Path(models_dir) if models_dir else self._default_models_dir()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.registry = ModelRegistry(self.models_dir)

    # ── 跨平台默认目录 ──

    @staticmethod
    def _default_models_dir() -> Path:
        backend_dir = Path(__file__).resolve().parent.parent
        return backend_dir / "models_data"

    # ── 查询 ──

    def list_models(self, active_model_id: Optional[str] = None) -> List[dict]:
        """返回所有注册模型及其安装状态"""
        registry_models = self.registry.get_models()
        result = []
        for model_id, meta in registry_models.items():
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
        # 排序：已安装优先，然后按下载量降序
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
        tmp_file = self.models_dir / f"{model_id}.tmp.tar.bz2"
        extract_tmp = self.models_dir / f"_extract_{model_id}"

        try:
            # 带断点续传和重试的流式下载
            logger.info(f"开始下载模型 {model_id}: {url}")
            self._download_with_resume(model_id, url, tmp_file)

            logger.info(f"模型 {model_id} 下载完成，开始解压...")
            self._set_progress(model_id, 91, DownloadStatus.EXTRACTING)

            # 清理旧目录
            if target_dir.exists():
                shutil.rmtree(target_dir)
            if extract_tmp.exists():
                shutil.rmtree(extract_tmp)
            extract_tmp.mkdir(parents=True)

            # 解压到临时目录
            with tarfile.open(tmp_file, "r:bz2") as tar:
                tar.extractall(path=extract_tmp)

            # 找到包含模型文件的目录
            source_dir = self._find_model_dir(extract_tmp)

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
            file_map = self._auto_detect_files(target_dir)
            if not file_map:
                raise RuntimeError("模型文件自动检测失败：缺少必要的 encoder/decoder/tokens 文件")

            model_meta = {
                "type": meta.get("type", "offline"),
                "model_type": meta.get("model_type", "transducer"),
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

    def _find_model_dir(self, extract_root: Path) -> Optional[Path]:
        """在解压目录中搜索包含模型文件（encoder+decoder+tokens）的目录"""

        def has_model_files(d: Path) -> bool:
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
