"""
字幕文件输出与 Emby 回写阶段。
"""
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from services.emby_connector import EmbyConnector
from services.path_mapping import apply_path_mapping
from services.progress_reporter import TaskProgressReporter
from services.subtitle_generator import SubtitleGenerator, SubtitleSegment

logger = logging.getLogger(__name__)


@dataclass
class SubtitleGenerationResult:
    """字幕文件生成阶段输出。"""

    subtitle_path: str
    subtitle_paths: Dict[str, str]
    step_logs: dict


@dataclass
class EmbyWritebackResult:
    """Emby 回写阶段输出。"""

    step_logs: dict
    skipped_steps: List[str]


def generate_subtitle_files(
    task_id: str,
    video_path: str,
    task_work_dir: str,
    per_lang_segments: Dict[str, List[SubtitleSegment]],
    emit_langs: List[str],
    primary_target_lang: str,
    reporter: TaskProgressReporter,
    step_logs: dict,
    format_step_log: Callable[[str, str], str],
) -> SubtitleGenerationResult:
    """按语言生成 SRT 文件，并选出主字幕路径。"""
    reporter.report("subtitle", 0.0)
    logger.info(f"[{task_id}] 步骤 4/5: 生成字幕文件")
    subtitle_generator = SubtitleGenerator()

    subtitle_paths: Dict[str, str] = {}
    subtitle_info_lines: List[str] = []
    for lang_code in emit_langs:
        segments = per_lang_segments.get(lang_code, [])
        if not segments:
            logger.warning(f"[{task_id}] 语言 {lang_code} 无字幕段，跳过生成")
            continue

        path = subtitle_generator.generate_srt(
            segments,
            video_path,
            lang_code,
            output_dir=task_work_dir,
        )
        subtitle_paths[lang_code] = path
        size_kb = os.path.getsize(path) / 1024 if os.path.exists(path) else 0
        logger.info(f"[{task_id}] 字幕文件生成完成: {path}")
        subtitle_info_lines.append(
            f"  - {lang_code}: {path} ({size_kb:.1f} KB, {len(segments)} 段)"
        )

    if not subtitle_paths:
        raise RuntimeError("未能生成任何字幕文件")

    subtitle_path = (
        subtitle_paths.get(primary_target_lang)
        or subtitle_paths[emit_langs[0]]
    )

    reporter.report("subtitle", 1.0)
    step_logs["subtitle"] = format_step_log(
        "subtitle",
        "生成字幕文件:\n" + "\n".join(subtitle_info_lines),
    )

    return SubtitleGenerationResult(
        subtitle_path=subtitle_path,
        subtitle_paths=subtitle_paths,
        step_logs=step_logs,
    )


