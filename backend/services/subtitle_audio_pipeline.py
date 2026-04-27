"""
字幕音频准备阶段。
"""
import logging
import os
from dataclasses import dataclass
from typing import Callable

from services.audio_denoiser import denoise_audio
from services.audio_extractor import AudioExtractor
from services.progress_reporter import TaskProgressReporter

logger = logging.getLogger(__name__)


@dataclass
class AudioPreparationResult:
    """音频准备阶段输出。"""

    audio_path: str
    step_logs: dict


def prepare_audio(
    task_id: str,
    video_path: str,
    task_work_dir: str,
    config,
    reporter: TaskProgressReporter,
    step_logs: dict,
    run_async: Callable,
    persist_step_logs: Callable[[dict], None],
    format_step_log: Callable[[str, str], str],
) -> AudioPreparationResult:
    """提取音频，并按配置执行可选降噪。"""
    reporter.report("audio", 0.0)
    logger.info(f"[{task_id}] 步骤 1/5: 提取音频")
    logger.info(f"[{task_id}] 视频路径: {video_path}")
    audio_extractor = AudioExtractor(task_work_dir)
    try:
        audio_path = run_async(audio_extractor.extract_audio(video_path))
        logger.info(f"[{task_id}] 音频提取成功: {audio_path}")
    except Exception as exc:
        logger.error(f"[{task_id}] 音频提取失败: {exc}", exc_info=True)
        raise

    audio_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
    step_logs["audio"] = format_step_log(
        "audio",
        (
            f"输入: {video_path}\n"
            f"输出: {audio_path}\n"
            f"音频大小: {audio_size / 1024 / 1024:.1f} MB"
        ),
    )
    persist_step_logs(step_logs)
    reporter.report("audio", 1.0)

    if getattr(config, "enable_denoise", False):
        audio_path = _denoise_audio(
            task_id=task_id,
            audio_path=audio_path,
            reporter=reporter,
            step_logs=step_logs,
            run_async=run_async,
            persist_step_logs=persist_step_logs,
            format_step_log=format_step_log,
        )

    return AudioPreparationResult(audio_path=audio_path, step_logs=step_logs)


def _denoise_audio(
    task_id: str,
    audio_path: str,
    reporter: TaskProgressReporter,
    step_logs: dict,
    run_async: Callable,
    persist_step_logs: Callable[[dict], None],
    format_step_log: Callable[[str, str], str],
) -> str:
    reporter.report("denoise", 0.0)
    logger.info(f"[{task_id}] 步骤 1.5: 音频降噪")
    try:
        denoised_path = run_async(denoise_audio(audio_path))
        denoised_size = (
            os.path.getsize(denoised_path)
            if os.path.exists(denoised_path)
            else 0
        )
        logger.info(f"[{task_id}] 降噪完成: {denoised_path}")
        step_logs["denoise"] = format_step_log(
            "denoise",
            (
                f"输入: {audio_path}\n"
                f"输出: {denoised_path}\n"
                f"降噪后大小: {denoised_size / 1024 / 1024:.1f} MB"
            ),
        )
        audio_path = denoised_path
    except Exception as exc:
        logger.warning(
            f"[{task_id}] 降噪失败，使用原始音频继续: {exc}",
            exc_info=True,
        )
        step_logs["denoise"] = format_step_log(
            "denoise",
            f"降噪失败: {exc}，使用原始音频",
        )
    reporter.report("denoise", 1.0)
    persist_step_logs(step_logs)
    return audio_path
