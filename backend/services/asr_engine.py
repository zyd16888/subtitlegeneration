"""
ASR (Automatic Speech Recognition) Engine Module

Supports:
- SherpaOnnxOnlineEngine  — 流式识别 (OnlineRecognizer)
- SherpaOnnxOfflineEngine — 离线识别 (OfflineRecognizer, 包括 whisper / transducer)
- CloudASREngine          — 云端 ASR API

参考官方示例优化：https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/generate-subtitles.py
"""

import asyncio
import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import tempfile
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import ffmpeg
import numpy as np
import sherpa_onnx

from services.signed_url import create_asr_audio_token

logger = logging.getLogger(__name__)

# 进度回调签名：fraction ∈ [0, 1]，表示当前 ASR 阶段内部完成度
ProgressCallback = Callable[[float], None]


def _safe_progress(cb: Optional[ProgressCallback], fraction: float) -> None:
    """调用进度回调，吞掉所有异常——上报失败永远不该影响主流程。"""
    if cb is None:
        return
    try:
        cb(fraction)
    except Exception as e:
        logger.warning(f"Progress callback failed: {e}")


def _read_wave(audio_path: str) -> Tuple[np.ndarray, int]:
    """
    读取 WAV 文件，返回 (float32 numpy array, sample_rate)
    
    与官方示例一致，返回 numpy array 而非 list
    """
    with wave.open(audio_path, "rb") as wf:
        sample_rate = wf.getframerate()
        num_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        num_frames = wf.getnframes()
        raw = wf.readframes(num_frames)

    if sample_width == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported sample width: {sample_width}")

    if num_channels > 1:
        samples = samples[::num_channels]  # 取第一声道

    if len(samples) == 0:
        raise RuntimeError(
            f"Audio file is empty (0 samples): {audio_path}"
        )

    return samples, sample_rate


@dataclass
class Segment:
    """Transcribed text segment with timestamps."""
    start: float
    end: float
    text: str
    
    @property
    def duration(self) -> float:
        return self.end - self.start


class ASREngine(ABC):
    """Abstract base class for ASR engines."""

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str = "ja",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        """
        转录音频。

        Args:
            progress_cb: 可选进度回调，参数 fraction ∈ [0, 1]。
                         可能从工作线程被调用，实现需自行保证线程安全。
        """
        pass


# ── Online (Streaming) Engine ───────────────────────────────────────────────


