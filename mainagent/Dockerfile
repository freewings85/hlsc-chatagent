# ============================================================
# MainAgent Dockerfile
#
# Build context: chatagent 项目根目录（含 com.celiang.hlsc.service.ai.base/ 子目录）
#   docker build -f mainagent/Dockerfile -t hlsc-mainagent .
#
# 前置：Jenkins 在 workspace 内部 git clone base：
#   git clone ssh://...base.git com.celiang.hlsc.service.ai.base
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
# Jenkins 在 workspace 内 clone 的 base 源码（完整 git working tree）
COPY com.celiang.hlsc.service.ai.base /app/base

# 关键：把 gitlab SSH URL 重定向到容器内本地 base 目录
# extensions 间接依赖 base 的 git 源，这个重定向让 uv sync 在 Docker 里走本地路径
RUN git config --global \
    url."/app/base".insteadOf "ssh://git@git.51cjml.com:8022/ai-hlsc/com.celiang.hlsc.service.ai.base.git"

# SDK 源码（本地依赖）
COPY sdk/pyproject.toml sdk/uv.lock sdk/
COPY sdk/agent_sdk sdk/agent_sdk

# Extensions 源码（本地依赖）
COPY extensions/pyproject.toml extensions/
COPY extensions/hlsc extensions/hlsc

# MainAgent 依赖文件
COPY mainagent/pyproject.toml mainagent/uv.lock mainagent/

# 安装依赖
# 先 upgrade base 再 sync：保证 lock 里 hlsc-orchestrator-protocol 的 git pin 永远是 base main 最新 commit。
# 否则提交者忘记本地 uv lock --upgrade，CI 会按老 sha 装 base，
# 出现 mainagent 跑老 dataclass、workflow 是新 dataclass 的字段错位（AttributeError）。
RUN --mount=type=cache,target=/root/.cache/uv \
    cd mainagent \
    && uv lock --upgrade-package hlsc-orchestrator-protocol \
    && uv sync --no-dev

# ---------- 应用层 ----------
COPY mainagent/server.py mainagent/
COPY mainagent/src mainagent/src
COPY mainagent/prompts mainagent/prompts
COPY mainagent/stage_config.yaml mainagent/

# 环境配置（.env.test/.env.uat 等，由 ACTIVE 环境变量决定加载哪个）
COPY mainagent/.env.test mainagent/.env.test.nacos mainagent/
COPY mainagent/.env.uat mainagent/.env.uat.nacos mainagent/
COPY mainagent/.env.prod mainagent/.env.prod.nacos mainagent/

# 运行时目录（生产环境挂载为 volume）
RUN mkdir -p mainagent/.chatagent/fstools/skills mainagent/logs mainagent/data/inner

WORKDIR /app/mainagent

EXPOSE 8100

# ACTIVE 环境变量决定加载哪个 .env 文件（test/uat）
ENV ACTIVE=test

CMD ["uv", "run", "--no-sync", "python", "server.py"]
