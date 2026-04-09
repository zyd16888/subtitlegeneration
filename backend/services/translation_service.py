"""Translation Service Module - Supports OpenAI, DeepSeek, Local LLM, Google, Microsoft, Baidu, and DeepL translation engines.

All translation services support source_lang="auto" for automatic language detection:
- LLM-based (OpenAI, DeepSeek, Local LLM): Use prompt to auto-detect source language
- Traditional APIs (Google, Microsoft, Baidu): Use native auto-detection feature
- DeepL: Auto-detection available in API mode

Usage:
    translator = OpenAITranslator(api_key="...")
    # Fixed source language
    result = await translator.translate("こんにちは", source_lang="ja", target_lang="zh")
    # Auto-detect source language (recommended)
    result = await translator.translate("Hello", source_lang="auto", target_lang="zh")
"""
import asyncio
import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class TranslationService(ABC):
    """Abstract base class for translation services."""

    # 默认并发数：子类按 provider 限速覆盖
    default_concurrency: int = 4

    @abstractmethod
    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        """单条翻译；失败时回退原文，永远返回字符串。如需失败标志请用 translate_batch。"""
        pass

    async def translate_batch(
        self,
        texts: List[str],
        source_lang: str = "ja",
        target_lang: str = "zh",
        concurrency: Optional[int] = None,
        all_texts: Optional[List[str]] = None,
        context_size: int = 0,
    ) -> List[Tuple[str, bool]]:
        """
        并发批量翻译，结果顺序与输入一一对应。

        Args:
            all_texts: 完整字幕文本列表，用于上下文窗口（仅 LLM 翻译器使用）。
            context_size: 上下文窗口大小，前后各 N 条（0=禁用）。

        Returns:
            List of (translated_text, success) tuples. success=False 表示翻译失败已回退原文。
        """
        if not texts:
            return []

        use_context = (
            context_size > 0
            and all_texts is not None
            and hasattr(self, '_do_translate_with_context')
        )

        # 确定并发数：用户显式指定 > provider 默认值，但不能小于 1
        effective = concurrency if concurrency and concurrency > 0 else self.default_concurrency
        effective = max(1, effective)
        sem = asyncio.Semaphore(effective)

        async def _one(idx: int, text: str) -> Tuple[str, bool]:
            # 空文本直接返回，不算失败也不算成功翻译
            if not text or not text.strip():
                return (text, False)
            async with sem:
                if use_context:
                    return await self._translate_with_retry_context(
                        all_texts, idx, source_lang, target_lang, context_size
                    )
                return await self._translate_with_retry(text, source_lang, target_lang)

        return await asyncio.gather(*[_one(i, t) for i, t in enumerate(texts)])

    async def _translate_with_retry(
        self, text: str, source_lang: str, target_lang: str, max_retries: int = 3
    ) -> Tuple[str, bool]:
        """重试包装：成功返回 (译文, True)，失败返回 (原文, False)。"""
        last_error = None
        for attempt in range(max_retries):
            try:
                result = await self._do_translate(text, source_lang, target_lang)
                return (result, True)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue
        logger.warning(f"Translation failed after {max_retries} retries: {last_error}")
        logger.warning(f"Preserving original text: {text}")
        return (text, False)

    async def _translate_with_retry_context(
        self,
        all_texts: List[str],
        index: int,
        source_lang: str,
        target_lang: str,
        context_size: int,
        max_retries: int = 3,
    ) -> Tuple[str, bool]:
        """重试包装（上下文模式）：成功返回 (译文, True)，失败返回 (原文, False)。"""
        last_error = None
        for attempt in range(max_retries):
            try:
                result = await self._do_translate_with_context(
                    all_texts, index, source_lang, target_lang, context_size
                )
                return (result, True)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue
        logger.warning(f"Context translation failed after {max_retries} retries: {last_error}")
        logger.warning(f"Preserving original text: {all_texts[index]}")
        return (all_texts[index], False)

    @abstractmethod
    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        pass


