# Task 2: 数据库模型和配置管理 - 实现文档

## 概述

本任务实现了 Emby 字幕生成服务的数据库模型和配置管理功能，包括：
- SQLAlchemy 数据库模型（Task 和 SystemConfig）
- 数据库基类和会话管理
- ConfigManager 配置管理服务

## 实现的文件

### 1. backend/models/base.py
**功能:** 数据库基类和会话管理

**主要组件:**
- `engine`: SQLAlchemy 数据库引擎（支持 SQLite）
- `SessionLocal`: 数据库会话工厂
- `Base`: SQLAlchemy 声明式基类
- `get_db()`: 数据库会话生成器（用于 FastAPI 依赖注入）
- `init_db()`: 初始化数据库，创建所有表

**特性:**
- 自动从 settings 读取数据库 URL
- SQLite 特殊配置（check_same_thread=False）
- 支持调试模式（echo SQL 语句）

### 2. backend/models/task.py
**功能:** 任务数据模型

**TaskStatus 枚举:**
- `PENDING`: 待处理
- `PROCESSING`: 处理中
- `COMPLETED`: 已完成
- `FAILED`: 失败
- `CANCELLED`: 已取消

**Task 模型字段:**
- `id` (String, PK): 任务唯一标识符
- `media_item_id` (String): Emby 媒体项 ID
- `media_item_title` (String): 媒体项标题
- `video_path` (String): 视频文件路径
- `status` (Enum): 任务状态
- `progress` (Integer): 任务进度 (0-100)
- `created_at` (DateTime): 创建时间
- `completed_at` (DateTime): 完成时间
- `error_message` (Text): 错误信息

**索引:**
- 主键索引: `id`
- 普通索引: `media_item_id`, `status`

### 3. backend/models/config.py
**功能:** 系统配置数据模型

**SystemConfig 模型字段:**
- `key` (String, PK): 配置键
- `value` (Text): 配置值（JSON 格式）
- `description` (String): 配置描述

**设计说明:**
- 使用键值对形式存储配置
- 支持任意类型的配置值（通过 JSON 序列化）
- 灵活扩展，无需修改数据库结构

### 4. backend/services/config_manager.py
**功能:** 配置管理服务

**SystemConfigData 模型:**
Pydantic 模型，定义所有系统配置参数：

**Emby 配置:**
- `emby_url`: Emby 服务器地址
- `emby_api_key`: Emby API 密钥

**ASR 配置:**
- `asr_engine`: ASR 引擎类型（sherpa-onnx 或 cloud）
- `asr_model_path`: sherpa-onnx 模型路径
- `cloud_asr_url`: 云端 ASR API 地址
- `cloud_asr_api_key`: 云端 ASR API 密钥

**翻译服务配置:**
- `translation_service`: 翻译服务类型（openai, deepseek, local）
- `openai_api_key`: OpenAI API 密钥
- `openai_model`: OpenAI 模型名称
- `deepseek_api_key`: DeepSeek API 密钥
- `local_llm_url`: 本地 LLM API 地址

**任务配置:**
- `max_concurrent_tasks`: 最大并发任务数
- `temp_dir`: 临时文件目录

**ConfigManager 类方法:**

1. `get_config() -> SystemConfigData`
   - 从数据库读取所有配置
   - 自动解析 JSON 值
   - 使用默认值填充缺失配置

2. `update_config(config: SystemConfigData) -> SystemConfigData`
   - 验证配置有效性
   - 将配置保存到数据库
   - 自动序列化为 JSON

3. `validate_config(config: SystemConfigData) -> ValidationResult`
   - 验证必填字段
   - 验证 URL 格式
   - 验证 API Key 配置
   - 验证引擎类型选择
   - 返回详细的错误信息

**验证规则:**
- Emby URL 和 API Key 必须同时配置
- sherpa-onnx 引擎需要模型路径
- 云端 ASR 需要 URL 和 API Key
- OpenAI 翻译需要 API Key
- DeepSeek 翻译需要 API Key
- 本地 LLM 翻译需要 URL
- 并发任务数范围: 1-10
- URL 必须以 http:// 或 https:// 开头

