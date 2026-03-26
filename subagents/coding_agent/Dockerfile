# ============================================================
# CodingAgent Subagent Dockerfile
# Build context: 仓库根目录（需要访问 sdk/）
#   docker build -f subagents/coding_agent/Dockerfile -t hlsc-coding-agent .
# ============================================================
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    procps curl net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_HTTP_TIMEOUT=600

# ---------- 依赖层（利用 Docker 缓存）----------
# SDK 源码（本地依赖）
COPY sdk/pyproject.toml sdk/uv.lock sdk/
COPY sdk/agent_sdk sdk/agent_sdk

# Subagent 依赖文件
COPY subagents/coding_agent/pyproject.toml subagents/coding_agent/uv.lock subagents/coding_agent/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd subagents/coding_agent && uv sync --no-dev --frozen \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 应用层 ----------
COPY subagents/coding_agent/server.py subagents/coding_agent/
COPY subagents/coding_agent/src subagents/coding_agent/src
COPY subagents/coding_agent/prompts subagents/coding_agent/prompts
COPY subagents/coding_agent/apis subagents/coding_agent/apis

# 环境配置（.env.*，由 ACTIVE 环境变量决定加载哪个）
COPY subagents/coding_agent/.env.* subagents/coding_agent/

# 运行时目录（生产环境应挂载为 volume）
RUN mkdir -p subagents/coding_agent/.chatagent/fstools subagents/coding_agent/logs subagents/coding_agent/data

# apis 同时拷贝到 fstools 下供运行时读取
RUN cp -r subagents/coding_agent/apis subagents/coding_agent/.chatagent/fstools/apis

WORKDIR /app/subagents/coding_agent

EXPOSE 8102

ENV ACTIVE=test

CMD ["uv", "run", "python", "server.py"]
