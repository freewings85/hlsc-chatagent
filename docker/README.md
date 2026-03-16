# Docker 构建与运行

所有命令在 **仓库根目录** 执行。

## 1. 构建镜像

```bash
# MainAgent
docker build -f mainagent/Dockerfile -t ${dockerimage} .

# RecommendProject Subagent
docker build -f subagents/recommend_project/Dockerfile -t ${dockerimage} .

# Web 前端（所有 Agent 共用同一镜像）
docker build -t ${dockerimage} web/
```

## 2. 启动容器

### MainAgent

```bash
docker run -d --name hlsc-mainagent \
  -p 8100:8100 \
  -e ACTIVE=test \
  -v /data/chatagent/shared/.chatagent:/app/mainagent/.chatagent \
  -v /data/chatagent/shared/data:/app/mainagent/data \
  -v /data/chatagent/mainagent/logs:/app/mainagent/logs \
  ${dockerimage}
```

### RecommendProject Subagent

```bash
docker run -d --name hlsc-recommend-project \
  -p 8105:8105 \
  -e ACTIVE=test \
  -v /data/chatagent/shared/.chatagent:/app/subagents/recommend_project/.chatagent \
  -v /data/chatagent/shared/data:/app/subagents/recommend_project/data \
  -v /data/chatagent/recommend_project/logs:/app/subagents/recommend_project/logs \
  ${dockerimage}
```

### Web 前端

同一个 `hlsc-web` 镜像通过环境变量指向不同后端。

```bash
docker run -d --name hlsc-web-mainagent \
  -p 3100:3100 \
  -e VITE_PROXY_TARGET=http://<mainagent-host>:8100 \
  -e VITE_PORT=3100 \
  ${dockerimage}
```

## 3. 环境配置

### ACTIVE 环境变量

`ACTIVE` 决定加载哪个 `.env` 文件（由 `nacos.py` 在 import 时自动执行）：

| ACTIVE | 加载文件 | 说明 |
|--------|----------|------|
| `test` | `.env.test` → Nacos 拉取配置 | 测试环境 |
| `uat`  | `.env.uat` → Nacos 拉取配置 | UAT 环境 |
| `local`| `.env.local`（镜像中不包含）| 本地开发，不用 Docker |

### 配置加载顺序

1. `nacos.py` import → 读取 `ACTIVE` → 加载 `.env.{ACTIVE}`
2. `nacos.py` → `get_nacos_config()` → 从 Nacos 服务端拉取完整配置写入 `os.environ`
3. 后续代码从 `os.environ` 读取所有配置
4. `server.py --port/--host` 命令行参数覆盖（优先级最高）

### Volume 挂载说明

| 目录 | 用途 | 必须挂载 |
|------|------|----------|
| `.chatagent/` | Agent 文件资源（fstools/skills、mcp.json） | 是（NFS 共享，或用镜像内置） |
| `data/inner/` | SDK 内部存储（消息、transcript、memory） | 是 |
| `logs/` | 运行日志 | 是 |

> **生产部署**：`.chatagent/` 和 `data/` 建议使用 NFS/PVC 共享挂载，所有 Pod 看到同一份 skills 和用户数据。详见 `doc/k8s-部署架构.md`。

## 4. 基础设施

```bash
# Kafka（可选，仅 mainagent 异步模式需要）
docker compose -f docker/docker-compose.kafka.yml up -d
```
