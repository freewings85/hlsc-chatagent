# ============================================================
# RecommendProject Subagent Dockerfile
# Build context: 仓库根目录（需要访问 sdk/）
#   docker build -f subagents/recommend_project/Dockerfile -t hlsc-recommend-project .
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
COPY subagents/recommend_project/pyproject.toml subagents/recommend_project/uv.lock subagents/recommend_project/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd subagents/recommend_project && uv sync --no-dev --frozen \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 应用层 ----------
COPY subagents/recommend_project/server.py subagents/recommend_project/
COPY subagents/recommend_project/src subagents/recommend_project/src
COPY subagents/recommend_project/prompts subagents/recommend_project/prompts

# 环境配置（.env.test/.env.uat 等，由 ACTIVE 环境变量决定加载哪个）
COPY subagents/recommend_project/.env.test subagents/recommend_project/.env.test.nacos subagents/recommend_project/
COPY subagents/recommend_project/.env.uat subagents/recommend_project/.env.uat.nacos subagents/recommend_project/

# 运行时目录（生产环境应挂载为 volume）
RUN mkdir -p subagents/recommend_project/.chatagent subagents/recommend_project/logs subagents/recommend_project/data

WORKDIR /app/subagents/recommend_project

EXPOSE 8103

ENV ACTIVE=test

CMD ["uv", "run", "python", "server.py"]
