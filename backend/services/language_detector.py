"""
音频语言检测服务（Whisper LID）

使用 sherpa-onnx 的 SpokenLanguageIdentification API，
基于 Whisper multilingual 模型检测音频的语言。
"""
import logging
import os
import wave
from typing import Optional

import numpy as np
import sherpa_onnx

logger = logging.getLogger(__name__)


class LanguageDetector:
    """基于 Whisper 的音频语言检测器。

    复用已下载的 Whisper multilingual 模型（tiny/base/small/medium/large），
    只需 encoder + decoder 两个 ONNX 文件即可。
    """

    def __init__(
        self,
        model_path: str,
        encoder_file: str,
        decoder_file: str,
        num_threads: int = 4,
    ):
        encoder = os.path.join(model_path, encoder_file)
        decoder = os.path.join(model_path, decoder_file)

        if not os.path.exists(encoder):
            raise FileNotFoundError(f"LID encoder 文件不存在: {encoder}")
        if not os.path.exists(decoder):
            raise FileNotFoundError(f"LID decoder 文件不存在: {decoder}")

        config = sherpa_onnx.SpokenLanguageIdentificationConfig(
            whisper=sherpa_onnx.SpokenLanguageIdentificationWhisperConfig(
                encoder=encoder,
                decoder=decoder,
            ),
            num_threads=num_threads,
        )
        self.slid = sherpa_onnx.SpokenLanguageIdentification(config)
        logger.info(
            f"LanguageDetector 初始化完成: encoder={encoder_file}, "
            f"decoder={decoder_file}"
        )

    def detect(self, audio_path: str, max_duration: float = 30.0) -> Optional[str]:
        """检测音频语言。

        Args:
            audio_path: 16kHz mono WAV 音频文件路径。
            max_duration: 最多使用前 N 秒音频做检测，减少开销。

        Returns:
            检测到的 2 字母语言代码（如 "ja", "en", "zh"），
            检测失败时返回 None。
        """
        try:
            samples, sample_rate = self._read_wav(audio_path, max_duration)
            if len(samples) == 0:
                logger.warning("音频为空，无法检测语言")
                return None

            stream = self.slid.create_stream()
            stream.accept_waveform(sample_rate=sample_rate, waveform=samples)
            lang = self.slid.compute(stream)

            logger.info(
                f"语言检测结果: {lang} "
                f"(采样 {len(samples) / sample_rate:.1f}s / {sample_rate}Hz)"
            )
            return lang if lang else None

        except Exception as e:
            logger.error(f"语言检测失败: {e}", exc_info=True)
            return None

    @staticmethod
    def _read_wav(path: str, max_duration: float) -> tuple:
        """读取 WAV 文件，返回 (samples_float32, sample_rate)。

        只读取前 max_duration 秒。
        """
        with wave.open(path, "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            n_frames = wf.getnframes()

            max_frames = int(max_duration * sample_rate)
            read_frames = min(n_frames, max_frames)

            raw = wf.readframes(read_frames)

        # 转换为 float32 [-1, 1]
        if sample_width == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        # 多声道取第一声道
        if n_channels > 1:
            samples = samples[::n_channels]

        return samples.tolist(), sample_rate
