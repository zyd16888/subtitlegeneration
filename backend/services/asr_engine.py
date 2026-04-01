"""
ASR (Automatic Speech Recognition) Engine Module

Supports:
- SherpaOnnxOnlineEngine  — 流式识别 (OnlineRecognizer)
- SherpaOnnxOfflineEngine — 离线识别 (OfflineRecognizer, 包括 whisper / transducer)
- CloudASREngine          — 云端 ASR API
"""

import asyncio
import logging
import os
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import sherpa_onnx

logger = logging.getLogger(__name__)


def _read_wave(audio_path: str) -> Tuple[List[float], int]:
    """读取 WAV 文件，返回 (float32 samples list, sample_rate)"""
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

    return samples.tolist(), sample_rate


@dataclass
class Segment:
    """Transcribed text segment with timestamps."""
    start: float
    end: float
    text: str


class ASREngine(ABC):
    """Abstract base class for ASR engines."""

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str = "ja",
    ) -> List[Segment]:
        pass


# ── Online (Streaming) Engine ───────────────────────────────────────────────


class SherpaOnnxOnlineEngine(ASREngine):
    """
    流式 ASR 引擎 (sherpa_onnx.OnlineRecognizer)。

    适用于 streaming-zipformer 系列模型，需要 encoder / decoder / joiner / tokens。
    """

    def __init__(self, model_path: str, file_map: Optional[Dict[str, str]] = None):
        """
        Args:
            model_path: 模型目录
            file_map:   {"tokens": "tokens.txt", "encoder": "...", "decoder": "...", "joiner": "..."}
                        不传则使用默认文件名。
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")

        self.model_path = model_path
        self.file_map = file_map or {
            "tokens": "tokens.txt",
            "encoder": "encoder.onnx",
            "decoder": "decoder.onnx",
            "joiner": "joiner.onnx",
        }
        self.recognizer: Optional[sherpa_onnx.OnlineRecognizer] = None
        self._initialize_recognizer()

    def _initialize_recognizer(self):
        try:
            tokens_path = os.path.join(self.model_path, self.file_map["tokens"])
            encoder_path = os.path.join(self.model_path, self.file_map["encoder"])
            decoder_path = os.path.join(self.model_path, self.file_map["decoder"])
            joiner_path = os.path.join(self.model_path, self.file_map["joiner"])

            logger.info(f"Initializing OnlineRecognizer with model_path: {self.model_path}")
            logger.info(f"  tokens: {tokens_path} (exists: {os.path.exists(tokens_path)})")
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

    async def transcribe(self, audio_path: str, language: str = "ja") -> List[Segment]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if self.recognizer is None:
            raise RuntimeError("Recognizer not initialized")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: str) -> List[Segment]:
        wave, sample_rate = _read_wave(audio_path)
        stream = self.recognizer.create_stream()

        chunk_size = int(0.1 * sample_rate)
        segments: List[Segment] = []
        current_time = 0.0

        for i in range(0, len(wave), chunk_size):
            chunk = wave[i : i + chunk_size]
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

        text = self.recognizer.get_result(stream).strip()
        if text:
            segments.append(
                Segment(
                    start=current_time - len(wave[-chunk_size:]) / sample_rate,
                    end=current_time,
                    text=text,
                )
            )
        return segments


# ── Offline (Non-streaming) Engine ──────────────────────────────────────────


class SherpaOnnxOfflineEngine(ASREngine):
    """
    离线 ASR 引擎 (sherpa_onnx.OfflineRecognizer)。

    支持两种模型类型：
    - transducer: zipformer 等离线模型 (encoder + decoder + joiner)
    - whisper:    whisper 系列模型 (encoder + decoder)
    """

    def __init__(
        self,
        model_path: str,
        model_type: str = "transducer",
        file_map: Optional[Dict[str, str]] = None,
        language: str = "",
    ):
        """
        Args:
            model_path: 模型目录
            model_type: "transducer" 或 "whisper"
            file_map:   各文件的映射
            language:   语言代码 (如 "ja", "zh", "en")，空字符串表示自动检测
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")

        self.model_path = model_path
        self.model_type = model_type
        self.language = language
        self.file_map = file_map or self._default_file_map()
        self.recognizer: Optional[sherpa_onnx.OfflineRecognizer] = None
        self._initialize_recognizer()

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

    def _initialize_recognizer(self):
        try:
            tokens_path = os.path.join(self.model_path, self.file_map["tokens"])
            encoder_path = os.path.join(self.model_path, self.file_map["encoder"])
            decoder_path = os.path.join(self.model_path, self.file_map["decoder"])

            logger.info(f"Initializing OfflineRecognizer with model_path: {self.model_path}")
            logger.info(f"  model_type: {self.model_type}")
            logger.info(f"  tokens: {tokens_path} (exists: {os.path.exists(tokens_path)})")
            logger.info(f"  encoder: {encoder_path} (exists: {os.path.exists(encoder_path)})")
            logger.info(f"  decoder: {decoder_path} (exists: {os.path.exists(decoder_path)})")

            if self.model_type == "whisper":
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    tokens=tokens_path,
                    language=self.language,
                    task="transcribe",
                    num_threads=4,
                    decoding_method="greedy_search",
                )
            else:
                joiner_path = os.path.join(self.model_path, self.file_map["joiner"])
                logger.info(f"  joiner: {joiner_path} (exists: {os.path.exists(joiner_path)})")

                self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    joiner=joiner_path,
                    tokens=tokens_path,
                    num_threads=4,
                    decoding_method="greedy_search",
                )

            logger.info("OfflineRecognizer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OfflineRecognizer ({self.model_type}): {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize OfflineRecognizer ({self.model_type}): {e}")

    async def transcribe(self, audio_path: str, language: str = "ja") -> List[Segment]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if self.recognizer is None:
            raise RuntimeError("Recognizer not initialized")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: str) -> List[Segment]:
        wave, sample_rate = _read_wave(audio_path)

        stream = self.recognizer.create_stream()
        stream.accept_waveform(sample_rate, wave)
        self.recognizer.decode_stream(stream)

        text = stream.result.text.strip()
        if not text:
            return []

        duration = len(wave) / sample_rate

        # OfflineRecognizer 不提供时间戳，按固定长度切分
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


