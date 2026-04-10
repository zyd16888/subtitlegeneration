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
from typing import List, Optional, Sequence, Tuple

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

    def detect(
        self,
        audio_path: str,
        max_duration: float = 30.0,
        whitelist_enabled: bool = False,
        whitelist: Optional[Sequence[str]] = None,
    ) -> Optional[str]:
        """检测音频语言（简单模式，取前 N 秒）。

        Args:
            audio_path: 16kHz mono WAV 音频文件路径。
            max_duration: 最多使用前 N 秒音频做检测，减少开销。
            whitelist_enabled: 是否启用语言白名单过滤。
            whitelist: 允许返回的语言白名单。

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
            selected_lang = self._pick_language_by_whitelist(
                [(lang, 1)] if lang else [],
                whitelist_enabled=whitelist_enabled,
                whitelist=whitelist,
            )

            logger.info(
                f"语言检测结果: 原始={lang}, 最终={selected_lang} "
                f"(采样 {len(samples) / sample_rate:.1f}s / {sample_rate}Hz)"
            )
            return selected_lang

        except Exception as e:
            logger.error(f"语言检测失败: {e}", exc_info=True)
            return None

    def detect_with_vad(
        self,
        audio_path: str,
        scan_duration: float = 600.0,
        num_segments: int = 3,
        segment_seconds: float = 15.0,
        whitelist_enabled: bool = False,
        whitelist: Optional[Sequence[str]] = None,
    ) -> Optional[str]:
        """VAD 预筛 + 多段采样投票检测音频语言。

        从音频中扫描 scan_duration 秒，用能量 VAD 找到有人声的区域，
        将时间线均分为 num_segments 个窗口，每个窗口内拼接有声片段
        凑够 segment_seconds 秒再送 LID 检测，投票决定最终结果。

        Args:
            audio_path: 16kHz mono WAV 音频文件路径。
            scan_duration: 扫描音频的最大时长（秒）。
            num_segments: 采样段数（投票数）。
            segment_seconds: 每段送入 LID 的目标时长（秒）。
            whitelist_enabled: 是否启用语言白名单过滤。
            whitelist: 允许返回的语言白名单，按投票排序顺延选择。

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
                return self.detect(
                    audio_path,
                    max_duration=30.0,
                    whitelist_enabled=whitelist_enabled,
                    whitelist=whitelist,
                )

            # 2. 将时间线均分为 num_segments 个窗口，每个窗口内拼接有声片段
            lid_segments = self._build_lid_segments(
                samples, speech_regions, num_segments,
                sample_rate, segment_seconds,
            )

            if not lid_segments:
                logger.warning("无法构建足够长的采样段，回退到前 30s 检测")
                return self.detect(
                    audio_path,
                    max_duration=30.0,
                    whitelist_enabled=whitelist_enabled,
                    whitelist=whitelist,
                )

            logger.info(
                f"VAD 找到 {len(speech_regions)} 个有声区域，"
                f"构建 {len(lid_segments)} 段送入 LID 检测"
            )

            # 3. 对每段做 LID，收集结果
            votes: List[str] = []
            for i, (seg_samples, seg_desc) in enumerate(lid_segments):
                stream = self.slid.create_stream()
                stream.accept_waveform(sample_rate=sample_rate, waveform=seg_samples)
                lang = self.slid.compute(stream)
                if lang:
                    duration = len(seg_samples) / sample_rate
                    logger.info(
                        f"  段 {i + 1}: {seg_desc} "
                        f"({duration:.1f}s 有效语音) → {lang}"
                    )
                    votes.append(lang)

            if not votes:
                logger.warning("所有采样段均未检测到语言，回退到前 30s 检测")
                return self.detect(
                    audio_path,
                    max_duration=30.0,
                    whitelist_enabled=whitelist_enabled,
                    whitelist=whitelist,
                )

            # 4. 投票
            counter = Counter(votes)
            ranked_results = counter.most_common()
            winner, count = ranked_results[0]
            selected_lang = self._pick_language_by_whitelist(
                ranked_results,
                whitelist_enabled=whitelist_enabled,
                whitelist=whitelist,
            )

            if whitelist_enabled and whitelist:
                whitelist_list = [code.strip().lower() for code in whitelist if code and code.strip()]
                if selected_lang:
                    logger.info(
                        f"语言检测白名单过滤已启用: whitelist={whitelist_list}, "
                        f"最终选择={selected_lang}, 原始冠军={winner}"
                    )
                else:
                    logger.warning(
                        f"语言检测白名单过滤后无可用语言: whitelist={whitelist_list}, "
                        f"排序结果={ranked_results}"
                    )

            logger.info(
                f"语言检测投票结果: 原始冠军={winner} ({count}/{len(votes)}), "
                f"最终结果={selected_lang}, 详细: {dict(counter)}"
            )
            return selected_lang

        except Exception as e:
            logger.error(f"VAD 语言检测失败: {e}", exc_info=True)
            return None

    @staticmethod
    def _pick_language_by_whitelist(
        ranked_results: Sequence[Tuple[str, int]],
        whitelist_enabled: bool,
        whitelist: Optional[Sequence[str]],
    ) -> Optional[str]:
        """按投票排序选择语言；启用白名单时跳过不在白名单中的结果。"""
        if not ranked_results:
            return None

        if not whitelist_enabled:
            return ranked_results[0][0]

        normalized_whitelist = {
            code.strip().lower()
            for code in (whitelist or [])
            if isinstance(code, str) and code.strip()
        }
        if not normalized_whitelist:
            return ranked_results[0][0]

        for lang, _ in ranked_results:
            if lang and lang.lower() in normalized_whitelist:
                return lang
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
    def _build_lid_segments(
        samples: list,
        regions: List[Tuple[int, int]],
        num_segments: int,
        sample_rate: int,
        target_seconds: float,
    ) -> List[Tuple[list, str]]:
        """将时间线均分为 num_segments 个窗口，每个窗口内拼接有声片段。

        返回 [(拼接后的采样列表, 描述字符串), ...] 。
        每段至少 5 秒有效语音，不足则跳过该窗口。
        """
        if not regions:
            return []

        target_samples = int(target_seconds * sample_rate)
        min_samples = int(5.0 * sample_rate)  # 至少 5 秒才送 LID

        # 将 regions 按时间均分为 num_segments 组
        group_size = max(1, len(regions) // num_segments)
        result: List[Tuple[list, str]] = []

        for i in range(num_segments):
            start_idx = i * group_size
            # 最后一组包含剩余所有
            end_idx = len(regions) if i == num_segments - 1 else start_idx + group_size
            if start_idx >= len(regions):
                break

            group = regions[start_idx:end_idx]
            collected: list = []
            first_time = group[0][0] / sample_rate
            last_time = first_time

            for reg_start, reg_end in group:
                remaining = target_samples - len(collected)
                if remaining <= 0:
                    break
                take_end = min(reg_end, reg_start + remaining)
                collected.extend(samples[reg_start:take_end])
                last_time = take_end / sample_rate

            if len(collected) >= min_samples:
                desc = f"窗口 {first_time:.0f}s-{last_time:.0f}s"
                result.append((collected[:target_samples], desc))

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
