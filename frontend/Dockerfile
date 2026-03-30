FROM node:20-alpine

# 安装 pnpm
RUN corepack enable && corepack prepare pnpm@8.15.0 --activate

# 设置工作目录
WORKDIR /app

# 复制 package.json 和 pnpm-lock.yaml
COPY package.json pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install --frozen-lockfile

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 3000

# 启动开发服务器
CMD ["pnpm", "run", "dev", "--", "--host", "0.0.0.0"]
