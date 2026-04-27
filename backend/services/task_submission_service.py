"""
任务提交应用服务

负责把 HTTP/Telegram 等入口传入的任务请求转换为持久化任务，并投递到 Celery。
"""
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from models.task import Task
from services.config_manager import ConfigManager
from services.emby_connector import EmbyConnector
from services.task_manager import TaskManager
from tasks.subtitle_tasks import generate_subtitle_task


@dataclass
class TaskConfigInput:
    """单个任务的入口配置。"""

    media_item_id: str
    asr_engine: Optional[str] = None
    translation_service: Optional[str] = None
    openai_model: Optional[str] = None
    path_mapping_index: Optional[int] = None
    source_language: Optional[str] = None
    target_languages: Optional[List[str]] = None
    keep_source_subtitle: Optional[bool] = None


@dataclass
class CreateTasksInput:
    """批量任务创建输入。"""

    media_item_ids: Optional[List[str]] = None
    tasks: Optional[List[TaskConfigInput]] = None
    library_id: Optional[str] = None


class MediaItemNotFoundError(Exception):
    """媒体项不存在或缺少必要信息。"""


class MediaItemFetchError(Exception):
    """媒体项信息获取失败。"""


class TaskSubmissionService:
    """任务创建、重试和 Celery 投递的应用服务。"""

    def __init__(self, db: Session, emby: Optional[EmbyConnector] = None):
        self.db = db
        self.emby = emby
        self.task_manager = TaskManager(db)
        self.config_manager = ConfigManager(db)

    async def create_tasks(self, request: CreateTasksInput) -> List[Task]:
        """创建字幕任务并投递 Celery。"""
        if not request.media_item_ids and not request.tasks:
            raise ValueError("必须提供 media_item_ids 或 tasks")
        if self.emby is None:
            raise ValueError("Emby 连接未配置")

        config = await self.config_manager.get_config()
        created_tasks: List[Task] = []

        for media_item_id in request.media_item_ids or []:
            task = await self._create_with_global_config(media_item_id, request.library_id, config)
            created_tasks.append(task)

        for task_config in request.tasks or []:
            task = await self._create_with_task_config(task_config, request.library_id, config)
            created_tasks.append(task)

        return created_tasks

    async def retry_task(self, task_id: str) -> Optional[Task]:
        """重试任务，并按当前全局配置重新投递。"""
        new_task = await self.task_manager.retry_task(task_id)
        if new_task is None:
            return None

        # 重试使用当前全局处理配置，便于调整模型/翻译参数后重新跑同一媒体。
        config = await self.config_manager.get_config()
        retry_target_languages = self._resolve_config_target_languages(config)
        retry_keep_source = bool(config.keep_source_subtitle)
        retry_primary_target = (
            retry_target_languages[0] if retry_target_languages else config.target_language
        )

        new_task.asr_engine = config.asr_engine
        new_task.asr_model_id = getattr(config, "asr_model_id", None)
        new_task.translation_service = config.translation_service
        new_task.source_language = config.source_language
        new_task.target_language = retry_primary_target
        self.db.commit()
        self.db.refresh(new_task)

        # 保留任务来源信息，避免 Telegram 来源任务重试后无法通知用户。
        original_task = await self.task_manager.get_task(task_id)
        original_extra = (original_task.extra_info or {}) if original_task else {}
        retry_extra = {
            "target_languages": retry_target_languages,
            "keep_source_subtitle": retry_keep_source,
        }
        telegram_user_id = (
            original_extra.get("telegram_user_id")
            or (original_task.telegram_user_id if original_task else None)
        )
        if telegram_user_id:
            retry_extra["telegram_user_id"] = telegram_user_id

        await self._update_task_extra(new_task.id, retry_extra)

        self._enqueue_task(
            task_id=new_task.id,
            kwargs=dict(
                task_id=new_task.id,
                media_item_id=new_task.media_item_id,
                video_path=new_task.video_path,
                asr_engine=new_task.asr_engine,
                asr_model_id=new_task.asr_model_id,
                translation_service=new_task.translation_service,
                source_language=new_task.source_language,
                target_languages=retry_target_languages,
                keep_source_subtitle=retry_keep_source,
            ),
        )

        return new_task

    async def _create_with_global_config(
        self,
        media_item_id: str,
        library_id: Optional[str],
        config,
    ) -> Task:
        media_item, audio_url = await self._get_media_audio(media_item_id)
        task = await self.task_manager.create_task(
            media_item_id=media_item_id,
            media_item_title=media_item.name,
            video_path=audio_url,
            asr_engine=config.asr_engine,
            asr_model_id=config.asr_model_id,
            translation_service=config.translation_service,
            source_language=config.source_language,
            target_language=config.target_language,
        )

        await self._update_task_extra(
            task.id,
            {
                "target_languages": self._resolve_config_target_languages(config),
                "keep_source_subtitle": bool(config.keep_source_subtitle),
            },
        )

        # task_id 与 Celery task ID 对齐，便于 revoke 取消。
        self._enqueue_task(
            task_id=task.id,
            kwargs=dict(
                task_id=task.id,
                media_item_id=media_item_id,
                video_path=audio_url,
                asr_model_id=config.asr_model_id,
                library_id=library_id,
                source_language=None,
                target_languages=None,
                keep_source_subtitle=None,
            ),
        )
        return task

    async def _create_with_task_config(
        self,
        task_config: TaskConfigInput,
        library_id: Optional[str],
        config,
    ) -> Task:
        media_item, audio_url = await self._get_media_audio(task_config.media_item_id)

        task_asr_engine = task_config.asr_engine or config.asr_engine
        task_translation_service = task_config.translation_service or config.translation_service
        task_source_language = task_config.source_language or config.source_language
        effective_target_languages = (
            task_config.target_languages
            if task_config.target_languages
            else self._resolve_config_target_languages(config)
        )
        effective_keep_source = (
            task_config.keep_source_subtitle
            if task_config.keep_source_subtitle is not None
            else bool(config.keep_source_subtitle)
        )
        task_primary_target = (
            effective_target_languages[0] if effective_target_languages else config.target_language
        )

        task = await self.task_manager.create_task(
            media_item_id=task_config.media_item_id,
            media_item_title=media_item.name,
            video_path=audio_url,
            asr_engine=task_asr_engine,
            asr_model_id=config.asr_model_id,
            translation_service=task_translation_service,
            source_language=task_source_language,
            target_language=task_primary_target,
        )

        await self._update_task_extra(
            task.id,
            {
                "target_languages": list(effective_target_languages),
                "keep_source_subtitle": effective_keep_source,
            },
        )

        self._enqueue_task(
            task_id=task.id,
            kwargs=dict(
                task_id=task.id,
                media_item_id=task_config.media_item_id,
                video_path=audio_url,
                asr_engine=task_config.asr_engine,
                asr_model_id=config.asr_model_id,
                translation_service=task_config.translation_service,
                openai_model=task_config.openai_model,
                library_id=library_id,
                path_mapping_index=task_config.path_mapping_index,
                source_language=task_config.source_language,
                target_languages=task_config.target_languages,
                keep_source_subtitle=task_config.keep_source_subtitle,
            ),
        )
        return task

    async def _get_media_audio(self, media_item_id: str):
        try:
            media_item = await self.emby.get_media_item(media_item_id)
            audio_url = await self.emby.get_audio_stream_url(media_item_id)
            return media_item, audio_url
        except ValueError as exc:
            raise MediaItemNotFoundError(str(exc)) from exc
        except Exception as exc:
            raise MediaItemFetchError(f"获取媒体项 {media_item_id} 失败: {exc}") from exc

    async def _update_task_extra(self, task_id: str, extra_info: dict) -> None:
        try:
            await self.task_manager.update_task_result(task_id, extra_info=extra_info)
        except Exception:
            # 与原行为保持一致：extra_info 写入失败不阻塞任务投递。
            pass

    @staticmethod
    def _resolve_config_target_languages(config) -> List[str]:
        if config.target_languages:
            return list(config.target_languages)
        return [config.target_language]

    @staticmethod
    def _enqueue_task(task_id: str, kwargs: dict) -> None:
        generate_subtitle_task.apply_async(kwargs=kwargs, task_id=task_id)
