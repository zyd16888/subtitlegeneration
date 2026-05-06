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
  target_language?: string;  // 主目标语言（列表第 0 个，向后兼容）
  target_languages?: string[];  // 多目标语言列表（从 extra_info 透传）

  // 结果信息
  subtitle_path?: string;
  segment_count?: number;  // 识别的字幕段落数
  audio_duration?: number;  // 音频时长（秒）

  // 字幕来源标记（"xunlei_search" 表示来自外部字幕搜索）
  subtitle_source?: string;

  // 任务类型："subtitle_generate"（默认）或 "library_subtitle_scan"
  task_type?: string;
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
  target_languages?: string[]; // 多目标语言，覆盖全局配置
  keep_source_subtitle?: boolean; // 是否额外保留源语言字幕
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
  cloud_asr_provider?: 'groq' | 'openai' | 'fireworks' | 'elevenlabs' | 'deepgram' | 'volcengine' | 'tencent' | 'aliyun';
  groq_asr_api_key?: string;
  groq_asr_model?: string;
  groq_asr_base_url?: string;
  groq_asr_public_audio_base_url?: string;
  groq_asr_prompt?: string;
  openai_asr_api_key?: string;
  openai_asr_model?: string;
  openai_asr_base_url?: string;
  openai_asr_prompt?: string;
  fireworks_asr_api_key?: string;
  fireworks_asr_model?: string;
  fireworks_asr_base_url?: string;
  fireworks_asr_public_audio_base_url?: string;
  fireworks_asr_prompt?: string;
  elevenlabs_asr_api_key?: string;
  elevenlabs_asr_model?: string;
  elevenlabs_asr_base_url?: string;
  elevenlabs_asr_public_audio_base_url?: string;
  deepgram_asr_api_key?: string;
  deepgram_asr_model?: string;
  deepgram_asr_base_url?: string;
  deepgram_asr_public_audio_base_url?: string;
  volcengine_asr_app_id?: string;
  volcengine_asr_access_token?: string;
  volcengine_asr_model?: string;
  volcengine_asr_base_url?: string;
  volcengine_asr_public_audio_base_url?: string;
  tencent_asr_secret_id?: string;
  tencent_asr_secret_key?: string;
  tencent_asr_engine_model_type?: string;
  tencent_asr_base_url?: string;
  tencent_asr_public_audio_base_url?: string;
  tencent_asr_region?: string;
  aliyun_asr_api_key?: string;
  aliyun_asr_model?: string;
  aliyun_asr_base_url?: string;
  aliyun_asr_public_audio_base_url?: string;

  // 语言检测与自适应模型选择
  enable_language_detection?: boolean;    // 启用音频语言检测（Whisper LID）
  lid_model_id?: string;                 // LID 使用的 Whisper 模型 ID
  lid_sample_duration?: number;          // LID 扫描时长（秒），在此范围内寻找有声片段
  lid_num_segments?: number;             // LID 采样段数，对多段分别检测后投票
  lid_filter_whitelist_enabled?: boolean; // 启用 LID 语言白名单过滤
  lid_filter_whitelist?: string[];        // LID 允许返回的语言白名单
  asr_language_model_map?: Record<string, string>;  // 语言→ASR模型映射

  // 语言配置
  source_language: string;
  target_language: string;  // 主目标语言（始终等于 target_languages[0]）
  target_languages?: string[];  // 多目标语言列表（空时回退 [target_language]）
  keep_source_subtitle?: boolean;  // 是否额外保留源语言字幕
  source_language_detection?: 'fixed' | 'auto';  // 源语言检测模式

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

  // 翻译并发数（留空使用各 provider 默认值；百度强制串行无视此值）
  translation_concurrency?: number | null;

  // 翻译上下文窗口：当前字幕前后各 N 条作为参考（0=禁用，仅 LLM 翻译器生效）
  translation_context_size?: number;

  // 音频预处理
  enable_denoise?: boolean;

  // VAD 配置
  enable_vad?: boolean;
  vad_mode?: 'energy' | 'silero';
  vad_model_id?: string;
  vad_threshold?: number;
  vad_min_silence_duration?: number;
  vad_min_speech_duration?: number;
  vad_max_speech_duration?: number;

  // 语气词过滤
  filter_filler_words?: boolean;
  custom_filler_words?: string[];

  // 路径映射配置
  path_mappings: PathMapping[];

  // Telegram Bot 配置
  telegram_bot_enabled?: boolean;
  telegram_bot_token?: string;
  telegram_admin_ids?: string;
  telegram_daily_task_limit?: number;
  telegram_max_concurrent_per_user?: number;
  telegram_accessible_libraries?: string[];

  // 任务配置
  max_concurrent_tasks: number;
  temp_dir: string;
  cleanup_temp_files_on_success: boolean;

  // 模型存储与下载
  model_storage_dir?: string;
  github_token?: string;

  // 字幕搜索（迅雷字幕 API）
  subtitle_search_enabled?: boolean;
  subtitle_search_auto_in_task?: boolean;
  subtitle_search_min_score?: number;
  subtitle_search_timeout?: number;
}

