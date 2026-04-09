"""
字幕生成 Celery 任务

协调音频提取、ASR、翻译、字幕生成、Emby 回写的完整流程
"""
import asyncio
import logging
import os
import shutil
import threading
from typing import Dict, List, Optional
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
from services.task_log_capture import TaskLogCapture
from config.settings import settings
from models.base import SessionLocal

logger = logging.getLogger(__name__)


# ── 线程本地的持久 event loop ────────────────────────────────────────
# 多线程 worker 池下，反复 _run_async() 会不停建毁 loop，对 httpx /
# SQLAlchemy 等持久化资源极不友好（偶发卡死、连接池泄漏）。
# 这里给每个 worker 线程绑定一个长期存活的 loop，全程复用。
_thread_local = threading.local()


def _run_async(coro):
    """在当前线程的持久 event loop 上同步执行一个协程。"""
    loop = getattr(_thread_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _thread_local.loop = loop
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class SubtitleGenerationTask(Task):
    """字幕生成任务基类，支持任务状态跟踪"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}")
        logger.error(f"Exception info: {einfo}")


def _resolve_vad_model_path(config) -> str:
    """解析 VAD 模型的 .onnx 文件路径"""
    models_dir = getattr(config, 'model_storage_dir', None) or settings.model_storage_dir
    github_token = getattr(config, 'github_token', None) or settings.github_token
    manager = ModelManager(models_dir=models_dir, github_token=github_token)
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


def _get_asr_engine(config, source_language: str = None) -> ASREngine:
    """
    根据配置创建 ASR 引擎实例。

    优先使用 asr_model_id（从模型注册表查找），否则回退到 asr_model_path。
    
    Args:
        config: 系统配置对象
        source_language: 可选，指定语音识别语言，覆盖 config.source_language
    """
    logger.info(f"=== Creating ASR Engine ===")
    logger.info(f"ASR Engine type: {config.asr_engine}")
    logger.info(f"ASR Model ID: {config.asr_model_id}")
    logger.info(f"ASR Model Path: {config.asr_model_path}")
    
    # 优先级：source_language 参数 > config.source_language
    if source_language:
        source_lang = source_language
        logger.info(f"Using task-specified language: {source_lang}")
    else:
        source_lang = config.source_language
        logger.info(f"Using config default language: {source_lang}")
    
    if config.asr_engine == "cloud":
        if not config.cloud_asr_url or not config.cloud_asr_api_key:
            raise ValueError("云端 ASR 引擎需要配置 API URL 和 API Key")
        logger.info(f"Creating CloudASREngine with URL: {config.cloud_asr_url}")
        return CloudASREngine(config.cloud_asr_url, config.cloud_asr_api_key)

    if config.asr_engine == "sherpa-onnx":
        # 优先使用 model_id
        if config.asr_model_id:
            logger.info(f"Using model_id: {config.asr_model_id}")
            models_dir = getattr(config, 'model_storage_dir', None) or settings.model_storage_dir
            github_token = getattr(config, 'github_token', None) or settings.github_token
            manager = ModelManager(models_dir=models_dir, github_token=github_token)
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

            if meta.get("type") == "online":
                logger.info("Creating SherpaOnnxOnlineEngine")
                return SherpaOnnxOnlineEngine(str(model_path), model_type=model_type, file_map=file_map)

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
        return OpenAITranslator(config.openai_api_key, config.openai_model, config.openai_base_url)
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


def _apply_path_mapping(
    emby_path: str,
    path_mappings: list,
    path_mapping_index: Optional[int] = None,
    library_id: Optional[str] = None,
) -> Optional[str]:
    """
    将 Emby 服务器上的视频路径映射为本地可访问路径。

    支持跨平台路径转换：
    - Linux → Windows: /mnt/media/film.mkv → Z:/Media/film.mkv
    - Windows → Linux: Z:/Media/film.mkv → /mnt/media/film.mkv
    - 同平台: 直接前缀替换

    匹配优先级：
    1. 明确指定 path_mapping_index
    2. library_id 匹配映射规则的 library_ids
    3. emby_prefix 前缀匹配（最长前缀优先）
    """
    if not path_mappings:
        return None

    def _do_replace(emby_path: str, emby_prefix: str, local_prefix: str) -> Optional[str]:
        """
        执行路径替换，自动处理跨平台分隔符。

        - 统一用正斜杠做前缀匹配
        - 替换后根据 local_prefix 的风格决定输出分隔符
        """
        # 统一正斜杠做匹配
        norm_path = emby_path.replace("\\", "/")
        norm_emby_prefix = emby_prefix.replace("\\", "/").rstrip("/")
        norm_local_prefix = local_prefix.replace("\\", "/").rstrip("/")

        if not norm_path.startswith(norm_emby_prefix):
            return None

        # 替换前缀，得到统一正斜杠的结果
        suffix = norm_path[len(norm_emby_prefix):]  # 保留开头的 /
        result = norm_local_prefix + suffix

        # 判断 local_prefix 是否是 Windows 风格（盘符开头，如 Z:/ 或 Z:\）
        is_windows_local = (
            len(local_prefix) >= 2 and local_prefix[1] == ':'
        )
        if is_windows_local:
            # 转为 Windows 反斜杠
            result = result.replace("/", "\\")

        return result

    # 1. 指定索引
    if path_mapping_index is not None:
        if 0 <= path_mapping_index < len(path_mappings):
            m = path_mappings[path_mapping_index]
            emby_prefix = m.get("emby_prefix", "")
            local_prefix = m.get("local_prefix", "")
            result = _do_replace(emby_path, emby_prefix, local_prefix)
            if result:
                return result
            # 前缀不匹配也强制替换（用户明确指定），只取文件名拼接
            norm_local = local_prefix.replace("\\", "/").rstrip("/")
            basename = emby_path.replace("\\", "/").split("/")[-1]
            fallback = norm_local + "/" + basename
            is_windows_local = len(local_prefix) >= 2 and local_prefix[1] == ':'
            return fallback.replace("/", "\\") if is_windows_local else fallback
        return None

    # 2. library_id 匹配
    if library_id:
        for m in path_mappings:
            lib_ids = m.get("library_ids", [])
            if library_id in lib_ids:
                result = _do_replace(emby_path, m.get("emby_prefix", ""), m.get("local_prefix", ""))
                if result:
                    return result

    # 3. 前缀匹配（最长前缀优先）
    best_match = None
    best_len = 0
    for m in path_mappings:
        norm_prefix = m.get("emby_prefix", "").replace("\\", "/").rstrip("/")
        norm_path = emby_path.replace("\\", "/")
        if norm_path.startswith(norm_prefix) and len(norm_prefix) > best_len:
            best_match = m
            best_len = len(norm_prefix)

    if best_match:
        result = _do_replace(emby_path, best_match["emby_prefix"], best_match["local_prefix"])
        if result:
            return result

    return None


async def _translate_segments(
    segments: List[Segment],
    translation_service: TranslationService,
    source_lang: str = "ja",
    target_lang: str = "zh",
    concurrency: Optional[int] = None,
    context_size: int = 0,
) -> List[SubtitleSegment]:
    """
    并发翻译 ASR 识别的文本片段。

    使用 translate_batch 并发执行，asyncio.gather 保证返回结果与输入索引一一对应，
    SRT 时间轴顺序不会乱。失败的段落 success=False，translated_text 等于 original_text。

    Args:
        context_size: 上下文窗口大小，前后各 N 条（0=禁用，仅 LLM 翻译器生效）。
    """
    if not segments:
        return []

    texts = [s.text for s in segments]
    results = await translation_service.translate_batch(
        texts,
        source_lang=source_lang,
        target_lang=target_lang,
        concurrency=concurrency,
        all_texts=texts if context_size > 0 else None,
        context_size=context_size,
    )

    subtitle_segments: List[SubtitleSegment] = []
    for segment, (translated_text, success) in zip(segments, results):
        subtitle_segments.append(
            SubtitleSegment(
                start=segment.start,
                end=segment.end,
                original_text=segment.text,
                translated_text=translated_text,
                is_translated=success,
            )
        )
    return subtitle_segments


def _build_source_segments(segments: List[Segment]) -> List[SubtitleSegment]:
    """构造"源语言字幕"的 SubtitleSegment 列表。

    直接用 ASR 识别文本，is_translated=False 让 SubtitleGenerator 回落到 original_text。
    """
    return [
        SubtitleSegment(
            start=s.start,
            end=s.end,
            original_text=s.text,
            translated_text=s.text,
            is_translated=False,
        )
        for s in segments
    ]


def _resolve_target_languages(
    config,
    task_override: Optional[List[str]] = None,
) -> List[str]:
    """解析本次任务要生成的目标语言列表。

    优先级：任务级 override > config.target_languages > [config.target_language]
    返回结果去重保持顺序。
    """
    candidates: List[str]
    if task_override:
        candidates = list(task_override)
    elif getattr(config, "target_languages", None):
        candidates = list(config.target_languages)
    else:
        candidates = [config.target_language]

    seen = set()
    result: List[str] = []
    for code in candidates:
        if not code:
            continue
        code = code.strip()
        if code and code not in seen:
            seen.add(code)
            result.append(code)
    return result


async def _translate_to_multi_targets(
    segments: List[Segment],
    translation_service: TranslationService,
    source_lang: str,
    translation_source_lang: str,
    target_langs: List[str],
    concurrency: Optional[int] = None,
    context_size: int = 0,
) -> Dict[str, List[SubtitleSegment]]:
    """按语言维度串行翻译到多个目标语言，段落维度由 translate_batch 并发。

    对于 source_lang == target_lang 且非 auto 模式的语言，跳过翻译直接返回源文本
    （与单语言路径行为一致）。返回 dict: {lang_code: subtitle_segments}。
    """
    results: Dict[str, List[SubtitleSegment]] = {}
    for target_lang in target_langs:
        if source_lang == target_lang and translation_source_lang != "auto":
            logger.info(
                f"目标语言 {target_lang} 与源语言相同，跳过翻译直接使用 ASR 原文"
            )
            results[target_lang] = _build_source_segments(segments)
            continue

        logger.info(f"开始翻译到 {target_lang}")
        results[target_lang] = await _translate_segments(
            segments,
            translation_service,
            source_lang=translation_source_lang,
            target_lang=target_lang,
            concurrency=concurrency,
            context_size=context_size,
        )
    return results


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
    library_id: str = None,
    path_mapping_index: int = None,
    source_language: str = None,
    target_languages: Optional[List[str]] = None,
    keep_source_subtitle: Optional[bool] = None,
):
    """
    字幕生成主任务

    1. 提取音频 (20%)
    2. 语音识别 (60%)
    3. 翻译文本 (90%)
    4. 生成字幕文件 (95%)
    5. 回写 Emby (100%)

    Args:
        target_languages: 任务级多目标语言覆盖；None 时使用 config.target_languages
        keep_source_subtitle: 任务级源语言字幕开关；None 时使用 config.keep_source_subtitle
    """
    db = SessionLocal()
    task_manager = TaskManager(db)
    config_manager = ConfigManager(db)
    audio_path = None
    subtitle_path = None  # finally 安全网用，跟踪是否生成了字幕文件

    # 挂载任务日志捕获器，将处理过程中的所有 logging 输出收集起来供前端展示
    log_capture = TaskLogCapture()
    root_logger = logging.getLogger()
    root_logger.addHandler(log_capture)
    if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
        # 确保 INFO 级别能流到 handler；不修改原有 level 行为以外的设置
        log_capture.setLevel(logging.INFO)

    def _persist_logs_extra(extra: dict) -> dict:
        """合并日志快照到 extra_info 更新载荷"""
        merged = dict(extra) if extra else {}
        merged["logs"] = log_capture.snapshot()
        return merged

    def _mark_step_start(stage: str) -> None:
        # 保留占位以兼容下面调用，无副作用
        pass

    def _format_step_log(stage: str, summary: str) -> str:
        return summary

    try:
        config = _run_async(config_manager.get_config())

        # 应用自定义配置覆盖
        if asr_engine:
            config.asr_engine = asr_engine
        if translation_service:
            config.translation_service = translation_service
        if openai_model:
            config.openai_model = openai_model

        # 语言参数：任务指定 > 全局配置
        source_lang = source_language if source_language else config.source_language
        # 多目标语言：任务级 override > config.target_languages > [config.target_language]
        resolved_target_langs = _resolve_target_languages(config, target_languages)
        primary_target_lang = resolved_target_langs[0] if resolved_target_langs else config.target_language
        # 源语言字幕开关：任务级 > 全局
        keep_source = keep_source_subtitle if keep_source_subtitle is not None else bool(
            getattr(config, "keep_source_subtitle", False)
        )

        # 根据配置决定是否使用自动检测模式
        # 如果配置为 auto 模式，翻译时传入 "auto" 让翻译服务自动检测
        translation_source_lang = source_lang
        if hasattr(config, 'source_language_detection') and config.source_language_detection == "auto":
            translation_source_lang = "auto"
            logger.info(f"[{task_id}] 源语言检测模式: auto（翻译服务将自动检测语言）")
        else:
            logger.info(f"[{task_id}] 源语言检测模式: fixed（使用配置的语言: {source_lang}）")

        logger.info(f"[{task_id}] 使用语音识别语言: {source_lang} (任务指定: {source_language}, 全局: {config.source_language})")
        logger.info(
            f"[{task_id}] 翻译源语言: {translation_source_lang}, 目标语言: {resolved_target_langs}"
        )
        if keep_source:
            logger.info(f"[{task_id}] 启用源语言字幕保留: {source_lang}")

        _run_async(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 0))
        logger.info(f"开始处理任务 {task_id}: {video_path}")
        logger.info(
            f"[{task_id}] 配置: ASR={config.asr_engine}, model_id={config.asr_model_id}, "
            f"翻译={config.translation_service}, 语言={source_lang}->{resolved_target_langs}"
        )

        # 为每个任务创建独立的工作目录，保留所有中间产物
        task_work_dir = os.path.join(config.temp_dir, "tasks", task_id)
        os.makedirs(task_work_dir, exist_ok=True)
        logger.info(f"[{task_id}] 任务工作目录: {task_work_dir}")

        # 用于收集每个步骤的详细日志
        step_logs = {}
        skipped_steps = []

        # 1. 提取音频
        _mark_step_start("audio")
        logger.info(f"[{task_id}] 步骤 1/5: 提取音频")
        logger.info(f"[{task_id}] 视频路径: {video_path}")
        audio_extractor = AudioExtractor(task_work_dir)
        try:
            audio_path = _run_async(audio_extractor.extract_audio(video_path))
            logger.info(f"[{task_id}] 音频提取成功: {audio_path}")
        except Exception as e:
            logger.error(f"[{task_id}] 音频提取失败: {e}", exc_info=True)
            raise
        audio_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
        step_logs["audio"] = _format_step_log(
            "audio",
            f"输入: {video_path}\n输出: {audio_path}\n音频大小: {audio_size / 1024 / 1024:.1f} MB",
        )
        _run_async(task_manager.update_task_result(task_id, extra_info=_persist_logs_extra({"step_logs": step_logs})))
        _run_async(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 20))

        # 2. 语音识别
        _mark_step_start("asr")
        logger.info(f"[{task_id}] 步骤 2/5: 语音识别")
        logger.info(f"[{task_id}] 创建 ASR 引擎...")
        try:
            asr_engine_instance = _get_asr_engine(config, source_language=source_lang)
            logger.info(f"[{task_id}] ASR 引擎创建成功: {type(asr_engine_instance).__name__}")
        except Exception as e:
            logger.error(f"[{task_id}] ASR 引擎创建失败: {e}", exc_info=True)
            raise
        
        logger.info(f"[{task_id}] 开始转录音频: {audio_path}")
        # Whisper 模型支持 transcribe 时指定语言，其他模型忽略
        segments = _run_async(
            asr_engine_instance.transcribe(audio_path, language=source_lang)
        )
        _run_async(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 60))
        logger.info(f"[{task_id}] 语音识别完成，识别到 {len(segments)} 个片段")
        step_logs["asr"] = _format_step_log(
            "asr",
            (
                f"引擎: {type(asr_engine_instance).__name__}\n"
                f"识别片段数: {len(segments)}\n"
                f"语言: {source_lang}"
            ),
        )
        _run_async(task_manager.update_task_result(task_id, segment_count=len(segments), extra_info=_persist_logs_extra({"step_logs": step_logs})))

        # 保存 ASR 原始识别结果
        import json
        asr_result_path = os.path.join(task_work_dir, "asr_result.json")
        with open(asr_result_path, "w", encoding="utf-8") as f:
            json.dump([{"start": s.start, "end": s.end, "text": s.text} for s in segments], f, ensure_ascii=False, indent=2)
        logger.info(f"[{task_id}] ASR 结果已保存: {asr_result_path}")

        if not segments:
            raise RuntimeError("语音识别未能识别出任何内容，请检查音频是否包含语音或更换 ASR 模型")

        # 3. 翻译文本（支持多目标语言）
        _mark_step_start("translation")
        logger.info(f"[{task_id}] 步骤 3/5: 翻译文本")

        # 判断是否有语言需要真正调用翻译服务
        # （auto 模式强制走翻译服务；非 auto 模式下，所有目标语言都等于源语言才能完全跳过）
        all_targets_equal_source = (
            translation_source_lang != "auto"
            and all(tl == source_lang for tl in resolved_target_langs)
        )

        per_lang_segments: Dict[str, List[SubtitleSegment]] = {}

        if all_targets_equal_source:
            logger.info(
                f"[{task_id}] 所有目标语言均等于源语言 ({source_lang})，跳过翻译"
            )
            source_subs = _build_source_segments(segments)
            for tl in resolved_target_langs:
                per_lang_segments[tl] = source_subs
            translation_skipped = True
            translation_service_instance = None
        else:
            if translation_source_lang == "auto":
                logger.info(
                    f"[{task_id}] 使用自动语言检测模式翻译到 {resolved_target_langs}"
                )
            translation_service_instance = _get_translation_service(config)
            translation_concurrency = getattr(config, "translation_concurrency", None)
            translation_context_size = getattr(config, "translation_context_size", 0) or 0
            logger.info(
                f"[{task_id}] 翻译并发数: "
                f"{translation_concurrency if translation_concurrency else f'默认 ({translation_service_instance.default_concurrency})'}"
            )
            if translation_context_size > 0:
                logger.info(f"[{task_id}] 翻译上下文窗口: 前后各 {translation_context_size} 条")

            per_lang_segments = _run_async(
                _translate_to_multi_targets(
                    segments,
                    translation_service_instance,
                    source_lang=source_lang,
                    translation_source_lang=translation_source_lang,
                    target_langs=resolved_target_langs,
                    concurrency=translation_concurrency,
                    context_size=translation_context_size,
                )
            )
            translation_skipped = False

        # 如果开启保留源语言字幕，且源语言不在目标列表中，额外追加一份
        emit_langs: List[str] = list(resolved_target_langs)
        if keep_source and source_lang not in per_lang_segments:
            per_lang_segments[source_lang] = _build_source_segments(segments)
            emit_langs.append(source_lang)
            logger.info(f"[{task_id}] 追加源语言字幕: {source_lang}")

        _run_async(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 90))

        if translation_skipped:
            step_logs["translation"] = _format_step_log(
                "translation",
                f"所有目标语言均等于源语言 ({source_lang})，已跳过翻译",
            )
            skipped_steps.append("translation")
        else:
            detection_mode = (
                "自动检测" if translation_source_lang == "auto" else f"固定 ({translation_source_lang})"
            )
            lines = [
                f"翻译服务: {config.translation_service}",
                f"源语言模式: {detection_mode}",
                f"目标语言: {', '.join(resolved_target_langs)}",
            ]
            for tl in resolved_target_langs:
                segs = per_lang_segments.get(tl, [])
                translated_count = sum(1 for s in segs if s.is_translated)
                lines.append(f"  - {tl}: 成功翻译 {translated_count}/{len(segs)} 段")
            step_logs["translation"] = _format_step_log("translation", "\n".join(lines))
        _run_async(task_manager.update_task_result(
            task_id,
            extra_info=_persist_logs_extra({
                "step_logs": step_logs,
                "skipped_steps": skipped_steps,
                "target_languages": list(resolved_target_langs),
                "keep_source_subtitle": keep_source,
            }),
        ))

        # 4. 生成字幕文件（每种语言一份）
        _mark_step_start("subtitle")
        logger.info(f"[{task_id}] 步骤 4/5: 生成字幕文件")
        subtitle_generator = SubtitleGenerator()

        # subtitle_paths: 按语言顺序记录 (lang, path)
        subtitle_paths: Dict[str, str] = {}
        subtitle_info_lines: List[str] = []
        for lang_code in emit_langs:
            segs = per_lang_segments.get(lang_code, [])
            if not segs:
                logger.warning(f"[{task_id}] 语言 {lang_code} 无字幕段，跳过生成")
                continue
            path = subtitle_generator.generate_srt(
                segs, video_path, lang_code, output_dir=task_work_dir
            )
            subtitle_paths[lang_code] = path
            size_kb = os.path.getsize(path) / 1024 if os.path.exists(path) else 0
            logger.info(f"[{task_id}] 字幕文件生成完成: {path}")
            subtitle_info_lines.append(
                f"  - {lang_code}: {path} ({size_kb:.1f} KB, {len(segs)} 段)"
            )

        if not subtitle_paths:
            raise RuntimeError("未能生成任何字幕文件")

        # 主字幕路径：primary_target_lang 对应那一份；不存在时用 emit_langs 第 0 个
        subtitle_path = subtitle_paths.get(primary_target_lang) or subtitle_paths[emit_langs[0]]

        _run_async(task_manager.update_task_status(task_id, TaskStatus.PROCESSING, 95))
        step_logs["subtitle"] = _format_step_log(
            "subtitle",
            "生成字幕文件:\n" + "\n".join(subtitle_info_lines),
        )
        _run_async(task_manager.update_task_result(
            task_id,
            subtitle_path=subtitle_path,
            extra_info=_persist_logs_extra({
                "step_logs": step_logs,
                "subtitles": [
                    {"lang": lc, "path": p}
                    for lc, p in subtitle_paths.items()
                ],
            }),
        ))

        # 5. 复制字幕到视频目录 + 刷新 Emby
        _mark_step_start("emby")
        logger.info(f"[{task_id}] 步骤 5/6: 复制字幕到视频目录")
        emby_log_lines = []
        emby_copy_skipped = False
        if config.emby_url and config.emby_api_key:

            async def get_video_real_path():
                async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                    return await emby.get_media_file_path(media_item_id)

            # 获取视频在 Emby 服务器上的真实路径
            try:
                emby_video_path = _run_async(get_video_real_path())
                logger.info(f"[{task_id}] Emby 视频真实路径: {emby_video_path}")
                emby_log_lines.append(f"Emby 视频路径: {emby_video_path}")
            except Exception as e:
                logger.warning(f"[{task_id}] 获取视频真实路径失败: {e}，跳过字幕文件复制")
                emby_video_path = None
                emby_log_lines.append(f"获取视频路径失败: {e}")
                emby_copy_skipped = True

            if emby_video_path and config.path_mappings:
                local_video_path = _apply_path_mapping(
                    emby_video_path,
                    config.path_mappings,
                    path_mapping_index=path_mapping_index,
                    library_id=library_id,
                )
                if local_video_path:
                    emby_log_lines.append(f"本地映射路径: {local_video_path}")
                    if not os.path.exists(local_video_path):
                        logger.error(
                            f"[{task_id}] 本地视频文件不存在: {local_video_path}，"
                            f"请检查路径映射配置是否正确 (Emby 路径: {emby_video_path})"
                        )
                        emby_log_lines.append(f"本地视频文件不存在，路径映射可能配置错误")
                        raise RuntimeError(
                            f"本地视频文件不存在: {local_video_path}，"
                            f"请检查路径映射配置 (Emby 路径: {emby_video_path})"
                        )
                    # 每种语言复制一份字幕到视频目录
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
                        except Exception as e:
                            logger.error(
                                f"[{task_id}] 复制字幕文件失败 [{lang_code}]: {e}",
                                exc_info=True,
                            )
                            raise RuntimeError(
                                f"复制字幕文件到视频目录失败 [{lang_code}]: {e}"
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

            # 6. 刷新 Emby 元数据
            logger.info(f"[{task_id}] 步骤 6/6: 刷新 Emby 元数据")

            async def refresh_emby():
                async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
                    return await emby.refresh_metadata(media_item_id)

            success = _run_async(refresh_emby())
            if success:
                logger.info(f"[{task_id}] Emby 元数据刷新成功")
                emby_log_lines.append("Emby 元数据刷新: 成功")
            else:
                logger.warning(f"[{task_id}] Emby 元数据刷新失败，但字幕文件已生成")
                emby_log_lines.append("Emby 元数据刷新: 失败")
        else:
            logger.warning(f"[{task_id}] 未配置 Emby 连接，跳过字幕回写")
            emby_log_lines.append("未配置 Emby 连接，跳过回写")

        step_logs["emby"] = _format_step_log("emby", "\n".join(emby_log_lines))
        # 判断 Emby 回写是否实质性跳过（未配置 Emby / 获取路径失败 / 路径映射未匹配或未配置）
        if not (config.emby_url and config.emby_api_key) or emby_copy_skipped:
            skipped_steps.append("emby")
        _run_async(task_manager.update_task_result(task_id, extra_info=_persist_logs_extra({"step_logs": step_logs, "skipped_steps": skipped_steps})))

        _run_async(task_manager.update_task_status(task_id, TaskStatus.COMPLETED, 100))
        # 任务完成后再写一次，捕获完成日志
        _run_async(task_manager.update_task_result(task_id, extra_info=_persist_logs_extra({})))
        logger.info(f"[{task_id}] 任务完成")

        # 按配置决定是否清理临时文件
        if config.cleanup_temp_files_on_success:
            try:
                shutil.rmtree(task_work_dir)
                logger.info(f"[{task_id}] 临时文件已清理: {task_work_dir}")
            except Exception as e:
                logger.warning(f"[{task_id}] 清理临时文件失败: {e}")

        return {"task_id": task_id, "status": "completed", "subtitle_path": subtitle_path}

    except Exception as e:
        error_message = str(e)
        logger.error(f"[{task_id}] 任务失败: {error_message}", exc_info=True)
        _run_async(
            task_manager.update_task_status(task_id, TaskStatus.FAILED, error_message=error_message)
        )
        # 失败时也持久化捕获到的日志，便于排查
        try:
            _run_async(task_manager.update_task_result(task_id, extra_info=_persist_logs_extra({})))
        except Exception:
            pass
        raise

    finally:
        # ── 安全网：保证任务一定离开 PROCESSING 状态 ─────────────────
        # 重新读取一次 DB（用独立 session 避免被前面的异常污染），
        # 如果发现状态仍是 PROCESSING/PENDING，根据 subtitle_path 是否
        # 已生成强制改成 COMPLETED 或 FAILED。这一层兜底独立于上面所有
        # 逻辑，无论 asyncio loop / SQLite 锁 / 第三方库出什么状况，
        # 任务都不会再卡在 95%。
        try:
            from models.task import Task as _TaskModel
            safety_db = SessionLocal()
            try:
                row = safety_db.query(_TaskModel).filter(_TaskModel.id == task_id).first()
                if row is not None and row.status in (TaskStatus.PROCESSING, TaskStatus.PENDING):
                    from config.time_utils import utc_now
                    if subtitle_path and os.path.exists(subtitle_path):
                        row.status = TaskStatus.COMPLETED
                        row.progress = 100
                        row.completed_at = utc_now()
                        if row.started_at:
                            from config.time_utils import ensure_utc
                            started = ensure_utc(row.started_at)
                            completed = ensure_utc(row.completed_at)
                            row.processing_time = (completed - started).total_seconds()
                        logger.warning(
                            f"[{task_id}] 安全网：任务退出时状态仍为 {row.status.value}，"
                            f"检测到字幕文件已生成，强制标记为 COMPLETED"
                        )
                    else:
                        row.status = TaskStatus.FAILED
                        row.completed_at = utc_now()
                        if not row.error_message:
                            row.error_message = "任务异常退出，未生成字幕文件"
                        logger.warning(
                            f"[{task_id}] 安全网：任务退出时状态仍为 {row.status.value}，"
                            f"未检测到字幕文件，强制标记为 FAILED"
                        )
                    safety_db.commit()
            finally:
                safety_db.close()
        except Exception as e:
            logger.error(f"[{task_id}] 安全网状态修正失败: {e}", exc_info=True)

        # 卸载日志捕获器
        try:
            root_logger.removeHandler(log_capture)
        except Exception:
            pass
        # 中间产物保留在 task_work_dir 中，不清理，方便调试
        try:
            db.close()
        except Exception:
            pass
