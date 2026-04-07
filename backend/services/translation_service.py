"""Translation Service Module - Supports OpenAI, DeepSeek, Local LLM, Google, Microsoft, Baidu, and DeepL translation engines."""
import asyncio
import hashlib
import random
import time
from abc import ABC, abstractmethod
from typing import List, Optional


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
    def __init__(self, api_key: str, model: str = "gpt-4", base_url: Optional[str] = None):
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/') if base_url else None
        self.client = None

    def _get_client(self):
        if self.client is None:
            from openai import AsyncOpenAI
            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self.client = AsyncOpenAI(**client_kwargs)
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


class GoogleTranslator(TranslationService):
    """Google 翻译 - 支持免费模式和官方 API 模式"""

    LANG_MAP = {
        "zh": "zh-CN", "en": "en", "ja": "ja", "ko": "ko",
        "fr": "fr", "de": "de", "es": "es", "ru": "ru",
        "pt": "pt", "it": "it", "th": "th", "vi": "vi",
        "ar": "ar", "yue": "zh-TW",
    }

    def __init__(self, mode: str = "free", api_key: Optional[str] = None):
        self.mode = mode
        self.api_key = api_key
        if mode == "api" and not api_key:
            raise ValueError("Google 翻译 API 模式需要 API Key")

    def _map_lang(self, lang: str) -> str:
        return self.LANG_MAP.get(lang, lang)

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        return await self._translate_with_retry(text, source_lang, target_lang)

    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        src = self._map_lang(source_lang)
        tgt = self._map_lang(target_lang)
        if self.mode == "free":
            return await self._translate_free(text, src, tgt)
        else:
            return await self._translate_api(text, src, tgt)

    async def _translate_free(self, text: str, src: str, tgt: str) -> str:
        try:
            from googletrans import Translator
            translator = Translator()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: translator.translate(text, src=src, dest=tgt))
            return result.text
        except Exception as e:
            raise RuntimeError(f"Google 免费翻译失败: {e}")

    async def _translate_api(self, text: str, src: str, tgt: str) -> str:
        try:
            import httpx
            url = "https://translation.googleapis.com/language/translate/v2"
            params = {
                "q": text,
                "source": src,
                "target": tgt,
                "key": self.api_key,
                "format": "text",
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, data=params)
                response.raise_for_status()
                result = response.json()
            return result["data"]["translations"][0]["translatedText"]
        except Exception as e:
            raise RuntimeError(f"Google API 翻译失败: {e}")


