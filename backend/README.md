# Emby AI 中文字幕生成服务 - 后端

这是 Emby AI 中文字幕生成服务的后端部分，使用 Python FastAPI + Celery + Redis + SQLite 构建。

## 目录结构

```
backend/
├── api/                    # FastAPI 路由和端点
│   ├── config.py          # 配置相关 API
│   ├── media.py           # 媒体库相关 API
│   ├── models.py          # ASR 模型管理 API
│   ├── stats.py           # 统计信息 API
│   └── tasks.py           # 任务相关 API
├── config/                 # 配置管理
│   └── settings.py        # 系统配置
├── docs/                   # 文档目录
│   └── usage/             # 使用文档
│       ├── AUDIO_EXTRACTOR_USAGE.md
│       ├── CELERY_TASKS_USAGE.md
│       ├── EMBY_CONNECTOR_USAGE.md
│       ├── SUBTITLE_GENERATOR_USAGE.md
│       ├── TASK_MANAGER_USAGE.md
│       └── TRANSLATION_SERVICE_USAGE.md
├── logs/                   # 日志文件
├── models/                 # 数据库模型
│   ├── base.py            # 数据库基类
│   ├── config.py          # 配置模型
│   └── task.py            # 任务模型
├── models_data/            # ASR 模型文件
│   ├── streaming-zipformer-bilingual-zh-en
│   ├── whisper-base
│   ├── whisper-tiny
│   └── zipformer-ja-reazonspeech
├── services/               # 业务逻辑服务
│   ├── asr_engine.py      # ASR 语音识别引擎
│   ├── audio_extractor.py # 音频提取服务
│   ├── config_manager.py  # 配置管理服务
│   ├── emby_connector.py  # Emby 连接器
│   ├── model_manager.py   # ASR 模型管理
│   ├── subtitle_generator.py # 字幕生成服务
│   ├── task_manager.py    # 任务管理服务
│   └── translation_service.py # 翻译服务
├── tasks/                  # Celery 异步任务
│   ├── celery_app.py      # Celery 应用配置
│   └── subtitle_tasks.py  # 字幕生成任务
├── tests/                  # 测试文件
├── utils/                  # 工具模块
│   └── logger.py          # 日志工具
├── main.py                 # FastAPI 应用入口
├── requirements.txt        # Python 依赖
├── .env.example           # 环境变量示例
└── Dockerfile             # Docker 配置
```

## 快速开始

### 1. 安装依赖

```bash
# 激活 conda 环境
conda activate ame

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

主要配置项：
- `REDIS_URL`: Redis 连接地址
- `EMBY_URL`: Emby 服务器地址
- `EMBY_API_KEY`: Emby API 密钥
- `OPENAI_API_KEY`: OpenAI API 密钥（用于翻译）

### 3. 启动服务

```bash
# 启动 FastAPI 服务器
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 启动 Celery Worker（另一个终端）
celery -A tasks.celery_app worker --loglevel=info --pool=solo
```

### 4. 访问 API 文档

启动服务后，访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 核心功能

### 1. Emby 集成
- 连接 Emby 服务器
- 获取媒体库和媒体项
- 获取视频文件路径
- 触发元数据刷新

### 2. 音频提取
- 使用 ffmpeg 从视频中提取音频
- 转换为 WAV 格式（16kHz, 单声道）

### 3. ASR 语音识别
- 支持 sherpa-onnx 本地识别（多种模型）
- 支持云端 ASR API
- 返回带时间戳的文本片段

### 4. 翻译服务
- 支持 OpenAI GPT 翻译
- 支持 DeepSeek 翻译
- 支持本地 LLM 翻译
- 支持 Google、Microsoft、Baidu、DeepL 翻译
- 批量翻译和重试机制

### 5. 字幕生成
- 生成 SRT 格式字幕
- 自动命名和保存
- 触发 Emby 刷新

### 6. 任务管理
- 创建和管理字幕生成任务
- 实时进度更新
- 任务取消和重试
- 统计信息

### 7. 模型管理
- 下载 ASR 模型
- 激活/停用模型
- 查看模型状态

## API 端点

### 配置管理
- `GET /api/config` - 获取系统配置
- `PUT /api/config` - 更新系统配置
- `POST /api/config/test-emby` - 测试 Emby 连接
- `POST /api/config/test-translation` - 测试翻译服务
- `GET /api/config/validate` - 验证配置完整性

### 媒体库
- `GET /api/libraries` - 获取媒体库列表
- `GET /api/media` - 获取媒体项列表
- `GET /api/series/{id}/episodes` - 获取剧集列表

### 任务管理
- `POST /api/tasks` - 创建任务
- `GET /api/tasks` - 获取任务列表
- `GET /api/tasks/{task_id}` - 获取任务详情
- `POST /api/tasks/{task_id}/cancel` - 取消任务
- `POST /api/tasks/{task_id}/retry` - 重试任务

### 统计信息
- `GET /api/stats` - 获取系统统计信息

### 模型管理
- `GET /api/models` - 获取模型列表
- `POST /api/models/{model_id}/download` - 下载模型
- `POST /api/models/{model_id}/activate` - 激活模型

## 开发指南

### 添加新的服务

1. 在 `services/` 目录创建新的服务文件
2. 实现服务类和方法
3. 在 `tests/` 目录添加单元测试

### 添加新的 API 端点

1. 在 `api/` 目录创建或修改路由文件
2. 在 `main.py` 中注册路由
3. 在 `tests/` 目录添加 API 测试

### 添加新的 Celery 任务

1. 在 `tasks/` 目录添加任务函数
2. 使用 `@celery_app.task` 装饰器
3. 在 `tests/` 目录添加任务测试

## 日志

日志文件位于 `logs/subtitle_service.log`，包含：
- 所有 API 请求和响应
- 任务执行过程
- 错误和异常信息

日志配置：
- 级别：INFO
- 轮转：每天
- 保留：30 天

## 故障排查

### Redis 连接失败
确保 Redis 服务正在运行：
```bash
redis-server
```

### 数据库错误
删除数据库文件重新初始化：
```bash
rm subtitle_service.db
```

### Celery Worker 无法启动
Windows 系统使用 `--pool=solo` 参数：
```bash
celery -A tasks.celery_app worker --loglevel=info --pool=solo
```

## 相关文档

- [使用文档](docs/usage/) - 各模块的使用说明
