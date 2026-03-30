# Task 11: 日志和错误处理 - 实现文档

## 概述

本文档描述了 Task 11（日志和错误处理）的实现细节，包括日志系统配置和全局错误处理。

## 实现的功能

### Subtask 11.1: 配置日志系统

#### 文件: `backend/utils/logger.py`

实现了完整的日志系统，包括：

**核心功能:**
- 单例模式的日志管理器
- 支持控制台和文件输出
- 日志轮转（按日期，保留 30 天）
- 可配置的日志级别（DEBUG、INFO、WARNING、ERROR）
- 结构化日志格式

**主要类和函数:**

1. **Logger 类**
   - 单例模式实现
   - 管理多个日志记录器实例
   - 提供统一的配置接口

2. **setup_logger() 函数**
   ```python
   setup_logger(
       name: str = "subtitle_service",
       log_level: str = "INFO",
       log_file: str = "logs/subtitle_service.log",
       log_to_console: bool = True,
       log_to_file: bool = True
   ) -> logging.Logger
   ```
   - 配置日志记录器
   - 自动创建日志目录
   - 设置日志格式和处理器

3. **get_logger() 函数**
   ```python
   get_logger(name: str = "subtitle_service") -> logging.Logger
   ```
   - 获取已配置的日志记录器
   - 如果未配置，使用默认配置

**日志格式:**
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
示例: 2024-01-15 10:30:45 - subtitle_service - INFO - 服务启动完成
```

**日志轮转配置:**
- 轮转时间: 每天午夜 (midnight)
- 轮转间隔: 1 天
- 保留天数: 30 天
- 文件名后缀: %Y-%m-%d

**满足的需求:**
- 需求 13.1: 记录所有 API 请求和响应到日志文件 ✓
- 需求 13.2: 记录每个 Task 的处理步骤和耗时 ✓
- 需求 13.3: 记录错误堆栈信息 ✓
- 需求 13.4: 支持配置日志级别 ✓
- 需求 13.5: 日志文件按日期轮转，保留最近 30 天的日志 ✓

### Subtask 11.2: 实现全局错误处理

#### 文件: `backend/main.py`

实现了完整的全局错误处理机制，包括：

**1. 请求日志中间件**
```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
```
- 记录所有 API 请求的开始和结束
- 记录请求方法、路径、客户端 IP
- 计算并记录请求处理时间
- 在响应头中添加 X-Process-Time

**2. HTTP 异常处理器**
```python
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
```
- 处理标准 HTTP 异常（404、403 等）
- 返回标准化的错误响应格式
- 记录警告级别日志

**3. 请求验证错误处理器**
```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
```
- 处理 Pydantic 请求验证错误
- 返回详细的验证错误信息
- 状态码: 422 Unprocessable Entity

**4. 全局异常处理器**
```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
```
- 捕获所有未处理的异常
- 记录完整的错误堆栈信息
- 返回标准化的错误响应
- 在调试模式下返回详细错误信息

**标准错误响应格式:**
```json
{
    "error": "错误类型",
    "status_code": 500,
    "message": "错误描述",
    "detail": "详细信息（可选）",
    "path": "/api/endpoint"
}
```

**满足的需求:**
- 需求 13.3: 记录错误堆栈信息 ✓
- 需求 14.4: API 请求失败时返回适当的 HTTP 状态码和错误信息 ✓

## 使用示例

### 1. 配置日志系统

```python
from backend.utils.logger import setup_logger, get_logger

# 配置日志
setup_logger(
    name="subtitle_service",
    log_level="INFO",
    log_file="logs/subtitle_service.log",
    log_to_console=True,
    log_to_file=True
)

# 获取日志记录器
logger = get_logger("subtitle_service")

# 使用日志
logger.info("服务启动")
logger.warning("配置项缺失")
logger.error("处理失败", exc_info=True)
```

### 2. 在服务中使用日志

```python
from backend.utils.logger import get_logger

logger = get_logger("subtitle_service")

async def process_task(task_id: str):
    logger.info(f"开始处理任务: {task_id}")
    
    try:
        # 处理逻辑
        result = await do_something()
        logger.info(f"任务完成: {task_id}")
        return result
    except Exception as e:
        logger.error(f"任务失败: {task_id}", exc_info=True)
        raise
