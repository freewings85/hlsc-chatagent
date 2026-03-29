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

# 业务地图转换脚本和源数据（构建时生成 data/）
COPY extensions/business-map/convert_tree.py extensions/business-map/
COPY extensions/business-map/AllTree.yaml extensions/business-map/
COPY extensions/business-map/intent_keywords.yaml extensions/business-map/

# MainAgent 依赖文件
COPY mainagent/pyproject.toml mainagent/uv.lock mainagent/

# 安装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    cd mainagent && uv sync --no-dev --frozen \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 构建时生成业务地图数据 ----------
# 使用 uv sync 安装的 venv（含 pyyaml），避免额外 pip install
RUN cd mainagent && \
    uv run python ../extensions/business-map/convert_tree.py \
    ../extensions/business-map/AllTree.yaml ../extensions/business-map/data

# ---------- 应用层 ----------
COPY mainagent/server.py mainagent/
COPY mainagent/src mainagent/src
COPY mainagent/prompts mainagent/prompts

# 环境配置（.env.test/.env.uat 等，由 ACTIVE 环境变量决定加载哪个）
# 不拷贝 .env.local（开发用）
COPY mainagent/.env.test mainagent/.env.test.nacos mainagent/
COPY mainagent/.env.uat mainagent/.env.uat.nacos mainagent/

# 运行时目录（生产环境应挂载为 volume）
# 运行时目录（.chatagent 和 data 生产环境通过 NFS 挂载，skills 通过 Web 上传）
RUN mkdir -p mainagent/.chatagent/fstools/skills mainagent/logs mainagent/data/inner

WORKDIR /app/mainagent

EXPOSE 8100

# ACTIVE 环境变量决定加载哪个 .env 文件（test/uat）
# nacos.py 在 import 时自动读取 .env.{ACTIVE} 并从 Nacos 拉取配置
ENV ACTIVE=test

CMD ["uv", "run", "--no-sync", "python", "server.py"]
