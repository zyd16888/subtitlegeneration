# API 服务使用说明

本目录包含前端 API 服务层，封装了所有与后端的通信。

## 文件结构

- `api.ts` - API 客户端实现，封装所有 HTTP 请求
- `../types/api.ts` - TypeScript 类型定义

## 使用示例

### 导入 API 客户端

```typescript
import { api } from '@/services/api';
import type { Library, Task, SystemConfig } from '@/types/api';
```

### 媒体库操作

```typescript
// 获取媒体库列表
const libraries = await api.media.getLibraries();

// 获取媒体项列表（支持筛选和分页）
const mediaItems = await api.media.getMediaItems({
  library_id: 'library-123',
  search: '电影名称',
  limit: 50,
  offset: 0,
});
```

### 任务操作

```typescript
// 创建字幕生成任务
const tasks = await api.tasks.createTasks({
  media_item_ids: ['item-1', 'item-2'],
});

// 获取任务列表
const taskList = await api.tasks.getTasks({
  status: TaskStatus.PROCESSING,
  limit: 100,
});

// 获取单个任务详情
const task = await api.tasks.getTask('task-id');

// 取消任务
await api.tasks.cancelTask('task-id');

// 重试失败的任务
await api.tasks.retryTask('task-id');
```

### 配置管理

```typescript
// 获取系统配置
const config = await api.config.getConfig();

// 更新系统配置
const updatedConfig = await api.config.updateConfig({
  emby_url: 'http://localhost:8096',
  emby_api_key: 'your-api-key',
  asr_engine: 'sherpa-onnx',
  translation_service: 'openai',
  openai_api_key: 'your-openai-key',
  openai_model: 'gpt-4',
  max_concurrent_tasks: 2,
  temp_dir: '/tmp/subtitle_service',
});

// 测试 Emby 连接
const embyResult = await api.config.testEmby({
  emby_url: 'http://localhost:8096',
  emby_api_key: 'your-api-key',
});

// 测试翻译服务
const translationResult = await api.config.testTranslation({
  translation_service: 'openai',
  api_key: 'your-api-key',
  model: 'gpt-4',
});
```

### 统计信息

```typescript
// 获取系统统计信息
const stats = await api.stats.getStatistics();
console.log(stats.task_statistics); // 任务统计
console.log(stats.recent_tasks);    // 最近任务
console.log(stats.system_status);   // 系统状态
```

## 错误处理

API 客户端提供统一的错误处理机制：

```typescript
import { api, ApiError } from '@/services/api';

try {
  const libraries = await api.media.getLibraries();
} catch (error) {
  if (error instanceof ApiError) {
    console.error('API 错误:', error.message);
    console.error('状态码:', error.statusCode);
    console.error('详细信息:', error.details);
  } else {
    console.error('未知错误:', error);
  }
}
```

## 配置

默认情况下，API 客户端连接到 `http://localhost:8000`。

如果需要修改后端地址，可以在 `api.ts` 中修改 `ApiClient` 构造函数的 `baseURL` 参数，或者通过环境变量配置。

## 类型安全

所有 API 方法都提供完整的 TypeScript 类型支持，确保类型安全：

- 请求参数类型检查
- 响应数据类型推断
- 枚举值自动补全

## 注意事项

1. 所有 API 方法都是异步的，需要使用 `async/await` 或 Promise
2. API 客户端会自动处理 JSON 序列化和反序列化
3. 错误会被统一转换为 `ApiError` 类型
4. 请求超时时间设置为 30 秒