class LLMTranslationService(TranslationService):
    """LLM 翻译器公共基类，提供上下文感知翻译能力。"""

    LANG_NAMES = {
        "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
        "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian",
        "pt": "Portuguese", "it": "Italian", "th": "Thai", "vi": "Vietnamese",
        "ar": "Arabic", "yue": "Cantonese",
    }

    def _get_lang_name(self, code: str) -> str:
        return self.LANG_NAMES.get(code, code)

    def _build_system_prompt(self, source_lang: str, target_lang: str) -> str:
        target_name = self._get_lang_name(target_lang)
        if source_lang == "auto" or not source_lang:
            return (
                f"You are a professional translator. Translate the following text to "
                f"{target_name}. Automatically detect the source language. "
                f"Only provide the translation without any explanations or additional text."
            )
        source_name = self._get_lang_name(source_lang)
        return (
            f"You are a professional translator. Translate the following text from "
            f"{source_name} to {target_name}. "
            f"Only provide the translation without any explanations or additional text."
        )

    def _build_context_prompt(
        self, all_texts: List[str], index: int,
        source_lang: str, target_lang: str, context_size: int,
    ) -> Tuple[str, str]:
        """构建带上下文的 (system_prompt, user_prompt)。"""
        total = len(all_texts)
        current_text = all_texts[index]

        start = max(0, index - context_size)
        end = min(total - 1, index + context_size)

        before = [f"[{j + 1}] {all_texts[j]}" for j in range(start, index)]
        after = [f"[{j + 1}] {all_texts[j]}" for j in range(index + 1, end + 1)]

        system_prompt = (
            "You are a professional subtitle translator. "
            "Translate faithfully, keep the original line breaks of the CURRENT segment. "
            "Do NOT include any timestamps or numbers in the output. "
            "Use the surrounding segments ONLY as context. "
            "Output ONLY the translation of the CURRENT segment."
        )

        target_name = self._get_lang_name(target_lang)
        parts = [f"Target language: {target_name}"]
        if source_lang and source_lang != "auto":
            parts.append(f"Source language (hint): {self._get_lang_name(source_lang)}")
        if before:
            parts.append("Context BEFORE (do not translate):\n" + "\n".join(before))
        parts.append(
            f"CURRENT [{index + 1}] (translate this only):\n"
            f"{current_text if current_text.strip() else ' '}"
        )
        if after:
            parts.append("Context AFTER (do not translate):\n" + "\n".join(after))

        user_prompt = "\n\n".join(parts)
        return system_prompt, user_prompt

    @abstractmethod
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM，返回回复文本。"""
        pass

    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        system_prompt = self._build_system_prompt(source_lang, target_lang)
        return await self._call_llm(system_prompt, text)

    async def _do_translate_with_context(
        self, all_texts: List[str], index: int,
        source_lang: str, target_lang: str, context_size: int,
    ) -> str:
        system_prompt, user_prompt = self._build_context_prompt(
            all_texts, index, source_lang, target_lang, context_size
        )
        return await self._call_llm(system_prompt, user_prompt)


class OpenAITranslator(LLMTranslationService):
    default_concurrency = 8

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
        result, _ = await self._translate_with_retry(text, source_lang, target_lang)
        return result
    
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"OpenAI translation failed: {e}")


class DeepSeekTranslator(LLMTranslationService):
    default_concurrency = 8

    def __init__(self, api_key: str, api_url: str = "https://api.deepseek.com/v1"):
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        result, _ = await self._translate_with_retry(text, source_lang, target_lang)
        return result
    
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import httpx
            headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1000,
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions", headers=headers, json=payload
                )
                response.raise_for_status()
                result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            if hasattr(e, 'response'):
                raise RuntimeError(f"DeepSeek API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"DeepSeek translation failed: {e}")


class LocalLLMTranslator(LLMTranslationService):
    # 本机算力瓶颈，并发过高反而拖慢
    default_concurrency = 2

    def __init__(self, api_url: str, model: str = "llama2"):
        if not api_url:
            raise ValueError("API URL cannot be empty")
        self.api_url = api_url.rstrip('/')
        self.model = model

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        result, _ = await self._translate_with_retry(text, source_lang, target_lang)
        return result
    
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import httpx
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 1000},
            }
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
        # 免费版易被封 IP，并发要低；官方 API 配额宽松
        self.default_concurrency = 2 if mode == "free" else 8

    def _map_lang(self, lang: str) -> str:
        return self.LANG_MAP.get(lang, lang)

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        result, _ = await self._translate_with_retry(text, source_lang, target_lang)
        return result

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
            # Google Translate 支持 src='auto' 自动检测
            if src == "auto" or not src:
                src = "auto"
            # googletrans 4.x translate() 是异步协程，直接 await
            coro_or_result = translator.translate(text, src=src, dest=tgt)
            if asyncio.iscoroutine(coro_or_result):
                result = await coro_or_result
            else:
                # 兼容旧版同步 API，放到线程池避免阻塞
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: translator.translate(text, src=src, dest=tgt)
                )
            return result.text
        except Exception as e:
            raise RuntimeError(f"Google 免费翻译失败: {e}")

    async def _translate_api(self, text: str, src: str, tgt: str) -> str:
        try:
            import httpx
            url = "https://translation.googleapis.com/language/translate/v2"
            # Google API 不需要 source 参数时会自动检测
            params = {
                "q": text,
                "target": tgt,
                "key": self.api_key,
                "format": "text",
            }
            if src != "auto" and src:
                params["source"] = src
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
        # 免费版（Bing）易被风控；Azure 官方 API 配额宽松
        self.default_concurrency = 2 if mode == "free" else 8

    def _map_lang(self, lang: str) -> str:
        return self.LANG_MAP.get(lang, lang)

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        result, _ = await self._translate_with_retry(text, source_lang, target_lang)
        return result

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
            # Bing 支持 auto-detect
            if src == "auto" or not src:
                src = "auto-detect"
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
            params = {"api-version": "3.0", "to": tgt}
            # Azure API 不指定 from 时会自动检测
            if src != "auto" and src:
                params["from"] = src
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

    # 百度标准版 1 QPS 硬限制，无论用户配置多少都强制串行
    default_concurrency = 1

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
        self._rate_lock = asyncio.Lock()

    def _map_lang(self, lang: str) -> str:
        return self.LANG_MAP.get(lang, lang)

    async def _wait_for_rate_limit(self) -> None:
        """串行限速：保证两次调用间隔 ≥ 1 秒。"""
        async with self._rate_lock:
            now = time.time()
            elapsed = now - self._last_call_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            self._last_call_time = time.time()

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        result, _ = await self._translate_with_retry(text, source_lang, target_lang)
        return result

    async def translate_batch(
        self,
        texts: List[str],
        source_lang: str = "ja",
        target_lang: str = "zh",
        concurrency: Optional[int] = None,
        all_texts: Optional[List[str]] = None,
        context_size: int = 0,
    ) -> List[Tuple[str, bool]]:
        """百度强制 concurrency=1，忽略上层传入的更大值。"""
        return await super().translate_batch(
            texts, source_lang, target_lang, concurrency=1,
            all_texts=all_texts, context_size=context_size,
        )

    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        # 限速放在 _do_translate 里，单条 translate 与批量 translate_batch 都生效
        await self._wait_for_rate_limit()
        try:
            import httpx
            url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
            salt = str(random.randint(10000, 99999))
            sign_str = self.app_id + text + salt + self.secret_key
            sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
            
            # 百度翻译支持 from='auto' 自动检测
            src_lang = self._map_lang(source_lang) if source_lang != "auto" and source_lang else "auto"
            
            params = {
                "q": text,
                "from": src_lang,
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
        # 官方 API 受限速；DeepLX 看自建服务承载，保守一点
        self.default_concurrency = 4

    def _map_lang(self, lang: str, is_source: bool = False) -> str:
        m = self.SOURCE_LANG_MAP if is_source else self.LANG_MAP
        mapped = m.get(lang)
        if mapped is None:
            raise ValueError(f"DeepL 不支持语言: {lang}")
        return mapped

    async def translate(self, text: str, source_lang: str = "ja", target_lang: str = "zh") -> str:
        if not text or not text.strip():
            return text
        result, _ = await self._translate_with_retry(text, source_lang, target_lang)
        return result

    async def _do_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        # DeepL 支持 auto 模式
        if source_lang == "auto" or not source_lang:
            src = None  # None 表示自动检测
        else:
            src = self._map_lang(source_lang, is_source=True)
        tgt = self._map_lang(target_lang, is_source=False)
        if self.mode == "deeplx":
            return await self._translate_deeplx(text, src, tgt)
        else:
            return await self._translate_api(text, src, tgt)

    async def _translate_deeplx(self, text: str, src: Optional[str], tgt: str) -> str:
        """通过 DeepLX 免费接口翻译（需自建 DeepLX 服务）"""
        try:
            import httpx
            payload = {
                "text": text,
                "target_lang": tgt,
            }
            # DeepLX 支持不指定 source_lang 时自动检测
            if src:
                payload["source_lang"] = src
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

    async def _translate_api(self, text: str, src: Optional[str], tgt: str) -> str:
        """通过 DeepL 官方 API 翻译"""
        try:
            import deepl
            loop = asyncio.get_event_loop()
            translator = deepl.Translator(self.api_key)
            # DeepL API 支持 source_lang=None 时自动检测
            result = await loop.run_in_executor(
                None, lambda: translator.translate_text(text, source_lang=src, target_lang=tgt)
            )
            return result.text
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"DeepL 翻译失败: {e}")
