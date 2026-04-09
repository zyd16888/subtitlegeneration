"""
音频降噪服务

使用 noisereduce 库的频谱门控算法对音频进行降噪处理，
降低背景噪声以提升 VAD 检测准确率和 ASR 识别准确率。
"""

import asyncio
import logging
import os
import wave
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _read_wave(audio_path: str) -> Tuple[np.ndarray, int]:
    """读取 WAV 文件，返回 (float32 numpy array, sample_rate)"""
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
        samples = samples[::num_channels]

    return samples, sample_rate


def _write_wave(audio_path: str, samples: np.ndarray, sample_rate: int) -> None:
    """将 float32 numpy array 写入 WAV 文件（pcm_s16le）"""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    with wave.open(audio_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _denoise_sync(
    input_path: str,
    output_path: str,
    prop_decrease: float = 0.8,
) -> str:
    """同步执行降噪处理"""
    import noisereduce as nr

    samples, sample_rate = _read_wave(input_path)
    duration = len(samples) / sample_rate
    logger.info(
        f"开始降噪: {input_path} "
        f"(采样率={sample_rate}, 时长={duration:.1f}s, prop_decrease={prop_decrease})"
    )

    denoised = nr.reduce_noise(
        y=samples,
        sr=sample_rate,
        prop_decrease=prop_decrease,
        stationary=True,
    )

    _write_wave(output_path, denoised, sample_rate)
    output_size = os.path.getsize(output_path) / 1024 / 1024
    logger.info(f"降噪完成: {output_path} ({output_size:.1f} MB)")
    return output_path


async def denoise_audio(
    input_path: str,
    output_path: Optional[str] = None,
    prop_decrease: float = 0.8,
) -> str:
    """
    对音频文件进行降噪处理。

    Args:
        input_path: 输入 WAV 文件路径（16kHz 单声道）
        output_path: 输出路径，None 时在同目录生成 *_denoised.wav
        prop_decrease: 噪声降低比例 (0-1)，越大降噪越强，默认 0.8

    Returns:
        降噪后的音频文件路径
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"音频文件不存在: {input_path}")

    if output_path is None:
        stem, ext = os.path.splitext(input_path)
        output_path = f"{stem}_denoised{ext}"

    return await asyncio.get_running_loop().run_in_executor(
        None, _denoise_sync, input_path, output_path, prop_decrease
    )
