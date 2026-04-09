"""
ASR (Automatic Speech Recognition) Engine Module

Supports:
- SherpaOnnxOnlineEngine  — 流式识别 (OnlineRecognizer)
- SherpaOnnxOfflineEngine — 离线识别 (OfflineRecognizer, 包括 whisper / transducer)
- CloudASREngine          — 云端 ASR API

参考官方示例优化：https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/generate-subtitles.py
"""

import asyncio
import logging
import os
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import sherpa_onnx

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
    DEFAULT_VAD_MIN_SILENCE_DURATION = 0.25
    DEFAULT_VAD_MIN_SPEECH_DURATION = 0.25
    DEFAULT_VAD_MAX_SPEECH_DURATION = 5.0
    FRAME_DURATION_MS = 30  # energy 模式帧长

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

        streams = []
        vad_segments = []
        while not self.vad.empty():
            start_time = self.vad.front.start / sample_rate
            seg_samples = self.vad.front.samples
            duration = len(seg_samples) / sample_rate

            stream = self.recognizer.create_stream()
            stream.accept_waveform(sample_rate, seg_samples)
            streams.append(stream)
            vad_segments.append((start_time, duration))
            self.vad.pop()

        total_streams = max(len(streams), 1)
        decode_report_interval = max(1, total_streams // 50)
        for idx, s in enumerate(streams):
            self.recognizer.decode_stream(s)
            if (idx + 1) % decode_report_interval == 0 or (idx + 1) == total_streams:
                progressed = VAD_SHARE + (1.0 - VAD_SHARE) * ((idx + 1) / total_streams)
                _safe_progress(progress_cb, min(0.99, progressed))

        segments: List[Segment] = []
        for (start_time, duration), stream in zip(vad_segments, streams):
            text = stream.result.text.strip()
            if not text or text in (".", "The.", "。"):
                continue
            segments.append(Segment(start=start_time, end=start_time + duration, text=text))

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

        streams = []
        seg_times: List[Tuple[float, float]] = []
        for start_frame, end_frame in regions:
            start_sample = start_frame * frame_size
            end_sample = min(end_frame * frame_size, len(samples))
            seg_samples = samples[start_sample:end_sample]

            stream = self.recognizer.create_stream()
            stream.accept_waveform(sample_rate, seg_samples)
            streams.append(stream)
            seg_times.append((start_sample / sample_rate, end_sample / sample_rate))

        total_streams = max(len(streams), 1)
        decode_report_interval = max(1, total_streams // 50)
        for idx, s in enumerate(streams):
            self.recognizer.decode_stream(s)
            if (idx + 1) % decode_report_interval == 0 or (idx + 1) == total_streams:
                progressed = SEG_SHARE + (1.0 - SEG_SHARE) * ((idx + 1) / total_streams)
                _safe_progress(progress_cb, min(0.99, progressed))

        segments: List[Segment] = []
        for (start_time, end_time), stream in zip(seg_times, streams):
            text = stream.result.text.strip()
            if not text:
                continue
            segments.append(Segment(start=start_time, end=end_time, text=text))

        logger.info(f"Energy segmentation + ASR complete: {len(segments)} segments")
        _safe_progress(progress_cb, 1.0)
        return segments


# ── Cloud ASR Engine ────────────────────────────────────────────────────────


class CloudASREngine(ASREngine):
    """Cloud-based ASR engine."""

    def __init__(self, api_url: str, api_key: str):
        if not api_url:
            raise ValueError("API URL cannot be empty")
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key

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
            import httpx

            with open(audio_path, "rb") as f:
                audio_data = f.read()

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/octet-stream",
            }
            params = {
                "language": effective_lang,
                "format": "wav",
                "sample_rate": 16000,
                "channels": 1,
            }

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.api_url}/transcribe",
                    headers=headers,
                    params=params,
                    content=audio_data,
                )
                response.raise_for_status()
                result = response.json()

            segments: List[Segment] = []
            if "segments" in result:
                for seg in result["segments"]:
                    segments.append(
                        Segment(start=float(seg["start"]), end=float(seg["end"]), text=seg["text"].strip())
                    )
            elif "text" in result:
                segments.append(
                    Segment(start=0.0, end=self._get_audio_duration(audio_path), text=result["text"].strip())
                )
            else:
                raise RuntimeError("Invalid response format from cloud ASR API")
            _safe_progress(progress_cb, 1.0)
            return segments

        except Exception as e:
            if hasattr(e, "response"):
                raise RuntimeError(f"Cloud ASR API error: {e}")
            raise RuntimeError(f"Transcription failed: {e}")

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float:
        try:
            import wave

            with wave.open(audio_path, "rb") as wf:
                return wf.getnframes() / float(wf.getframerate())
        except Exception:
            return 0.0


# ── 向后兼容别名 ────────────────────────────────────────────────────────────

# 旧代码 import SherpaOnnxEngine 的地方仍能工作
SherpaOnnxEngine = SherpaOnnxOnlineEngine
