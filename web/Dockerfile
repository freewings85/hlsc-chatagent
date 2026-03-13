# ============================================================
# Web 前端 Dockerfile（多阶段构建）
# Build context: web/ 目录
#   docker build -t hlsc-web web/
#
# 同一镜像通过环境变量启动不同实例：
#   BACKEND_URL  — 后端 Agent 地址（默认 http://localhost:8100）
#   LISTEN_PORT  — 监听端口（默认 3100）
# ============================================================

# --- Stage 1: Build ---
FROM node:22-slim AS build

WORKDIR /app

COPY package*.json ./

RUN --mount=type=cache,target=/root/.npm \
    npm install --registry=https://registry.npmmirror.com

COPY . .

RUN npm run build

# --- Stage 2: Serve ---
FROM nginx:alpine

# nginx 模板（envsubst 在启动时替换环境变量）
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# 复制构建产物
COPY --from=build /app/dist /usr/share/nginx/html

# 默认值：指向 mainagent
ENV BACKEND_URL=http://localhost:8100
ENV LISTEN_PORT=3100

EXPOSE 3100

# nginx:alpine 自带 docker-entrypoint 会自动对 /etc/nginx/templates/*.template
# 执行 envsubst 并输出到 /etc/nginx/conf.d/
CMD ["nginx", "-g", "daemon off;"]
