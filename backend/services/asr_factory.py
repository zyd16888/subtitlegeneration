"""
ASR 引擎创建与语言检测辅助。
"""
import logging
import os
from typing import Dict, Optional

from config.settings import settings
from services.asr_engine import (
    ASREngine,
    AliyunASRProvider,
    CloudASREngine,
    DeepgramASRProvider,
    ElevenLabsASRProvider,
    FireworksASRProvider,
    GroqASRProvider,
    OpenAIWhisperASRProvider,
    SherpaOnnxOfflineEngine,
    SherpaOnnxOnlineEngine,
    SherpaOnnxVadOfflineEngine,
    TencentASRProvider,
    VolcengineASRProvider,
)
from services.language_detector import LanguageDetector
from services.model_manager import ModelManager

logger = logging.getLogger(__name__)


def resolve_vad_model_path(config) -> str:
    """解析 VAD 模型的 .onnx 文件路径。"""
    models_dir = getattr(config, "model_storage_dir", None) or settings.model_storage_dir
    github_token = getattr(config, "github_token", None) or settings.github_token
    manager = ModelManager(models_dir=models_dir, github_token=github_token)
    vad_path = manager.get_model_path(config.vad_model_id)
    if not vad_path:
        raise ValueError(f"VAD 模型 {config.vad_model_id} 未安装")
    vad_meta = manager.get_model_meta(config.vad_model_id)
    vad_file = vad_meta.get("files", {}).get("model", "") if vad_meta else ""
    if not vad_file:
        vad_files = manager._auto_detect_vad_files(vad_path)
        vad_file = vad_files.get("model", "")
    if not vad_file:
        raise ValueError(f"VAD 模型 {config.vad_model_id} 找不到 .onnx 文件")
    full_path = str(vad_path / vad_file)
    if not os.path.exists(full_path):
        raise ValueError(f"VAD 模型文件不存在: {full_path}")
    return full_path


def detect_language(config, audio_path: str) -> Optional[str]:
    """使用 Whisper LID 检测音频语言。"""
    if not config.enable_language_detection or not config.lid_model_id:
        return None

    models_dir = getattr(config, "model_storage_dir", None) or settings.model_storage_dir
    github_token = getattr(config, "github_token", None) or settings.github_token
    manager = ModelManager(models_dir=models_dir, github_token=github_token)

    meta = manager.get_model_meta(config.lid_model_id)
    if not meta:
        logger.warning(f"LID 模型 {config.lid_model_id} 元数据不存在，跳过语言检测")
        return None

    model_path = manager.get_model_path(config.lid_model_id)
    if not model_path:
        logger.warning(f"LID 模型 {config.lid_model_id} 未安装，跳过语言检测")
        return None

    file_map = meta.get("files", {})
    encoder_file = file_map.get("encoder", "")
    decoder_file = file_map.get("decoder", "")
    if not encoder_file or not decoder_file:
        logger.warning(
            f"LID 模型 {config.lid_model_id} 缺少 encoder/decoder 文件映射，跳过语言检测"
        )
        return None

    detector = LanguageDetector(
        model_path=str(model_path),
        encoder_file=encoder_file,
        decoder_file=decoder_file,
    )
    return detector.detect_with_vad(
        audio_path,
        scan_duration=float(getattr(config, "lid_sample_duration", 600) or 600),
        num_segments=int(getattr(config, "lid_num_segments", 3) or 3),
        whitelist_enabled=bool(getattr(config, "lid_filter_whitelist_enabled", False)),
        whitelist=getattr(config, "lid_filter_whitelist", []) or [],
    )


def resolve_model_by_language(
    detected_lang: Optional[str],
    language_model_map: Dict[str, str],
    default_model_id: Optional[str],
) -> tuple:
    """根据检测到的语言和映射选择 ASR 模型。"""
    if not detected_lang:
        return default_model_id, None
    mapped = language_model_map.get(detected_lang)
    if mapped:
        return mapped, detected_lang
    return default_model_id, detected_lang


def get_asr_engine(config, source_language: str = None) -> ASREngine:
    """根据配置创建 ASR 引擎实例。"""
    logger.info("=== Creating ASR Engine ===")
    logger.info(f"ASR Engine type: {config.asr_engine}")
    logger.info(f"ASR Model ID: {config.asr_model_id}")
    logger.info(f"ASR Model Path: {config.asr_model_path}")

    if source_language:
        source_lang = source_language
        logger.info(f"Using task-specified language: {source_lang}")
    else:
        source_lang = config.source_language
        logger.info(f"Using config default language: {source_lang}")

    if config.asr_engine == "cloud":
        return _get_cloud_asr_engine(config)

    if config.asr_engine == "sherpa-onnx":
        return _get_sherpa_asr_engine(config, source_lang)

    raise ValueError(f"不支持的 ASR 引擎类型: {config.asr_engine}")


