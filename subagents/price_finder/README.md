# PriceFinder Subagent

汽车维修项目最低价查询 Agent，支持比价和用户确认（HITL interrupt）。

## 启动

```bash
uv sync
uv run python server.py
```

默认端口 8101。

## 配置

所有配置在 `.env.local` 中，主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `SERVER_PORT` | 服务端口 | 8101 |
| `USER_FS_DIR` | 用户数据目录 | subagents/price_finder/data |
| `PROMPTS_DIR` | 提示词目录 | subagents/price_finder/prompts |
| `MEMORY_SERVICE_TYPE` | 存储实现 | fs |
| `TEMPORAL_ENABLED` | Temporal 开关 | true |

## 调用方式

- **被 MainAgent 调用**：MainAgent 的 `call_price_finder` 工具通过 A2A 协议调用本服务
- **独立访问**：启动前端连接 8101 端口直接对话

## 目录结构

```
server.py                 # 启动入口
.env.local                # 本地配置
data/                     # 用户数据（运行时生成）
logs/                     # 日志（运行时生成）
prompts/                  # 提示词模板
src/                      # 业务代码
  tools/                  # 比价工具（find_best_price）
  services/               # 业务服务
```
