/**
 * API 类型定义
 * 
 * 定义前端与后端 API 交互的所有数据类型
 */

/**
 * 任务状态枚举
 */
export type TaskStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';

/**
 * 媒体库类型
 */
export interface Library {
  id: string;
  name: string;
  type: string;
}

/**
 * 媒体项类型
 */
export interface MediaItem {
  id: string;
  name: string;
  type: string;
  path?: string;
  has_subtitles: boolean;
  image_url?: string;
}

/**
 * 分页媒体项响应
 */
export interface PaginatedMediaResponse {
  items: MediaItem[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * 任务类型
 */
export interface Task {
  id: string;
  media_item_id: string;
  media_item_title?: string;
  video_path?: string;
  
  // 用户追踪信息
  telegram_user_id?: number;
  telegram_username?: string;
  telegram_display_name?: string;
  emby_username?: string;
  
  // 状态信息
  status: TaskStatus;
  progress: number;
  
  // 时间信息
  created_at: string;
  started_at?: string;
  completed_at?: string;
  processing_time?: number;  // 处理耗时（秒）
  
  // 错误信息
  error_message?: string;
  error_stage?: string;  // 错误发生的阶段
  
  // 配置信息
  asr_engine?: string;
  asr_model_id?: string;
  translation_service?: string;
  source_language?: string;
  target_language?: string;
  
  // 结果信息
  subtitle_path?: string;
  segment_count?: number;  // 识别的字幕段落数
  audio_duration?: number;  // 音频时长（秒）
}

/**
 * 任务详情（包含更多细节）
 */
export interface TaskDetail extends Task {
  extra_info?: Record<string, any>;
  wait_time?: number;  // 等待时间（秒）
}

/**
 * 分页任务响应
 */
export interface PaginatedTaskResponse {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * 路径映射规则
 */
export interface PathMapping {
  name: string;
  emby_prefix: string;
  local_prefix: string;
  library_ids: string[];
}

/**
 * 单个任务配置
 */
export interface TaskConfig {
  media_item_id: string;
  asr_engine?: 'sherpa-onnx' | 'cloud';
  translation_service?: 'openai' | 'deepseek' | 'local' | 'google' | 'microsoft' | 'baidu' | 'deepl';
  openai_model?: string;
  path_mapping_index?: number;
  source_language?: string; // 语音识别语言，覆盖全局配置
}

/**
 * 创建任务请求
 */
export interface CreateTaskRequest {
  media_item_ids?: string[]; // 批量创建，使用全局配置
  tasks?: TaskConfig[]; // 单独配置每个任务
  library_id?: string; // 当前媒体库 ID（用于路径映射匹配）
}

/**
 * 系统配置类型
 */
export interface SystemConfig {
  // Emby 配置
  emby_url?: string;
  emby_api_key?: string;

  // ASR 配置
  asr_engine: 'sherpa-onnx' | 'cloud';
  asr_model_path?: string;
  asr_model_id?: string;
  cloud_asr_url?: string;
  cloud_asr_api_key?: string;

  // 语言配置
  source_language: string;
  target_language: string;

  // 翻译服务配置
  translation_service: 'openai' | 'deepseek' | 'local' | 'google' | 'microsoft' | 'baidu' | 'deepl';
  openai_api_key?: string;
  openai_model: string;
  openai_base_url?: string;  // OpenAI 自定义 base_url，支持中转站点
  deepseek_api_key?: string;
  local_llm_url?: string;
  google_translate_mode?: string;
  google_api_key?: string;
  microsoft_translate_mode?: string;
  microsoft_api_key?: string;
  microsoft_region?: string;
  baidu_app_id?: string;
  baidu_secret_key?: string;
  deepl_mode?: string;
  deepl_api_key?: string;
  deeplx_url?: string;

  // VAD 配置
  enable_vad?: boolean;
  vad_model_id?: string;
  vad_threshold?: number;
  vad_min_silence_duration?: number;
  vad_min_speech_duration?: number;
  vad_max_speech_duration?: number;

  // 路径映射配置
  path_mappings: PathMapping[];

  // Telegram Bot 配置
  telegram_bot_enabled?: boolean;
  telegram_bot_token?: string;
  telegram_admin_ids?: string;
  telegram_daily_task_limit?: number;
  telegram_max_concurrent_per_user?: number;

  // 任务配置
  max_concurrent_tasks: number;
  temp_dir: string;
  cleanup_temp_files_on_success: boolean;

  // 模型存储与下载
  model_storage_dir?: string;
  github_token?: string;
}

/**
 * ASR 模型信息
 */
export interface ASRModel {
  id: string;
  name: string;
  type: 'online' | 'offline';
  model_type: string;
  languages: string[];
  size: string;
  installed: boolean;
  active: boolean;
  download_count?: number;
}

/**
 * 模型下载进度
 */
export interface ModelDownloadProgress {
  model_id: string;
  progress: number;
  status: 'idle' | 'downloading' | 'extracting' | 'completed' | 'failed';
  error?: string;
}

/**
 * 语言信息
 */
export interface LanguageInfo {
  code: string;
  name: string;
}

/**
 * 测试结果类型
 */
export interface TestResult {
  success: boolean;
  message: string;
}

/**
 * 测试 Emby 连接请求
 */
export interface TestEmbyRequest {
  emby_url: string;
  emby_api_key: string;
}

/**
 * 测试翻译服务请求
 */
export interface TestTranslationRequest {
  translation_service: 'openai' | 'deepseek' | 'local' | 'google' | 'microsoft' | 'baidu' | 'deepl';
  api_key?: string;
  api_url?: string;
  model?: string;
  google_translate_mode?: string;
  microsoft_translate_mode?: string;
  microsoft_region?: string;
  baidu_app_id?: string;
  baidu_secret_key?: string;
  deepl_mode?: string;
  deeplx_url?: string;
}

/**
 * 任务统计类型
 */
export interface TaskStatistics {
  total: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  cancelled: number;
}

/**
 * 最近任务类型
 */
export interface RecentTask {
  id: string;
  media_item_title?: string;
  status: TaskStatus;
  completed_at?: string;
}

/**
 * 系统状态类型
 */
export interface SystemStatus {
  emby_connected: boolean;
  emby_message: string;
  asr_configured: boolean;
  asr_message: string;
  translation_configured: boolean;
  translation_message: string;
}

/**
 * 统计信息类型
 */
export interface Statistics {
  task_statistics: TaskStatistics;
  recent_tasks: RecentTask[];
  system_status: SystemStatus;
}

/**
 * 清理结果类型
 */
export interface CleanupResult {
  success: boolean;
  cleaned_count: number;
  freed_bytes: number;
  message: string;
}

/**
 * 临时文件磁盘占用
 */
export interface TempDiskUsage {
  total_bytes: number;
  total_mb: number;
  task_count: number;
  details: { task_id: string; bytes: number; mb: number }[];
}

/**
 * Bot 状态类型
 */
export interface BotStatus {
  running: boolean;
  uptime_seconds?: number;
  message: string;
}

/**
 * Celery Worker 状态类型
 */
export interface WorkerStatus {
  running: boolean;
  pid?: number;
  uptime_seconds?: number;
  message?: string;
}

/**
 * 配置验证结果类型
 */
export interface ConfigValidationResult {
  is_valid: boolean;
  missing_fields: string[];
  message: string;
}

/**
 * 语言代码到名称的映射
 */
export const LANGUAGE_NAMES: Record<string, string> = {
  'ja': '日语',
  'zh': '中文',
  'en': '英语',
  'ko': '韩语',
  'fr': '法语',
  'de': '德语',
  'es': '西班牙语',
  'ru': '俄语',
  'pt': '葡萄牙语',
  'it': '意大利语',
  'th': '泰语',
  'vi': '越南语',
  'ar': '阿拉伯语',
  'yue': '粤语',
};

/**
 * 翻译服务名称映射
 */
export const TRANSLATION_SERVICE_NAMES: Record<string, string> = {
  'openai': 'OpenAI',
  'deepseek': 'DeepSeek',
  'local': '本地 LLM',
  'google': 'Google 翻译',
  'microsoft': '微软翻译',
  'baidu': '百度翻译',
  'deepl': 'DeepL',
};

/**
 * ASR 引擎名称映射
 */
export const ASR_ENGINE_NAMES: Record<string, string> = {
  'sherpa-onnx': 'Sherpa-ONNX (本地)',
  'cloud': '云端 ASR',
};
