# Docker 构建与运行

所有命令在 **仓库根目录** 执行。

## 1. 构建镜像

```bash
# MainAgent
docker build -f mainagent/Dockerfile -t hlsc-mainagent .

# DemoPriceFinder Subagent
docker build -f subagents/demo_price_finder/Dockerfile -t hlsc-demo-price-finder .

# Web 前端
docker build -t hlsc-web web/
```

## 2. 启动容器

### MainAgent

```bash
docker run -d --name hlsc-mainagent \
  -p 8100:8100 \
  -e ACTIVE=test \
  -e DEMO_PRICE_FINDER_URL=http://<subagent-host>:8101 \
  -v $(pwd)/mainagent/.chatagent:/app/mainagent/.chatagent \
  -v $(pwd)/mainagent/logs:/app/mainagent/logs \
  -v $(pwd)/mainagent/data:/app/mainagent/data \
  hlsc-mainagent
```

### DemoPriceFinder Subagent

```bash
docker run -d --name hlsc-demo-price-finder \
  -p 8101:8101 \
  -e ACTIVE=test \
  -v $(pwd)/subagents/demo_price_finder/.chatagent:/app/subagents/demo_price_finder/.chatagent \
  -v $(pwd)/subagents/demo_price_finder/logs:/app/subagents/demo_price_finder/logs \
  -v $(pwd)/subagents/demo_price_finder/data:/app/subagents/demo_price_finder/data \
  hlsc-demo-price-finder
```

### Web 前端

```bash
docker run -d --name hlsc-web \
  -p 3100:3100 \
  hlsc-web
```

> **注意**：Web 的 nginx 配置中 `proxy_pass` 指向 `http://mainagent:8100`。
> 如果不用 Docker 网络，需要挂载自定义 nginx.conf 替换 `mainagent` 为实际 IP：
>
> ```bash
> docker run -d --name hlsc-web \
>   -p 3100:3100 \
>   -v $(pwd)/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
>   hlsc-web
> ```

## 3. 环境配置

### ACTIVE 环境变量

`ACTIVE` 决定加载哪个 `.env` 文件（由 `nacos.py` 在 import 时自动执行）：

| ACTIVE | 加载文件 | 说明 |
|--------|----------|------|
| `test` | `.env.test` → Nacos 拉取 `.env.test.nacos` 中的配置 | 测试环境 |
| `uat`  | `.env.uat` → Nacos 拉取 `.env.uat.nacos` 中的配置 | UAT 环境 |
| `local`| `.env.local`（镜像中不包含）| 本地开发，不用 Docker |

### 加载顺序

1. `server.py --env /dev/null` → 跳过 `.env.local` 加载
2. `nacos.py` import → 读取 `ACTIVE` → 加载 `.env.{ACTIVE}`
3. `nacos.py` → `get_nacos_config()` → 从 Nacos 服务端拉取完整配置写入 `os.environ`
4. 后续代码从 `os.environ` 读取所有配置

## 4. 基础设施

```bash
# Kafka（可选，仅 mainagent 异步模式需要）
docker compose -f docker/docker-compose.kafka.yml up -d
```