## 数据库设计

### 表结构

**tasks 表:**
```sql
CREATE TABLE tasks (
    id VARCHAR PRIMARY KEY,
    media_item_id VARCHAR NOT NULL,
    media_item_title VARCHAR,
    video_path VARCHAR,
    status VARCHAR NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    completed_at DATETIME,
    error_message TEXT
);
CREATE INDEX ix_tasks_media_item_id ON tasks(media_item_id);
CREATE INDEX ix_tasks_status ON tasks(status);
```

**system_config 表:**
```sql
CREATE TABLE system_config (
    key VARCHAR PRIMARY KEY,
    value TEXT,
    description VARCHAR
);
```

## 测试

### 测试文件

1. **backend/test_models.py**
   - 测试 Task 模型的 CRUD 操作
   - 测试 SystemConfig 模型的存储和读取
   - 验证数据库初始化

2. **backend/test_config_manager.py**
   - 测试配置的读取和更新
   - 测试配置验证逻辑（有效和无效配置）
   - 测试 URL 格式验证
   - 测试必填字段验证

### 运行测试

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 运行数据库模型测试
python backend/test_models.py

# 运行配置管理器测试
python backend/test_config_manager.py
```

## 使用示例

### 初始化数据库

```python
from backend.models import init_db

# 创建所有表
init_db()
```

### 使用 Task 模型

```python
from backend.models import SessionLocal, Task, TaskStatus
import uuid

db = SessionLocal()

# 创建任务
task = Task(
    id=str(uuid.uuid4()),
    media_item_id="emby_item_123",
    media_item_title="我的视频.mp4",
    video_path="/media/videos/my_video.mp4",
    status=TaskStatus.PENDING,
    progress=0
)
db.add(task)
db.commit()

# 查询任务
task = db.query(Task).filter(Task.id == task_id).first()

# 更新任务状态
task.status = TaskStatus.PROCESSING
task.progress = 50
db.commit()

# 查询所有待处理任务
pending_tasks = db.query(Task).filter(Task.status == TaskStatus.PENDING).all()
```

### 使用 ConfigManager

```python
from backend.models import SessionLocal
from backend.services import ConfigManager, SystemConfigData

db = SessionLocal()
config_manager = ConfigManager(db)

# 获取配置
config = await config_manager.get_config()
print(f"Emby URL: {config.emby_url}")

# 更新配置
config.emby_url = "http://localhost:8096"
config.emby_api_key = "your_api_key"
config.openai_api_key = "sk-your_key"

updated_config = await config_manager.update_config(config)

# 验证配置
validation_result = await config_manager.validate_config(config)
if not validation_result.valid:
    print(f"配置错误: {validation_result.errors}")
```

## 满足的需求

### 需求 12.1: 使用 SQLite 存储 Task 信息
✅ 实现了 Task 模型，包含所有必需字段

### 需求 12.2: 存储系统配置参数
✅ 实现了 SystemConfig 模型，支持键值对存储

### 需求 12.3: 数据库基类和会话管理
✅ 实现了 Base 基类和 SessionLocal 会话工厂

### 需求 10.4: 配置参数验证
✅ 实现了 validate_config() 方法，包含完整的验证逻辑

### 需求 10.5: 配置存储
✅ 实现了 get_config() 和 update_config() 方法

### 需求 12.4: 配置管理
✅ 实现了 ConfigManager 服务，提供完整的配置管理功能

## 技术亮点

1. **类型安全**: 使用 Pydantic 进行配置验证和类型检查
2. **灵活的配置存储**: 键值对设计支持任意配置扩展
3. **完善的验证**: 多层次验证（字段级、模型级、业务级）
4. **异步支持**: ConfigManager 方法支持异步调用
5. **错误处理**: 详细的错误信息和验证结果
6. **索引优化**: 为常用查询字段添加索引

## 下一步

Task 2 已完成，可以继续实现：
- Task 3: Emby 集成模块
- Task 8: 任务管理模块（依赖 Task 模型）
- Task 10: FastAPI 路由和端点（依赖 ConfigManager）