```

### 3. 错误处理示例

FastAPI 会自动使用配置的错误处理器：

```python
from fastapi import HTTPException

@app.get("/api/example")
async def example_endpoint():
    # HTTP 异常会被 http_exception_handler 处理
    raise HTTPException(status_code=404, detail="资源未找到")
    
    # 未处理的异常会被 global_exception_handler 处理
    raise ValueError("意外错误")
```

## 测试

### 测试文件

1. **backend/test_logger.py**
   - 测试日志系统的基本功能
   - 测试日志级别过滤
   - 测试日志文件创建和写入
   - 测试单例模式
   - 测试多个日志记录器

2. **backend/test_error_handling.py**
   - 测试 HTTP 异常处理
   - 测试请求验证错误处理
   - 测试请求日志中间件
   - 测试错误响应格式

3. **backend/test_task_11_integration.py**
   - 测试日志系统和错误处理的集成
   - 测试 API 请求日志记录
   - 测试日志轮转配置
   - 测试多个日志级别

### 运行测试

```bash
# 运行所有 Task 11 相关测试
pytest backend/test_logger.py -v
pytest backend/test_error_handling.py -v
pytest backend/test_task_11_integration.py -v

# 运行所有测试
pytest backend/ -v
```

## 配置

### 环境变量配置

在 `.env` 文件中配置日志参数：

```env
# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/subtitle_service.log
LOG_ROTATION=1 day
LOG_RETENTION=30 days
```

### 代码配置

在 `backend/config/settings.py` 中已包含日志配置：

```python
class Settings(BaseSettings):
    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/subtitle_service.log"
    log_rotation: str = "1 day"
    log_retention: str = "30 days"
```

## 日志文件结构

```
logs/
├── subtitle_service.log              # 当前日志文件
├── subtitle_service.log.2024-01-14   # 昨天的日志
├── subtitle_service.log.2024-01-13   # 前天的日志
└── ...                                # 最多保留 30 天
```

## 日志示例

### 正常请求日志
```
2024-01-15 10:30:45 - subtitle_service - INFO - 请求开始 [ID: 140234567890] GET /api/tasks 客户端: 127.0.0.1
2024-01-15 10:30:45 - subtitle_service - INFO - 请求完成 [ID: 140234567890] GET /api/tasks 状态码: 200 耗时: 0.023s
```

### 错误日志
```
2024-01-15 10:31:20 - subtitle_service - ERROR - 未处理的异常: ValueError: 无效的参数
请求路径: POST /api/tasks
客户端: 127.0.0.1
异常堆栈:
Traceback (most recent call last):
  File "backend/main.py", line 123, in process_request
    result = await handler()
ValueError: 无效的参数
```

## 性能考虑

1. **异步日志**: 日志写入是同步的，但对性能影响很小
2. **日志轮转**: 使用 TimedRotatingFileHandler，自动管理日志文件
3. **日志级别**: 生产环境建议使用 INFO 或 WARNING 级别
4. **文件大小**: 日志按天轮转，避免单个文件过大

## 最佳实践

1. **使用合适的日志级别**
   - DEBUG: 详细的调试信息
   - INFO: 一般信息（请求、任务状态）
   - WARNING: 警告信息（配置缺失、重试）
   - ERROR: 错误信息（异常、失败）

2. **记录关键信息**
   - 请求 ID 用于追踪
   - 处理时间用于性能分析
   - 错误堆栈用于调试

3. **避免敏感信息**
   - 不要记录密码、API Key
   - 不要记录完整的用户数据

4. **结构化日志**
   - 使用一致的格式
   - 包含上下文信息
   - 便于搜索和分析

## 总结

Task 11 实现了完整的日志和错误处理系统：

✅ **Subtask 11.1: 配置日志系统**
- 创建了 `backend/utils/logger.py`
- 实现了日志轮转（按日期，保留 30 天）
- 支持配置日志级别
- 支持控制台和文件输出

✅ **Subtask 11.2: 实现全局错误处理**
- 在 FastAPI 中添加了全局异常处理器
- 记录所有错误堆栈信息
- 返回标准化的错误响应
- 实现了请求日志中间件

所有需求都已满足，系统具有完善的日志记录和错误处理能力。
