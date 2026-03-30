# FastAPI 路由和端点实现文档

## 概述

本文档描述了 Task 10 "FastAPI 路由和端点" 的实现细节。所有 API 端点已按照设计文档和需求实现。

## 实现的子任务

### 10.1 媒体库相关 API ✅

**文件:** `backend/api/media.py`

**实现的端点:**

1. **GET /api/libraries**
   - 功能: 获取 Emby 媒体库列表
   - 响应: `List[LibraryResponse]`
   - 需求: 14.2, 9.1, 9.2

2. **GET /api/media**
   - 功能: 获取媒体项列表，支持筛选和分页
   - 查询参数:
     - `library_id`: 可选的媒体库 ID 筛选
     - `item_type`: 可选的媒体类型筛选 (Movie, Episode 等)
     - `search`: 可选的搜索关键词
     - `limit`: 每页数量 (默认 50, 最大 200)
     - `offset`: 分页偏移量 (默认 0)
   - 响应: `PaginatedMediaResponse`
   - 需求: 14.2, 9.1, 9.2

**特性:**
- 自动从配置中获取 Emby 连接信息
- 如果 Emby 未配置，返回 400 错误
- 支持异步上下文管理器确保连接正确关闭
- 完整的错误处理和 HTTP 状态码

### 10.2 任务相关 API ✅

**文件:** `backend/api/tasks.py`

**实现的端点:**

1. **POST /api/tasks**
   - 功能: 创建字幕生成任务（支持批量）
   - 请求体: `CreateTaskRequest` (包含 `media_item_ids` 列表)
   - 响应: `List[TaskResponse]`
   - 自动触发 Celery 异步任务
   - 需求: 14.2, 8.1, 8.2, 8.3, 8.4, 9.5, 15.1

2. **GET /api/tasks**
   - 功能: 获取任务列表
   - 查询参数:
     - `status`: 可选的任务状态筛选
     - `limit`: 每页数量 (默认 100, 最大 500)
     - `offset`: 分页偏移量 (默认 0)
   - 响应: `PaginatedTaskResponse`
   - 需求: 14.2, 8.1, 8.2, 8.3, 8.4, 9.5, 15.1

3. **GET /api/tasks/{task_id}**
   - 功能: 获取任务详情
   - 路径参数: `task_id`
   - 响应: `TaskResponse`
   - 需求: 14.2, 8.1, 8.2, 8.3, 8.4, 9.5, 15.1

4. **POST /api/tasks/{task_id}/cancel**
   - 功能: 取消任务
   - 路径参数: `task_id`
   - 响应: `TaskResponse`
   - 只能取消 PENDING 或 PROCESSING 状态的任务
   - 需求: 14.2, 8.1, 8.2, 8.3, 8.4, 9.5, 15.1

5. **POST /api/tasks/{task_id}/retry**
   - 功能: 重试失败的任务
   - 路径参数: `task_id`
   - 响应: `TaskResponse` (新创建的任务)
   - 只能重试 FAILED 状态的任务
   - 自动触发新的 Celery 任务
   - 需求: 14.2, 8.1, 8.2, 8.3, 8.4, 9.5, 15.1

**特性:**
- 批量创建任务支持
- 自动从 Emby 获取媒体项信息和文件路径
- 集成 Celery 异步任务队列
- 完整的任务状态管理
- 详细的错误处理

### 10.3 配置相关 API ✅

**文件:** `backend/api/config.py`

**实现的端点:**

1. **GET /api/config**
   - 功能: 获取系统配置
   - 响应: `SystemConfigData`
   - 需求: 14.2, 10.1, 10.2, 10.3

2. **PUT /api/config**
   - 功能: 更新系统配置
   - 请求体: `SystemConfigData`
   - 响应: `SystemConfigData`
   - 自动验证配置参数
   - 需求: 14.2, 10.1, 10.2, 10.3

3. **POST /api/config/test-emby**
   - 功能: 测试 Emby 连接
   - 请求体: `TestEmbyRequest` (包含 URL 和 API Key)
   - 响应: `TestResult`
   - 需求: 14.2, 10.1, 10.2, 10.3

4. **POST /api/config/test-translation**
   - 功能: 测试翻译服务连接
   - 请求体: `TestTranslationRequest` (包含服务类型和凭证)
   - 响应: `TestResult`
   - 支持 OpenAI, DeepSeek, 本地 LLM
   - 执行实际翻译测试 ("こんにちは")
   - 需求: 14.2, 10.1, 10.2, 10.3

