"""
测试翻译服务的自动语言检测模式
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.translation_service import (
    OpenAITranslator,
    DeepSeekTranslator,
    LocalLLMTranslator,
)


class TestAutoLanguageDetection:
    """测试所有翻译服务的 auto 模式"""

    @pytest.mark.asyncio
    async def test_openai_auto_mode(self):
        """测试 OpenAI 翻译器的自动语言检测"""
        translator = OpenAITranslator(api_key="test-key", model="gpt-4")
        
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好世界"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        translator.client = mock_client
        
        # 测试 auto 模式
        result = await translator.translate("Hello world", source_lang="auto", target_lang="zh")
        
        assert result == "你好世界"
        # 验证 prompt 包含 "Automatically detect"
        call_args = mock_client.chat.completions.create.call_args
        system_message = call_args.kwargs['messages'][0]['content']
        assert "Automatically detect" in system_message
        assert "Chinese" in system_message

    @pytest.mark.asyncio
    async def test_openai_fixed_mode(self):
        """测试 OpenAI 翻译器的固定语言模式"""
        translator = OpenAITranslator(api_key="test-key", model="gpt-4")
        
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好世界"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        translator.client = mock_client
        
        # 测试固定语言模式
        result = await translator.translate("Hello world", source_lang="en", target_lang="zh")
        
        assert result == "你好世界"
        # 验证 prompt 包含 "from English to Chinese"
        call_args = mock_client.chat.completions.create.call_args
        system_message = call_args.kwargs['messages'][0]['content']
        assert "from English to Chinese" in system_message

    @pytest.mark.asyncio
    async def test_deepseek_auto_mode(self):
        """测试 DeepSeek 翻译器的自动语言检测"""
        translator = DeepSeekTranslator(api_key="test-key")
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = {
                'choices': [{'message': {'content': '你好世界'}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            result = await translator.translate("Hello world", source_lang="auto", target_lang="zh")
            
            assert result == "你好世界"
            # 验证请求包含自动检测的 prompt
            call_args = mock_client.post.call_args
            payload = call_args.kwargs['json']
            system_message = payload['messages'][0]['content']
            assert "Automatically detect" in system_message

    @pytest.mark.asyncio
    async def test_local_llm_auto_mode(self):
        """测试本地 LLM 翻译器的自动语言检测"""
        translator = LocalLLMTranslator(api_url="http://localhost:11434")
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = {
                'message': {'content': '你好世界'}
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            result = await translator.translate("Hello world", source_lang="auto", target_lang="zh")
            
            assert result == "你好世界"
            # 验证请求包含自动检测的 prompt
            call_args = mock_client.post.call_args
            payload = call_args.kwargs['json']
            system_message = payload['messages'][0]['content']
            assert "Automatically detect" in system_message

    @pytest.mark.asyncio
    async def test_empty_source_lang_treated_as_auto(self):
        """测试空字符串源语言被当作 auto 处理"""
        translator = OpenAITranslator(api_key="test-key", model="gpt-4")
        
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        translator.client = mock_client
        
        # 测试空字符串
        result = await translator.translate("Hello", source_lang="", target_lang="zh")
        
        assert result == "你好"
        # 验证 prompt 包含自动检测
        call_args = mock_client.chat.completions.create.call_args
        system_message = call_args.kwargs['messages'][0]['content']
        assert "Automatically detect" in system_message
