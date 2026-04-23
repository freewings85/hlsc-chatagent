# ============================================================
# Auctioneer Dockerfile
# Build context: 仓库根目录（需要访问 sdk/ 和 extensions/）
#   docker build -f auctioneer/Dockerfile -t hlsc-auctioneer .
# ============================================================
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    procps curl net-tools git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_HTTP_TIMEOUT=600

# ---------- 依赖层（利用 Docker 缓存）----------
# Jenkins 在 workspace 内 clone 的 base 源码（完整 git working tree）
COPY com.celiang.hlsc.service.ai.base /app/base

RUN git config --global \
    url."/app/base".insteadOf "ssh://git@git.51cjml.com:8022/ai-hlsc/com.celiang.hlsc.service.ai.base.git"

# SDK 源码（本地依赖）
COPY sdk/pyproject.toml sdk/uv.lock sdk/
COPY sdk/agent_sdk sdk/agent_sdk

# Extensions 源码（本地依赖）
COPY extensions/pyproject.toml extensions/
COPY extensions/hlsc extensions/hlsc

# Auctioneer 依赖文件
COPY auctioneer/pyproject.toml auctioneer/uv.lock auctioneer/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd auctioneer \
    && uv lock --upgrade-package hlsc-orchestrator-protocol \
    && uv sync --no-dev \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 应用层 ----------
COPY auctioneer/server.py auctioneer/
COPY auctioneer/src auctioneer/src
COPY auctioneer/prompts auctioneer/prompts

# 环境配置（.env.test/.env.uat，由 ACTIVE 环境变量决定加载哪个）
# 不拷贝 .env.local（开发用）
COPY auctioneer/.env.test auctioneer/.env.uat auctioneer/

# 运行时目录
RUN mkdir -p auctioneer/logs

WORKDIR /app/auctioneer

EXPOSE 50306

# ACTIVE 环境变量决定加载哪个 .env 文件（test/uat）
# nacos.py 在 import 时自动读取 .env.{ACTIVE} 并从 Nacos 拉取配置
ENV ACTIVE=test

CMD ["uv", "run", "--no-sync", "python", "server.py"]
