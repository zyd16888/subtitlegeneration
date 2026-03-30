"""
Unit tests for Translation Service Module

Tests the translation service implementations including:
- OpenAITranslator
- DeepSeekTranslator
- LocalLLMTranslator
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.translation_service import (
    TranslationService,
    OpenAITranslator,
    DeepSeekTranslator,
    LocalLLMTranslator
)


class TestOpenAITranslator:
    """Test OpenAI translator implementation."""
    
    def test_init_with_valid_api_key(self):
        """Test initialization with valid API key."""
        translator = OpenAITranslator(api_key="test-key", model="gpt-4")
        assert translator.api_key == "test-key"
        assert translator.model == "gpt-4"
    
    def test_init_with_empty_api_key(self):
        """Test initialization with empty API key raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            OpenAITranslator(api_key="")
    
    @pytest.mark.asyncio
    async def test_translate_empty_text(self):
        """Test translating empty text returns empty string."""
        translator = OpenAITranslator(api_key="test-key")
        result = await translator.translate("")
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_translate_success(self):
        """Test successful translation."""
        translator = OpenAITranslator(api_key="test-key")
        
        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好世界"
        
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        translator.client = mock_client
        
        result = await translator.translate("こんにちは世界", source_lang="ja", target_lang="zh")
        assert result == "你好世界"
        
        # Verify API was called with correct parameters
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs['model'] == "gpt-4"
        assert len(call_args.kwargs['messages']) == 2
    
    @pytest.mark.asyncio
    async def test_translate_with_retry_on_failure(self):
        """Test translation retry mechanism on failure."""
        translator = OpenAITranslator(api_key="test-key")
        
        # Mock client to fail twice then succeed
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好"
        
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                RuntimeError("API Error"),
                RuntimeError("API Error"),
                mock_response
            ]
        )
        
        translator.client = mock_client
        
        result = await translator.translate("こんにちは", source_lang="ja", target_lang="zh")
        assert result == "你好"
        assert mock_client.chat.completions.create.call_count == 3
    
    @pytest.mark.asyncio
    async def test_translate_returns_original_after_max_retries(self):
        """Test translation returns original text after max retries."""
        translator = OpenAITranslator(api_key="test-key")
        
        # Mock client to always fail
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("API Error")
        )
        
        translator.client = mock_client
        
        original_text = "こんにちは"
        result = await translator.translate(original_text, source_lang="ja", target_lang="zh")
        
        # Should return original text after 3 failed retries
        assert result == original_text
        assert mock_client.chat.completions.create.call_count == 3


class TestDeepSeekTranslator:
    """Test DeepSeek translator implementation."""
    
    def test_init_with_valid_api_key(self):
        """Test initialization with valid API key."""
        translator = DeepSeekTranslator(api_key="test-key")
        assert translator.api_key == "test-key"
        assert translator.api_url == "https://api.deepseek.com/v1"
    
    def test_init_with_empty_api_key(self):
        """Test initialization with empty API key raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            DeepSeekTranslator(api_key="")
    
    @pytest.mark.asyncio
    async def test_translate_empty_text(self):
        """Test translating empty text returns empty string."""
        translator = DeepSeekTranslator(api_key="test-key")
        result = await translator.translate("")
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_translate_success(self):
        """Test successful translation."""
        translator = DeepSeekTranslator(api_key="test-key")
        
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "你好世界"
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            result = await translator.translate("こんにちは世界", source_lang="ja", target_lang="zh")
            assert result == "你好世界"


class TestLocalLLMTranslator:
    """Test Local LLM translator implementation."""
    
    def test_init_with_valid_api_url(self):
        """Test initialization with valid API URL."""
        translator = LocalLLMTranslator(api_url="http://localhost:11434/api")
        assert translator.api_url == "http://localhost:11434/api"
        assert translator.model == "llama2"
    
    def test_init_with_empty_api_url(self):
        """Test initialization with empty API URL raises ValueError."""
        with pytest.raises(ValueError, match="API URL cannot be empty"):
            LocalLLMTranslator(api_url="")
    
    @pytest.mark.asyncio
    async def test_translate_empty_text(self):
        """Test translating empty text returns empty string."""
        translator = LocalLLMTranslator(api_url="http://localhost:11434/api")
        result = await translator.translate("")
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_translate_success_ollama_format(self):
        """Test successful translation with Ollama response format."""
        translator = LocalLLMTranslator(api_url="http://localhost:11434/api")
        
        # Mock httpx response (Ollama format)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": "你好世界"
            }
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            result = await translator.translate("こんにちは世界", source_lang="ja", target_lang="zh")
            assert result == "你好世界"
    
    @pytest.mark.asyncio
    async def test_translate_success_openai_format(self):
        """Test successful translation with OpenAI-compatible response format."""
        translator = LocalLLMTranslator(api_url="http://localhost:11434/api")
        
        # Mock httpx response (OpenAI format)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "你好世界"
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            
            result = await translator.translate("こんにちは世界", source_lang="ja", target_lang="zh")
            assert result == "你好世界"


class TestTranslationServiceBatch:
    """Test batch translation functionality."""
    
    @pytest.mark.asyncio
    async def test_translate_batch(self):
        """Test batch translation."""
        translator = OpenAITranslator(api_key="test-key")
        
        # Mock successful translations
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        
        mock_client = AsyncMock()
        
        # Return different translations for each call
        translations = ["你好", "世界", "测试"]
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                MagicMock(choices=[MagicMock(message=MagicMock(content=t))])
                for t in translations
            ]
        )
        
        translator.client = mock_client
        
        texts = ["こんにちは", "世界", "テスト"]
        results = await translator.translate_batch(texts, source_lang="ja", target_lang="zh")
        
        assert len(results) == 3
        assert results == translations
        assert mock_client.chat.completions.create.call_count == 3
