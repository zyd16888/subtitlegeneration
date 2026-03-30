"""
ASR 模型管理服务

提供模型注册表、下载、进度跟踪和跨平台路径管理。
"""

import logging
import os
import platform
import shutil
import tarfile
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

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


# ── 模型注册表 ──────────────────────────────────────────────────────────────

MODEL_REGISTRY: Dict[str, dict] = {
    # ── Online (Streaming) 模型 ──
    "streaming-zipformer-bilingual-zh-en": {
        "name": "中英双语流式模型",
        "type": "online",
        "languages": ["zh", "en"],
        "size": "~300MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
        "archive_dir": "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-99-avg-1.onnx",
            "decoder": "decoder-epoch-99-avg-1.onnx",
            "joiner": "joiner-epoch-99-avg-1.onnx",
        },
    },
    "streaming-zipformer-en": {
        "name": "English Streaming",
        "type": "online",
        "languages": ["en"],
        "size": "~300MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2",
        "archive_dir": "sherpa-onnx-streaming-zipformer-en-2023-06-26",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-99-avg-1-chunk-16-left-128.onnx",
            "decoder": "decoder-epoch-99-avg-1-chunk-16-left-128.onnx",
            "joiner": "joiner-epoch-99-avg-1-chunk-16-left-128.onnx",
        },
    },
    "streaming-zipformer-korean": {
        "name": "한국어 Streaming",
        "type": "online",
        "languages": ["ko"],
        "size": "~300MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-korean-2024-06-16.tar.bz2",
        "archive_dir": "sherpa-onnx-streaming-zipformer-korean-2024-06-16",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-99-avg-1.onnx",
            "decoder": "decoder-epoch-99-avg-1.onnx",
            "joiner": "joiner-epoch-99-avg-1.onnx",
        },
    },
    "streaming-zipformer-fr": {
        "name": "Français Streaming",
        "type": "online",
        "languages": ["fr"],
        "size": "~300MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-fr-2023-04-14.tar.bz2",
        "archive_dir": "sherpa-onnx-streaming-zipformer-fr-2023-04-14",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-29-avg-9-with-averaged-model.onnx",
            "decoder": "decoder-epoch-29-avg-9-with-averaged-model.onnx",
            "joiner": "joiner-epoch-29-avg-9-with-averaged-model.onnx",
        },
    },
    # ── Offline (Non-streaming) 模型 ──
    "zipformer-ja-reazonspeech": {
        "name": "日本語 Offline (ReazonSpeech)",
        "type": "offline",
        "model_type": "transducer",
        "languages": ["ja"],
        "size": "~500MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-ja-reazonspeech-2024-08-01.tar.bz2",
        "archive_dir": "sherpa-onnx-zipformer-ja-reazonspeech-2024-08-01",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-99-avg-1.onnx",
            "decoder": "decoder-epoch-99-avg-1.onnx",
            "joiner": "joiner-epoch-99-avg-1.onnx",
        },
    },
    "zipformer-zh-en": {
        "name": "中英双语 Offline",
        "type": "offline",
        "model_type": "transducer",
        "languages": ["zh", "en"],
        "size": "~500MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-zh-en-2023-11-22.tar.bz2",
        "archive_dir": "sherpa-onnx-zipformer-zh-en-2023-11-22",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-34-avg-19.onnx",
            "decoder": "decoder-epoch-34-avg-19.onnx",
            "joiner": "joiner-epoch-34-avg-19.onnx",
        },
    },
    "zipformer-korean": {
        "name": "한국어 Offline",
        "type": "offline",
        "model_type": "transducer",
        "languages": ["ko"],
        "size": "~500MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-korean-2024-06-24.tar.bz2",
        "archive_dir": "sherpa-onnx-zipformer-korean-2024-06-24",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-99-avg-1.onnx",
            "decoder": "decoder-epoch-99-avg-1.onnx",
            "joiner": "joiner-epoch-99-avg-1.onnx",
        },
    },
    "zipformer-thai": {
        "name": "ไทย Offline",
        "type": "offline",
        "model_type": "transducer",
        "languages": ["th"],
        "size": "~500MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-thai-2024-06-20.tar.bz2",
        "archive_dir": "sherpa-onnx-zipformer-thai-2024-06-20",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-12-avg-5.onnx",
            "decoder": "decoder-epoch-12-avg-5.onnx",
            "joiner": "joiner-epoch-12-avg-5.onnx",
        },
    },
    "zipformer-ru": {
        "name": "Русский Offline",
        "type": "offline",
        "model_type": "transducer",
        "languages": ["ru"],
        "size": "~500MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-ru-2024-09-18.tar.bz2",
        "archive_dir": "sherpa-onnx-zipformer-ru-2024-09-18",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-99-avg-1.onnx",
            "decoder": "decoder-epoch-99-avg-1.onnx",
            "joiner": "joiner-epoch-99-avg-1.onnx",
        },
    },
    "zipformer-gigaspeech-en": {
        "name": "English Offline (GigaSpeech)",
        "type": "offline",
        "model_type": "transducer",
        "languages": ["en"],
        "size": "~500MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-gigaspeech-2023-12-12.tar.bz2",
        "archive_dir": "sherpa-onnx-zipformer-gigaspeech-2023-12-12",
        "files": {
            "tokens": "tokens.txt",
            "encoder": "encoder-epoch-30-avg-1.onnx",
            "decoder": "decoder-epoch-30-avg-1.onnx",
            "joiner": "joiner-epoch-30-avg-1.onnx",
        },
    },
    # ── Whisper 模型 (Offline, 多语言) ──
    "whisper-tiny": {
        "name": "Whisper Tiny (多语言)",
        "type": "offline",
        "model_type": "whisper",
        "languages": ["ja", "en", "zh", "ko", "fr", "de", "es", "ru", "pt", "it", "th", "vi", "ar"],
        "size": "~120MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.tar.bz2",
        "archive_dir": "sherpa-onnx-whisper-tiny",
        "files": {
            "tokens": "tiny-tokens.txt",
            "encoder": "tiny-encoder.onnx",
            "decoder": "tiny-decoder.onnx",
        },
    },
    "whisper-base": {
        "name": "Whisper Base (多语言)",
        "type": "offline",
        "model_type": "whisper",
        "languages": ["ja", "en", "zh", "ko", "fr", "de", "es", "ru", "pt", "it", "th", "vi", "ar"],
        "size": "~290MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-base.tar.bz2",
        "archive_dir": "sherpa-onnx-whisper-base",
        "files": {
            "tokens": "base-tokens.txt",
            "encoder": "base-encoder.onnx",
            "decoder": "base-decoder.onnx",
        },
    },
    "whisper-small": {
        "name": "Whisper Small (多语言, 推荐)",
        "type": "offline",
        "model_type": "whisper",
        "languages": ["ja", "en", "zh", "ko", "fr", "de", "es", "ru", "pt", "it", "th", "vi", "ar"],
        "size": "~950MB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-small.tar.bz2",
        "archive_dir": "sherpa-onnx-whisper-small",
        "files": {
            "tokens": "small-tokens.txt",
            "encoder": "small-encoder.onnx",
            "decoder": "small-decoder.onnx",
        },
    },
    "whisper-medium": {
        "name": "Whisper Medium (多语言, 高精度)",
        "type": "offline",
        "model_type": "whisper",
        "languages": ["ja", "en", "zh", "ko", "fr", "de", "es", "ru", "pt", "it", "th", "vi", "ar"],
        "size": "~3GB",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-medium.tar.bz2",
        "archive_dir": "sherpa-onnx-whisper-medium",
        "files": {
            "tokens": "medium-tokens.txt",
            "encoder": "medium-encoder.onnx",
            "decoder": "medium-decoder.onnx",
        },
    },
}


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


