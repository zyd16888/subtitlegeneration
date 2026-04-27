"""
翻译服务工厂。
"""
from services.translation_service import (
    BaiduTranslator,
    DeepLTranslator,
    DeepSeekTranslator,
    GoogleTranslator,
    LocalLLMTranslator,
    MicrosoftTranslator,
    OpenAITranslator,
    TranslationService,
)


def get_translation_service(config) -> TranslationService:
    """根据配置创建翻译服务实例。"""
    if config.translation_service == "openai":
        if not config.openai_api_key:
            raise ValueError("OpenAI 翻译服务需要配置 API Key")
        return OpenAITranslator(
            config.openai_api_key,
            config.openai_model,
            config.openai_base_url,
        )
    if config.translation_service == "deepseek":
        if not config.deepseek_api_key:
            raise ValueError("DeepSeek 翻译服务需要配置 API Key")
        return DeepSeekTranslator(config.deepseek_api_key)
    if config.translation_service == "local":
        if not config.local_llm_url:
            raise ValueError("本地 LLM 翻译服务需要配置 API URL")
        return LocalLLMTranslator(config.local_llm_url)
    if config.translation_service == "google":
        return GoogleTranslator(
            mode=getattr(config, "google_translate_mode", "free"),
            api_key=getattr(config, "google_api_key", None),
        )
    if config.translation_service == "microsoft":
        return MicrosoftTranslator(
            mode=getattr(config, "microsoft_translate_mode", "free"),
            api_key=getattr(config, "microsoft_api_key", None),
            region=getattr(config, "microsoft_region", "global"),
        )
    if config.translation_service == "baidu":
        if not getattr(config, "baidu_app_id", None):
            raise ValueError("百度翻译服务需要配置 APP ID 和 Secret Key")
        if not getattr(config, "baidu_secret_key", None):
            raise ValueError("百度翻译服务需要配置 APP ID 和 Secret Key")
        return BaiduTranslator(
            app_id=config.baidu_app_id,
            secret_key=config.baidu_secret_key,
        )
    if config.translation_service == "deepl":
        return DeepLTranslator(
            mode=getattr(config, "deepl_mode", "deeplx"),
            api_key=getattr(config, "deepl_api_key", None),
            deeplx_url=getattr(config, "deeplx_url", None),
        )
    raise ValueError(f"不支持的翻译服务类型: {config.translation_service}")
