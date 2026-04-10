"""
音频语言检测服务（Whisper LID）

使用 sherpa-onnx 的 SpokenLanguageIdentification API，
基于 Whisper multilingual 模型检测音频的语言。

支持 VAD 预筛 + 多段采样投票，避免 OP/ED 音乐导致误判。
"""
import logging
import os
import wave
from collections import Counter
from typing import List, Optional, Tuple

import numpy as np
import sherpa_onnx

logger = logging.getLogger(__name__)

# energy VAD 常量
_FRAME_DURATION_MS = 30
_ENERGY_MARGIN_DB = 10.0
_MIN_SILENCE_S = 0.3
_MIN_SPEECH_S = 1.0


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
        """检测音频语言（简单模式，取前 N 秒）。

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

    def detect_with_vad(
        self,
        audio_path: str,
        scan_duration: float = 600.0,
        num_segments: int = 3,
        segment_seconds: float = 15.0,
    ) -> Optional[str]:
        """VAD 预筛 + 多段采样投票检测音频语言。

        从音频中扫描 scan_duration 秒，用能量 VAD 找到有人声的区域，
        均匀挑选 num_segments 段进行语言检测，投票决定最终结果。

        Args:
            audio_path: 16kHz mono WAV 音频文件路径。
            scan_duration: 扫描音频的最大时长（秒）。
            num_segments: 采样段数（投票数）。
            segment_seconds: 每段送入 LID 的时长（秒）。

        Returns:
            检测到的 2 字母语言代码，检测失败时返回 None。
        """
        try:
            samples, sample_rate = self._read_wav(audio_path, scan_duration)
            if len(samples) == 0:
                logger.warning("音频为空，无法检测语言")
                return None

            samples_np = np.array(samples, dtype=np.float32)

            # 1. 用 energy VAD 找有声区域
            speech_regions = self._find_speech_regions(samples_np, sample_rate)
            if not speech_regions:
                logger.warning("未找到有声区域，回退到前 30s 检测")
                return self.detect(audio_path, max_duration=30.0)

            # 2. 均匀选取 num_segments 个区域
            selected = self._select_segments(
                speech_regions, num_segments, sample_rate, segment_seconds
            )

            logger.info(
                f"VAD 找到 {len(speech_regions)} 个有声区域，"
                f"选取 {len(selected)} 段进行语言检测"
            )

            # 3. 对每段做 LID，收集结果
            votes: List[str] = []
            for i, (start_sample, end_sample) in enumerate(selected):
                seg = samples[start_sample:end_sample]
                if len(seg) < sample_rate:  # 不足 1 秒，跳过
                    continue
                stream = self.slid.create_stream()
                stream.accept_waveform(sample_rate=sample_rate, waveform=seg)
                lang = self.slid.compute(stream)
                if lang:
                    start_s = start_sample / sample_rate
                    end_s = end_sample / sample_rate
                    logger.info(
                        f"  段 {i + 1}: {start_s:.1f}s-{end_s:.1f}s → {lang}"
                    )
                    votes.append(lang)

            if not votes:
                logger.warning("所有采样段均未检测到语言，回退到前 30s 检测")
                return self.detect(audio_path, max_duration=30.0)

            # 4. 投票
            counter = Counter(votes)
            winner, count = counter.most_common(1)[0]
            logger.info(
                f"语言检测投票结果: {winner} ({count}/{len(votes)}) "
                f"— 详细: {dict(counter)}"
            )
            return winner

        except Exception as e:
            logger.error(f"VAD 语言检测失败: {e}", exc_info=True)
            return None

    @staticmethod
    def _find_speech_regions(
        samples: np.ndarray, sample_rate: int
    ) -> List[Tuple[int, int]]:
        """用 RMS 能量检测有声区域，返回 (start_sample, end_sample) 列表。"""
        frame_size = int(sample_rate * _FRAME_DURATION_MS / 1000)
        num_frames = len(samples) // frame_size
        if num_frames == 0:
            return []

        # 计算每帧 RMS 能量 (dB)
        frames = samples[:num_frames * frame_size].reshape(num_frames, frame_size)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        energy_db = 20 * np.log10(np.maximum(rms, 1e-10))

        # 自动校准阈值：噪底 + margin
        noise_floor = np.percentile(energy_db, 10)
        threshold = noise_floor + _ENERGY_MARGIN_DB
        is_active = energy_db > threshold

        frame_duration_s = _FRAME_DURATION_MS / 1000.0
        min_silence_frames = max(1, int(_MIN_SILENCE_S / frame_duration_s))
        min_speech_frames = max(1, int(_MIN_SPEECH_S / frame_duration_s))

        # 找连续活跃区间
        regions: List[List[int]] = []
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

        # 过滤太短的段（< min_speech）
        merged = [r for r in merged if (r[1] - r[0]) >= min_speech_frames]

        # 转换为 sample 索引
        return [(r[0] * frame_size, r[1] * frame_size) for r in merged]

    @staticmethod
    def _select_segments(
        regions: List[Tuple[int, int]],
        num_segments: int,
        sample_rate: int,
        segment_seconds: float,
    ) -> List[Tuple[int, int]]:
        """从有声区域中均匀选取 num_segments 段，每段最多 segment_seconds 秒。"""
        max_samples = int(segment_seconds * sample_rate)

        # 如果区域数 <= 需要的段数，直接用全部（各自截断到 max_samples）
        if len(regions) <= num_segments:
            result = []
            for start, end in regions:
                seg_end = min(end, start + max_samples)
                result.append((start, seg_end))
            return result

        # 均匀间隔选取
        step = len(regions) / num_segments
        result = []
        for i in range(num_segments):
            idx = int(i * step + step / 2)
            idx = min(idx, len(regions) - 1)
            start, end = regions[idx]
            seg_end = min(end, start + max_samples)
            result.append((start, seg_end))
        return result

    @staticmethod
    def _read_wav(path: str, max_duration: float) -> tuple:
        """读取 WAV 文件，返回 (samples_float32_list, sample_rate)。

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
