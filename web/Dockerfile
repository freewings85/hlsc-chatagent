# ============================================================
# Web 前端 Dockerfile（多阶段构建）
# Build context: web/ 目录
#   docker build -t hlsc-web web/
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

# 自定义 nginx 配置（反向代理 /api /chat 到后端）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制构建产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3100

CMD ["nginx", "-g", "daemon off;"]
