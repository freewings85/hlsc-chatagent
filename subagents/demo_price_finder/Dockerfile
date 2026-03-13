# ============================================================
# DemoPriceFinder Subagent Dockerfile
# Build context: 仓库根目录（需要访问 sdk/）
#   docker build -f subagents/demo_price_finder/Dockerfile -t hlsc-demo-price-finder .
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
COPY subagents/demo_price_finder/pyproject.toml subagents/demo_price_finder/uv.lock subagents/demo_price_finder/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd subagents/demo_price_finder && uv sync --no-dev --frozen \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 应用层 ----------
COPY subagents/demo_price_finder/server.py subagents/demo_price_finder/
COPY subagents/demo_price_finder/src subagents/demo_price_finder/src
COPY subagents/demo_price_finder/prompts subagents/demo_price_finder/prompts
COPY subagents/demo_price_finder/.env* subagents/demo_price_finder/

# 创建运行时目录
RUN mkdir -p subagents/demo_price_finder/.chatagent subagents/demo_price_finder/logs subagents/demo_price_finder/data

WORKDIR /app/subagents/demo_price_finder

EXPOSE 8101

CMD ["uv", "run", "python", "server.py"]
