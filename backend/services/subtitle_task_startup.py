"""
字幕任务启动流程。
"""
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from models.task import TaskStatus
from services.subtitle_pipeline import create_task_work_dir, prepare_task_runtime

logger = logging.getLogger(__name__)


@dataclass
class SubtitleTaskStartup:
    """字幕任务启动后的运行时信息。"""

    config: object
    source_lang: str
    resolved_target_langs: List[str]
    primary_target_lang: str
    keep_source: bool
    translation_source_lang: str
    reporter: object
    task_work_dir: str


def start_subtitle_task(
    task_id: str,
    video_path: str,
    config_manager,
    task_manager,
    result_persister,
    session_factory: Callable,
    run_async: Callable,
    asr_engine: Optional[str] = None,
    asr_model_id: Optional[str] = None,
    translation_service: Optional[str] = None,
    openai_model: Optional[str] = None,
    source_language: Optional[str] = None,
    target_languages: Optional[List[str]] = None,
    keep_source_subtitle: Optional[bool] = None,
) -> SubtitleTaskStartup:
    """读取配置、准备运行时并标记任务进入处理中。"""
    config = run_async(config_manager.get_config())
    runtime = prepare_task_runtime(
        config,
        task_id=task_id,
        session_factory=session_factory,
        asr_engine=asr_engine,
        asr_model_id=asr_model_id,
        translation_service=translation_service,
        openai_model=openai_model,
        source_language=source_language,
        target_languages=target_languages,
        keep_source_subtitle=keep_source_subtitle,
    )

    result_persister.persist_stage_weights(runtime.reporter)
    run_async(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 0))
    logger.info(f"开始处理任务 {task_id}: {video_path}")
    logger.info(
        f"[{task_id}] 配置: ASR={runtime.config.asr_engine}, "
        f"model_id={runtime.config.asr_model_id}, "
        f"翻译={runtime.config.translation_service}, "
        f"语言={runtime.source_lang}->{runtime.resolved_target_langs}"
    )

    return SubtitleTaskStartup(
        config=runtime.config,
        source_lang=runtime.source_lang,
        resolved_target_langs=runtime.resolved_target_langs,
        primary_target_lang=runtime.primary_target_lang,
        keep_source=runtime.keep_source,
        translation_source_lang=runtime.translation_source_lang,
        reporter=runtime.reporter,
        task_work_dir=create_task_work_dir(task_id, runtime.config.temp_dir),
    )
