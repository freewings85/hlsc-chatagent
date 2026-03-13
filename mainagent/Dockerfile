# ============================================================
# MainAgent Dockerfile
# Build context: 仓库根目录（需要访问 sdk/）
#   docker build -f mainagent/Dockerfile -t hlsc-mainagent .
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

# MainAgent 依赖文件
COPY mainagent/pyproject.toml mainagent/uv.lock mainagent/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd mainagent && uv sync --no-dev --frozen \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 应用层 ----------
COPY mainagent/server.py mainagent/
COPY mainagent/src mainagent/src
COPY mainagent/prompts mainagent/prompts
COPY mainagent/.env* mainagent/

# 创建运行时目录
RUN mkdir -p mainagent/.chatagent mainagent/logs mainagent/data

WORKDIR /app/mainagent

EXPOSE 8100

CMD ["uv", "run", "python", "server.py"]