def _get_cloud_asr_engine(config) -> ASREngine:
    provider = getattr(config, "cloud_asr_provider", "groq")
    logger.info(f"Cloud ASR provider: {provider}")
    if provider == "groq":
        if not config.groq_asr_api_key:
            raise ValueError("Groq ASR 需要配置 API Key")
        return CloudASREngine(GroqASRProvider(
            api_key=config.groq_asr_api_key,
            model=config.groq_asr_model,
            base_url=config.groq_asr_base_url,
            public_audio_base_url=config.groq_asr_public_audio_base_url,
            prompt=config.groq_asr_prompt,
        ))
    if provider == "openai":
        if not config.openai_asr_api_key:
            raise ValueError("OpenAI ASR 需要配置 API Key")
        return CloudASREngine(OpenAIWhisperASRProvider(
            api_key=config.openai_asr_api_key,
            model=config.openai_asr_model,
            base_url=config.openai_asr_base_url,
            prompt=config.openai_asr_prompt,
        ))
    if provider == "fireworks":
        if not config.fireworks_asr_api_key:
            raise ValueError("Fireworks ASR 需要配置 API Key")
        return CloudASREngine(FireworksASRProvider(
            api_key=config.fireworks_asr_api_key,
            model=config.fireworks_asr_model,
            base_url=config.fireworks_asr_base_url,
            public_audio_base_url=config.fireworks_asr_public_audio_base_url,
            prompt=config.fireworks_asr_prompt,
        ))
    if provider == "elevenlabs":
        if not config.elevenlabs_asr_api_key:
            raise ValueError("ElevenLabs ASR 需要配置 API Key")
        return CloudASREngine(ElevenLabsASRProvider(
            api_key=config.elevenlabs_asr_api_key,
            model=config.elevenlabs_asr_model,
            base_url=config.elevenlabs_asr_base_url,
            public_audio_base_url=config.elevenlabs_asr_public_audio_base_url,
        ))
    if provider == "deepgram":
        if not config.deepgram_asr_api_key:
            raise ValueError("Deepgram ASR 需要配置 API Key")
        return CloudASREngine(DeepgramASRProvider(
            api_key=config.deepgram_asr_api_key,
            model=config.deepgram_asr_model,
            base_url=config.deepgram_asr_base_url,
            public_audio_base_url=config.deepgram_asr_public_audio_base_url,
        ))
    if provider == "volcengine":
        if not config.volcengine_asr_access_token:
            raise ValueError("火山引擎 ASR 需要配置 Access Token")
        if not config.volcengine_asr_app_id:
            raise ValueError("火山引擎 ASR 需要配置 App ID")
        return CloudASREngine(VolcengineASRProvider(
            api_key=config.volcengine_asr_access_token,
            app_id=config.volcengine_asr_app_id,
            model=config.volcengine_asr_model,
            base_url=config.volcengine_asr_base_url,
            public_audio_base_url=config.volcengine_asr_public_audio_base_url,
        ))
    if provider == "tencent":
        if not config.tencent_asr_secret_id:
            raise ValueError("腾讯云 ASR 需要配置 SecretId")
        if not config.tencent_asr_secret_key:
            raise ValueError("腾讯云 ASR 需要配置 SecretKey")
        return CloudASREngine(TencentASRProvider(
            api_key=config.tencent_asr_secret_key,
            secret_id=config.tencent_asr_secret_id,
            model=config.tencent_asr_engine_model_type,
            base_url=config.tencent_asr_base_url,
            public_audio_base_url=config.tencent_asr_public_audio_base_url,
            region=config.tencent_asr_region,
        ))
    if provider == "aliyun":
        if not config.aliyun_asr_api_key:
            raise ValueError("阿里云 ASR 需要配置 API Key")
        return CloudASREngine(AliyunASRProvider(
            api_key=config.aliyun_asr_api_key,
            model=config.aliyun_asr_model,
            base_url=config.aliyun_asr_base_url,
            public_audio_base_url=config.aliyun_asr_public_audio_base_url,
        ))
    raise ValueError(f"不支持的云端 ASR 厂商: {provider}")


def _get_sherpa_asr_engine(config, source_lang: str) -> ASREngine:
    if config.asr_model_id:
        models_dir = getattr(config, "model_storage_dir", None) or settings.model_storage_dir
        github_token = getattr(config, "github_token", None) or settings.github_token
        manager = ModelManager(models_dir=models_dir, github_token=github_token)
        meta = manager.get_model_meta(config.asr_model_id)
        if not meta:
            raise ValueError(f"模型 {config.asr_model_id} 元数据不存在，请重新下载")

        model_path = manager.get_model_path(config.asr_model_id)
        if not model_path:
            raise ValueError(f"模型 {config.asr_model_id} 未安装")

        model_type = meta.get("model_type", "transducer")
        file_map = meta.get("files", {})
        if meta.get("type") == "online":
            return SherpaOnnxOnlineEngine(str(model_path), model_type=model_type, file_map=file_map)

        if config.enable_vad:
            vad_mode = getattr(config, "vad_mode", "energy")
            vad_kwargs = dict(
                model_path=str(model_path),
                model_type=model_type,
                file_map=file_map,
                language=source_lang,
                vad_mode=vad_mode,
                vad_min_silence_duration=config.vad_min_silence_duration,
                vad_min_speech_duration=config.vad_min_speech_duration,
                vad_max_speech_duration=config.vad_max_speech_duration,
            )
            if vad_mode == "silero" and config.vad_model_id:
                vad_kwargs["vad_model_path"] = resolve_vad_model_path(config)
                vad_kwargs["vad_threshold"] = config.vad_threshold
            return SherpaOnnxVadOfflineEngine(**vad_kwargs)

        return SherpaOnnxOfflineEngine(
            str(model_path),
            model_type=model_type,
            file_map=file_map,
            language=source_lang,
        )

    if not config.asr_model_path:
        raise ValueError("sherpa-onnx 引擎需要配置模型路径或选择一个已下载的模型")
    return SherpaOnnxOnlineEngine(config.asr_model_path)