class SherpaOnnxOnlineEngine(ASREngine):
    """
    流式 ASR 引擎 (sherpa_onnx.OnlineRecognizer)。

    支持两种流式模型结构：
    - transducer:     encoder + decoder + joiner + tokens （streaming-zipformer）
    - zipformer2_ctc: 单个 *ctc*.onnx + tokens（可选 HLG.fst WFST 解码图）
    """

    def __init__(
        self,
        model_path: str,
        model_type: str = "transducer",
        file_map: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            model_path: 模型目录
            model_type: "transducer" 或 "zipformer2_ctc"
            file_map:   transducer: {"tokens", "encoder", "decoder", "joiner"}
                        zipformer2_ctc: {"tokens", "model", 可选 "ctc_graph", "bpe_model"}
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")

        self.model_path = model_path
        self.model_type = model_type
        self.file_map = file_map or self._default_file_map()
        self.recognizer: Optional[sherpa_onnx.OnlineRecognizer] = None
        self._initialize_recognizer()

    def _default_file_map(self) -> Dict[str, str]:
        if self.model_type == "zipformer2_ctc":
            return {"tokens": "tokens.txt", "model": "model.onnx"}
        return {
            "tokens": "tokens.txt",
            "encoder": "encoder.onnx",
            "decoder": "decoder.onnx",
            "joiner": "joiner.onnx",
        }

    def _initialize_recognizer(self):
        try:
            tokens_path = os.path.join(self.model_path, self.file_map["tokens"])
            logger.info(f"Initializing OnlineRecognizer with model_path: {self.model_path}")
            logger.info(f"  model_type: {self.model_type}")
            logger.info(f"  tokens: {tokens_path} (exists: {os.path.exists(tokens_path)})")

            if self.model_type == "zipformer2_ctc":
                ctc_model_path = os.path.join(self.model_path, self.file_map["model"])
                logger.info(f"  ctc model: {ctc_model_path} (exists: {os.path.exists(ctc_model_path)})")

                ctc_graph = ""
                if "ctc_graph" in self.file_map:
                    graph_path = os.path.join(self.model_path, self.file_map["ctc_graph"])
                    if os.path.exists(graph_path):
                        ctc_graph = graph_path
                        logger.info(f"  ctc_graph (HLG WFST): {graph_path}")

                self.recognizer = sherpa_onnx.OnlineRecognizer.from_zipformer2_ctc(
                    tokens=tokens_path,
                    model=ctc_model_path,
                    num_threads=4,
                    sample_rate=16000,
                    feature_dim=80,
                    decoding_method="greedy_search",
                    provider="cpu",
                    ctc_graph=ctc_graph,
                    enable_endpoint_detection=True,
                )
            else:
                encoder_path = os.path.join(self.model_path, self.file_map["encoder"])
                decoder_path = os.path.join(self.model_path, self.file_map["decoder"])
                joiner_path = os.path.join(self.model_path, self.file_map["joiner"])

                logger.info(f"  encoder: {encoder_path} (exists: {os.path.exists(encoder_path)})")
                logger.info(f"  decoder: {decoder_path} (exists: {os.path.exists(decoder_path)})")
                logger.info(f"  joiner: {joiner_path} (exists: {os.path.exists(joiner_path)})")

                self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                    tokens=tokens_path,
                    encoder=encoder_path,
                    decoder=decoder_path,
                    joiner=joiner_path,
                    num_threads=4,
                    decoding_method="greedy_search",
                    max_active_paths=4,
                    enable_endpoint_detection=True,
                )
            logger.info("OnlineRecognizer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OnlineRecognizer: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize OnlineRecognizer: {e}")

    async def transcribe(
        self,
        audio_path: str,
        language: str = None,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if self.recognizer is None:
            raise RuntimeError("Recognizer not initialized")

        # Online 流式模型是单语言固定的，language 参数不影响识别行为
        return await asyncio.get_running_loop().run_in_executor(
            None, self._transcribe_sync, audio_path, progress_cb
        )

    def _transcribe_sync(
        self,
        audio_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        logger.info(f"OnlineEngine._transcribe_sync started, progress_cb={'enabled' if progress_cb else 'None'}")
        samples, sample_rate = _read_wave(audio_path)
        stream = self.recognizer.create_stream()

        chunk_size = int(0.1 * sample_rate)
        segments: List[Segment] = []
        current_time = 0.0

        total = max(len(samples), 1)
        _safe_progress(progress_cb, 0.0)
        # 节流：每 ~50 个 chunk（约 5s 音频）回调一次，避免高频调用
        report_interval = max(1, (total // chunk_size) // 50 or 1)
        chunk_idx = 0

        for i in range(0, len(samples), chunk_size):
            chunk = samples[i : i + chunk_size]
            stream.accept_waveform(sample_rate, chunk)
            while self.recognizer.is_ready(stream):
                self.recognizer.decode_stream(stream)

            # get_result 返回 str
            text = self.recognizer.get_result(stream).strip()
            if text:
                start_time = current_time
                end_time = current_time + len(chunk) / sample_rate
                segments.append(Segment(start=start_time, end=end_time, text=text))
                stream = self.recognizer.create_stream()

            current_time += len(chunk) / sample_rate
            chunk_idx += 1
            if chunk_idx % report_interval == 0:
                _safe_progress(progress_cb, min(0.99, (i + chunk_size) / total))

        text = self.recognizer.get_result(stream).strip()
        if text:
            segments.append(
                Segment(
                    start=current_time - len(samples[-chunk_size:]) / sample_rate,
                    end=current_time,
                    text=text,
                )
            )
        _safe_progress(progress_cb, 1.0)
        return segments


# ── Offline (Non-streaming) Engine ──────────────────────────────────────────


class SherpaOnnxOfflineEngine(ASREngine):
    """
    离线 ASR 引擎 (sherpa_onnx.OfflineRecognizer)。

    支持两种模型类型：
    - transducer: zipformer 等离线模型 (encoder + decoder + joiner)
    - whisper:    whisper 系列模型 (encoder + decoder)

    Whisper 模型支持运行时指定语言（通过 transcribe 的 language 参数）。
    
    注意：此引擎不提供精确时间戳，建议使用 SherpaOnnxVadOfflineEngine 获得更好的效果。
    """

    def __init__(
        self,
        model_path: str,
        model_type: str = "transducer",
        file_map: Optional[Dict[str, str]] = None,
        language: str = "",
        num_threads: int = 4,
        debug: bool = False,
    ):
        """
        Args:
            model_path: 模型目录
            model_type: "transducer" 或 "whisper"
            file_map:   各文件的映射
            language:   默认语言代码 (如 "ja", "zh", "en")，空字符串表示自动检测
            num_threads: 线程数
            debug:      是否输出调试信息
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")

        self.model_path = model_path
        self.model_type = model_type
        self.default_language = language
        self.file_map = file_map or self._default_file_map()
        self.num_threads = num_threads
        self.debug = debug
        self.recognizer: Optional[sherpa_onnx.OfflineRecognizer] = None
        # 锁：Whisper 模型切换语言时防止并发重复初始化
        self._init_lock = asyncio.Lock()
        self._initialize_recognizer(language)

    def _default_file_map(self) -> Dict[str, str]:
        if self.model_type == "whisper":
            return {
                "tokens": "tokens.txt",
                "encoder": "encoder.onnx",
                "decoder": "decoder.onnx",
            }
        return {
            "tokens": "tokens.txt",
            "encoder": "encoder.onnx",
            "decoder": "decoder.onnx",
            "joiner": "joiner.onnx",
        }

    def _initialize_recognizer(self, language: str = ""):
        """
        初始化识别器。

        Args:
            language: 初始语言代码，Whisper 模型使用
        """
        try:
            tokens_path = os.path.join(self.model_path, self.file_map["tokens"])
            encoder_path = os.path.join(self.model_path, self.file_map["encoder"])
            decoder_path = os.path.join(self.model_path, self.file_map["decoder"])

            logger.info(f"Initializing OfflineRecognizer with model_path: {self.model_path}")
            logger.info(f"  model_type: {self.model_type}")
            logger.info(f"  language: {language or 'auto'}")
            logger.info(f"  tokens: {tokens_path} (exists: {os.path.exists(tokens_path)})")
            logger.info(f"  encoder: {encoder_path} (exists: {os.path.exists(encoder_path)})")
            logger.info(f"  decoder: {decoder_path} (exists: {os.path.exists(decoder_path)})")

            if self.model_type == "whisper":
                # Whisper 模型初始化时不设置语言，等待 transcribe 时动态指定
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    tokens=tokens_path,
                    language=language or "",  # 空字符串表示自动检测
                    task="transcribe",
                    num_threads=self.num_threads,
                    decoding_method="greedy_search",
                    debug=self.debug,
                )
            else:
                joiner_path = os.path.join(self.model_path, self.file_map["joiner"])
                logger.info(f"  joiner: {joiner_path} (exists: {os.path.exists(joiner_path)})")

                self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    joiner=joiner_path,
                    tokens=tokens_path,
                    num_threads=self.num_threads,
                    decoding_method="greedy_search",
                    debug=self.debug,
                )

            logger.info("OfflineRecognizer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OfflineRecognizer ({self.model_type}): {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize OfflineRecognizer ({self.model_type}): {e}")

    async def transcribe(
        self,
        audio_path: str,
        language: str = None,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        """
        转录音频。

        Args:
            audio_path: 音频文件路径
            language: 可选，指定语言代码（如 "ja", "zh", "en"）。
                     如果为 None 或空，使用初始化时的默认语言。
                     Whisper 模型支持运行时指定语言。
            progress_cb: 进度回调（颗粒度有限，仅在开始/结束上报）。
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if self.recognizer is None:
            raise RuntimeError("Recognizer not initialized")

        # Whisper 模型支持运行时指定语言
        effective_lang = language if language else self.default_language
        if effective_lang and self.model_type == "whisper":
            # 如果语言与初始语言不同，需要重新初始化识别器（加锁防止并发冲突）
            if effective_lang != self.default_language:
                async with self._init_lock:
                    # Double-check：锁内再判断一次
                    if effective_lang != self.default_language:
                        logger.info(f"Re-initializing Whisper recognizer with language: {effective_lang}")
                        self._initialize_recognizer(effective_lang)
                        self.default_language = effective_lang

        _safe_progress(progress_cb, 0.0)
        result = await asyncio.get_running_loop().run_in_executor(
            None, self._transcribe_sync, audio_path
        )
        _safe_progress(progress_cb, 1.0)
        return result

    def _transcribe_sync(self, audio_path: str) -> List[Segment]:
        samples, sample_rate = _read_wave(audio_path)

        stream = self.recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        self.recognizer.decode_stream(stream)

        text = stream.result.text.strip()
        if not text:
            return []

        duration = len(samples) / sample_rate

        # OfflineRecognizer 不提供时间戳，按固定长度切分
        # 建议：使用 SherpaOnnxVadOfflineEngine 获得精确时间戳
        sentences = self._split_text(text)
        segments: List[Segment] = []
        avg_duration = duration / max(len(sentences), 1)
        for i, sentence in enumerate(sentences):
            segments.append(
                Segment(
                    start=i * avg_duration,
                    end=(i + 1) * avg_duration,
                    text=sentence,
                )
            )
        return segments

    @staticmethod
    def _split_text(text: str, max_chars: int = 40) -> List[str]:
        """按标点或长度切分文本为字幕段"""
        import re

        # 按常见标点切分
        parts = re.split(r'(?<=[。！？.!?\n])\s*', text)
        result: List[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= max_chars:
                result.append(part)
            else:
                # 长句再按逗号切
                sub = re.split(r'(?<=[，,、;；])\s*', part)
                for s in sub:
                    s = s.strip()
                    if s:
                        result.append(s)
        return result if result else [text]


# ── VAD + Offline Engine (优化版，参考官方示例) ────────────────────────────


class SherpaOnnxVadOfflineEngine(ASREngine):
    """
    分段 + 离线 ASR 引擎，支持两种分段模式：

    - silero: 使用 silero_vad 神经网络检测语音段，精确但较慢
    - energy: 使用 RMS 能量检测静音做切分，不做语音判断，极快且不漏检
    """

    DEFAULT_VAD_THRESHOLD = 0.2
    DEFAULT_VAD_MIN_SILENCE_DURATION = 0.7
    DEFAULT_VAD_MIN_SPEECH_DURATION = 0.5  # 提高到 0.5s，避免过短片段
    DEFAULT_VAD_MAX_SPEECH_DURATION = 20.0
    FRAME_DURATION_MS = 30  # energy 模式帧长
    MIN_SEGMENT_DURATION_S = 0.8
    RETRY_PADDING_S = 0.25
    MAX_RETRY_DEPTH = 2

    def __init__(
        self,
        model_path: str,
        model_type: str = "transducer",
        file_map: Optional[Dict[str, str]] = None,
        language: str = "",
        vad_mode: str = "energy",
        vad_model_path: str = "",
        vad_threshold: float = DEFAULT_VAD_THRESHOLD,
        vad_min_silence_duration: float = DEFAULT_VAD_MIN_SILENCE_DURATION,
        vad_min_speech_duration: float = DEFAULT_VAD_MIN_SPEECH_DURATION,
        vad_max_speech_duration: float = DEFAULT_VAD_MAX_SPEECH_DURATION,
        num_threads: int = 4,
        debug: bool = False,
    ):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")

        self.model_path = model_path
        self.model_type = model_type
        self.default_language = language
        self.file_map = file_map or self._default_file_map()
        self.vad_mode = vad_mode
        self.vad_model_path = vad_model_path
        self.vad_threshold = vad_threshold
        self.vad_min_silence_duration = vad_min_silence_duration
        self.vad_min_speech_duration = vad_min_speech_duration
        self.vad_max_speech_duration = vad_max_speech_duration
        self.num_threads = num_threads
        self.debug = debug

        self.recognizer: Optional[sherpa_onnx.OfflineRecognizer] = None
        self.vad: Optional[sherpa_onnx.VoiceActivityDetector] = None
        # 锁：Whisper 模型切换语言时防止并发重复初始化
        self._init_lock = asyncio.Lock()
        self._initialize()

    def _default_file_map(self) -> Dict[str, str]:
        if self.model_type == "whisper":
            return {
                "tokens": "tokens.txt",
                "encoder": "encoder.onnx",
                "decoder": "decoder.onnx",
            }
        return {
            "tokens": "tokens.txt",
            "encoder": "encoder.onnx",
            "decoder": "decoder.onnx",
            "joiner": "joiner.onnx",
        }

    def _initialize(self, language: str = None):
        """
        初始化 OfflineRecognizer，silero 模式下同时初始化 VAD。

        Args:
            language: 语言代码，None 时使用 self.default_language
        """
        lang = language if language is not None else self.default_language
        try:
            tokens_path = os.path.join(self.model_path, self.file_map["tokens"])
            encoder_path = os.path.join(self.model_path, self.file_map["encoder"])
            decoder_path = os.path.join(self.model_path, self.file_map["decoder"])

            if self.model_type == "whisper":
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    tokens=tokens_path,
                    language=lang or "",
                    task="transcribe",
                    num_threads=self.num_threads,
                    decoding_method="greedy_search",
                    debug=self.debug,
                )
            else:
                joiner_path = os.path.join(self.model_path, self.file_map["joiner"])
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    joiner=joiner_path,
                    tokens=tokens_path,
                    num_threads=self.num_threads,
                    decoding_method="greedy_search",
                    debug=self.debug,
                )

            # silero 模式：初始化 silero_vad
            if self.vad_mode == "silero" and self.vad is None:
                if not self.vad_model_path or not os.path.exists(self.vad_model_path):
                    raise FileNotFoundError(f"VAD model not found: {self.vad_model_path}")
                vad_config = sherpa_onnx.VadModelConfig()
                vad_config.silero_vad.model = self.vad_model_path
                vad_config.silero_vad.threshold = self.vad_threshold
                vad_config.silero_vad.min_silence_duration = self.vad_min_silence_duration
                vad_config.silero_vad.min_speech_duration = self.vad_min_speech_duration
                vad_config.silero_vad.max_speech_duration = self.vad_max_speech_duration
                vad_config.sample_rate = 16000
                vad_config.num_threads = self.num_threads
                self.vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=100)

            logger.info(
                f"VadOfflineEngine initialized (mode={self.vad_mode}, language={lang or 'auto'})"
            )
            logger.info(
                f"  params: min_silence={self.vad_min_silence_duration}s, "
                f"min_speech={self.vad_min_speech_duration}s, "
                f"max_speech={self.vad_max_speech_duration}s"
            )
        except Exception as e:
            logger.error(f"Failed to initialize VadOfflineEngine: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize VadOfflineEngine: {e}")

    async def transcribe(
        self,
        audio_path: str,
        language: str = None,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        """
        转录音频。

        Args:
            audio_path: 音频文件路径
            language: 可选，指定语言代码（如 "ja", "zh", "en"）。
                     Whisper 模型支持运行时指定语言，其他模型忽略此参数。
            progress_cb: 进度回调，0..1。VAD 投喂占前 30%，decode 占后 70%。
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Whisper 模型支持运行时指定语言
        effective_lang = language if language else self.default_language
        if effective_lang and self.model_type == "whisper":
            if effective_lang != self.default_language:
                async with self._init_lock:
                    # Double-check：锁内再判断一次
                    if effective_lang != self.default_language:
                        logger.info(f"Re-initializing VAD+Whisper recognizer with language: {effective_lang}")
                        self._initialize(effective_lang)
                        self.default_language = effective_lang

        return await asyncio.get_running_loop().run_in_executor(
            None, self._transcribe_sync, audio_path, progress_cb
        )

    @staticmethod
    def _compute_rms_energy(
        samples: np.ndarray,
        sample_rate: int,
        frame_duration_ms: int = 30,
    ) -> Tuple[np.ndarray, int]:
        """按帧计算 RMS 能量 (dB)，单次 numpy 向量化运算。"""
        frame_size = int(sample_rate * frame_duration_ms / 1000)
        num_frames = len(samples) // frame_size
        if num_frames == 0:
            return np.array([], dtype=np.float32), frame_size
        frames = samples[:num_frames * frame_size].reshape(num_frames, frame_size)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        rms_db = 20 * np.log10(np.maximum(rms, 1e-10))
        return rms_db, frame_size

    @staticmethod
    def _segment_by_energy(
        energy_db: np.ndarray,
        frame_duration_s: float,
        min_silence_duration: float,
        min_speech_duration: float,
        max_speech_duration: float,
        margin_db: float = 10.0,
    ) -> List[Tuple[int, int]]:
        """
        基于能量的静音分段，不做语音判断。

        自动校准阈值：取能量第 10 百分位作为噪底 + margin 作为阈值。
        返回 (start_frame, end_frame) 列表。
        """
        if len(energy_db) == 0:
            return []

        # 自动校准阈值
        noise_floor = np.percentile(energy_db, 10)
        threshold = noise_floor + margin_db

        is_active = energy_db > threshold
        min_silence_frames = max(1, int(min_silence_duration / frame_duration_s))
        min_speech_frames = max(1, int(min_speech_duration / frame_duration_s))
        max_speech_frames = int(max_speech_duration / frame_duration_s)

        # 找连续活跃区间
        regions: List[List[int]] = []  # [[start, end], ...]
        in_region = False
        start = 0
        for i in range(len(is_active)):
            if is_active[i] and not in_region:
                start = i
                in_region = True
            elif not is_active[i] and in_region:
                regions.append([start, i])
                in_region = False
        if in_region:
            regions.append([start, len(is_active)])

        if not regions:
            return []

        # 合并间隔过短的相邻区间
        merged: List[List[int]] = [regions[0]]
        for r in regions[1:]:
            gap = r[0] - merged[-1][1]
            if gap < min_silence_frames:
                merged[-1][1] = r[1]
            else:
                merged.append(r)

        # 过滤过短段
        merged = [r for r in merged if (r[1] - r[0]) >= min_speech_frames]

        # 拆分过长段（在最安静帧处切分）
        final: List[Tuple[int, int]] = []
        for r in merged:
            if (r[1] - r[0]) <= max_speech_frames:
                final.append((r[0], r[1]))
            else:
                # 递归拆分
                seg_start = r[0]
                while seg_start < r[1]:
                    seg_end = min(seg_start + max_speech_frames, r[1])
                    if seg_end < r[1] and (seg_end - seg_start) >= max_speech_frames:
                        # 在后半段找最安静帧作为切分点
                        search_start = seg_start + max_speech_frames // 2
                        search_end = min(seg_end, r[1])
                        if search_start < search_end:
                            quiet_idx = search_start + int(np.argmin(energy_db[search_start:search_end]))
                            seg_end = quiet_idx + 1
                    final.append((seg_start, seg_end))
                    seg_start = seg_end

        return final

    def _transcribe_sync(
        self,
        audio_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        if self.vad_mode == "silero":
            return self._transcribe_sync_silero(audio_path, progress_cb)
        return self._transcribe_sync_energy(audio_path, progress_cb)

    @staticmethod
    def _is_retryable_decode_error(exc: Exception) -> bool:
        """识别由 ONNX shape/broadcast 触发的可恢复解码错误。"""
        message = str(exc).lower()
        retryable_markers = (
            "invalid expand shape",
            "expand node",
            "expand",
            "broadcast",
            "shape",
        )
        return any(marker in message for marker in retryable_markers)

    def _try_decode_samples(
        self,
        seg_samples: np.ndarray,
        sample_rate: int,
    ) -> str:
        """单次创建 stream 并解码，返回识别文本。"""
        stream = self.recognizer.create_stream()
        stream.accept_waveform(sample_rate, seg_samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()

    def _decode_segment_with_retry(
        self,
        samples: np.ndarray,
        sample_rate: int,
        start_sample: int,
        end_sample: int,
        *,
        depth: int = 0,
        add_padding: bool = False,
    ) -> List[Segment]:
        """
        对单个分段做安全解码。

        失败时按以下顺序补救：
        1. 前后加 padding 再试一次
        2. 仍失败则二分成两个子段递归解码
        3. 超过最大深度后跳过，不抛出异常
        """
        total_samples = len(samples)
        if total_samples == 0:
            return []

        pad_samples = int(sample_rate * self.RETRY_PADDING_S) if add_padding else 0
        decode_start = max(0, start_sample - pad_samples)
        decode_end = min(total_samples, end_sample + pad_samples)
        decode_samples = samples[decode_start:decode_end]

        min_segment_samples = int(sample_rate * self.MIN_SEGMENT_DURATION_S)
        duration_s = max(0.0, (end_sample - start_sample) / sample_rate)
        if len(decode_samples) < min_segment_samples:
            logger.warning(
                "Skipping segment due to short duration: start=%.2fs end=%.2fs duration=%.2fs",
                start_sample / sample_rate,
                end_sample / sample_rate,
                duration_s,
            )
            return []

        try:
            text = self._try_decode_samples(decode_samples, sample_rate)
            if not text or text in (".", "The.", "。"):
                return []
            return [
                Segment(
                    start=start_sample / sample_rate,
                    end=end_sample / sample_rate,
                    text=text,
                )
            ]
        except RuntimeError as exc:
            if not self._is_retryable_decode_error(exc):
                raise

            logger.warning(
                "Retryable decode error: start=%.2fs end=%.2fs duration=%.2fs depth=%d padded=%s error=%s",
                start_sample / sample_rate,
                end_sample / sample_rate,
                duration_s,
                depth,
                add_padding,
                exc,
            )

            if not add_padding:
                return self._decode_segment_with_retry(
                    samples,
                    sample_rate,
                    start_sample,
                    end_sample,
                    depth=depth,
                    add_padding=True,
                )

            if depth >= self.MAX_RETRY_DEPTH or (end_sample - start_sample) < (min_segment_samples * 2):
                logger.warning(
                    "Skipping segment after retries: start=%.2fs end=%.2fs duration=%.2fs",
                    start_sample / sample_rate,
                    end_sample / sample_rate,
                    duration_s,
                )
                return []

            mid_sample = start_sample + ((end_sample - start_sample) // 2)
            if mid_sample <= start_sample or mid_sample >= end_sample:
                logger.warning(
                    "Skipping unsplittable segment after retries: start=%.2fs end=%.2fs duration=%.2fs",
                    start_sample / sample_rate,
                    end_sample / sample_rate,
                    duration_s,
                )
                return []

            logger.info(
                "Splitting segment for retry: start=%.2fs end=%.2fs depth=%d",
                start_sample / sample_rate,
                end_sample / sample_rate,
                depth + 1,
            )
            left_segments = self._decode_segment_with_retry(
                samples,
                sample_rate,
                start_sample,
                mid_sample,
                depth=depth + 1,
                add_padding=True,
            )
            right_segments = self._decode_segment_with_retry(
                samples,
                sample_rate,
                mid_sample,
                end_sample,
                depth=depth + 1,
                add_padding=True,
            )
            return left_segments + right_segments

    # ── silero 模式 ─────────────────────────────────────────────────

    def _transcribe_sync_silero(
        self,
        audio_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        """silero_vad 检测语音段 → 批量 ASR。进度：VAD 0–30%，decode 30–100%。"""
        VAD_SHARE = 0.3
        logger.info("VadOfflineEngine._transcribe_sync started (silero mode)")
        _safe_progress(progress_cb, 0.0)

        samples, sample_rate = _read_wave(audio_path)
        window_size = self.vad.config.silero_vad.window_size

        total_samples = max(len(samples), 1)
        total_steps = max(total_samples // window_size, 1)
        vad_report_interval = max(1, total_steps // 50)
        step_idx = 0

        for i in range(0, len(samples), window_size):
            chunk = samples[i: i + window_size]
            if len(chunk) < window_size:
                break
            self.vad.accept_waveform(chunk)
            step_idx += 1
            if step_idx % vad_report_interval == 0:
                _safe_progress(progress_cb, min(VAD_SHARE - 0.001, (i / total_samples) * VAD_SHARE))

        self.vad.flush()
        _safe_progress(progress_cb, VAD_SHARE)

        decode_ranges: List[Tuple[int, int]] = []
        while not self.vad.empty():
            start_sample = int(self.vad.front.start)
            seg_samples = self.vad.front.samples
            end_sample = start_sample + len(seg_samples)
            decode_ranges.append((start_sample, end_sample))
            self.vad.pop()

        total_streams = max(len(decode_ranges), 1)
        decode_report_interval = max(1, total_streams // 50)
        segments: List[Segment] = []
        for idx, (start_sample, end_sample) in enumerate(decode_ranges):
            segments.extend(
                self._decode_segment_with_retry(
                    samples,
                    sample_rate,
                    start_sample,
                    end_sample,
                )
            )
            if (idx + 1) % decode_report_interval == 0 or (idx + 1) == total_streams:
                progressed = VAD_SHARE + (1.0 - VAD_SHARE) * ((idx + 1) / total_streams)
                _safe_progress(progress_cb, min(0.99, progressed))

        logger.info(f"silero VAD + ASR complete: {len(segments)} segments")
        _safe_progress(progress_cb, 1.0)
        return segments

    # ── energy 模式 ─────────────────────────────────────────────────

    def _transcribe_sync_energy(
        self,
        audio_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        """能量分段 → 批量 ASR。不做语音判断。进度：分段 0–10%，decode 10–100%。"""
        SEG_SHARE = 0.1
        logger.info("VadOfflineEngine._transcribe_sync started (energy mode)")
        _safe_progress(progress_cb, 0.0)

        samples, sample_rate = _read_wave(audio_path)
        frame_duration_s = self.FRAME_DURATION_MS / 1000.0

        energy_db, frame_size = self._compute_rms_energy(
            samples, sample_rate, self.FRAME_DURATION_MS
        )
        regions = self._segment_by_energy(
            energy_db, frame_duration_s,
            self.vad_min_silence_duration,
            self.vad_min_speech_duration,
            self.vad_max_speech_duration,
        )
        logger.info(f"Energy segmentation: {len(regions)} segments "
                    f"(threshold auto-calibrated, min_silence={self.vad_min_silence_duration}s)")
        _safe_progress(progress_cb, SEG_SHARE)

        decode_ranges: List[Tuple[int, int]] = []
        min_segment_samples = int(self.MIN_SEGMENT_DURATION_S * sample_rate)
        for start_frame, end_frame in regions:
            start_sample = start_frame * frame_size
            end_sample = min(end_frame * frame_size, len(samples))

            # 跳过太短的片段
            if (end_sample - start_sample) < min_segment_samples:
                logger.debug(
                    f"Skipping short segment: {(end_sample - start_sample)/sample_rate:.2f}s"
                )
                continue

            decode_ranges.append((start_sample, end_sample))

        total_streams = max(len(decode_ranges), 1)
        decode_report_interval = max(1, total_streams // 50)
        segments: List[Segment] = []
        for idx, (start_sample, end_sample) in enumerate(decode_ranges):
            segments.extend(
                self._decode_segment_with_retry(
                    samples,
                    sample_rate,
                    start_sample,
                    end_sample,
                )
            )
            if (idx + 1) % decode_report_interval == 0 or (idx + 1) == total_streams:
                progressed = SEG_SHARE + (1.0 - SEG_SHARE) * ((idx + 1) / total_streams)
                _safe_progress(progress_cb, min(0.99, progressed))

        logger.info(f"Energy segmentation + ASR complete: {len(segments)} segments")
        _safe_progress(progress_cb, 1.0)
        return segments


# ── Cloud ASR Engine ────────────────────────────────────────────────────────


class CloudASRProvider(ABC):
    """云端 ASR 厂商适配接口。"""

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str = None,
    ) -> List[Segment]:
        """调用厂商 API 并返回统一的字幕段。"""
        pass


class OpenAICompatibleASRProvider(CloudASRProvider):
    """OpenAI-compatible Speech-to-Text provider base."""

    PROVIDER_NAME = "Cloud"
    DEFAULT_BASE_URL = ""
    DEFAULT_MODEL = ""
    AUTH_SCHEME = "Bearer"
    MAX_UPLOAD_BYTES = 24 * 1024 * 1024
    URL_PREFERRED_ABOVE_BYTES = 24 * 1024 * 1024
    SUPPORTS_URL_TRANSCRIPTION = False
    URL_FORM_FIELD = "url"
    TIMESTAMP_GRANULARITY_FIELD = "timestamp_granularities[]"
    WORK_DIR_NAME = "cloud_asr"
    CHUNK_OVERLAP_SECONDS = 1.5
    MAX_CHUNK_SECONDS = 600.0
    MIN_CHUNK_SECONDS = 30.0

    def __init__(
        self,
        api_key: str,
        model: str = "",
        base_url: Optional[str] = None,
        public_audio_base_url: Optional[str] = None,
        prompt: Optional[str] = None,
    ):
        if not api_key:
            raise ValueError(f"{self.PROVIDER_NAME} ASR API key cannot be empty")
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.public_audio_base_url = (public_audio_base_url or "").rstrip("/")
        self.prompt = prompt

    async def transcribe(
        self,
        audio_path: str,
        language: str = None,
    ) -> List[Segment]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        work_dir = self._prepare_work_dir(audio_path)
        try:
            flac_path = self._convert_to_flac(audio_path, work_dir)
            flac_size = os.path.getsize(flac_path)
            duration = _get_audio_duration(flac_path)

            should_try_url = (
                self.SUPPORTS_URL_TRANSCRIPTION
                and self.public_audio_base_url
                and flac_size > self.URL_PREFERRED_ABOVE_BYTES
            )

            if should_try_url:
                audio_url = self._build_signed_audio_url(flac_path)
                try:
                    logger.info(
                        "%s ASR URL upload: url=%s size=%.2fMB duration=%.1fs",
                        self.PROVIDER_NAME,
                        audio_url.split("?", 1)[0],
                        flac_size / 1024 / 1024,
                        duration,
                    )
                    result = await self._request_transcription_url(audio_url, language)
                    return self._parse_response(result, flac_path)
                except Exception as e:
                    logger.warning(
                        "%s ASR URL transcription failed, fallback to upload/chunks: %s",
                        self.PROVIDER_NAME,
                        e,
                    )

            if flac_size <= self.MAX_UPLOAD_BYTES:
                logger.info(
                    "%s ASR direct upload: file=%s size=%.2fMB duration=%.1fs",
                    self.PROVIDER_NAME,
                    flac_path,
                    flac_size / 1024 / 1024,
                    duration,
                )
                result = await self._request_transcription(flac_path, language)
                return self._parse_response(result, flac_path)

            if self.SUPPORTS_URL_TRANSCRIPTION and self.public_audio_base_url:
                audio_url = self._build_signed_audio_url(flac_path)
                try:
                    logger.info(
                        "%s ASR URL upload: url=%s size=%.2fMB duration=%.1fs",
                        self.PROVIDER_NAME,
                        audio_url.split("?", 1)[0],
                        flac_size / 1024 / 1024,
                        duration,
                    )
                    result = await self._request_transcription_url(audio_url, language)
                    return self._parse_response(result, flac_path)
                except Exception as e:
                    logger.warning(
                        "%s ASR URL transcription failed, fallback to chunks: %s",
                        self.PROVIDER_NAME,
                        e,
                    )

            logger.info(
                "%s ASR chunking required: file=%s size=%.2fMB duration=%.1fs",
                self.PROVIDER_NAME,
                flac_path,
                flac_size / 1024 / 1024,
                duration,
            )
            return await self._transcribe_chunks(flac_path, language, duration, work_dir)
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Failed to cleanup %s ASR temp dir %s: %s", self.PROVIDER_NAME, work_dir, e)

    def _prepare_work_dir(self, audio_path: str) -> str:
        task_dir = os.path.dirname(audio_path) or None
        if task_dir:
            work_dir = os.path.join(task_dir, self.WORK_DIR_NAME)
            if os.path.isdir(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
            os.makedirs(work_dir, exist_ok=True)
            return work_dir
        return tempfile.mkdtemp(prefix=f"{self.WORK_DIR_NAME}_")

    def _convert_to_flac(self, audio_path: str, work_dir: str) -> str:
        output_path = os.path.join(work_dir, "audio.flac")
        try:
            stream = ffmpeg.input(audio_path)
            stream = ffmpeg.output(
                stream,
                output_path,
                acodec="flac",
                ar=16000,
                ac=1,
            )
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            stderr_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg error while converting audio to FLAC: {stderr_msg}")

        if not os.path.exists(output_path):
            raise RuntimeError(f"FLAC output file not created: {output_path}")
        return output_path

    def _build_signed_audio_url(self, flac_path: str) -> str:
        filename = os.path.basename(flac_path)
        task_dir = os.path.dirname(os.path.dirname(flac_path))
        task_id = os.path.basename(task_dir)
        if not task_id:
            raise RuntimeError(f"Cannot infer task_id for {self.PROVIDER_NAME} ASR signed audio URL")

        token = create_asr_audio_token(task_id, filename)
        return f"{self.public_audio_base_url}/api/asr-audio/{task_id}/{filename}?token={token}"

    async def _transcribe_chunks(
        self,
        flac_path: str,
        language: str,
        duration: float,
        work_dir: str,
    ) -> List[Segment]:
        if duration <= 0:
            raise RuntimeError("Cannot chunk audio with unknown duration")

        chunk_duration = self._estimate_chunk_duration(flac_path, duration)
        logger.info(
            "%s ASR chunk plan: chunk_duration=%.1fs overlap=%.1fs",
            self.PROVIDER_NAME,
            chunk_duration,
            self.CHUNK_OVERLAP_SECONDS,
        )

        segments: List[Segment] = []
        start = 0.0
        chunk_index = 0
        while start < duration:
            remaining = duration - start
            current_duration = min(chunk_duration, remaining)
            chunk_path = os.path.join(work_dir, f"chunk_{chunk_index:04d}.flac")
            self._create_flac_chunk(flac_path, chunk_path, start, current_duration)

            while os.path.getsize(chunk_path) > self.MAX_UPLOAD_BYTES:
                if current_duration <= self.MIN_CHUNK_SECONDS:
                    size_mb = os.path.getsize(chunk_path) / 1024 / 1024
                    raise RuntimeError(
                        f"{self.PROVIDER_NAME} ASR chunk still exceeds upload limit: {size_mb:.2f}MB"
                    )
                current_duration = max(self.MIN_CHUNK_SECONDS, current_duration / 2)
                self._create_flac_chunk(flac_path, chunk_path, start, current_duration)

            logger.info(
                "%s ASR chunk upload: index=%d start=%.2fs duration=%.2fs size=%.2fMB",
                self.PROVIDER_NAME,
                chunk_index,
                start,
                current_duration,
                os.path.getsize(chunk_path) / 1024 / 1024,
            )
            result = await self._request_transcription(chunk_path, language)
            chunk_segments = self._parse_response(result, chunk_path, offset=start)
            segments.extend(chunk_segments)

            if start + current_duration >= duration:
                break
            start += max(1.0, current_duration - self.CHUNK_OVERLAP_SECONDS)
            chunk_index += 1

        return self._deduplicate_segments(segments)

    def _estimate_chunk_duration(self, flac_path: str, duration: float) -> float:
        bytes_per_second = max(os.path.getsize(flac_path) / duration, 1.0)
        target = (self.MAX_UPLOAD_BYTES * 0.85) / bytes_per_second
        return max(self.MIN_CHUNK_SECONDS, min(self.MAX_CHUNK_SECONDS, target))

    def _create_flac_chunk(
        self,
        flac_path: str,
        output_path: str,
        start: float,
        duration: float,
    ) -> None:
        try:
            stream = ffmpeg.input(flac_path, ss=start, t=duration)
            stream = ffmpeg.output(
                stream,
                output_path,
                acodec="flac",
                ar=16000,
                ac=1,
            )
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            stderr_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg error while creating {self.PROVIDER_NAME} ASR chunk: {stderr_msg}")

        if not os.path.exists(output_path):
            raise RuntimeError(f"{self.PROVIDER_NAME} ASR chunk file not created: {output_path}")

    def _build_form_data(self, language: str = None) -> dict:
        data = {
            "model": self.model,
            "response_format": "verbose_json",
            self.TIMESTAMP_GRANULARITY_FIELD: "segment",
        }
        if language:
            data["language"] = language
        if self.prompt:
            data["prompt"] = self.prompt
        return data

    def _auth_headers(self) -> dict:
        if self.AUTH_SCHEME:
            return {"Authorization": f"{self.AUTH_SCHEME} {self.api_key}"}
        return {"Authorization": self.api_key}

    async def _request_transcription(self, audio_path: str, language: str = None) -> dict:
        try:
            import httpx

            with open(audio_path, "rb") as f:
                audio_data = f.read()

            data = self._build_form_data(language)
            files = {
                "file": (os.path.basename(audio_path), audio_data, "audio/flac"),
            }

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=self._auth_headers(),
                    data=data,
                    files=files,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"{self.PROVIDER_NAME} ASR API error: {e}")
            raise RuntimeError(f"{self.PROVIDER_NAME} transcription failed: {e}")

    async def _request_transcription_url(self, audio_url: str, language: str = None) -> dict:
        try:
            import httpx

            data = self._build_form_data(language)
            data[self.URL_FORM_FIELD] = audio_url
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=self._auth_headers(),
                    data=data,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"{self.PROVIDER_NAME} ASR API error: {e}")
            raise RuntimeError(f"{self.PROVIDER_NAME} URL transcription failed: {e}")

    def _parse_response(
        self,
        result: dict,
        audio_path: str,
        offset: float = 0.0,
    ) -> List[Segment]:
        segments = self._parse_response_if_present(result, audio_path, offset)
        if segments:
            return segments

        raise RuntimeError(f"Invalid response format from {self.PROVIDER_NAME} ASR API")

    def _parse_response_if_present(
        self,
        result: dict,
        audio_path: str,
        offset: float = 0.0,
    ) -> List[Segment]:
        segments: List[Segment] = []
        for seg in result.get("segments") or []:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            start = offset + float(seg.get("start", 0.0))
            end = offset + float(seg.get("end", 0.0))
            segments.append(
                Segment(
                    start=start,
                    end=max(start, end),
                    text=text,
                )
            )

        if segments:
            return segments

        text = str(result.get("text", "")).strip()
        if text:
            return [
                Segment(
                    start=offset,
                    end=offset + _get_audio_duration(audio_path),
                    text=text,
                )
            ]

        return []

    def _deduplicate_segments(self, segments: List[Segment]) -> List[Segment]:
        if not segments:
            return []

        result: List[Segment] = []
        for segment in sorted(segments, key=lambda s: (s.start, s.end)):
            if not segment.text:
                continue
            if result and self._is_duplicate_segment(result[-1], segment):
                continue
            result.append(segment)
        return result

    @staticmethod
    def _is_duplicate_segment(prev: Segment, current: Segment) -> bool:
        if prev.text.strip() != current.text.strip():
            return False
        overlap = min(prev.end, current.end) - max(prev.start, current.start)
        if overlap <= 0:
            return False
        min_duration = max(min(prev.duration, current.duration), 0.001)
        return overlap / min_duration >= 0.5


class GroqASRProvider(OpenAICompatibleASRProvider):
    """Groq Speech-to-Text adapter."""

    PROVIDER_NAME = "Groq"
    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
    DEFAULT_MODEL = "whisper-large-v3-turbo"
    MAX_UPLOAD_BYTES = 24 * 1024 * 1024
    SUPPORTS_URL_TRANSCRIPTION = True
    URL_FORM_FIELD = "url"


class OpenAIWhisperASRProvider(OpenAICompatibleASRProvider):
    """OpenAI Whisper transcription adapter."""

    PROVIDER_NAME = "OpenAI"
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "whisper-1"
    MAX_UPLOAD_BYTES = 24 * 1024 * 1024
    SUPPORTS_URL_TRANSCRIPTION = False


class FireworksASRProvider(OpenAICompatibleASRProvider):
    """Fireworks Whisper-compatible transcription adapter."""

    PROVIDER_NAME = "Fireworks"
    DEFAULT_BASE_URL = "https://audio-turbo.api.fireworks.ai/v1"
    DEFAULT_MODEL = "whisper-v3-turbo"
    AUTH_SCHEME = ""
    MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
    URL_PREFERRED_ABOVE_BYTES = 24 * 1024 * 1024
    SUPPORTS_URL_TRANSCRIPTION = True
    URL_FORM_FIELD = "file"
    TIMESTAMP_GRANULARITY_FIELD = "timestamp_granularities"

    async def _request_transcription_url(self, audio_url: str, language: str = None) -> dict:
        try:
            import httpx

            data = self._build_form_data(language)
            data["file"] = audio_url
            files = {key: (None, str(value)) for key, value in data.items()}
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=self._auth_headers(),
                    files=files,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Fireworks ASR API error: {e}")
            raise RuntimeError(f"Fireworks URL transcription failed: {e}")


class ElevenLabsASRProvider(OpenAICompatibleASRProvider):
    """ElevenLabs Scribe transcription adapter."""

    PROVIDER_NAME = "ElevenLabs"
    DEFAULT_BASE_URL = "https://api.elevenlabs.io/v1"
    DEFAULT_MODEL = "scribe_v2"
    MAX_UPLOAD_BYTES = 3 * 1024 * 1024 * 1024
    URL_PREFERRED_ABOVE_BYTES = 24 * 1024 * 1024
    SUPPORTS_URL_TRANSCRIPTION = True

    def _auth_headers(self) -> dict:
        return {"xi-api-key": self.api_key}

    def _build_form_data(self, language: str = None) -> dict:
        data = {
            "model_id": self.model,
            "timestamps_granularity": "word",
            "tag_audio_events": "false",
        }
        if language:
            data["language_code"] = language
        return data

    async def _request_transcription(self, audio_path: str, language: str = None) -> dict:
        try:
            import httpx

            with open(audio_path, "rb") as f:
                audio_data = f.read()

            files = {
                "file": (os.path.basename(audio_path), audio_data, "audio/flac"),
            }
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/speech-to-text",
                    headers=self._auth_headers(),
                    data=self._build_form_data(language),
                    files=files,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"ElevenLabs ASR API error: {e}")
            raise RuntimeError(f"ElevenLabs transcription failed: {e}")

    async def _request_transcription_url(self, audio_url: str, language: str = None) -> dict:
        try:
            import httpx

            data = self._build_form_data(language)
            data["cloud_storage_url"] = audio_url
            files = {key: (None, str(value)) for key, value in data.items()}
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/speech-to-text",
                    headers=self._auth_headers(),
                    files=files,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"ElevenLabs ASR API error: {e}")
            raise RuntimeError(f"ElevenLabs URL transcription failed: {e}")

    def _parse_response(
        self,
        result: dict,
        audio_path: str,
        offset: float = 0.0,
    ) -> List[Segment]:
        segments: List[Segment] = []
        for seg in result.get("segments") or []:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            start = offset + float(seg.get("start", 0.0))
            end = offset + float(seg.get("end", 0.0))
            segments.append(Segment(start=start, end=max(start, end), text=text))
        if segments:
            return segments

        words = result.get("words") or []
        if words:
            return self._segments_from_words(words, offset)

        text = str(result.get("text", "")).strip()
        if text:
            return [
                Segment(
                    start=offset,
                    end=offset + _get_audio_duration(audio_path),
                    text=text,
                )
            ]

        raise RuntimeError("Invalid response format from ElevenLabs ASR API")

    def _segments_from_words(self, words: List[dict], offset: float) -> List[Segment]:
        normalized = []
        for word in words:
            raw_text = str(word.get("text") or word.get("word") or "").strip()
            if not raw_text:
                continue
            try:
                start = float(word.get("start", 0.0))
                end = float(word.get("end", start))
            except (TypeError, ValueError):
                continue
            normalized.append({"text": raw_text, "start": start, "end": end})
        return self._segments_from_word_items(normalized, offset)

    @staticmethod
    def _segments_from_word_items(words: List[dict], offset: float) -> List[Segment]:
        segments: List[Segment] = []
        current: List[dict] = []
        current_start: Optional[float] = None
        previous_end: Optional[float] = None

        for word in words:
            raw_text = str(word.get("text") or "").strip()
            if not raw_text:
                continue
            start = float(word.get("start", 0.0))
            end = float(word.get("end", start))

            gap = start - previous_end if previous_end is not None else 0.0
            should_flush = (
                bool(current)
                and (
                    gap > 1.0
                    or end - (current_start or start) >= 6.0
                    or len(ElevenLabsASRProvider._join_word_text(current)) >= 80
                    or ElevenLabsASRProvider._join_word_text(current).endswith((".", "?", "!", "。", "？", "！"))
                )
            )
            if should_flush:
                segments.append(ElevenLabsASRProvider._word_segment(current, offset))
                current = []
                current_start = None

            if current_start is None:
                current_start = start
            current.append({"text": raw_text, "start": start, "end": end})
            previous_end = end

        if current:
            segments.append(ElevenLabsASRProvider._word_segment(current, offset))

        return segments

    @staticmethod
    def _word_segment(words: List[dict], offset: float) -> Segment:
        return Segment(
            start=offset + float(words[0]["start"]),
            end=offset + float(words[-1]["end"]),
            text=ElevenLabsASRProvider._join_word_text(words),
        )

    @staticmethod
    def _join_word_text(words: List[dict]) -> str:
        parts = [str(word["text"]).strip() for word in words if str(word["text"]).strip()]
        separator = "" if any(ElevenLabsASRProvider._has_cjk(part) for part in parts) else " "
        text = separator.join(parts)
        for punct in [".", ",", "?", "!", ":", ";", "。", "、", "？", "！"]:
            text = text.replace(f" {punct}", punct)
        return text.strip()

    @staticmethod
    def _has_cjk(text: str) -> bool:
        return any(
            "\u3040" <= char <= "\u30ff"
            or "\u3400" <= char <= "\u9fff"
            or "\uf900" <= char <= "\ufaff"
            for char in text
        )


class DeepgramASRProvider(OpenAICompatibleASRProvider):
    """Deepgram pre-recorded audio adapter."""

    PROVIDER_NAME = "Deepgram"
    DEFAULT_BASE_URL = "https://api.deepgram.com/v1"
    DEFAULT_MODEL = "nova-3"
    MAX_UPLOAD_BYTES = 24 * 1024 * 1024
    URL_PREFERRED_ABOVE_BYTES = 0
    SUPPORTS_URL_TRANSCRIPTION = True

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Token {self.api_key}"}

    def _request_params(self, language: str = None) -> dict:
        params = {
            "model": self.model,
            "smart_format": "true",
            "punctuate": "true",
            "utterances": "true",
        }
        if language:
            params["language"] = language
        return params

    async def _request_transcription(self, audio_path: str, language: str = None) -> dict:
        try:
            import httpx

            with open(audio_path, "rb") as f:
                audio_data = f.read()

            async with httpx.AsyncClient(timeout=600.0) as client:
                response = await client.post(
                    f"{self.base_url}/listen",
                    headers={
                        **self._auth_headers(),
                        "Content-Type": "audio/flac",
                    },
                    params=self._request_params(language),
                    content=audio_data,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Deepgram ASR API error: {e}")
            raise RuntimeError(f"Deepgram transcription failed: {e}")

    async def _request_transcription_url(self, audio_url: str, language: str = None) -> dict:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=600.0) as client:
                response = await client.post(
                    f"{self.base_url}/listen",
                    headers=self._auth_headers(),
                    params=self._request_params(language),
                    json={"url": audio_url},
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Deepgram ASR API error: {e}")
            raise RuntimeError(f"Deepgram URL transcription failed: {e}")

    def _parse_response(
        self,
        result: dict,
        audio_path: str,
        offset: float = 0.0,
    ) -> List[Segment]:
        segments: List[Segment] = []

        for utterance in result.get("results", {}).get("utterances") or []:
            text = str(utterance.get("transcript") or "").strip()
            if not text:
                continue
            segments.append(
                Segment(
                    start=offset + float(utterance.get("start", 0.0)),
                    end=offset + float(utterance.get("end", utterance.get("start", 0.0))),
                    text=text,
                )
            )
        if segments:
            return segments

        alternative = self._first_deepgram_alternative(result)
        paragraphs = alternative.get("paragraphs", {}).get("paragraphs") or []
        for paragraph in paragraphs:
            for sentence in paragraph.get("sentences") or []:
                text = str(sentence.get("text") or "").strip()
                if not text:
                    continue
                segments.append(
                    Segment(
                        start=offset + float(sentence.get("start", 0.0)),
                        end=offset + float(sentence.get("end", sentence.get("start", 0.0))),
                        text=text,
                    )
                )
        if segments:
            return segments

        words = alternative.get("words") or []
        if words:
            return self._segments_from_words(words, offset)

        text = str(alternative.get("transcript") or "").strip()
        if text:
            return [Segment(start=offset, end=offset + _get_audio_duration(audio_path), text=text)]

        raise RuntimeError("Invalid response format from Deepgram ASR API")

    @staticmethod
    def _first_deepgram_alternative(result: dict) -> dict:
        channels = result.get("results", {}).get("channels") or []
        if not channels:
            return {}
        alternatives = channels[0].get("alternatives") or []
        return alternatives[0] if alternatives else {}

    def _segments_from_words(self, words: List[dict], offset: float) -> List[Segment]:
        normalized = []
        for word in words:
            text = str(word.get("punctuated_word") or word.get("word") or "").strip()
            if not text:
                continue
            try:
                start = float(word.get("start", 0.0))
                end = float(word.get("end", start))
            except (TypeError, ValueError):
                continue
            normalized.append({"text": text, "start": start, "end": end})
        return ElevenLabsASRProvider._segments_from_word_items(normalized, offset)


class AsyncUrlJobASRProvider(OpenAICompatibleASRProvider):
    """Base class for providers that require a public audio URL and async polling."""

    POLL_INTERVAL_SECONDS = 5.0
    POLL_TIMEOUT_SECONDS = 1800.0
    URL_PREFERRED_ABOVE_BYTES = 0
    SUPPORTS_URL_TRANSCRIPTION = True

    async def transcribe(
        self,
        audio_path: str,
        language: str = None,
    ) -> List[Segment]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if not self.public_audio_base_url:
            raise RuntimeError(f"{self.PROVIDER_NAME} ASR requires a public audio access URL")

        work_dir = self._prepare_work_dir(audio_path)
        try:
            flac_path = self._convert_to_flac(audio_path, work_dir)
            flac_size = os.path.getsize(flac_path)
            duration = _get_audio_duration(flac_path)
            audio_url = self._build_signed_audio_url(flac_path)
            logger.info(
                "%s ASR async URL submit: url=%s size=%.2fMB duration=%.1fs",
                self.PROVIDER_NAME,
                audio_url.split("?", 1)[0],
                flac_size / 1024 / 1024,
                duration,
            )
            job_id = await self._submit_job(audio_url, language)
            result = await self._poll_job(job_id)
            segments = self._parse_response(result, flac_path)
            if segments:
                return segments
            raise RuntimeError(f"Invalid response format from {self.PROVIDER_NAME} ASR API")
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Failed to cleanup %s ASR temp dir %s: %s", self.PROVIDER_NAME, work_dir, e)

    async def _submit_job(self, audio_url: str, language: str = None) -> str:
        raise NotImplementedError

    async def _poll_job(self, job_id: str) -> dict:
        deadline = asyncio.get_event_loop().time() + self.POLL_TIMEOUT_SECONDS
        last_status = None
        while asyncio.get_event_loop().time() < deadline:
            result, done, failed, status = await self._query_job(job_id)
            last_status = status
            if done:
                return result
            if failed:
                raise RuntimeError(f"{self.PROVIDER_NAME} ASR job failed: {status}")
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
        raise RuntimeError(f"{self.PROVIDER_NAME} ASR job timed out, last status: {last_status}")

    async def _query_job(self, job_id: str) -> Tuple[dict, bool, bool, str]:
        raise NotImplementedError


class VolcengineASRProvider(AsyncUrlJobASRProvider):
    """Volcengine audio/video subtitle generation adapter."""

    PROVIDER_NAME = "Volcengine"
    DEFAULT_BASE_URL = "https://openspeech.bytedance.com/api/v1/vc"
    DEFAULT_MODEL = "bigmodel"

    def __init__(
        self,
        api_key: str,
        app_id: str,
        model: str = DEFAULT_MODEL,
        base_url: Optional[str] = None,
        public_audio_base_url: Optional[str] = None,
    ):
        if not app_id:
            raise ValueError("Volcengine ASR app_id cannot be empty")
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            public_audio_base_url=public_audio_base_url,
        )
        self.app_id = app_id

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer; {self.api_key}"}

    async def _submit_job(self, audio_url: str, language: str = None) -> str:
        try:
            import httpx

            payload = {
                "url": audio_url,
                "audio_text": "",
            }
            params = {
                "appid": self.app_id,
                "language": self._map_language(language),
            }
            if self.model:
                params["cluster"] = self.model
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/submit",
                    headers=self._auth_headers(),
                    params=params,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            job_id = str(data.get("id") or data.get("task_id") or data.get("job_id") or "")
            if not job_id and isinstance(data.get("resp"), dict):
                resp = data["resp"]
                job_id = str(resp.get("id") or resp.get("task_id") or resp.get("job_id") or "")
            if not job_id:
                raise RuntimeError(f"Volcengine submit response missing job id: {data}")
            return job_id
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Volcengine ASR API error: {e}")
            raise RuntimeError(f"Volcengine submit failed: {e}")

    async def _query_job(self, job_id: str) -> Tuple[dict, bool, bool, str]:
        try:
            import httpx

            params = {"appid": self.app_id, "id": job_id}
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(
                    f"{self.base_url}/query",
                    headers=self._auth_headers(),
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            code = str(data.get("code", "0"))
            status = str(data.get("status") or data.get("message") or code)
            failed = code not in {"0", "20000000"} and any(
                keyword in status.lower() for keyword in ["fail", "error", "invalid", "not"]
            )
            done = bool(self._extract_utterances(data)) or status.lower() in {"success", "done", "completed"}
            return data, done, failed, status
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Volcengine ASR API error: {e}")
            raise RuntimeError(f"Volcengine query failed: {e}")

    def _parse_response(self, result: dict, audio_path: str, offset: float = 0.0) -> List[Segment]:
        segments: List[Segment] = []
        for utterance in self._extract_utterances(result):
            text = str(utterance.get("text") or utterance.get("utterance") or "").strip()
            if not text:
                continue
            start = self._time_to_seconds(
                utterance.get("start_time")
                or utterance.get("start")
                or utterance.get("begin_time")
                or utterance.get("begin")
            )
            end = self._time_to_seconds(
                utterance.get("end_time")
                or utterance.get("end")
                or utterance.get("stop_time")
                or utterance.get("stop")
            )
            segments.append(Segment(start=offset + start, end=offset + max(start, end), text=text))
        return segments

    @staticmethod
    def _extract_utterances(data: dict) -> List[dict]:
        for key in ("utterances", "result", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if isinstance(data.get("data"), dict):
            return VolcengineASRProvider._extract_utterances(data["data"])
        if isinstance(data.get("resp"), dict):
            return VolcengineASRProvider._extract_utterances(data["resp"])
        return []

    @staticmethod
    def _time_to_seconds(value) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return numeric / 1000.0 if numeric > 1000 else numeric

    @staticmethod
    def _map_language(language: str = None) -> str:
        mapping = {"en": "en-US", "ja": "ja-JP"}
        return mapping.get(language or "", language or "ja-JP")


class TencentASRProvider(AsyncUrlJobASRProvider):
    """Tencent Cloud recording file recognition adapter."""

    PROVIDER_NAME = "Tencent"
    DEFAULT_BASE_URL = "https://asr.tencentcloudapi.com"
    DEFAULT_MODEL = "16k_ja"
    API_VERSION = "2019-06-14"
    SERVICE = "asr"
    REGION = "ap-guangzhou"

    def __init__(
        self,
        api_key: str,
        secret_id: str,
        model: str = DEFAULT_MODEL,
        base_url: Optional[str] = None,
        public_audio_base_url: Optional[str] = None,
        region: Optional[str] = None,
    ):
        if not secret_id:
            raise ValueError("Tencent ASR SecretId cannot be empty")
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            public_audio_base_url=public_audio_base_url,
        )
        self.secret_id = secret_id
        self.region = region or self.REGION

    async def _submit_job(self, audio_url: str, language: str = None) -> str:
        payload = {
            "EngineModelType": self._engine_model_type(language),
            "ChannelNum": 1,
            "ResTextFormat": 0,
            "SourceType": 0,
            "Url": audio_url,
        }
        data = await self._call_tencent_api("CreateRecTask", payload)
        response = data.get("Response", {})
        task_id = (
            response.get("Data", {}).get("TaskId")
            if isinstance(response.get("Data"), dict)
            else None
        ) or response.get("TaskId")
        if not task_id:
            raise RuntimeError(f"Tencent submit response missing TaskId: {data}")
        return str(task_id)

    async def _query_job(self, job_id: str) -> Tuple[dict, bool, bool, str]:
        task_id = int(job_id) if str(job_id).isdigit() else job_id
        data = await self._call_tencent_api("DescribeTaskStatus", {"TaskId": task_id})
        response = data.get("Response", {})
        task_data = response.get("Data") if isinstance(response.get("Data"), dict) else response
        status_value = task_data.get("Status")
        status_text = str(task_data.get("StatusStr") or status_value)
        done = status_value == 2 or status_text.lower() in {"success", "done", "completed"}
        failed = status_value in {3, -1} or status_text.lower() in {"failed", "error"}
        return task_data, done, failed, status_text

    async def _call_tencent_api(self, action: str, payload: dict) -> dict:
        try:
            import httpx

            body = json.dumps(payload, separators=(",", ":"))
            timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            headers = self._sign_headers(action, body, timestamp)
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(self.base_url, headers=headers, content=body)
                response.raise_for_status()
                data = response.json()
            if data.get("Response", {}).get("Error"):
                raise RuntimeError(data["Response"]["Error"])
            return data
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Tencent ASR API error: {e}")
            raise RuntimeError(f"Tencent API call failed: {e}")

    def _sign_headers(self, action: str, body: str, timestamp: int) -> dict:
        host = self.base_url.replace("https://", "").replace("http://", "").split("/", 1)[0]
        date = datetime.datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        hashed_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_request = "\n".join([
            "POST",
            "/",
            "",
            f"content-type:application/json; charset=utf-8\nhost:{host}\nx-tc-action:{action.lower()}\n",
            "content-type;host;x-tc-action",
            hashed_payload,
        ])
        credential_scope = f"{date}/{self.SERVICE}/tc3_request"
        string_to_sign = "\n".join([
            "TC3-HMAC-SHA256",
            str(timestamp),
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])
        secret_date = hmac.new(("TC3" + self.api_key).encode("utf-8"), date.encode("utf-8"), hashlib.sha256).digest()
        secret_service = hmac.new(secret_date, self.SERVICE.encode("utf-8"), hashlib.sha256).digest()
        secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "TC3-HMAC-SHA256 "
            f"Credential={self.secret_id}/{credential_scope}, "
            "SignedHeaders=content-type;host;x-tc-action, "
            f"Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.API_VERSION,
            "X-TC-Region": self.region,
        }

    def _parse_response(self, result: dict, audio_path: str, offset: float = 0.0) -> List[Segment]:
        segments = self._parse_tencent_details(result, offset)
        if segments:
            return segments
        text = str(result.get("Result") or "").strip()
        if text:
            parsed = self._parse_tencent_result_text(text, offset)
            if parsed:
                return parsed
            return [Segment(start=offset, end=offset + _get_audio_duration(audio_path), text=text)]
        return []

    @staticmethod
    def _parse_tencent_details(result: dict, offset: float) -> List[Segment]:
        details = result.get("ResultDetail") or result.get("SentenceDetail") or []
        segments: List[Segment] = []
        for item in details:
            text = str(item.get("FinalSentence") or item.get("Text") or item.get("SliceSentence") or "").strip()
            if not text:
                continue
            start = (
                TencentASRProvider._milliseconds_to_seconds(item.get("StartMs"))
                if item.get("StartMs") is not None
                else TencentASRProvider._time_to_seconds(item.get("StartTime") or item.get("BeginTime"))
            )
            end = (
                TencentASRProvider._milliseconds_to_seconds(item.get("EndMs"))
                if item.get("EndMs") is not None
                else TencentASRProvider._time_to_seconds(item.get("EndTime") or item.get("End"))
            )
            segments.append(Segment(start=offset + start, end=offset + max(start, end), text=text))
        return segments

    @staticmethod
    def _parse_tencent_result_text(text: str, offset: float) -> List[Segment]:
        segments: List[Segment] = []
        pattern = re.compile(r"\[(\d+(?:\.\d+)?)[:：](\d+(?:\.\d+)?)\]\s*(.+?)(?=\n\[|\Z)", re.S)
        for match in pattern.finditer(text):
            start = float(match.group(1))
            end = float(match.group(2))
            content = match.group(3).strip()
            if content:
                segments.append(Segment(start=offset + start, end=offset + max(start, end), text=content))
        return segments

    @staticmethod
    def _time_to_seconds(value) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return numeric / 1000.0 if numeric > 10000 else numeric

    @staticmethod
    def _milliseconds_to_seconds(value) -> float:
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            return 0.0

    def _engine_model_type(self, language: str = None) -> str:
        if self.model:
            return self.model
        mapping = {"en": "16k_en", "ja": "16k_ja"}
        return mapping.get(language or "", "16k_ja")


class AliyunASRProvider(AsyncUrlJobASRProvider):
    """Alibaba Cloud Model Studio Fun-ASR transcription adapter."""

    PROVIDER_NAME = "Aliyun"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
    DEFAULT_MODEL = "fun-asr-mtl"

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _submit_job(self, audio_url: str, language: str = None) -> str:
        try:
            import httpx

            payload = {
                "model": self.model,
                "input": {"file_urls": [audio_url]},
                "parameters": {
                    "channel_id": [0],
                    "language_hints": [self._map_language(language)],
                },
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/services/audio/asr/transcription",
                    headers={
                        **self._auth_headers(),
                        "X-DashScope-Async": "enable",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            task_id = str(data.get("output", {}).get("task_id") or "")
            if not task_id:
                raise RuntimeError(f"Aliyun submit response missing task_id: {data}")
            return task_id
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Aliyun ASR API error: {e}")
            raise RuntimeError(f"Aliyun submit failed: {e}")

    async def _query_job(self, job_id: str) -> Tuple[dict, bool, bool, str]:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/tasks/{job_id}",
                    headers={
                        **self._auth_headers(),
                        "X-DashScope-Async": "enable",
                    },
                )
                response.raise_for_status()
                data = response.json()

            output = data.get("output", data)
            status = str(output.get("task_status") or data.get("task_status") or "")
            if status == "SUCCEEDED":
                return await self._load_transcription_result(output), True, False, status
            failed = status in {"FAILED", "CANCELED", "UNKNOWN"}
            return data, False, failed, status
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Aliyun ASR API error: {e}")
            raise RuntimeError(f"Aliyun query failed: {e}")

    async def _load_transcription_result(self, output: dict) -> dict:
        try:
            import httpx

            results = output.get("results") or []
            for item in results:
                if item.get("subtask_status") != "SUCCEEDED":
                    continue
                transcription_url = item.get("transcription_url")
                if not transcription_url:
                    continue
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.get(transcription_url)
                    response.raise_for_status()
                    return response.json()
            raise RuntimeError(f"Aliyun task succeeded but no transcription_url found: {output}")
        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Aliyun transcription result download failed: {e}")
            raise

    def _parse_response(self, result: dict, audio_path: str, offset: float = 0.0) -> List[Segment]:
        segments: List[Segment] = []
        for transcript in result.get("transcripts") or []:
            for sentence in transcript.get("sentences") or []:
                text = str(sentence.get("text") or "").strip()
                if not text:
                    continue
                start = self._milliseconds_to_seconds(sentence.get("begin_time"))
                end = self._milliseconds_to_seconds(sentence.get("end_time"))
                segments.append(
                    Segment(
                        start=offset + start,
                        end=offset + max(start, end),
                        text=text,
                    )
                )
        if segments:
            return segments

        text_parts = [
            str(transcript.get("text") or "").strip()
            for transcript in result.get("transcripts") or []
            if str(transcript.get("text") or "").strip()
        ]
        if text_parts:
            return [
                Segment(
                    start=offset,
                    end=offset + _get_audio_duration(audio_path),
                    text="\n".join(text_parts),
                )
            ]
        return []

    @staticmethod
    def _milliseconds_to_seconds(value) -> float:
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _map_language(language: str = None) -> str:
        mapping = {"en": "en", "ja": "ja"}
        return mapping.get(language or "", language or "ja")


def _get_audio_duration(audio_path: str) -> float:
    try:
        with wave.open(audio_path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        try:
            probe = ffmpeg.probe(audio_path)
            duration = probe.get("format", {}).get("duration")
            return float(duration) if duration else 0.0
        except Exception:
            return 0.0


class CloudASREngine(ASREngine):
    """Cloud-based ASR engine."""

    def __init__(self, provider: CloudASRProvider):
        self.provider = provider

    async def transcribe(
        self,
        audio_path: str,
        language: str = None,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> List[Segment]:
        """
        转录音频。

        Args:
            audio_path: 音频文件路径
            language: 语言代码（如 "ja", "zh", "en"），传给云端 API
            progress_cb: 进度回调，云端 API 是单次请求只在开始/结束上报。
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        _safe_progress(progress_cb, 0.0)
        effective_lang = language if language else "ja"
        try:
            segments = await self.provider.transcribe(audio_path, effective_lang)
            _safe_progress(progress_cb, 1.0)
            return segments
        except Exception as e:
            raise RuntimeError(f"Transcription failed: {e}")


# ── 向后兼容别名 ────────────────────────────────────────────────────────────

# 旧代码 import SherpaOnnxEngine 的地方仍能工作
SherpaOnnxEngine = SherpaOnnxOnlineEngine
