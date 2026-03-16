# ============================================================
# MainAgent Dockerfile
# Build context: 仓库根目录（需要访问 sdk/ 和 extensions/）
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

# Extensions 源码（本地依赖）
COPY extensions/pyproject.toml extensions/
COPY extensions/hlsc extensions/hlsc

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

# Skills（内置到镜像，生产环境可通过 NFS 覆盖挂载）
COPY mainagent/.chatagent mainagent/.chatagent

# 环境配置（.env.test/.env.uat 等，由 ACTIVE 环境变量决定加载哪个）
# 不拷贝 .env.local（开发用）
COPY mainagent/.env.test mainagent/.env.test.nacos mainagent/
COPY mainagent/.env.uat mainagent/.env.uat.nacos mainagent/

# 运行时目录（生产环境应挂载为 volume）
RUN mkdir -p mainagent/logs mainagent/data/inner

WORKDIR /app/mainagent

EXPOSE 8100

# ACTIVE 环境变量决定加载哪个 .env 文件（test/uat）
# nacos.py 在 import 时自动读取 .env.{ACTIVE} 并从 Nacos 拉取配置
ENV ACTIVE=test

CMD ["uv", "run", "python", "server.py"]
