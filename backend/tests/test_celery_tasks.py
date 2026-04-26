"""
Celery 任务测试

测试 Celery 配置和字幕生成任务的基本功能
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from backend.tasks.celery_app import celery_app
from backend.tasks.subtitle_tasks import (
    generate_subtitle_task,
    _get_asr_engine,
    _get_translation_service,
    _translate_segments
)
from backend.services.asr_engine import Segment
from backend.services.config_manager import SystemConfigData


def test_celery_app_configuration():
    """测试 Celery 应用配置"""
    # 验证 Celery 应用已正确创建
    assert celery_app is not None
    assert celery_app.main == "subtitle_service"
    
    # 验证配置
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.task_track_started is True


def test_celery_task_registration():
    """测试 Celery 任务注册"""
    # 验证任务已注册
    task_name = "backend.tasks.subtitle_tasks.generate_subtitle_task"
    assert task_name in celery_app.tasks
    
    # 验证任务配置
    task = celery_app.tasks[task_name]
    assert task.max_retries == 3
    assert task.default_retry_delay == 60


def test_get_asr_engine_sherpa_onnx():
    """测试创建 sherpa-onnx ASR 引擎"""
    config = SystemConfigData(
        asr_engine="sherpa-onnx",
        asr_model_path="/path/to/model"
    )
    
    with patch("backend.tasks.subtitle_tasks.SherpaOnnxEngine") as mock_engine:
        _get_asr_engine(config)
        mock_engine.assert_called_once_with("/path/to/model")


def test_get_asr_engine_cloud():
    """测试创建云端 ASR 引擎"""
    config = SystemConfigData(
        asr_engine="cloud",
        cloud_asr_provider="groq",
        groq_asr_api_key="test-key",
        groq_asr_model="whisper-large-v3-turbo",
        groq_asr_base_url="https://api.groq.com/openai/v1",
    )
    
    with patch("backend.tasks.subtitle_tasks.GroqASRProvider") as mock_provider, \
            patch("backend.tasks.subtitle_tasks.CloudASREngine") as mock_engine:
        provider_instance = Mock()
        mock_provider.return_value = provider_instance
        _get_asr_engine(config)
        mock_provider.assert_called_once_with(
            api_key="test-key",
            model="whisper-large-v3-turbo",
            base_url="https://api.groq.com/openai/v1",
            public_audio_base_url=None,
            prompt=None,
        )
        mock_engine.assert_called_once_with(provider_instance)


def test_get_asr_engine_invalid():
    """测试无效的 ASR 引擎配置"""
    config = SystemConfigData(asr_engine="invalid")
    
    with pytest.raises(ValueError, match="不支持的 ASR 引擎类型"):
        _get_asr_engine(config)


def test_get_translation_service_openai():
    """测试创建 OpenAI 翻译服务"""
    config = SystemConfigData(
        translation_service="openai",
        openai_api_key="test-key",
        openai_model="gpt-4"
    )
    
    with patch("backend.tasks.subtitle_tasks.OpenAITranslator") as mock_translator:
        _get_translation_service(config)
        mock_translator.assert_called_once_with("test-key", "gpt-4")


def test_get_translation_service_deepseek():
    """测试创建 DeepSeek 翻译服务"""
    config = SystemConfigData(
        translation_service="deepseek",
        deepseek_api_key="test-key"
    )
    
    with patch("backend.tasks.subtitle_tasks.DeepSeekTranslator") as mock_translator:
        _get_translation_service(config)
        mock_translator.assert_called_once_with("test-key")


def test_get_translation_service_local():
    """测试创建本地 LLM 翻译服务"""
    config = SystemConfigData(
        translation_service="local",
        local_llm_url="http://localhost:11434"
    )
    
    with patch("backend.tasks.subtitle_tasks.LocalLLMTranslator") as mock_translator:
        _get_translation_service(config)
        mock_translator.assert_called_once_with("http://localhost:11434")


def test_get_translation_service_invalid():
    """测试无效的翻译服务配置"""
    config = SystemConfigData(translation_service="invalid")
    
    with pytest.raises(ValueError, match="不支持的翻译服务类型"):
        _get_translation_service(config)


@pytest.mark.asyncio
async def test_translate_segments_success():
    """测试成功翻译文本片段"""
    segments = [
        Segment(start=0.0, end=2.0, text="こんにちは"),
        Segment(start=2.0, end=4.0, text="世界")
    ]
    
    mock_translator = AsyncMock()
    mock_translator.translate.side_effect = ["你好", "世界"]
    
    result = await _translate_segments(segments, mock_translator)
    
    assert len(result) == 2
    assert result[0].original_text == "こんにちは"
    assert result[0].translated_text == "你好"
    assert result[0].is_translated is True
    assert result[1].original_text == "世界"
    assert result[1].translated_text == "世界"
    assert result[1].is_translated is True


@pytest.mark.asyncio
async def test_translate_segments_with_failure():
    """测试翻译失败时保留原文"""
    segments = [
        Segment(start=0.0, end=2.0, text="こんにちは"),
        Segment(start=2.0, end=4.0, text="世界")
    ]
    
    mock_translator = AsyncMock()
    mock_translator.translate.side_effect = [
        "你好",
        Exception("Translation failed")
    ]
    
    result = await _translate_segments(segments, mock_translator)
    
    assert len(result) == 2
    assert result[0].is_translated is True
    assert result[1].is_translated is False
    assert result[1].translated_text == "世界"  # 保留原文


def test_generate_subtitle_task_structure():
    """测试字幕生成任务的基本结构"""
    # 验证任务函数存在
    assert callable(generate_subtitle_task)
    
    # 验证任务参数
    import inspect
    sig = inspect.signature(generate_subtitle_task)
    params = list(sig.parameters.keys())
    
    # 第一个参数是 self (因为 bind=True)
    assert "self" in params
    assert "task_id" in params
    assert "media_item_id" in params
    assert "video_path" in params
