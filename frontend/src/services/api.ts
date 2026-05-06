/**
 * API 服务层
 * 
 * 封装所有后端 API 调用，提供统一的接口和错误处理
 * 支持自动 Token 认证
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  Library,
  MediaItem,
  PaginatedMediaResponse,
  Task,
  TaskDetail,
  PaginatedTaskResponse,
  CreateTaskRequest,
  SystemConfig,
  TestResult,
  TestEmbyRequest,
  TestTranslationRequest,
  Statistics,
  TaskStatus,
  ConfigValidationResult,
  ASRModel,
  ModelDownloadProgress,
  LanguageInfo,
  CleanupResult,
  TempDiskUsage,
  BotStatus,
  WorkerStatus,
  SubtitleSearchResponse,
  SubtitleApplyRequest,
  SubtitleApplyResponse,
} from '../types/api';

/**
 * API 错误类型
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public details?: any
  ) {
    super(message);
    this.name = 'ApiError';
    this.message = message;
  }
}

/**
 * 获取认证 Token
 */
function getToken(): string | null {
  return localStorage.getItem('token');
}

/**
 * 为图片代理 URL 附加认证 token（img 标签无法通过 Header 传递 token）
 */
export function getImageUrl(url?: string): string | undefined {
  if (!url) return undefined;
  const token = getToken();
  if (!token) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

/**
 * API 客户端类
 */
class ApiClient {
  private client: AxiosInstance;
  private abortControllers = new Map<string, AbortController>();

  /**
   * Create an AbortSignal for a keyed request, cancelling any in-flight request with the same key
   */
  createAbortSignal(key: string): AbortSignal {
    const existing = this.abortControllers.get(key);
    if (existing) {
      existing.abort();
    }
    const controller = new AbortController();
    this.abortControllers.set(key, controller);
    return controller.signal;
  }

  /**
   * Cancel an in-flight request by key
   */
  cancelRequest(key: string): void {
    const controller = this.abortControllers.get(key);
    if (controller) {
      controller.abort();
      this.abortControllers.delete(key);
    }
  }

  constructor(baseURL: string = '') {
    this.client = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // 请求拦截器：自动添加 Token
    this.client.interceptors.request.use(
      (config) => {
        const token = getToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // 响应拦截器：统一错误处理 + 401 自动跳转登录
    this.client.interceptors.response.use(
      (response: any) => response,
      (error: AxiosError) => {
        // Silently propagate cancelled requests
        if (axios.isCancel(error)) {
          return Promise.reject(error);
        }
        // 401 未授权时跳转到登录页
        if (error.response?.status === 401) {
          localStorage.removeItem('token');
          window.location.href = '/login';
        }
        return Promise.reject(this.handleError(error));
      }
    );
  }

  /**
   * 统一错误处理
   */
  private handleError(error: AxiosError): ApiError {
    if (error.response) {
      const { status, data } = error.response;
      const d = data as any;
      const detail = d?.detail || d?.message;
      let msg: string;
      if (typeof detail === 'string') {
        msg = detail;
      } else if (Array.isArray(detail)) {
        msg = detail.map((item: any) => item.msg || JSON.stringify(item)).join('; ');
      } else if (typeof data === 'string') {
        msg = data;
      } else {
        msg = `请求失败 (${status})`;
      }
      return new ApiError(msg, status, data);
    } else if (error.request) {
      return new ApiError('网络错误，请检查服务器连接', undefined, error);
    } else {
      return new ApiError(error.message, undefined, error);
    }
  }

  /**
   * 媒体库相关 API
   */
  media = {
    /**
     * 获取媒体库列表
     */
    getLibraries: async (): Promise<Library[]> => {
      const response = await this.client.get<Library[]>('/api/libraries');
      return response.data;
    },

    /**
     * 获取媒体项列表
     */
    getMediaItems: async (params?: {
      library_id?: string;
      item_type?: string;
      search?: string;
      limit?: number;
      offset?: number;
    }, signal?: AbortSignal): Promise<PaginatedMediaResponse> => {
      const response = await this.client.get<PaginatedMediaResponse>(
        '/api/media',
        { params, signal }
      );
      return response.data;
    },

    /**
     * 获取剧集下的所有集
     */
    getSeriesEpisodes: async (seriesId: string, signal?: AbortSignal): Promise<MediaItem[]> => {
      const response = await this.client.get<MediaItem[]>(
        `/api/series/${seriesId}/episodes`,
        { signal }
      );
      return response.data;
    },
  };

  /**
   * 任务相关 API
   */
  tasks = {
    /**
     * 创建字幕生成任务
     */
    createTasks: async (
      request: CreateTaskRequest
    ): Promise<Task[]> => {
      const response = await this.client.post<Task[]>('/api/tasks', request);
      return response.data;
    },

    /**
     * 获取任务列表
     */
    getTasks: async (params?: {
      status?: TaskStatus;
      limit?: number;
      offset?: number;
    }, signal?: AbortSignal): Promise<PaginatedTaskResponse> => {
      const response = await this.client.get<PaginatedTaskResponse>(
        '/api/tasks',
        { params, signal }
      );
      return response.data;
    },

    /**
     * 获取任务详情
     */
    getTask: async (taskId: string): Promise<TaskDetail> => {
      const response = await this.client.get<TaskDetail>(`/api/tasks/${taskId}`);
      return response.data;
    },

    /**
     * 取消任务
     */
    cancelTask: async (taskId: string): Promise<Task> => {
      const response = await this.client.post<Task>(
        `/api/tasks/${taskId}/cancel`
      );
      return response.data;
    },

    /**
     * 重试任务
     */
    retryTask: async (taskId: string): Promise<Task> => {
      const response = await this.client.post<Task>(
        `/api/tasks/${taskId}/retry`
      );
      return response.data;
    },
  };

  /**
   * 配置相关 API
   */
  config = {
    /**
     * 获取系统配置
     */
    getConfig: async (): Promise<SystemConfig> => {
      const response = await this.client.get<SystemConfig>('/api/config');
      return response.data;
    },

    /**
     * 更新系统配置（完整更新）
     */
    updateConfig: async (config: SystemConfig): Promise<SystemConfig> => {
      const response = await this.client.put<SystemConfig>(
        '/api/config',
        config
      );
      return response.data;
    },

    /**
     * 部分更新系统配置（只更新指定字段）
     */
    partialUpdateConfig: async (config: Partial<SystemConfig>): Promise<SystemConfig> => {
      const response = await this.client.patch<SystemConfig>(
        '/api/config',
        config
      );
      return response.data;
    },

    /**
     * 测试 Emby 连接
     */
    testEmby: async (request: TestEmbyRequest): Promise<TestResult> => {
      const response = await this.client.post<TestResult>(
        '/api/config/test-emby',
        request
      );
      return response.data;
    },

    /**
     * 测试翻译服务连接
     */
    testTranslation: async (
      request: TestTranslationRequest
    ): Promise<TestResult> => {
      const response = await this.client.post<TestResult>(
        '/api/config/test-translation',
        request
      );
      return response.data;
    },

    /**
     * 验证系统配置是否完整
     */
    validateConfig: async (): Promise<ConfigValidationResult> => {
      const response = await this.client.get<ConfigValidationResult>(
        '/api/config/validate'
      );
      return response.data;
    },

    /**
     * 获取内置默认语气词列表
     */
    getDefaultFillerWords: async (): Promise<Record<string, string[]>> => {
      const response = await this.client.get<Record<string, string[]>>('/api/config/filler-words/defaults');
      return response.data;
    },

    /**
     * 手动清理临时文件
     */
    cleanupTemp: async (): Promise<CleanupResult> => {
      const response = await this.client.post<CleanupResult>('/api/config/cleanup-temp');
      return response.data;
    },

    /**
     * 查询临时文件磁盘占用
     */
    getTempDiskUsage: async (): Promise<TempDiskUsage> => {
      const response = await this.client.get<TempDiskUsage>('/api/config/temp-disk-usage');
      return response.data;
    },

    /**
     * 获取 Telegram Bot 状态
     */
    getBotStatus: async (): Promise<BotStatus> => {
      const response = await this.client.get<BotStatus>('/api/config/bot-status');
      return response.data;
    },

    /**
     * 启动 Telegram Bot
     */
    startBot: async (): Promise<BotStatus> => {
      const response = await this.client.post<BotStatus>('/api/config/bot-start');
      return response.data;
    },

    /**
     * 停止 Telegram Bot
     */
    stopBot: async (): Promise<BotStatus> => {
      const response = await this.client.post<BotStatus>('/api/config/bot-stop');
      return response.data;
    },
  };

  /**
   * Celery Worker 管理相关 API
   */
  worker = {
    getStatus: async (): Promise<WorkerStatus> => {
      const response = await this.client.get<WorkerStatus>('/api/worker/status');
      return response.data;
    },
    start: async (): Promise<WorkerStatus> => {
      const response = await this.client.post<WorkerStatus>('/api/worker/start');
      return response.data;
    },
    stop: async (): Promise<WorkerStatus> => {
      const response = await this.client.post<WorkerStatus>('/api/worker/stop');
      return response.data;
    },
    restart: async (): Promise<WorkerStatus> => {
      const response = await this.client.post<WorkerStatus>('/api/worker/restart');
      return response.data;
    },
  };

  /**
   * 模型管理相关 API
   */
  models = {
    /**
     * 获取所有可用模型
     */
    listModels: async (): Promise<ASRModel[]> => {
      const response = await this.client.get<ASRModel[]>('/api/models');
      return response.data;
    },

    /**
     * 开始下载模型
     */
    downloadModel: async (modelId: string): Promise<ModelDownloadProgress> => {
      const response = await this.client.post<ModelDownloadProgress>(
        `/api/models/${modelId}/download`
      );
      return response.data;
    },

    /**
     * 查询模型下载进度
     */
    getDownloadProgress: async (modelId: string): Promise<ModelDownloadProgress> => {
      const response = await this.client.get<ModelDownloadProgress>(
        `/api/models/${modelId}/progress`
      );
      return response.data;
    },

    /**
     * 删除已下载的模型
     */
    deleteModel: async (modelId: string): Promise<void> => {
      await this.client.post(`/api/models/${modelId}/delete`);
    },

    /**
     * 激活模型
     */
    activateModel: async (modelId: string): Promise<void> => {
      await this.client.post(`/api/models/${modelId}/activate`);
    },

    /**
     * 从 GitHub 刷新模型列表
     */
    refreshModels: async (): Promise<ASRModel[]> => {
      const response = await this.client.post<ASRModel[]>('/api/models/refresh');
      return response.data;
    },

    /**
     * 获取支持的语言列表
     */
    listLanguages: async (): Promise<LanguageInfo[]> => {
      const response = await this.client.get<LanguageInfo[]>('/api/models/languages');
      return response.data;
    },

    /**
     * 获取 VAD 模型列表
     */
    listVadModels: async (): Promise<ASRModel[]> => {
      const response = await this.client.get<ASRModel[]>('/api/models/vad');
      return response.data;
    },

    /**
     * 下载 VAD 模型
     */
    downloadVadModel: async (modelId: string): Promise<ModelDownloadProgress> => {
      const response = await this.client.post<ModelDownloadProgress>(
        `/api/models/vad/${modelId}/download`
      );
      return response.data;
    },

    /**
     * 激活 VAD 模型
     */
    activateVadModel: async (modelId: string): Promise<void> => {
      await this.client.post(`/api/models/vad/${modelId}/activate`);
    },
  };

  /**
   * 字幕搜索相关 API（迅雷字幕 API 集成）
   */
  subtitleSearch = {
    /**
     * 搜索字幕候选
     */
    search: async (params: {
      query: string;
      media_item_id?: string;
    }): Promise<SubtitleSearchResponse> => {
      const response = await this.client.get<SubtitleSearchResponse>(
        '/api/subtitle-search',
        { params }
      );
      return response.data;
    },

    /**
     * 下载并应用选中的字幕
     */
    apply: async (request: SubtitleApplyRequest): Promise<SubtitleApplyResponse> => {
      const response = await this.client.post<SubtitleApplyResponse>(
        '/api/subtitle-search/apply',
        request
      );
      return response.data;
    },
  };

  /**
   * 统计相关 API
   */
  stats = {
    /**
     * 获取系统统计信息
     */
    getStatistics: async (): Promise<Statistics> => {
      const response = await this.client.get<Statistics>('/api/stats');
      return response.data;
    },
  };
}

// 导出单例实例
export const api = new ApiClient();

// 判断错误是否为请求取消
export const isRequestCancelled = axios.isCancel;

// 导出类型供外部使用
export type { ApiClient };