# ── ModelManager ────────────────────────────────────────────────────────────

# 全局下载进度表
_download_progress: Dict[str, DownloadProgress] = {}
_download_lock = threading.Lock()


class ModelManager:
    """ASR 模型管理器：注册表查询、下载、删除、路径管理"""

    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = Path(models_dir) if models_dir else self._default_models_dir()
        self.models_dir.mkdir(parents=True, exist_ok=True)

    # ── 跨平台默认目录 ──

    @staticmethod
    def _default_models_dir() -> Path:
        system = platform.system()
        if system == "Windows":
            base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
            return Path(base) / "subtitle-service" / "models"
        else:
            base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
            return Path(base) / "subtitle-service" / "models"

    # ── 查询 ──

    def list_models(self, active_model_id: Optional[str] = None) -> List[dict]:
        """返回所有注册模型及其安装状态"""
        result = []
        for model_id, meta in MODEL_REGISTRY.items():
            installed = self._is_installed(model_id)
            result.append({
                "id": model_id,
                "name": meta["name"],
                "type": meta["type"],
                "model_type": meta.get("model_type", "transducer"),
                "languages": meta["languages"],
                "size": meta["size"],
                "installed": installed,
                "active": model_id == active_model_id,
            })
        return result

    def get_model_path(self, model_id: str) -> Optional[Path]:
        """返回已安装模型的目录路径"""
        if model_id not in MODEL_REGISTRY:
            return None
        model_dir = self.models_dir / model_id
        if model_dir.exists():
            return model_dir
        return None

    def get_model_file_paths(self, model_id: str) -> Optional[Dict[str, str]]:
        """返回模型各文件的绝对路径"""
        model_dir = self.get_model_path(model_id)
        if not model_dir:
            return None
        meta = MODEL_REGISTRY[model_id]
        paths = {}
        for key, filename in meta["files"].items():
            full_path = model_dir / filename
            if full_path.exists():
                paths[key] = str(full_path)
        return paths if paths else None

    def _is_installed(self, model_id: str) -> bool:
        """检查模型是否已完整安装"""
        model_dir = self.models_dir / model_id
        if not model_dir.exists():
            return False
        meta = MODEL_REGISTRY.get(model_id)
        if not meta:
            return False
        for filename in meta["files"].values():
            if not (model_dir / filename).exists():
                return False
        return True

    # ── 下载 ──

    def start_download(self, model_id: str) -> DownloadProgress:
        """启动后台下载线程"""
        if model_id not in MODEL_REGISTRY:
            return DownloadProgress(model_id=model_id, status=DownloadStatus.FAILED, error="未知模型")

        with _download_lock:
            existing = _download_progress.get(model_id)
            if existing and existing.status == DownloadStatus.DOWNLOADING:
                return existing

            progress = DownloadProgress(model_id=model_id, status=DownloadStatus.DOWNLOADING)
            _download_progress[model_id] = progress

        thread = threading.Thread(
            target=self._download_worker,
            args=(model_id,),
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

    def _download_worker(self, model_id: str):
        """后台下载 + 解压"""
        import httpx

        meta = MODEL_REGISTRY[model_id]
        url = meta["url"]
        archive_dir_name = meta["archive_dir"]
        target_dir = self.models_dir / model_id
        tmp_file = self.models_dir / f"{model_id}.tmp.tar.bz2"

        try:
            # 流式下载
            with httpx.stream("GET", url, follow_redirects=True, timeout=600.0) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0

                with open(tmp_file, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = min(int(downloaded / total * 90), 90)
                        else:
                            pct = 50
                        self._set_progress(model_id, pct, DownloadStatus.DOWNLOADING)

            # 解压
            self._set_progress(model_id, 91, DownloadStatus.EXTRACTING)
            if target_dir.exists():
                shutil.rmtree(target_dir)

            with tarfile.open(tmp_file, "r:bz2") as tar:
                tar.extractall(path=self.models_dir)

            # sherpa-onnx 的 tar 包解压后目录名通常是 archive_dir
            extracted_dir = self.models_dir / archive_dir_name
            if extracted_dir.exists() and extracted_dir != target_dir:
                extracted_dir.rename(target_dir)

            self._set_progress(model_id, 100, DownloadStatus.COMPLETED)
            logger.info(f"模型 {model_id} 下载完成: {target_dir}")

        except Exception as e:
            logger.error(f"模型 {model_id} 下载失败: {e}")
            self._set_progress(model_id, 0, DownloadStatus.FAILED, str(e))
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
        finally:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)

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
