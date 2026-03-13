# ============================================================
# Web 前端 Dockerfile
# Build context: web/ 目录
#   docker build -t hlsc-web web/
#
# 同一镜像通过环境变量启动不同实例：
#   VITE_PROXY_TARGET — 后端 Agent 地址（默认 http://127.0.0.1:8100）
#   VITE_PORT         — 监听端口（默认 3100）
# ============================================================
FROM node:22-slim

WORKDIR /app

COPY package*.json ./

RUN --mount=type=cache,target=/root/.npm \
    npm install --registry=https://registry.npmmirror.com

COPY . .

EXPOSE 3100

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
