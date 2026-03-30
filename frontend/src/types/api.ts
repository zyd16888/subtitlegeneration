/**
 * API 类型定义
 * 
 * 定义前端与后端 API 交互的所有数据类型
 */

/**
 * 任务状态枚举
 */
export enum TaskStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

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
  status: TaskStatus;
  progress: number;
  created_at: string;
  completed_at?: string;
  error_message?: string;
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
 * 单个任务配置
 */
export interface TaskConfig {
  media_item_id: string;
  asr_engine?: 'sherpa-onnx' | 'cloud';
  translation_service?: 'openai' | 'deepseek' | 'local';
  openai_model?: string;
}

/**
 * 创建任务请求
 */
export interface CreateTaskRequest {
  media_item_ids?: string[]; // 批量创建，使用全局配置
  tasks?: TaskConfig[]; // 单独配置每个任务
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
  translation_service: 'openai' | 'deepseek' | 'local';
  openai_api_key?: string;
  openai_model: string;
  deepseek_api_key?: string;
  local_llm_url?: string;

  // 任务配置
  max_concurrent_tasks: number;
  temp_dir: string;
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
  translation_service: 'openai' | 'deepseek' | 'local';
  api_key?: string;
  api_url?: string;
  model?: string;
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
 * 配置验证结果类型
 */
export interface ConfigValidationResult {
  is_valid: boolean;
  missing_fields: string[];
  message: string;
}
