# ============================================================
# Gateway Dockerfile
# Build context: 仓库根目录
#   docker build -f gateway/Dockerfile -t hlsc-gateway .
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

# ---------- 依赖层 ----------
COPY gateway/pyproject.toml gateway/

RUN --mount=type=cache,target=/root/.cache/uv \
    cd gateway && uv sync --no-dev \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 应用层 ----------
COPY gateway/server.py gateway/
COPY gateway/app.py gateway/
COPY gateway/routes gateway/routes

WORKDIR /app/gateway

EXPOSE 9000

CMD ["uv", "run", "--no-sync", "python", "server.py"]
