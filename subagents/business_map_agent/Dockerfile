# ============================================================
# BusinessMapAgent Subagent Dockerfile
# Build context: 仓库根目录（需要访问 sdk/ 和 extensions/）
#   docker build -f subagents/business_map_agent/Dockerfile -t hlsc-business-map-agent .
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

# 业务地图转换脚本和源数据（用于构建时生成 data/）
COPY extensions/business-map/convert_tree.py extensions/business-map/
COPY extensions/business-map/AllTree.yaml extensions/business-map/
COPY extensions/business-map/intent_keywords.yaml extensions/business-map/

# Subagent 依赖文件
COPY subagents/business_map_agent/pyproject.toml subagents/business_map_agent/uv.lock subagents/business_map_agent/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd subagents/business_map_agent && uv sync --no-dev --frozen \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 构建时生成业务地图数据 ----------
# 使用 uv sync 安装的 venv（含 pyyaml），避免额外 pip install
RUN cd subagents/business_map_agent && \
    uv run python ../../extensions/business-map/convert_tree.py \
    ../../extensions/business-map/AllTree.yaml ../../extensions/business-map/data

# ---------- 应用层 ----------
COPY subagents/business_map_agent/server.py subagents/business_map_agent/
COPY subagents/business_map_agent/src subagents/business_map_agent/src
COPY subagents/business_map_agent/prompts subagents/business_map_agent/prompts

# 环境配置（.env.*，由 ACTIVE 环境变量决定加载哪个）
COPY subagents/business_map_agent/.env.* subagents/business_map_agent/

# 运行时目录
RUN mkdir -p subagents/business_map_agent/.chatagent subagents/business_map_agent/logs subagents/business_map_agent/data

WORKDIR /app/subagents/business_map_agent

EXPOSE 8106

# ACTIVE 环境变量决定加载哪个 .env 文件（test/uat）
ENV ACTIVE=test

CMD ["uv", "run", "--no-sync", "python", "server.py"]
