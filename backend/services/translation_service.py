"""Translation Service Module - Supports OpenAI, DeepSeek, and Local LLM translation engines."""
import asyncio
from abc import ABC, abstractmethod
from typing import List


class TranslationService(ABC):
    """Abstract base class for translation services."""
    
    @abstractmethod
    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        pass
    
    async def translate_batch(self, texts: List[str], source_lang: str = "ja", target_lang: str = "zh") -> List[str]:
        results = []
        for text in texts:
            translated = await self.translate(text, source_lang, target_lang)
            results.append(translated)
        return results
    
    async def _translate_with_retry(self, text: str, source_lang: str, target_lang: str, max_retries: int = 3) -> str:
        last_error = None
        for attempt in range(max_retries):
            try:
                result = await self._do_translate(text, source_lang, target_lang)
                return result
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue
        print(f"Translation failed after {max_retries} retries: {last_error}")
        print(f"Preserving original text: {text}")
        return text
    
    @abstractmethod
    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        pass


class OpenAITranslator(TranslationService):
    def __init__(self, api_key: str, model: str = "gpt-4"):
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.model = model
        self.client = None
    
    def _get_client(self):
        if self.client is None:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=self.api_key)
        return self.client
    
    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        return await self._translate_with_retry(text, source_lang, target_lang)
    
    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            client = self._get_client()
            lang_names = {
                "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
                "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian",
                "pt": "Portuguese", "it": "Italian", "th": "Thai", "vi": "Vietnamese",
                "ar": "Arabic", "yue": "Cantonese",
            }
            source_name = lang_names.get(source_lang, source_lang)
            target_name = lang_names.get(target_lang, target_lang)
            system_prompt = f"You are a professional translator. Translate the following text from {source_name} to {target_name}. Only provide the translation without any explanations or additional text."
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
                temperature=0.3,
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"OpenAI translation failed: {e}")


class DeepSeekTranslator(TranslationService):
    def __init__(self, api_key: str, api_url: str = "https://api.deepseek.com/v1"):
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')
    
    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        return await self._translate_with_retry(text, source_lang, target_lang)
    
    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            import httpx
            lang_names = {
                "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
                "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian",
                "pt": "Portuguese", "it": "Italian", "th": "Thai", "vi": "Vietnamese",
                "ar": "Arabic", "yue": "Cantonese",
            }
            source_name = lang_names.get(source_lang, source_lang)
            target_name = lang_names.get(target_lang, target_lang)
            system_prompt = f"You are a professional translator. Translate the following text from {source_name} to {target_name}. Only provide the translation without any explanations or additional text."
            headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
            payload = {"model": "deepseek-chat", "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}], "temperature": 0.3, "max_tokens": 1000}
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{self.api_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            if hasattr(e, 'response'):
                raise RuntimeError(f"DeepSeek API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"DeepSeek translation failed: {e}")


class LocalLLMTranslator(TranslationService):
    def __init__(self, api_url: str, model: str = "llama2"):
        if not api_url:
            raise ValueError("API URL cannot be empty")
        self.api_url = api_url.rstrip('/')
        self.model = model
    
    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        return await self._translate_with_retry(text, source_lang, target_lang)
    
    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            import httpx
            lang_names = {
                "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
                "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian",
                "pt": "Portuguese", "it": "Italian", "th": "Thai", "vi": "Vietnamese",
                "ar": "Arabic", "yue": "Cantonese",
            }
            source_name = lang_names.get(source_lang, source_lang)
            target_name = lang_names.get(target_lang, target_lang)
            system_prompt = f"You are a professional translator. Translate the following text from {source_name} to {target_name}. Only provide the translation without any explanations or additional text."
            payload = {"model": self.model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}], "stream": False, "options": {"temperature": 0.3, "num_predict": 1000}}
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{self.api_url}/chat", json=payload)
                response.raise_for_status()
                result = response.json()
            if 'message' in result and 'content' in result['message']:
                return result['message']['content'].strip()
            elif 'choices' in result:
                return result['choices'][0]['message']['content'].strip()
            else:
                raise RuntimeError("Invalid response format from Local LLM API")
        except Exception as e:
            if hasattr(e, 'response'):
                raise RuntimeError(f"Local LLM API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"Local LLM translation failed: {e}")
