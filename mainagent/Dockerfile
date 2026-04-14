# ============================================================
# MainAgent Dockerfile
#
# Build context: 上一级目录（含 base/ 和 chatagent/ 两个 sibling）
#   docker build -f com.celiang.hlsc.service.ai.chatagent/mainagent/Dockerfile \
#                -t hlsc-mainagent ..
#
# 前置：Jenkins 先在 workspace 上一级 git clone base（完整 clone，不要 --depth=1）
# ============================================================
FROM python:3.12-slim

# 换国内 apt 镜像（加速 apt-get install）
RUN sed -i \
    -e 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' \
    -e 's|http://security.debian.org|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
    /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

# 装 git（uv sync 要调 git 从本地 base 目录构建 wheel）
RUN apt-get update && apt-get install -y \
    procps curl net-tools git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_HTTP_TIMEOUT=600

# ---------- 依赖层 ----------
# Jenkins 在上一级 clone 的 base 源码（完整 git working tree，含 .git）
COPY com.celiang.hlsc.service.ai.base /app/base

# 把 gitlab SSH URL 重定向到容器内本地 base 目录
# extensions 间接依赖 base 的 git 源，这个重定向让 uv sync 在 Docker 里走本地路径
RUN git config --global \
    url."/app/base".insteadOf "ssh://git@git.51cjml.com:8022/ai-hlsc/com.celiang.hlsc.service.ai.base.git"

# SDK 源码（本地依赖）
COPY com.celiang.hlsc.service.ai.chatagent/sdk/pyproject.toml \
     com.celiang.hlsc.service.ai.chatagent/sdk/uv.lock \
     sdk/
COPY com.celiang.hlsc.service.ai.chatagent/sdk/agent_sdk sdk/agent_sdk

# Extensions 源码（本地依赖）
COPY com.celiang.hlsc.service.ai.chatagent/extensions/pyproject.toml extensions/
COPY com.celiang.hlsc.service.ai.chatagent/extensions/hlsc extensions/hlsc

# MainAgent 依赖文件
COPY com.celiang.hlsc.service.ai.chatagent/mainagent/pyproject.toml \
     com.celiang.hlsc.service.ai.chatagent/mainagent/uv.lock \
     mainagent/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd mainagent && uv sync --no-dev --frozen

# ---------- 应用层 ----------
COPY com.celiang.hlsc.service.ai.chatagent/mainagent/server.py mainagent/
COPY com.celiang.hlsc.service.ai.chatagent/mainagent/src mainagent/src
COPY com.celiang.hlsc.service.ai.chatagent/mainagent/prompts mainagent/prompts
COPY com.celiang.hlsc.service.ai.chatagent/mainagent/stage_config.yaml mainagent/

# 环境配置（.env.test/.env.uat 等，由 ACTIVE 环境变量决定加载哪个）
COPY com.celiang.hlsc.service.ai.chatagent/mainagent/.env.test \
     com.celiang.hlsc.service.ai.chatagent/mainagent/.env.test.nacos \
     mainagent/
COPY com.celiang.hlsc.service.ai.chatagent/mainagent/.env.uat \
     com.celiang.hlsc.service.ai.chatagent/mainagent/.env.uat.nacos \
     mainagent/

# 运行时目录（生产环境挂载为 volume）
RUN mkdir -p mainagent/.chatagent/fstools/skills mainagent/logs mainagent/data/inner

WORKDIR /app/mainagent

EXPOSE 8100

# ACTIVE 环境变量决定加载哪个 .env 文件（test/uat）
# nacos.py 在 import 时自动读取 .env.{ACTIVE} 并从 Nacos 拉取配置
ENV ACTIVE=test

CMD ["uv", "run", "--no-sync", "python", "server.py"]
