"""
配置管理服务
"""
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl, field_validator, model_validator
from models.config import SystemConfig
import json


class SystemConfigData(BaseModel):
    """系统配置数据模型"""
    model_config = {"protected_namespaces": ()}

    # Emby 配置
    emby_url: Optional[str] = None
    emby_api_key: Optional[str] = None
    
    # ASR 配置
    asr_engine: str = "sherpa-onnx"  # sherpa-onnx 或 cloud
    asr_model_path: Optional[str] = None
    asr_model_id: Optional[str] = None
    cloud_asr_url: Optional[str] = None
    cloud_asr_api_key: Optional[str] = None

    # 语言配置
    source_language: str = "ja"
    target_language: str = "zh"  # 主目标语言，向后兼容单语言场景
    # 多目标语言：同时生成多份字幕（空列表 = 回退到 [target_language]）
    # 顺序即生成顺序，第 0 个视为"主目标"（写回 target_language 字段）
    target_languages: List[str] = []
    # 是否额外保留源语言字幕（直接用 ASR 原文，不翻译）
    # 与 target_languages 独立生效；若 source_language 已在 target_languages 中则不重复生成
    keep_source_subtitle: bool = False
    # 源语言检测模式：
    # - "fixed": 强制使用 source_language 配置（适合单一语言场景）
    # - "auto": 让翻译服务自动检测源语言（推荐，适合多语言或不确定场景）
    source_language_detection: str = "auto"

    # 翻译服务配置
    translation_service: str = "openai"  # openai, deepseek, local, google, microsoft, baidu, deepl
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    openai_base_url: Optional[str] = None  # OpenAI 自定义 base_url，支持中转站点
    deepseek_api_key: Optional[str] = None
    local_llm_url: Optional[str] = None
    google_translate_mode: str = "free"  # free, api
    google_api_key: Optional[str] = None
    microsoft_translate_mode: str = "free"  # free, api
    microsoft_api_key: Optional[str] = None
    microsoft_region: str = "global"
    baidu_app_id: Optional[str] = None
    baidu_secret_key: Optional[str] = None
    deepl_mode: str = "deeplx"  # deeplx, api
    deepl_api_key: Optional[str] = None
    deeplx_url: Optional[str] = None

    # 翻译并发数（None = 使用各 provider 默认值；百度强制串行无视此值）
    translation_concurrency: Optional[int] = None

    # 翻译上下文窗口大小：当前字幕前后各 N 条作为参考（0=禁用，仅 LLM 翻译器生效，推荐 2-5）
    translation_context_size: int = 0

    # 降噪配置
    enable_denoise: bool = False

    # VAD 配置
    enable_vad: bool = False
    vad_mode: str = "energy"  # "silero" 或 "energy"
    vad_model_id: Optional[str] = None
    vad_threshold: float = 0.5
    vad_min_silence_duration: float = 0.5
    vad_min_speech_duration: float = 0.25
    vad_max_speech_duration: float = 20.0

    # 路径映射配置（Emby 路径前缀 → 本地路径前缀）
    # 格式: [{"name": "映射名称", "emby_prefix": "/me/matched", "local_prefix": "/mnt/drive/matched", "library_ids": []}]
    path_mappings: list = []

    # Telegram Bot 配置
    telegram_bot_enabled: bool = False  # Bot 启用开关（UI 控制）
    telegram_bot_token: Optional[str] = None
    telegram_admin_ids: Optional[str] = None
    telegram_daily_task_limit: int = 10
    telegram_max_concurrent_per_user: int = 2
    # 媒体库访问控制：允许 BOT 用户访问的 Emby 媒体库 ID 列表
    # None 或空列表 = 允许所有（向后兼容）
    telegram_accessible_libraries: Optional[List[str]] = None

    # 任务配置
    max_concurrent_tasks: int = 2
    temp_dir: str = "./data"
    cleanup_temp_files_on_success: bool = True  # 任务成功后自动清理临时文件

    # 模型存储目录
    model_storage_dir: Optional[str] = None

    # GitHub Token（可选，用于提高模型下载 API 速率限制）
    github_token: Optional[str] = None
    
    @field_validator('emby_url', 'cloud_asr_url', 'local_llm_url', 'deeplx_url')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """验证 URL 格式"""
        if v is None or v == "":
            return v
        # 简单的 URL 格式验证
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('URL 必须以 http:// 或 https:// 开头')
        return v
    
    @field_validator('asr_engine')
    @classmethod
    def validate_asr_engine(cls, v: str) -> str:
        """验证 ASR 引擎类型"""
        if v not in ['sherpa-onnx', 'cloud']:
            raise ValueError('ASR 引擎必须是 sherpa-onnx 或 cloud')
        return v
    
    @field_validator('source_language_detection')
    @classmethod
    def validate_source_language_detection(cls, v: str) -> str:
        """验证源语言检测模式"""
        if v not in ['fixed', 'auto']:
            raise ValueError('源语言检测模式必须是 fixed 或 auto')
        return v

    @model_validator(mode='after')
    def sync_target_language_fields(self) -> 'SystemConfigData':
        """保持 target_language / target_languages 一致：
        - 如果 target_languages 非空，target_language = target_languages[0]
        - 如果 target_languages 为空，回填为 [target_language]
        这样所有调用方读到的都是一致的。
        """
        if self.target_languages:
            self.target_language = self.target_languages[0]
        elif self.target_language:
            self.target_languages = [self.target_language]
        return self

    @field_validator('target_languages', mode='before')
    @classmethod
    def validate_target_languages(cls, v: Any) -> List[str]:
        """target_languages 必须为字符串列表；去重保持顺序"""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            # 从 DB 读出来可能是 JSON 字符串或单个语言码
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    v = parsed
                else:
                    v = [v]
            except (json.JSONDecodeError, TypeError):
                v = [v]
        if not isinstance(v, list):
            raise ValueError('target_languages 必须为列表')
        seen = set()
        result = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError('target_languages 元素必须为字符串')
            code = item.strip()
            if code and code not in seen:
                seen.add(code)
                result.append(code)
        return result
    
    @field_validator('translation_service')
    @classmethod
    def validate_translation_service(cls, v: str) -> str:
        """验证翻译服务类型"""
        if v not in ['openai', 'deepseek', 'local', 'google', 'microsoft', 'baidu', 'deepl']:
            raise ValueError('翻译服务必须是 openai, deepseek, local, google, microsoft, baidu 或 deepl')
        return v

    @field_validator('translation_concurrency')
    @classmethod
    def validate_translation_concurrency(cls, v: Optional[int]) -> Optional[int]:
        """翻译并发数：None 用默认；显式值需在 1-32 之间"""
        if v is None:
            return None
        if v < 1 or v > 32:
            raise ValueError('翻译并发数必须在 1-32 之间')
        return v
    
    @field_validator('telegram_accessible_libraries', mode='before')
    @classmethod
    def validate_accessible_libraries_field(cls, v: Any) -> Optional[List[str]]:
        """telegram_accessible_libraries 必须为字符串列表或 None"""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError('telegram_accessible_libraries 必须为列表')
        result = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError('telegram_accessible_libraries 元素必须为字符串')
            result.append(item)
        return result

    @field_validator('telegram_admin_ids', mode='before')
    @classmethod
    def validate_telegram_admin_ids(cls, v: Any) -> Optional[str]:
        """处理 telegram_admin_ids，可能是 int 或 str"""
        if v is None:
            return None
        return str(v)


