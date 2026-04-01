"""
字幕生成 Celery 任务

协调音频提取、ASR、翻译、字幕生成、Emby 回写的完整流程
"""
import logging
import os
from typing import List
from celery import Task

from .celery_app import celery_app
from models.task import TaskStatus
from services.emby_connector import EmbyConnector
from services.audio_extractor import AudioExtractor
from services.asr_engine import (
    ASREngine,
    SherpaOnnxOnlineEngine,
    SherpaOnnxOfflineEngine,
    SherpaOnnxVadOfflineEngine,
    CloudASREngine,
    Segment,
)
from services.translation_service import (
    TranslationService,
    OpenAITranslator,
    DeepSeekTranslator,
    LocalLLMTranslator,
    GoogleTranslator,
    MicrosoftTranslator,
    BaiduTranslator,
    DeepLTranslator,
)
from services.subtitle_generator import SubtitleGenerator, SubtitleSegment
from services.task_manager import TaskManager
from services.config_manager import ConfigManager
from services.model_manager import ModelManager
from config.settings import settings
from models.base import SessionLocal

logger = logging.getLogger(__name__)


class SubtitleGenerationTask(Task):
    """字幕生成任务基类，支持任务状态跟踪"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}")
        logger.error(f"Exception info: {einfo}")


def _resolve_vad_model_path(config) -> str:
    """解析 VAD 模型的 .onnx 文件路径"""
    manager = ModelManager(models_dir=settings.model_storage_dir)
    vad_path = manager.get_model_path(config.vad_model_id)
    if not vad_path:
        raise ValueError(f"VAD 模型 {config.vad_model_id} 未安装")
    vad_meta = manager.get_model_meta(config.vad_model_id)
    vad_file = vad_meta.get("files", {}).get("model", "") if vad_meta else ""
    if not vad_file:
        # 回退：自动检测
        vad_files = manager._auto_detect_vad_files(vad_path)
        vad_file = vad_files.get("model", "")
    if not vad_file:
        raise ValueError(f"VAD 模型 {config.vad_model_id} 找不到 .onnx 文件")
    full_path = str(vad_path / vad_file)
    if not os.path.exists(full_path):
        raise ValueError(f"VAD 模型文件不存在: {full_path}")
    return full_path


def _get_asr_engine(config) -> ASREngine:
    """
    根据配置创建 ASR 引擎实例。

    优先使用 asr_model_id（从模型注册表查找），否则回退到 asr_model_path。
    """
    logger.info(f"=== Creating ASR Engine ===")
    logger.info(f"ASR Engine type: {config.asr_engine}")
    logger.info(f"ASR Model ID: {config.asr_model_id}")
    logger.info(f"ASR Model Path: {config.asr_model_path}")
    
    if config.asr_engine == "cloud":
        if not config.cloud_asr_url or not config.cloud_asr_api_key:
            raise ValueError("云端 ASR 引擎需要配置 API URL 和 API Key")
        logger.info(f"Creating CloudASREngine with URL: {config.cloud_asr_url}")
        return CloudASREngine(config.cloud_asr_url, config.cloud_asr_api_key)

    if config.asr_engine == "sherpa-onnx":
        # 优先使用 model_id
        if config.asr_model_id:
            logger.info(f"Using model_id: {config.asr_model_id}")
            manager = ModelManager(models_dir=settings.model_storage_dir)
            meta = manager.get_model_meta(config.asr_model_id)
            if not meta:
                raise ValueError(f"模型 {config.asr_model_id} 元数据不存在，请重新下载")
            
            logger.info(f"Model metadata: {meta}")
            model_path = manager.get_model_path(config.asr_model_id)
            if not model_path:
                raise ValueError(f"模型 {config.asr_model_id} 未安装")
            
            logger.info(f"Model path: {model_path}")
            model_type = meta.get("model_type", "transducer")
            file_map = meta.get("files", {})
            logger.info(f"Model type: {model_type}")
            logger.info(f"File map: {file_map}")

            source_lang = config.source_language

            if meta.get("type") == "online":
                logger.info("Creating SherpaOnnxOnlineEngine")
                return SherpaOnnxOnlineEngine(str(model_path), file_map=file_map)

            # 离线模型：检查是否启用 VAD
            if config.enable_vad and config.vad_model_id:
                vad_model_path = _resolve_vad_model_path(config)
                logger.info(f"Creating SherpaOnnxVadOfflineEngine (VAD: {config.vad_model_id})")
                return SherpaOnnxVadOfflineEngine(
                    model_path=str(model_path),
                    model_type=model_type,
                    file_map=file_map,
                    language=source_lang,
                    vad_model_path=vad_model_path,
                    vad_threshold=config.vad_threshold,
                    vad_min_silence_duration=config.vad_min_silence_duration,
                    vad_min_speech_duration=config.vad_min_speech_duration,
                    vad_max_speech_duration=config.vad_max_speech_duration,
                )
            else:
                logger.info("Creating SherpaOnnxOfflineEngine")
                return SherpaOnnxOfflineEngine(str(model_path), model_type=model_type, file_map=file_map, language=source_lang)

        # 回退到手动路径
        if not config.asr_model_path:
            raise ValueError("sherpa-onnx 引擎需要配置模型路径或选择一个已下载的模型")
        logger.info(f"Using manual model path: {config.asr_model_path}")
        return SherpaOnnxOnlineEngine(config.asr_model_path)

    raise ValueError(f"不支持的 ASR 引擎类型: {config.asr_engine}")


def _get_translation_service(config) -> TranslationService:
    """根据配置创建翻译服务实例"""
    if config.translation_service == "openai":
        if not config.openai_api_key:
            raise ValueError("OpenAI 翻译服务需要配置 API Key")
        return OpenAITranslator(config.openai_api_key, config.openai_model)
    elif config.translation_service == "deepseek":
        if not config.deepseek_api_key:
            raise ValueError("DeepSeek 翻译服务需要配置 API Key")
        return DeepSeekTranslator(config.deepseek_api_key)
    elif config.translation_service == "local":
        if not config.local_llm_url:
            raise ValueError("本地 LLM 翻译服务需要配置 API URL")
        return LocalLLMTranslator(config.local_llm_url)
    elif config.translation_service == "google":
        mode = getattr(config, "google_translate_mode", "free")
        api_key = getattr(config, "google_api_key", None)
        return GoogleTranslator(mode=mode, api_key=api_key)
    elif config.translation_service == "microsoft":
        mode = getattr(config, "microsoft_translate_mode", "free")
        api_key = getattr(config, "microsoft_api_key", None)
        region = getattr(config, "microsoft_region", "global")
        return MicrosoftTranslator(mode=mode, api_key=api_key, region=region)
    elif config.translation_service == "baidu":
        if not getattr(config, "baidu_app_id", None) or not getattr(config, "baidu_secret_key", None):
            raise ValueError("百度翻译服务需要配置 APP ID 和 Secret Key")
        return BaiduTranslator(app_id=config.baidu_app_id, secret_key=config.baidu_secret_key)
    elif config.translation_service == "deepl":
        mode = getattr(config, "deepl_mode", "deeplx")
        api_key = getattr(config, "deepl_api_key", None)
        deeplx_url = getattr(config, "deeplx_url", None)
        return DeepLTranslator(mode=mode, api_key=api_key, deeplx_url=deeplx_url)
    else:
        raise ValueError(f"不支持的翻译服务类型: {config.translation_service}")


async def _translate_segments(
    segments: List[Segment],
    translation_service: TranslationService,
    source_lang: str = "ja",
    target_lang: str = "zh",
) -> List[SubtitleSegment]:
    """翻译 ASR 识别的文本片段"""
    subtitle_segments = []

    for segment in segments:
        try:
            translated_text = await translation_service.translate(
                segment.text,
                source_lang=source_lang,
                target_lang=target_lang,
            )
            subtitle_segment = SubtitleSegment(
                start=segment.start,
                end=segment.end,
                original_text=segment.text,
                translated_text=translated_text,
                is_translated=True,
            )
        except Exception as e:
            logger.warning(f"翻译失败，保留原文: {e}")
            subtitle_segment = SubtitleSegment(
                start=segment.start,
                end=segment.end,
                original_text=segment.text,
                translated_text=segment.text,
                is_translated=False,
            )
        subtitle_segments.append(subtitle_segment)

    return subtitle_segments


@celery_app.task(
    bind=True,
    base=SubtitleGenerationTask,
    name="backend.tasks.subtitle_tasks.generate_subtitle_task",
    max_retries=3,
    default_retry_delay=60,
)
def generate_subtitle_task(
    self,
    task_id: str,
    media_item_id: str,
    video_path: str,
    asr_engine: str = None,
    translation_service: str = None,
    openai_model: str = None,
):
    """
    字幕生成主任务

    1. 提取音频 (20%)
    2. 语音识别 (60%)
    3. 翻译文本 (90%)
    4. 生成字幕文件 (95%)
    5. 回写 Emby (100%)
    """
    import asyncio

    db = SessionLocal()
    task_manager = TaskManager(db)
    config_manager = ConfigManager(db)
    audio_path = None

    try:
        loop = asyncio.get_event_loop()
        config = loop.run_until_complete(config_manager.get_config())

        # 应用自定义配置覆盖
        if asr_engine:
            config.asr_engine = asr_engine
        if translation_service:
            config.translation_service = translation_service
        if openai_model:
            config.openai_model = openai_model

        source_lang = config.source_language
        target_lang = config.target_language

        loop.run_until_complete(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 0))
        logger.info(f"开始处理任务 {task_id}: {video_path}")
        logger.info(
            f"[{task_id}] 配置: ASR={config.asr_engine}, model_id={config.asr_model_id}, "
            f"翻译={config.translation_service}, 语言={source_lang}->{target_lang}"
        )

        # 为每个任务创建独立的工作目录，保留所有中间产物
        task_work_dir = os.path.join(config.temp_dir, "tasks", task_id)
        os.makedirs(task_work_dir, exist_ok=True)
        logger.info(f"[{task_id}] 任务工作目录: {task_work_dir}")

        # 1. 提取音频
        logger.info(f"[{task_id}] 步骤 1/5: 提取音频")
        logger.info(f"[{task_id}] 视频路径: {video_path}")
        audio_extractor = AudioExtractor(task_work_dir)
        try:
            audio_path = loop.run_until_complete(audio_extractor.extract_audio(video_path))
            logger.info(f"[{task_id}] 音频提取成功: {audio_path}")
        except Exception as e:
            logger.error(f"[{task_id}] 音频提取失败: {e}", exc_info=True)
            raise
        loop.run_until_complete(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 20))

        # 2. 语音识别
        logger.info(f"[{task_id}] 步骤 2/5: 语音识别")
        logger.info(f"[{task_id}] 创建 ASR 引擎...")
        try:
            asr_engine_instance = _get_asr_engine(config)
            logger.info(f"[{task_id}] ASR 引擎创建成功: {type(asr_engine_instance).__name__}")
        except Exception as e:
            logger.error(f"[{task_id}] ASR 引擎创建失败: {e}", exc_info=True)
            raise
        
        logger.info(f"[{task_id}] 开始转录音频: {audio_path}")
        segments = loop.run_until_complete(
            asr_engine_instance.transcribe(audio_path, language=source_lang)
        )
        loop.run_until_complete(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 60))
        logger.info(f"[{task_id}] 语音识别完成，识别到 {len(segments)} 个片段")

        # 保存 ASR 原始识别结果
        import json
        asr_result_path = os.path.join(task_work_dir, "asr_result.json")
        with open(asr_result_path, "w", encoding="utf-8") as f:
            json.dump([{"start": s.start, "end": s.end, "text": s.text} for s in segments], f, ensure_ascii=False, indent=2)
        logger.info(f"[{task_id}] ASR 结果已保存: {asr_result_path}")

        if not segments:
            raise RuntimeError("语音识别未能识别出任何内容，请检查音频是否包含语音或更换 ASR 模型")

        # 3. 翻译文本
        logger.info(f"[{task_id}] 步骤 3/5: 翻译文本")
        if source_lang == target_lang:
            logger.info(f"[{task_id}] 源语言与目标语言相同 ({source_lang})，跳过翻译")
            subtitle_segments = [
                SubtitleSegment(start=s.start, end=s.end, original_text=s.text, translated_text=s.text, is_translated=False)
                for s in segments
            ]
        else:
            translation_service_instance = _get_translation_service(config)
            subtitle_segments = loop.run_until_complete(
                _translate_segments(segments, translation_service_instance, source_lang, target_lang)
            )
        loop.run_until_complete(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 90))

        # 4. 生成字幕文件
        logger.info(f"[{task_id}] 步骤 4/5: 生成字幕文件")
        subtitle_generator = SubtitleGenerator()
        subtitle_path = subtitle_generator.generate_srt(subtitle_segments, video_path, target_lang, output_dir=task_work_dir)
        loop.run_until_complete(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 95))
        logger.info(f"[{task_id}] 字幕文件生成完成: {subtitle_path}")

        # 5. 回写 Emby
        logger.info(f"[{task_id}] 步骤 5/5: 回写 Emby")
        if config.emby_url and config.emby_api_key:

            async def refresh_emby():
                async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                    return await emby.refresh_metadata(media_item_id)

            success = loop.run_until_complete(refresh_emby())
            if success:
                logger.info(f"[{task_id}] Emby 元数据刷新成功")
            else:
                logger.warning(f"[{task_id}] Emby 元数据刷新失败，但字幕文件已生成")
        else:
            logger.warning(f"[{task_id}] 未配置 Emby 连接，跳过元数据刷新")

        loop.run_until_complete(task_manager.update_task_status(task_id, TaskStatus.COMPLETED, 100))
        logger.info(f"[{task_id}] 任务完成")

        return {"task_id": task_id, "status": "completed", "subtitle_path": subtitle_path}

    except Exception as e:
        error_message = str(e)
        logger.error(f"[{task_id}] 任务失败: {error_message}", exc_info=True)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            task_manager.update_task_status(task_id, TaskStatus.FAILED, error_message=error_message)
        )
        raise

    finally:
        # 中间产物保留在 task_work_dir 中，不清理，方便调试
        db.close()
