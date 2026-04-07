# ========================================
# 多阶段构建：前端 + 后端合并镜像
# ========================================

# ========== Stage 1: 构建前端 ==========
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# 安装 pnpm
RUN corepack enable && corepack prepare pnpm@8.15.0 --activate

# 复制前端依赖文件
COPY frontend/package.json frontend/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install

# 复制前端源码
COPY frontend/ .

# 构建生产版本
RUN pnpm run build

# ========== Stage 2: 后端运行镜像 ==========
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY backend/requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ .

# 从前端构建阶段复制静态文件
COPY --from=frontend-builder /frontend/dist ./static

# 创建数据目录
RUN mkdir -p /data /tmp/subtitle_service

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