# ── VAD + Offline Engine ───────────────────────────────────────────────────


class SherpaOnnxVadOfflineEngine(ASREngine):
    """
    VAD + 离线 ASR 引擎。

    先用 silero_vad 检测语音段获得精确时间戳，再逐段用 OfflineRecognizer 识别。
    相比 SherpaOnnxOfflineEngine，字幕时间戳更准确。
    """

    def __init__(
        self,
        model_path: str,
        model_type: str = "transducer",
        file_map: Optional[Dict[str, str]] = None,
        language: str = "",
        vad_model_path: str = "",
        vad_threshold: float = 0.5,
        vad_min_silence_duration: float = 0.5,
        vad_min_speech_duration: float = 0.25,
        vad_max_speech_duration: float = 20.0,
    ):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")
        if not vad_model_path or not os.path.exists(vad_model_path):
            raise FileNotFoundError(f"VAD model not found: {vad_model_path}")

        self.model_path = model_path
        self.model_type = model_type
        self.language = language
        self.file_map = file_map or SherpaOnnxOfflineEngine(model_path, model_type)._default_file_map()
        self.vad_model_path = vad_model_path
        self.vad_threshold = vad_threshold
        self.vad_min_silence_duration = vad_min_silence_duration
        self.vad_min_speech_duration = vad_min_speech_duration
        self.vad_max_speech_duration = vad_max_speech_duration

        self.recognizer: Optional[sherpa_onnx.OfflineRecognizer] = None
        self.vad: Optional[sherpa_onnx.VoiceActivityDetector] = None
        self._initialize()

    def _initialize(self):
        try:
            tokens_path = os.path.join(self.model_path, self.file_map["tokens"])
            encoder_path = os.path.join(self.model_path, self.file_map["encoder"])
            decoder_path = os.path.join(self.model_path, self.file_map["decoder"])

            # 创建 OfflineRecognizer
            if self.model_type == "whisper":
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    tokens=tokens_path,
                    language=self.language,
                    task="transcribe",
                    num_threads=4,
                    decoding_method="greedy_search",
                )
            else:
                joiner_path = os.path.join(self.model_path, self.file_map["joiner"])
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    joiner=joiner_path,
                    tokens=tokens_path,
                    num_threads=4,
                    decoding_method="greedy_search",
                )

            # 创建 VAD
            vad_config = sherpa_onnx.VadModelConfig()
            vad_config.silero_vad.model = self.vad_model_path
            vad_config.silero_vad.threshold = self.vad_threshold
            vad_config.silero_vad.min_silence_duration = self.vad_min_silence_duration
            vad_config.silero_vad.min_speech_duration = self.vad_min_speech_duration
            vad_config.silero_vad.max_speech_duration = self.vad_max_speech_duration
            vad_config.sample_rate = 16000
            vad_config.num_threads = 4

            self.vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)
            logger.info("VadOfflineEngine initialized (VAD + OfflineRecognizer)")
        except Exception as e:
            logger.error(f"Failed to initialize VadOfflineEngine: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize VadOfflineEngine: {e}")

    async def transcribe(self, audio_path: str, language: str = "ja") -> List[Segment]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: str) -> List[Segment]:
        samples, sample_rate = _read_wave(audio_path)
        window_size = self.vad.config.silero_vad.window_size  # 512 for 16kHz

        segments: List[Segment] = []

        # 逐窗口喂入 VAD
        for i in range(0, len(samples), window_size):
            chunk = samples[i: i + window_size]
            if len(chunk) < window_size:
                break
            self.vad.accept_waveform(chunk)
            self._process_vad_segments(sample_rate, segments)

        # 处理剩余音频
        self.vad.flush()
        self._process_vad_segments(sample_rate, segments)

        logger.info(f"VAD+ASR transcription complete: {len(segments)} segments")
        return segments

    def _process_vad_segments(self, sample_rate: int, segments: List[Segment]):
        while not self.vad.empty():
            start_time = self.vad.front.start / sample_rate
            seg_samples = self.vad.front.samples
            duration = len(seg_samples) / sample_rate

            stream = self.recognizer.create_stream()
            stream.accept_waveform(sample_rate, list(seg_samples))
            self.recognizer.decode_stream(stream)
            text = stream.result.text.strip()

            if text:
                segments.append(Segment(start=start_time, end=start_time + duration, text=text))

            self.vad.pop()


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

    async def transcribe(self, audio_path: str, language: str = "ja") -> List[Segment]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            import httpx

            with open(audio_path, "rb") as f:
                audio_data = f.read()

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/octet-stream",
            }
            params = {
                "language": language,
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