class ValidationResult(BaseModel):
    """配置验证结果"""
    valid: bool
    errors: list[str] = []


class ConfigManager:
    """
    配置管理器
    
    负责系统配置的读取、更新和验证
    """
    
    def __init__(self, db: Session):
        """初始化配置管理器"""
        self.db = db
    
    async def get_config(self) -> SystemConfigData:
        """
        获取系统配置
        
        从数据库读取所有配置项，组装成 SystemConfigData 对象
        """
        config_dict = {}
        
        # 从数据库读取所有配置
        configs = self.db.query(SystemConfig).all()
        for config in configs:
            # 尝试解析 JSON 值
            try:
                config_dict[config.key] = json.loads(config.value) if config.value else None
            except (json.JSONDecodeError, TypeError):
                config_dict[config.key] = config.value
        
        # 创建配置对象，使用默认值填充缺失的配置
        return SystemConfigData(**config_dict)
    
    async def update_config(self, config: SystemConfigData) -> SystemConfigData:
        """
        更新系统配置
        
        将配置对象保存到数据库
        """
        # 验证配置
        validation_result = await self.validate_config(config)
        if not validation_result.valid:
            raise ValueError(f"配置验证失败: {', '.join(validation_result.errors)}")
        
        # 将配置对象转换为字典
        config_dict = config.model_dump()
        
        # 保存到数据库
        for key, value in config_dict.items():
            # 查找现有配置
            db_config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
            
            # 将值转换为 JSON 字符串（如果不是字符串）
            if value is not None and not isinstance(value, str):
                value_str = json.dumps(value)
            else:
                value_str = value
            
            if db_config:
                # 更新现有配置
                db_config.value = value_str
            else:
                # 创建新配置
                db_config = SystemConfig(key=key, value=value_str)
                self.db.add(db_config)
        
        self.db.commit()
        
        return config
    
    async def partial_update_config(self, config: SystemConfigData, updated_keys: set) -> SystemConfigData:
        """
        部分更新系统配置（只验证和更新指定的字段）
        
        Args:
            config: 完整的配置对象
            updated_keys: 需要更新的字段名集合
        
        Returns:
            更新后的配置对象
        """
        # 部分验证配置
        validation_result = await self.validate_partial_config(config, updated_keys)
        if not validation_result.valid:
            raise ValueError(f"配置验证失败: {', '.join(validation_result.errors)}")
        
        # 将配置对象转换为字典
        config_dict = config.model_dump()
        
        # 只保存更新的字段到数据库
        for key in updated_keys:
            if key in config_dict:
                value = config_dict[key]
                
                # 查找现有配置
                db_config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
                
                # 将值转换为 JSON 字符串（如果不是字符串）
                if value is not None and not isinstance(value, str):
                    value_str = json.dumps(value)
                else:
                    value_str = value
                
                if db_config:
                    # 更新现有配置
                    db_config.value = value_str
                else:
                    # 创建新配置
                    db_config = SystemConfig(key=key, value=value_str)
                    self.db.add(db_config)
        
        self.db.commit()
        
        return config
    
    async def validate_partial_config(self, config: SystemConfigData, updated_keys: set) -> ValidationResult:
        """
        部分验证配置参数（只验证更新的字段）
        
        Args:
            config: 完整的配置对象
            updated_keys: 需要验证的字段名集合
        
        Returns:
            验证结果
        """
        errors = []
        
        # 验证 Emby 配置（只在相关字段更新时验证）
        if 'emby_url' in updated_keys or 'emby_api_key' in updated_keys:
            if config.emby_url and not config.emby_api_key:
                errors.append("Emby URL 已配置但缺少 API Key")
            if config.emby_api_key and not config.emby_url:
                errors.append("Emby API Key 已配置但缺少 URL")
        
        # 验证 ASR 配置（只在相关字段更新时验证）
        if 'asr_engine' in updated_keys or 'asr_model_path' in updated_keys or 'asr_model_id' in updated_keys or 'cloud_asr_url' in updated_keys or 'cloud_asr_api_key' in updated_keys:
            if config.asr_engine == "sherpa-onnx":
                # 必须配置模型路径或模型ID（二选一）
                if not config.asr_model_path and not config.asr_model_id:
                    errors.append("使用 sherpa-onnx 引擎时必须配置模型路径或选择模型")
            if config.asr_engine == "cloud":
                if not config.cloud_asr_url:
                    errors.append("使用云端 ASR 时必须配置 API URL")
                if not config.cloud_asr_api_key:
                    errors.append("使用云端 ASR 时必须配置 API Key")
        
        # 验证翻译服务配置（只在相关字段更新时验证）
        translation_keys = {'translation_service', 'openai_api_key', 'openai_model', 'openai_base_url', 'deepseek_api_key', 'local_llm_url'}
        if translation_keys & updated_keys:  # 如果有交集
            if config.translation_service == "openai" and not config.openai_api_key:
                errors.append("使用 OpenAI 翻译时必须配置 API Key")
            if config.translation_service == "deepseek" and not config.deepseek_api_key:
                errors.append("使用 DeepSeek 翻译时必须配置 API Key")
            if config.translation_service == "local" and not config.local_llm_url:
                errors.append("使用本地 LLM 翻译时必须配置 API URL")

        # 验证翻译并发数
        if 'translation_concurrency' in updated_keys:
            if config.translation_concurrency is not None:
                if config.translation_concurrency < 1 or config.translation_concurrency > 32:
                    errors.append("翻译并发数必须在 1-32 之间")
        
        # 验证任务配置（只在相关字段更新时验证）
        if 'max_concurrent_tasks' in updated_keys:
            if config.max_concurrent_tasks < 1:
                errors.append("最大并发任务数必须大于 0")
            if config.max_concurrent_tasks > 16:
                errors.append("最大并发任务数不应超过 16")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def validate_accessible_libraries(
        self,
        library_ids: Optional[List[str]],
        emby_url: Optional[str],
        emby_api_key: Optional[str],
    ) -> List[str]:
        """
        验证媒体库 ID 是否有效

        Args:
            library_ids: 要验证的 Library ID 列表
            emby_url: Emby URL
            emby_api_key: Emby API Key

        Returns:
            无效的 Library ID 列表（空列表表示全部有效）。
            Emby 连接失败时返回空列表并记录 warning（跳过验证）。
        """
        if not library_ids:
            return []
        if not emby_url or not emby_api_key:
            logger.warning("Emby 未配置，跳过 Library ID 验证")
            return []
        try:
            from services.emby_connector import EmbyConnector
            async with EmbyConnector(emby_url, emby_api_key) as emby:
                libraries = await emby.get_libraries()
            valid_ids = {lib.id for lib in libraries}
            invalid = [lid for lid in library_ids if lid not in valid_ids]
            return invalid
        except Exception as e:
            logger.warning(f"连接 Emby 验证 Library ID 失败，跳过验证: {e}")
            return []

    async def validate_config(self, config: SystemConfigData) -> ValidationResult:
        """
        验证配置参数的有效性
        
        检查必填字段、URL 格式、API Key 等
        """
        errors = []
        
        # 验证 Emby 配置
        if config.emby_url and not config.emby_api_key:
            errors.append("Emby URL 已配置但缺少 API Key")
        if config.emby_api_key and not config.emby_url:
            errors.append("Emby API Key 已配置但缺少 URL")
        
        # 验证 ASR 配置
        if config.asr_engine == "sherpa-onnx":
            # 必须配置模型路径或模型ID（二选一）
            if not config.asr_model_path and not config.asr_model_id:
                errors.append("使用 sherpa-onnx 引擎时必须配置模型路径或选择模型")
        if config.asr_engine == "cloud":
            if not config.cloud_asr_url:
                errors.append("使用云端 ASR 时必须配置 API URL")
            if not config.cloud_asr_api_key:
                errors.append("使用云端 ASR 时必须配置 API Key")
        
        # 验证翻译服务配置
        if config.translation_service == "openai" and not config.openai_api_key:
            errors.append("使用 OpenAI 翻译时必须配置 API Key")
        if config.translation_service == "deepseek" and not config.deepseek_api_key:
            errors.append("使用 DeepSeek 翻译时必须配置 API Key")
        if config.translation_service == "local" and not config.local_llm_url:
            errors.append("使用本地 LLM 翻译时必须配置 API URL")
        
        # 验证任务配置
        if config.max_concurrent_tasks < 1:
            errors.append("最大并发任务数必须大于 0")
        if config.max_concurrent_tasks > 16:
            errors.append("最大并发任务数不应超过 16")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
