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


_SUPPORTED_LANGUAGE_CODES = {
    "zh", "en", "ja", "ko", "fr", "de", "es", "ru", "pt", "it", "th", "vi", "ar", "yue",
}

_SUPPORTED_CLOUD_ASR_PROVIDERS = {
    "groq",
    "openai",
    "fireworks",
    "elevenlabs",
    "deepgram",
    "volcengine",
    "tencent",
    "aliyun",
}


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
    cloud_asr_provider: str = "groq"
    groq_asr_api_key: Optional[str] = None
    groq_asr_model: str = "whisper-large-v3-turbo"
    groq_asr_base_url: str = "https://api.groq.com/openai/v1"
    groq_asr_public_audio_base_url: Optional[str] = None
    groq_asr_prompt: Optional[str] = None
    openai_asr_api_key: Optional[str] = None
    openai_asr_model: str = "whisper-1"
    openai_asr_base_url: str = "https://api.openai.com/v1"
    openai_asr_prompt: Optional[str] = None
    fireworks_asr_api_key: Optional[str] = None
    fireworks_asr_model: str = "whisper-v3-turbo"
    fireworks_asr_base_url: str = "https://audio-turbo.api.fireworks.ai/v1"
    fireworks_asr_public_audio_base_url: Optional[str] = None
    fireworks_asr_prompt: Optional[str] = None
    elevenlabs_asr_api_key: Optional[str] = None
    elevenlabs_asr_model: str = "scribe_v2"
    elevenlabs_asr_base_url: str = "https://api.elevenlabs.io/v1"
    elevenlabs_asr_public_audio_base_url: Optional[str] = None
    deepgram_asr_api_key: Optional[str] = None
    deepgram_asr_model: str = "nova-3"
    deepgram_asr_base_url: str = "https://api.deepgram.com/v1"
    deepgram_asr_public_audio_base_url: Optional[str] = None
    volcengine_asr_app_id: Optional[str] = None
    volcengine_asr_access_token: Optional[str] = None
    volcengine_asr_model: str = "bigmodel"
    volcengine_asr_base_url: str = "https://openspeech.bytedance.com/api/v1/vc"
    volcengine_asr_public_audio_base_url: Optional[str] = None
    tencent_asr_secret_id: Optional[str] = None
    tencent_asr_secret_key: Optional[str] = None
    tencent_asr_engine_model_type: str = "16k_ja"
    tencent_asr_base_url: str = "https://asr.tencentcloudapi.com"
    tencent_asr_public_audio_base_url: Optional[str] = None
    tencent_asr_region: str = "ap-guangzhou"
    aliyun_asr_api_key: Optional[str] = None
    aliyun_asr_model: str = "fun-asr-mtl"
    aliyun_asr_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    aliyun_asr_public_audio_base_url: Optional[str] = None

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

    # 语言检测与自适应模型选择
    enable_language_detection: bool = False          # 启用音频语言检测（Whisper LID）
    lid_model_id: Optional[str] = None               # LID 使用的 Whisper 模型 ID
    lid_sample_duration: int = 600                     # LID 扫描时长（秒），在此范围内寻找有声片段
    lid_num_segments: int = 3                          # LID 采样段数，对多段分别检测后投票
    lid_filter_whitelist_enabled: bool = False        # 是否启用 LID 语言白名单过滤
    lid_filter_whitelist: List[str] = []              # LID 允许返回的语言白名单
    asr_language_model_map: Dict[str, str] = {}       # 语言→ASR模型映射 {"ja":"model-a","en":"model-b"}

    # 降噪配置
    enable_denoise: bool = False

    # VAD 配置
    enable_vad: bool = False
    vad_mode: str = "energy"  # "silero" 或 "energy"
    vad_model_id: Optional[str] = None
    vad_threshold: float = 0.5
    vad_min_silence_duration: float = 0.7
    vad_min_speech_duration: float = 0.5
    vad_max_speech_duration: float = 20.0

    # 语气词过滤配置
    filter_filler_words: bool = True          # 过滤纯语气词段落（あ、え、うん 等），减少无意义翻译
    custom_filler_words: List[str] = []       # 用户自定义语气词（与内置列表合并生效）

    # 路径映射配置（Emby 路径前缀 → 本地路径前缀）
    # 格式: [{"name": "映射名称", "emby_prefix": "/me/matched", "local_prefix": "/mnt/drive/matched", "library_ids": []}]
    path_mappings: list = []

    # 字幕搜索（迅雷字幕 API）
    subtitle_search_enabled: bool = False              # 总开关：关闭时手动入口与自动检索都不生效
    subtitle_search_auto_in_task: bool = False         # 任务开始前自动检索；命中即跳过 ASR/翻译
    subtitle_search_min_score: float = 0.7             # 自动模式下的命中阈值
    subtitle_search_timeout: int = 5                   # API 超时（秒）

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
    
    @field_validator(
        'emby_url',
        'groq_asr_base_url',
        'groq_asr_public_audio_base_url',
        'openai_asr_base_url',
        'fireworks_asr_base_url',
        'fireworks_asr_public_audio_base_url',
        'elevenlabs_asr_base_url',
        'elevenlabs_asr_public_audio_base_url',
        'deepgram_asr_base_url',
        'deepgram_asr_public_audio_base_url',
        'volcengine_asr_base_url',
        'volcengine_asr_public_audio_base_url',
        'tencent_asr_base_url',
        'tencent_asr_public_audio_base_url',
        'aliyun_asr_base_url',
        'aliyun_asr_public_audio_base_url',
        'local_llm_url',
        'deeplx_url',
    )
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

    @field_validator('cloud_asr_provider')
    @classmethod
    def validate_cloud_asr_provider(cls, v: str) -> str:
        """验证云端 ASR 厂商"""
        if v not in _SUPPORTED_CLOUD_ASR_PROVIDERS:
            raise ValueError('云端 ASR 厂商必须是 groq、openai、fireworks、elevenlabs、deepgram、volcengine、tencent 或 aliyun')
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
    
    @field_validator('custom_filler_words', mode='before')
    @classmethod
    def validate_custom_filler_words(cls, v: Any) -> List[str]:
        """custom_filler_words: JSON 字符串或列表 → 去重字符串列表"""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    v = parsed
                else:
                    v = [v]
            except (json.JSONDecodeError, TypeError):
                v = [v]
        if not isinstance(v, list):
            raise ValueError('custom_filler_words 必须为列表')
        seen = set()
        result = []
        for item in v:
            if not isinstance(item, str):
                continue
            word = item.strip()
            if word and word not in seen:
                seen.add(word)
                result.append(word)
        return result

    @field_validator('lid_filter_whitelist', mode='before')
    @classmethod
    def validate_lid_filter_whitelist(cls, v: Any) -> List[str]:
        """lid_filter_whitelist: JSON 字符串或列表 → 去重后的合法语言码列表"""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    v = parsed
                else:
                    v = [v]
            except (json.JSONDecodeError, TypeError):
                v = [v]
        if not isinstance(v, list):
            raise ValueError('lid_filter_whitelist 必须为列表')

        seen = set()
        result = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError('lid_filter_whitelist 元素必须为字符串')
            code = item.strip().lower()
            if not code:
                continue
            if code not in _SUPPORTED_LANGUAGE_CODES:
                raise ValueError(f'lid_filter_whitelist 包含不支持的语言: {code}')
            if code not in seen:
                seen.add(code)
                result.append(code)
        return result

    @field_validator('asr_language_model_map', mode='before')
    @classmethod
    def validate_asr_language_model_map(cls, v: Any) -> Dict[str, str]:
        """asr_language_model_map: JSON 字符串或 dict → dict[str, str]"""
        if v is None or v == "":
            return {}
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return {str(k): str(val) for k, val in parsed.items() if k and val}
            except (json.JSONDecodeError, TypeError):
                return {}
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items() if k and val}
        return {}

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

    @field_validator('subtitle_search_min_score')
    @classmethod
    def validate_subtitle_search_min_score(cls, v: float) -> float:
        """字幕搜索命中阈值必须在 0-1 之间"""
        if v < 0 or v > 1:
            raise ValueError('subtitle_search_min_score 必须在 0-1 之间')
        return v

    @field_validator('subtitle_search_timeout')
    @classmethod
    def validate_subtitle_search_timeout(cls, v: int) -> int:
        """字幕搜索 API 超时必须在 1-60 秒之间"""
        if v < 1 or v > 60:
            raise ValueError('subtitle_search_timeout 必须在 1-60 秒之间')
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

    def _validate_cloud_asr_config(self, config: SystemConfigData) -> List[str]:
        errors = []
        provider = config.cloud_asr_provider

        if provider not in _SUPPORTED_CLOUD_ASR_PROVIDERS:
            errors.append("当前仅支持 Groq、OpenAI、Fireworks、ElevenLabs、Deepgram、火山引擎、腾讯云、阿里云 ASR")
            return errors

        if provider == "groq":
            if not config.groq_asr_api_key:
                errors.append("使用 Groq ASR 时必须配置 API Key")
            if not config.groq_asr_model:
                errors.append("使用 Groq ASR 时必须配置模型")
            if not config.groq_asr_base_url:
                errors.append("使用 Groq ASR 时必须配置 Base URL")
        elif provider == "openai":
            if not config.openai_asr_api_key:
                errors.append("使用 OpenAI ASR 时必须配置 API Key")
            if not config.openai_asr_model:
                errors.append("使用 OpenAI ASR 时必须配置模型")
            if not config.openai_asr_base_url:
                errors.append("使用 OpenAI ASR 时必须配置 Base URL")
        elif provider == "fireworks":
            if not config.fireworks_asr_api_key:
                errors.append("使用 Fireworks ASR 时必须配置 API Key")
            if not config.fireworks_asr_model:
                errors.append("使用 Fireworks ASR 时必须配置模型")
            if not config.fireworks_asr_base_url:
                errors.append("使用 Fireworks ASR 时必须配置 Base URL")
        elif provider == "elevenlabs":
            if not config.elevenlabs_asr_api_key:
                errors.append("使用 ElevenLabs ASR 时必须配置 API Key")
            if not config.elevenlabs_asr_model:
                errors.append("使用 ElevenLabs ASR 时必须配置模型")
            if not config.elevenlabs_asr_base_url:
                errors.append("使用 ElevenLabs ASR 时必须配置 Base URL")
        elif provider == "deepgram":
            if not config.deepgram_asr_api_key:
                errors.append("使用 Deepgram ASR 时必须配置 API Key")
            if not config.deepgram_asr_model:
                errors.append("使用 Deepgram ASR 时必须配置模型")
            if not config.deepgram_asr_base_url:
                errors.append("使用 Deepgram ASR 时必须配置 Base URL")
        elif provider == "volcengine":
            if not config.volcengine_asr_app_id:
                errors.append("使用火山引擎 ASR 时必须配置 App ID")
            if not config.volcengine_asr_access_token:
                errors.append("使用火山引擎 ASR 时必须配置 Access Token")
            if not config.volcengine_asr_base_url:
                errors.append("使用火山引擎 ASR 时必须配置 Base URL")
            if not config.volcengine_asr_public_audio_base_url:
                errors.append("使用火山引擎 ASR 时必须配置公网音频访问地址")
        elif provider == "tencent":
            if not config.tencent_asr_secret_id:
                errors.append("使用腾讯云 ASR 时必须配置 SecretId")
            if not config.tencent_asr_secret_key:
                errors.append("使用腾讯云 ASR 时必须配置 SecretKey")
            if not config.tencent_asr_engine_model_type:
                errors.append("使用腾讯云 ASR 时必须配置引擎模型类型")
            if not config.tencent_asr_base_url:
                errors.append("使用腾讯云 ASR 时必须配置 Base URL")
            if not config.tencent_asr_public_audio_base_url:
                errors.append("使用腾讯云 ASR 时必须配置公网音频访问地址")
        elif provider == "aliyun":
            if not config.aliyun_asr_api_key:
                errors.append("使用阿里云 ASR 时必须配置 API Key")
            if not config.aliyun_asr_model:
                errors.append("使用阿里云 ASR 时必须配置模型")
            if not config.aliyun_asr_base_url:
                errors.append("使用阿里云 ASR 时必须配置 Base URL")
            if not config.aliyun_asr_public_audio_base_url:
                errors.append("使用阿里云 ASR 时必须配置公网音频访问地址")

        return errors
    
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
        asr_keys = {
            'asr_engine',
            'asr_model_path',
            'asr_model_id',
            'cloud_asr_provider',
            'groq_asr_api_key',
            'groq_asr_model',
            'groq_asr_base_url',
            'groq_asr_public_audio_base_url',
            'groq_asr_prompt',
            'openai_asr_api_key',
            'openai_asr_model',
            'openai_asr_base_url',
            'openai_asr_prompt',
            'fireworks_asr_api_key',
            'fireworks_asr_model',
            'fireworks_asr_base_url',
            'fireworks_asr_public_audio_base_url',
            'fireworks_asr_prompt',
            'elevenlabs_asr_api_key',
            'elevenlabs_asr_model',
            'elevenlabs_asr_base_url',
            'elevenlabs_asr_public_audio_base_url',
            'deepgram_asr_api_key',
            'deepgram_asr_model',
            'deepgram_asr_base_url',
            'deepgram_asr_public_audio_base_url',
            'volcengine_asr_app_id',
            'volcengine_asr_access_token',
            'volcengine_asr_model',
            'volcengine_asr_base_url',
            'volcengine_asr_public_audio_base_url',
            'tencent_asr_secret_id',
            'tencent_asr_secret_key',
            'tencent_asr_engine_model_type',
            'tencent_asr_base_url',
            'tencent_asr_public_audio_base_url',
            'tencent_asr_region',
            'aliyun_asr_api_key',
            'aliyun_asr_model',
            'aliyun_asr_base_url',
            'aliyun_asr_public_audio_base_url',
        }
        if asr_keys & updated_keys:
            if config.asr_engine == "sherpa-onnx":
                # 必须配置模型路径或模型ID（二选一）
                if not config.asr_model_path and not config.asr_model_id:
                    errors.append("使用 sherpa-onnx 引擎时必须配置模型路径或选择模型")
            if config.asr_engine == "cloud":
                errors.extend(self._validate_cloud_asr_config(config))
        
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
            errors.extend(self._validate_cloud_asr_config(config))
        
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