def write_subtitles_to_emby(
    task_id: str,
    config,
    media_item_id: str,
    subtitle_paths: Dict[str, str],
    path_mapping_index: Optional[int],
    library_id: Optional[str],
    reporter: TaskProgressReporter,
    step_logs: dict,
    skipped_steps: List[str],
    run_async: Callable,
    format_step_log: Callable[[str, str], str],
) -> EmbyWritebackResult:
    """复制字幕到视频目录，并刷新 Emby 元数据。"""
    reporter.report("emby", 0.0)
    logger.info(f"[{task_id}] 步骤 5/6: 复制字幕到视频目录")
    emby_log_lines = []
    emby_copy_skipped = False
    skipped_steps = list(skipped_steps)

    if config.emby_url and config.emby_api_key:

        async def get_video_real_path():
            async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                return await emby.get_media_file_path(media_item_id)

        try:
            emby_video_path = run_async(get_video_real_path())
            logger.info(f"[{task_id}] Emby 视频真实路径: {emby_video_path}")
            emby_log_lines.append(f"Emby 视频路径: {emby_video_path}")
        except Exception as exc:
            logger.warning(f"[{task_id}] 获取视频真实路径失败: {exc}，跳过字幕文件复制")
            emby_video_path = None
            emby_log_lines.append(f"获取视频路径失败: {exc}")
            emby_copy_skipped = True

        if emby_video_path and config.path_mappings:
            local_video_path = apply_path_mapping(
                emby_video_path,
                config.path_mappings,
                path_mapping_index=path_mapping_index,
                library_id=library_id,
            )
            if local_video_path:
                _copy_subtitles_to_video_dir(
                    task_id=task_id,
                    local_video_path=local_video_path,
                    emby_video_path=emby_video_path,
                    subtitle_paths=subtitle_paths,
                    emby_log_lines=emby_log_lines,
                )
            else:
                logger.warning(
                    f"[{task_id}] 路径映射未匹配，Emby 路径: {emby_video_path}，"
                    f"已配置 {len(config.path_mappings)} 条映射规则，跳过复制"
                )
                emby_log_lines.append(
                    f"路径映射未匹配 (已配置 {len(config.path_mappings)} 条规则)，跳过复制"
                )
                emby_copy_skipped = True
        elif emby_video_path and not config.path_mappings:
            logger.warning(f"[{task_id}] 未配置路径映射规则，跳过字幕文件复制到视频目录")
            emby_log_lines.append("未配置路径映射规则，跳过复制")
            emby_copy_skipped = True

        logger.info(f"[{task_id}] 步骤 6/6: 刷新 Emby 元数据")

        async def refresh_emby():
            async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                return await emby.refresh_metadata(media_item_id)

        success = run_async(refresh_emby())
        if success:
            logger.info(f"[{task_id}] Emby 元数据刷新成功")
            emby_log_lines.append("Emby 元数据刷新: 成功")
        else:
            logger.warning(f"[{task_id}] Emby 元数据刷新失败，但字幕文件已生成")
            emby_log_lines.append("Emby 元数据刷新: 失败")
    else:
        logger.warning(f"[{task_id}] 未配置 Emby 连接，跳过字幕回写")
        emby_log_lines.append("未配置 Emby 连接，跳过回写")

    step_logs["emby"] = format_step_log("emby", "\n".join(emby_log_lines))
    if not (config.emby_url and config.emby_api_key) or emby_copy_skipped:
        skipped_steps.append("emby")

    reporter.report("emby", 1.0)
    return EmbyWritebackResult(step_logs=step_logs, skipped_steps=skipped_steps)


def _copy_subtitles_to_video_dir(
    task_id: str,
    local_video_path: str,
    emby_video_path: str,
    subtitle_paths: Dict[str, str],
    emby_log_lines: List[str],
) -> None:
    emby_log_lines.append(f"本地映射路径: {local_video_path}")
    if not os.path.exists(local_video_path):
        logger.error(
            f"[{task_id}] 本地视频文件不存在: {local_video_path}，"
            f"请检查路径映射配置是否正确 (Emby 路径: {emby_video_path})"
        )
        emby_log_lines.append("本地视频文件不存在，路径映射可能配置错误")
        raise RuntimeError(
            f"本地视频文件不存在: {local_video_path}，"
            f"请检查路径映射配置 (Emby 路径: {emby_video_path})"
        )

    video_basename = os.path.splitext(os.path.basename(local_video_path))[0]
    video_dir = os.path.dirname(local_video_path)

    for lang_code, src_path in subtitle_paths.items():
        target_srt = os.path.join(video_dir, f"{video_basename}.{lang_code}.srt")
        try:
            shutil.copy2(src_path, target_srt)
            logger.info(
                f"[{task_id}] 字幕文件已复制 [{lang_code}]: "
                f"{src_path} → {target_srt}"
            )
            emby_log_lines.append(f"字幕已复制 [{lang_code}]: {target_srt}")
        except Exception as exc:
            logger.error(
                f"[{task_id}] 复制字幕文件失败 [{lang_code}]: {exc}",
                exc_info=True,
            )
            raise RuntimeError(
                f"复制字幕文件到视频目录失败 [{lang_code}]: {exc}"
            )
