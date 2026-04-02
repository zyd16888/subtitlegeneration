/**
 * API 服务层
 * 
 * 封装所有后端 API 调用，提供统一的接口和错误处理
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
  }
}

/**
 * API 客户端类
 */
class ApiClient {
  private client: AxiosInstance;

  constructor(baseURL: string = 'http://localhost:8000') {
    this.client = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // 响应拦截器：统一错误处理
    this.client.interceptors.response.use(
      (response: any) => response,
      (error: AxiosError) => {
        return Promise.reject(this.handleError(error));
      }
    );
  }

  /**
   * 统一错误处理
   */
  private handleError(error: AxiosError): ApiError {
    if (error.response) {
      // 服务器返回错误响应
      const { status, data } = error.response;
      const message = (data as any)?.detail || error.message;
      return new ApiError(message, status, data);
    } else if (error.request) {
      // 请求已发送但没有收到响应
      return new ApiError('网络错误，请检查服务器连接', undefined, error);
    } else {
      // 请求配置错误
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
    }): Promise<PaginatedMediaResponse> => {
      const response = await this.client.get<PaginatedMediaResponse>(
        '/api/media',
        { params }
      );
      return response.data;
    },

    /**
     * 获取剧集下的所有集
     */
    getSeriesEpisodes: async (seriesId: string): Promise<MediaItem[]> => {
      const response = await this.client.get<MediaItem[]>(
        `/api/series/${seriesId}/episodes`
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
    }): Promise<PaginatedTaskResponse> => {
      const response = await this.client.get<PaginatedTaskResponse>(
        '/api/tasks',
        { params }
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

// 导出类型供外部使用
export type { ApiClient };
