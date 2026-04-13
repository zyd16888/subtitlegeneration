# Emby AI 中文字幕生成服务

自动为日语视频生成中文字幕的独立服务，支持多种 ASR 引擎和翻译服务。

## 功能特性

- 🎬 Emby 媒体库集成
- 🎵 自动音频提取（ffmpeg）
- 🗣️ 语音识别（sherpa-onnx 本地引擎 / 云端 ASR）
- 🌐 多翻译引擎（OpenAI / DeepSeek / 本地 LLM / Google / Microsoft / Baidu / DeepL）
- 📝 SRT 字幕生成
- ⚡ 异步任务处理（Celery + Redis）
- 🖥️ Web 管理界面（React + Ant Design）

## 技术栈

**后端:**
- Python 3.11+
- FastAPI
- Celery + Redis
- SQLAlchemy + SQLite
- sherpa-onnx

**前端:**
- React 18
- TypeScript
- Ant Design
- Vite

## 快速开始

### 方式 1: 使用 Docker Compose（推荐生产环境）

1. 克隆项目
```bash
git clone <repository-url>
cd emby-subtitle-generator
```

2. 配置环境变量
```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入你的配置
```

3. 启动服务
```bash
# Windows
start.bat

# Linux/Mac
./start.sh
```

4. 访问服务
- 前端: http://localhost:3000
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

### 方式 2: 本地开发（推荐开发调试）

适合本地开发和调试，不依赖 Docker，可连接外部 Redis。

详细步骤请查看 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

**快速启动：**

1. 配置环境变量
```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，配置 Redis 地址
```

2. 启动后端（终端 1）
```bash
cd backend
conda create -n ame python=3.11  # 首次创建环境
conda activate ame
pip install -r requirements.txt
uvicorn main:app --reload
```

3. 启动 Celery Worker（终端 2）
```bash
cd backend
conda activate ame
celery -A tasks.celery_app worker --loglevel=info --pool=solo
```

4. 启动前端（终端 3）
```bash
cd frontend
pnpm install
pnpm run dev
```

访问：
- 前端: http://localhost:3000
- 后端: http://localhost:8000
- API 文档: http://localhost:8000/docs

## 配置说明

### Emby 配置

在设置页面配置 Emby Server URL 和 API Key。

### ASR 引擎

支持两种 ASR 引擎：
- **sherpa-onnx**: 本地引擎，轻量快速，低配置要求
- **云端 ASR**: 需要配置 API URL 和 API Key

### 翻译服务

支持七种翻译服务：
- **OpenAI**: 需要 API Key
- **DeepSeek**: 需要 API Key
- **本地 LLM**: 需要配置 API URL
- **Google Translate**: 免费/付费 API
- **Microsoft Translator**: 需要 API Key
- **Baidu Translate**: 需要 API Key
- **DeepL**: 需要 API Key

## 使用流程

1. 在设置页面配置 Emby 和翻译服务
2. 在媒体库页面浏览视频
3. 选择需要生成字幕的视频
4. 点击"生成字幕"按钮
5. 在任务页面查看进度
6. 字幕生成后自动添加到 Emby

## 项目结构

```
.
├── backend/                    # 后端服务
│   ├── api/                   # FastAPI 路由和端点
│   ├── config/                # 配置管理
│   ├── docs/                  # 文档目录
│   │   └── usage/            # 使用文档
│   ├── logs/                  # 日志文件
│   ├── models/                # 数据库模型
│   ├── models_data/           # ASR 模型文件
│   ├── services/              # 业务逻辑服务
│   ├── tasks/                 # Celery 异步任务
│   ├── tests/                 # 测试文件
│   ├── utils/                 # 工具模块
│   ├── main.py               # FastAPI 应用入口
│   ├── requirements.txt      # Python 依赖
│   └── README.md             # 后端文档
├── frontend/                  # 前端应用
│   └── src/
│       ├── pages/            # 页面组件
│       ├── components/       # 通用组件
│       ├── services/         # API 服务
│       └── types/            # TypeScript 类型
├── docs/                      # 项目文档
├── .kiro/                     # Kiro 配置和规范
├── docker-compose.yml         # Docker 编排配置
├── start.bat / start.sh       # 启动脚本
├── stop.bat / stop.sh         # 停止脚本
└── dev-local.bat / dev-local.sh  # 本地开发脚本
```

详细的项目结构说明请查看 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## 文档

- [开发指南](docs/DEVELOPMENT.md) - 本地开发环境配置
- [部署指南](docs/DEPLOYMENT.md) - 生产环境部署
- [项目结构](docs/PROJECT_STRUCTURE.md) - 目录结构说明
- [后端文档](backend/README.md) - 后端 API 和服务说明
- [Celery 说明](docs/CELERY_EXPLAINED.md) - 异步任务处理