class MicrosoftTranslator(TranslationService):
    """微软翻译 - 支持免费模式（Bing Translator）和官方 Azure API 模式"""

    LANG_MAP = {
        "zh": "zh-Hans", "en": "en", "ja": "ja", "ko": "ko",
        "fr": "fr", "de": "de", "es": "es", "ru": "ru",
        "pt": "pt", "it": "it", "th": "th", "vi": "vi",
        "ar": "ar", "yue": "yue",
    }

    def __init__(self, mode: str = "free", api_key: Optional[str] = None, region: str = "global"):
        self.mode = mode
        self.api_key = api_key
        self.region = region
        if mode == "api" and not api_key:
            raise ValueError("微软翻译 API 模式需要 API Key")

    def _map_lang(self, lang: str) -> str:
        return self.LANG_MAP.get(lang, lang)

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        return await self._translate_with_retry(text, source_lang, target_lang)

    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        src = self._map_lang(source_lang)
        tgt = self._map_lang(target_lang)
        if self.mode == "free":
            return await self._translate_free(text, src, tgt)
        else:
            return await self._translate_api(text, src, tgt)

    async def _translate_free(self, text: str, src: str, tgt: str) -> str:
        """通过 Bing Translator 非官方接口翻译（无需 API Key）"""
        try:
            import httpx
            # 先获取认证 token
            async with httpx.AsyncClient(timeout=30.0) as client:
                page_resp = await client.get("https://www.bing.com/translator")
                page_resp.raise_for_status()
                page_text = page_resp.text
                # 提取 IG 和 token
                import re
                ig_match = re.search(r'IG:"([^"]+)"', page_text)
                iid_match = re.search(r'data-iid="([^"]+)"', page_text)
                ig = ig_match.group(1) if ig_match else ""
                iid = iid_match.group(1) if iid_match else "translator.5023"
                url = f"https://www.bing.com/ttranslatev3?IG={ig}&IID={iid}"
                data = {"fromLang": src, "to": tgt, "text": text}
                resp = await client.post(url, data=data)
                resp.raise_for_status()
                result = resp.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0]["translations"][0]["text"]
            elif isinstance(result, dict) and "statusCode" in result:
                raise RuntimeError(f"Bing 翻译错误: {result.get('errorMessage', result)}")
            raise RuntimeError(f"Bing 翻译返回格式异常: {result}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"微软免费翻译失败: {e}")

    async def _translate_api(self, text: str, src: str, tgt: str) -> str:
        """通过 Azure Translator 官方 API 翻译"""
        try:
            import httpx
            url = "https://api.cognitive.microsofttranslator.com/translate"
            params = {"api-version": "3.0", "from": src, "to": tgt}
            headers = {
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Ocp-Apim-Subscription-Region": self.region,
                "Content-Type": "application/json",
            }
            body = [{"Text": text}]
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params=params, headers=headers, json=body)
                response.raise_for_status()
                result = response.json()
            return result[0]["translations"][0]["text"]
        except Exception as e:
            if hasattr(e, 'response'):
                raise RuntimeError(f"微软翻译 API 错误: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"微软翻译失败: {e}")


class BaiduTranslator(TranslationService):
    """百度翻译 - 官方 API"""

    LANG_MAP = {
        "zh": "zh", "en": "en", "ja": "jp", "ko": "kor",
        "fr": "fra", "de": "de", "es": "spa", "ru": "ru",
        "pt": "pt", "it": "it", "th": "th", "vi": "vie",
        "ar": "ara", "yue": "yue",
    }

    def __init__(self, app_id: str, secret_key: str):
        if not app_id or not secret_key:
            raise ValueError("百度翻译需要 APP ID 和 Secret Key")
        self.app_id = app_id
        self.secret_key = secret_key
        self._last_call_time = 0.0

    def _map_lang(self, lang: str) -> str:
        return self.LANG_MAP.get(lang, lang)

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        # 百度标准版 QPS 限制：1次/秒
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        self._last_call_time = time.time()
        return await self._translate_with_retry(text, source_lang, target_lang)

    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            import httpx
            url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
            salt = str(random.randint(10000, 99999))
            sign_str = self.app_id + text + salt + self.secret_key
            sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
            params = {
                "q": text,
                "from": self._map_lang(source_lang),
                "to": self._map_lang(target_lang),
                "appid": self.app_id,
                "salt": salt,
                "sign": sign,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                result = response.json()
            if "error_code" in result:
                raise RuntimeError(f"百度翻译错误 {result['error_code']}: {result.get('error_msg', '')}")
            return result["trans_result"][0]["dst"]
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"百度翻译失败: {e}")


class DeepLTranslator(TranslationService):
    """DeepL 翻译 - 支持官方 API 和 DeepLX 免费模式"""

    LANG_MAP = {
        "zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO",
        "fr": "FR", "de": "DE", "es": "ES", "ru": "RU",
        "pt": "PT", "it": "IT", "ar": "AR",
    }
    SOURCE_LANG_MAP = {
        "zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO",
        "fr": "FR", "de": "DE", "es": "ES", "ru": "RU",
        "pt": "PT", "it": "IT", "ar": "AR",
    }

    def __init__(self, mode: str = "deeplx", api_key: Optional[str] = None, deeplx_url: Optional[str] = None):
        self.mode = mode
        self.api_key = api_key
        self.deeplx_url = (deeplx_url or "http://localhost:1188").rstrip("/")
        if mode == "api" and not api_key:
            raise ValueError("DeepL 官方 API 模式需要 API Key")

    def _map_lang(self, lang: str, is_source: bool = False) -> str:
        m = self.SOURCE_LANG_MAP if is_source else self.LANG_MAP
        mapped = m.get(lang)
        if mapped is None:
            raise ValueError(f"DeepL 不支持语言: {lang}")
        return mapped

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        return await self._translate_with_retry(text, source_lang, target_lang)

    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        src = self._map_lang(source_lang, is_source=True)
        tgt = self._map_lang(target_lang, is_source=False)
        if self.mode == "deeplx":
            return await self._translate_deeplx(text, src, tgt)
        else:
            return await self._translate_api(text, src, tgt)

    async def _translate_deeplx(self, text: str, src: str, tgt: str) -> str:
        """通过 DeepLX 免费接口翻译（需自建 DeepLX 服务）"""
        try:
            import httpx
            payload = {
                "text": text,
                "source_lang": src,
                "target_lang": tgt,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{self.deeplx_url}/translate", json=payload)
                response.raise_for_status()
                result = response.json()
            if result.get("code") == 200 and result.get("data"):
                return result["data"]
            raise RuntimeError(f"DeepLX 返回错误: {result}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"DeepLX 翻译失败: {e}")

    async def _translate_api(self, text: str, src: str, tgt: str) -> str:
        """通过 DeepL 官方 API 翻译"""
        try:
            import deepl
            loop = asyncio.get_event_loop()
            translator = deepl.Translator(self.api_key)
            result = await loop.run_in_executor(
                None, lambda: translator.translate_text(text, source_lang=src, target_lang=tgt)
            )
            return result.text
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"DeepL 翻译失败: {e}")