**特性:**
- 完整的配置验证
- 实时连接测试
- 支持多种翻译服务
- 详细的错误信息

### 10.4 统计相关 API ✅

**文件:** `backend/api/stats.py`

**实现的端点:**

1. **GET /api/stats**
   - 功能: 获取系统统计信息
   - 响应: `StatisticsResponse`
   - 包含:
     - 任务统计 (总数、各状态数量)
     - 最近完成的任务 (最多 10 个)
     - 系统状态 (Emby、ASR、翻译服务连接状态)
   - 需求: 14.2, 11.1, 11.2, 11.3

**特性:**
- 实时任务统计
- 系统健康检查
- 配置状态验证
- Emby 连接测试

### 10.5 FastAPI 应用配置 ✅

**文件:** `backend/main.py`

**实现的功能:**

1. **CORS 配置**
   - 允许所有来源 (生产环境应限制)
   - 支持凭证
   - 允许所有方法和头部
   - 需求: 14.1, 14.3, 14.4, 13.1

2. **全局异常处理**
   - 捕获所有未处理的异常
   - 记录详细的错误日志和堆栈信息
   - 返回标准化的 JSON 错误响应
   - 需求: 14.1, 14.3, 14.4, 13.1

3. **日志配置**
   - 配置基本日志格式
   - 记录所有 API 请求和错误
   - 需求: 14.1, 14.3, 14.4, 13.1

4. **启动和关闭事件**
   - 启动时自动初始化数据库
   - 记录启动和关闭日志
   - 需求: 14.1, 14.3, 14.4, 13.1

5. **路由注册**
   - 注册所有 API 路由模块
   - 统一的 `/api` 前缀
   - 需求: 14.1, 14.3, 14.4, 13.1

6. **API 文档**
   - Swagger UI: `/api/docs`
   - ReDoc: `/api/redoc`
   - 需求: 14.5

## API 响应格式

所有 API 端点遵循标准的 JSON 响应格式:

### 成功响应
```json
{
  "id": "...",
  "field1": "value1",
  "field2": "value2"
}
```

### 错误响应
```json
{
  "detail": "错误描述信息"
}
```

### 分页响应
```json
{
  "items": [...],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

## HTTP 状态码

- `200 OK`: 请求成功
- `400 Bad Request`: 请求参数错误或验证失败
- `404 Not Found`: 资源不存在
- `500 Internal Server Error`: 服务器内部错误

## 依赖注入

所有端点使用 FastAPI 的依赖注入系统:

- `get_db()`: 获取数据库会话
- `get_emby_connector()`: 获取 Emby 连接器实例

## 测试

**测试文件:** `backend/test_api_endpoints.py`

包含以下测试用例:
- 根路径和健康检查
- 配置的获取和更新
- 任务的创建、查询、取消、重试
- 统计信息获取
- 错误处理

运行测试:
```bash
pytest backend/test_api_endpoints.py -v
```

## 使用示例

### 获取媒体库列表
```bash
curl http://localhost:8000/api/libraries
```

### 创建字幕生成任务
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"media_item_ids": ["item1", "item2"]}'
```

### 获取任务列表
```bash
curl http://localhost:8000/api/tasks?status=processing&limit=10
```

### 更新配置
```bash
curl -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "emby_url": "http://localhost:8096",
    "emby_api_key": "your_api_key",
    "asr_engine": "sherpa-onnx",
    "translation_service": "openai"
  }'
```

### 测试 Emby 连接
```bash
curl -X POST http://localhost:8000/api/config/test-emby \
  -H "Content-Type: application/json" \
  -d '{
    "emby_url": "http://localhost:8096",
    "emby_api_key": "your_api_key"
  }'
```

## 注意事项

1. **Emby 配置**: 在使用媒体库和任务相关 API 之前，必须先配置 Emby 连接
2. **异步处理**: 任务创建后立即返回，实际处理由 Celery 异步执行
3. **错误处理**: 所有端点都有完整的错误处理和日志记录
4. **分页**: 媒体项和任务列表都支持分页，避免一次返回过多数据
5. **CORS**: 当前配置允许所有来源，生产环境应限制为前端域名

## 下一步

所有 API 端点已实现完成。可以继续进行:
- 前端开发 (Task 13-20)
- 集成测试
- 部署配置
