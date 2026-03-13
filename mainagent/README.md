# HLSC MainAgent

话痨说车主 Agent，基于 Agent SDK 构建。

## 启动

```bash
uv sync
uv run python server.py
```

指定配置文件或端口：

```bash
uv run python server.py --env .env.uat
uv run python server.py --port 9000
```

默认端口 8100。

## 配置

所有配置在 `.env.local` 中，主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `SERVER_PORT` | 服务端口 | 8100 |
| `USER_FS_DIR` | 用户数据目录 | mainagent/data |
| `PROMPTS_DIR` | 提示词目录 | mainagent/prompts |
| `MEMORY_SERVICE_TYPE` | 存储实现 (fs/sqlite) | sqlite |
| `TEMPORAL_ENABLED` | Temporal 开关 | true |
| `PRICE_FINDER_URL` | PriceFinder 地址 | http://localhost:8101 |

## 目录结构

```
server.py                 # 启动入口
.env.local                # 本地配置
data/                     # 用户数据（运行时生成）
logs/                     # 日志（运行时生成）
prompts/                  # 提示词模板
  templates/
src/                      # 业务代码
  app.py                  # Agent 工厂
  prompt_loader.py        # PromptLoader 实现
  hlsc_context.py         # 业务请求上下文
  hlsc_core.py            # 核心模型（CarInfo 等）
  tools/                  # 业务工具（call_price_finder 等）
  services/               # 业务服务
tests/                    # 测试
```

## 测试

```bash
uv run pytest tests/ -v
```