/**
 * 字幕搜索结果中语言信息
 */
export interface SubtitleSearchLanguageInfo {
  code: string | null;
  source: 'api_field' | 'filename' | 'content' | 'unknown' | string;
  confidence: number;
  is_bilingual: boolean;
  secondary_code?: string | null;
}

/**
 * 单条字幕搜索结果
 */
export interface SubtitleSearchResult {
  gcid: string;
  cid: string;
  url: string;
  ext: string;
  name: string;
  duration_ms: number;
  raw_languages: string[];
  extra_name?: string | null;
  language: SubtitleSearchLanguageInfo;
  score: number;
  duration_match: number;
  score_breakdown: Record<string, any>;
}

/**
 * 字幕搜索响应
 */
export interface SubtitleSearchResponse {
  query: string;
  media_duration_ms?: number | null;
  target_languages: string[];
  items: SubtitleSearchResult[];
}

/**
 * 字幕应用请求
 */
export interface SubtitleApplyRequest {
  media_item_id: string;
  url: string;
  ext: string;
  name?: string;
  raw_languages?: string[];
  library_id?: string;
  path_mapping_index?: number;
  force_language?: string;
}

/**
 * 字幕应用响应
 */
export interface SubtitleApplyResponse {
  media_item_id: string;
  target_path: string;
  ext: string;
  language: SubtitleSearchLanguageInfo;
  emby_refreshed: boolean;
  source_url: string;
  file_size: number;
}

/**
 * 库扫描启动请求
 */
export interface LibraryScanStartRequest {
  library_id: string;
  target_languages?: string[];
  skip_if_has_subtitle?: boolean;
  max_items?: number;
  concurrency?: number;
  item_type?: string;
}

/**
 * 库扫描启动响应
 */
export interface LibraryScanStartResponse {
  task_id: string;
  library_id: string;
  library_name?: string;
  status: string;
}

/**
 * 库扫描单项结果
 */
export interface LibraryScanItemReport {
  media_item_id: string;
  name: string;
  outcome: 'applied' | 'no_match' | 'skipped_already_has_subtitle' | 'error' | 'cancelled';
  languages: string[];
  score?: number | null;
  error?: string | null;
}

/**
 * 库扫描汇总报告（写入 task.extra_info.scan_report）
 */
export interface LibraryScanReport {
  library_id: string;
  library_name: string;
  target_languages: string[];
  skip_if_has_subtitle: boolean;
  scanned_total: number;
  applied: number;
  no_match: number;
  skipped_already_has_subtitle: number;
  errors: number;
  cancelled: boolean;
  halted_reason?: string | null;
  items: LibraryScanItemReport[];
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
