"""
配置相关 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from models.base import get_db
from services.config_manager import ConfigManager, SystemConfigData
from services.emby_connector import EmbyConnector
from services.translation_service import (
    OpenAITranslator,
    DeepSeekTranslator,
    LocalLLMTranslator,
    GoogleTranslator,
    MicrosoftTranslator,
    BaiduTranslator,
    DeepLTranslator,
)

router = APIRouter(prefix="/api", tags=["config"])


class TestResult(BaseModel):
    """测试结果模型"""
    success: bool
    message: str


class TestEmbyRequest(BaseModel):
    """测试 Emby 连接请求模型"""
    emby_url: str
    emby_api_key: str


class TestTranslationRequest(BaseModel):
    """测试翻译服务请求模型"""
    translation_service: str  # openai, deepseek, local, google, microsoft, baidu, deepl
    api_key: Optional[str] = None
    api_url: Optional[str] = None
    model: Optional[str] = None
    # Google 翻译
    google_translate_mode: Optional[str] = "free"
    # 微软翻译
    microsoft_translate_mode: Optional[str] = "free"
    microsoft_region: Optional[str] = "global"
    # 百度翻译
    baidu_app_id: Optional[str] = None
    baidu_secret_key: Optional[str] = None
    # DeepL
    deepl_mode: Optional[str] = "deeplx"
    deeplx_url: Optional[str] = None


@router.get("/config", response_model=SystemConfigData)
async def get_config(db: Session = Depends(get_db)):
    """
    获取系统配置
    
    Returns:
        系统配置对象
    """
    config_manager = ConfigManager(db)
    
    try:
        config = await config_manager.get_config()
        return config
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取系统配置失败: {str(e)}"
        )


@router.put("/config", response_model=SystemConfigData)
async def update_config(
    config: SystemConfigData,
    db: Session = Depends(get_db)
):
    """
    更新系统配置
    
    Args:
        config: 新的系统配置
        
    Returns:
        更新后的系统配置
    """
    config_manager = ConfigManager(db)
    
    try:
        # 验证并更新配置
        updated_config = await config_manager.update_config(config)
        return updated_config
        
    except ValueError as e:
        # 配置验证失败
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"更新系统配置失败: {str(e)}"
        )


@router.patch("/config", response_model=SystemConfigData)
async def partial_update_config(
    config: dict,
    db: Session = Depends(get_db)
):
    """
    部分更新系统配置（支持只更新部分字段）
    
    Args:
        config: 要更新的配置字段（字典格式）
        
    Returns:
        更新后的完整系统配置
    """
    config_manager = ConfigManager(db)
    
    try:
        # 获取当前配置
        current_config = await config_manager.get_config()
        
        # 合并配置（只更新提供的字段）
        current_dict = current_config.model_dump()
        current_dict.update(config)
        
        # 创建新的配置对象
        merged_config = SystemConfigData(**current_dict)
        
        # 部分验证并更新配置
        updated_config = await config_manager.partial_update_config(merged_config, config.keys())
        return updated_config
        
    except ValueError as e:
        # 配置验证失败
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"更新系统配置失败: {str(e)}"
        )


@router.post("/config/test-emby", response_model=TestResult)
async def test_emby_connection(request: TestEmbyRequest):
    """
    测试 Emby 连接
    
    Args:
        request: 包含 Emby URL 和 API Key 的请求
        
    Returns:
        测试结果
    """
    try:
        emby = EmbyConnector(request.emby_url, request.emby_api_key)
        
        async with emby:
            success = await emby.test_connection()
        
        if success:
            return TestResult(
                success=True,
                message="Emby 连接测试成功"
            )
        else:
            return TestResult(
                success=False,
                message="Emby 连接测试失败，请检查 URL 和 API Key"
            )
            
    except Exception as e:
        return TestResult(
            success=False,
            message=f"Emby 连接测试失败: {str(e)}"
        )


@router.post("/config/test-translation", response_model=TestResult)
async def test_translation_service(request: TestTranslationRequest):
    """
    测试翻译服务连接
    
    Args:
        request: 包含翻译服务类型和凭证的请求
        
    Returns:
        测试结果
    """
    try:
        # 根据类型创建翻译服务实例
        if request.translation_service == "openai":
            if not request.api_key:
                raise ValueError("OpenAI 翻译服务需要 API Key")
            
            translator = OpenAITranslator(
                api_key=request.api_key,
                model=request.model or "gpt-4"
            )
            
        elif request.translation_service == "deepseek":
            if not request.api_key:
                raise ValueError("DeepSeek 翻译服务需要 API Key")
            
            translator = DeepSeekTranslator(api_key=request.api_key)
            
        elif request.translation_service == "local":
            if not request.api_url:
                raise ValueError("本地 LLM 翻译服务需要 API URL")

            translator = LocalLLMTranslator(api_url=request.api_url)

        elif request.translation_service == "google":
            translator = GoogleTranslator(
                mode=request.google_translate_mode or "free",
                api_key=request.api_key,
            )

        elif request.translation_service == "microsoft":
            ms_mode = request.microsoft_translate_mode or "free"
            if ms_mode == "api" and not request.api_key:
                raise ValueError("微软翻译 API 模式需要 API Key")
            translator = MicrosoftTranslator(
                mode=ms_mode,
                api_key=request.api_key,
                region=request.microsoft_region or "global",
            )

        elif request.translation_service == "baidu":
            if not request.baidu_app_id or not request.baidu_secret_key:
                raise ValueError("百度翻译服务需要 APP ID 和 Secret Key")
            translator = BaiduTranslator(
                app_id=request.baidu_app_id,
                secret_key=request.baidu_secret_key,
            )

        elif request.translation_service == "deepl":
            dl_mode = request.deepl_mode or "deeplx"
            if dl_mode == "api" and not request.api_key:
                raise ValueError("DeepL 官方 API 模式需要 API Key")
            translator = DeepLTranslator(
                mode=dl_mode,
                api_key=request.api_key,
                deeplx_url=request.deeplx_url,
            )

        else:
            raise ValueError(f"不支持的翻译服务类型: {request.translation_service}")
        
        # 测试翻译功能（翻译一个简单的测试文本）
        test_text = "こんにちは"
        result = await translator.translate(test_text, source_lang="ja", target_lang="zh")
        
        if result and len(result) > 0:
            return TestResult(
                success=True,
                message=f"翻译服务测试成功（测试翻译: {test_text} -> {result}）"
            )
        else:
            return TestResult(
                success=False,
                message="翻译服务返回空结果"
            )
            
    except ValueError as e:
        return TestResult(
            success=False,
            message=str(e)
        )
    except Exception as e:
        return TestResult(
            success=False,
            message=f"翻译服务测试失败: {str(e)}"
        )


class ConfigValidationResult(BaseModel):
    """配置验证结果模型"""
    is_valid: bool
    missing_fields: list[str] = []
    message: str


@router.get("/config/validate", response_model=ConfigValidationResult)
async def validate_config(db: Session = Depends(get_db)):
    """
    验证系统配置是否完整
    
    检查 Emby、ASR 引擎和翻译服务的所有必需配置
    
    Returns:
        配置验证结果
    """
    config_manager = ConfigManager(db)
    
    try:
        config = await config_manager.get_config()
        missing_fields = []
        
        # 检查 Emby 配置
        if not config.emby_url:
            missing_fields.append("Emby Server URL")
        if not config.emby_api_key:
            missing_fields.append("Emby API Key")
        
        # 检查 ASR 引擎配置
        if not config.asr_engine:
            missing_fields.append("ASR 引擎类型")
        elif config.asr_engine == "sherpa-onnx":
            # 必须配置模型路径或模型ID（二选一）
            if not config.asr_model_path and not config.asr_model_id:
                missing_fields.append("ASR 模型路径或模型选择")
        elif config.asr_engine == "cloud":
            if not config.cloud_asr_url:
                missing_fields.append("云端 ASR URL")
            if not config.cloud_asr_api_key:
                missing_fields.append("云端 ASR API Key")
        
        # 检查翻译服务配置
        if not config.translation_service:
            missing_fields.append("翻译服务类型")
        elif config.translation_service == "openai":
            if not config.openai_api_key:
                missing_fields.append("OpenAI API Key")
            if not config.openai_model:
                missing_fields.append("OpenAI 模型")
        elif config.translation_service == "deepseek":
            if not config.deepseek_api_key:
                missing_fields.append("DeepSeek API Key")
        elif config.translation_service == "local":
            if not config.local_llm_url:
                missing_fields.append("本地 LLM URL")
        elif config.translation_service == "google":
            mode = getattr(config, "google_translate_mode", "free")
            if mode == "api" and not getattr(config, "google_api_key", None):
                missing_fields.append("Google API Key")
        elif config.translation_service == "microsoft":
            ms_mode = getattr(config, "microsoft_translate_mode", "free")
            if ms_mode == "api" and not getattr(config, "microsoft_api_key", None):
                missing_fields.append("微软翻译 API Key")
        elif config.translation_service == "baidu":
            if not getattr(config, "baidu_app_id", None):
                missing_fields.append("百度翻译 APP ID")
            if not getattr(config, "baidu_secret_key", None):
                missing_fields.append("百度翻译 Secret Key")
        elif config.translation_service == "deepl":
            dl_mode = getattr(config, "deepl_mode", "deeplx")
            if dl_mode == "api" and not getattr(config, "deepl_api_key", None):
                missing_fields.append("DeepL API Key")
            if dl_mode == "deeplx" and not getattr(config, "deeplx_url", None):
                missing_fields.append("DeepLX 服务地址")

        is_valid = len(missing_fields) == 0
        
        if is_valid:
            message = "所有配置完整，可以正常使用字幕生成功能"
        else:
            message = f"配置不完整，缺少以下配置项: {', '.join(missing_fields)}"
        
        return ConfigValidationResult(
            is_valid=is_valid,
            missing_fields=missing_fields,
            message=message
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"验证配置失败: {str(e)}"
        )
