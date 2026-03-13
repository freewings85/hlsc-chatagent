# DemoPriceFinder Subagent（参考模板）

这是一个 **示例 Subagent**，展示如何基于 Agent SDK 编写一个独立的 Subagent 服务。新建 Subagent 时，可以复制本目录作为起点。

## 功能

汽车维修项目最低价查询，支持比价和用户确认（HITL interrupt）。

## 如何参考本 Demo 编写新 Subagent

### 需要修改的文件（业务代码）

| 文件 | 说明 |
|------|------|
| `src/app.py` | Agent 工厂 — 组装 prompt_loader + tools，创建 AgentApp |
| `src/prompt_loader.py` | 提示词加载 — 指定模板文件列表 |
| `src/tools/` | 业务工具 — 实现具体功能 |
| `prompts/templates/` | 系统提示词 — markdown 文件 |
| `.env.local` | 环境配置 — 端口、Agent 名称、LLM 等 |

### 不需要修改的文件（通用模板）

| 文件 | 说明 |
|------|------|
| `server.py` | 启动入口 — 所有 Agent 完全一样，直接复制 |

### 步骤

1. 复制 `subagents/demo_price_finder/` 为 `subagents/your_agent/`
2. 修改 `.env.local` 中的 `AGENT_NAME` 和 `SERVER_PORT`
3. 编写 `prompts/templates/system.md`（系统提示词）
4. 实现 `src/tools/` 中的业务工具
5. 修改 `src/app.py` 组装 prompt_loader 和 tools
6. 修改 `pyproject.toml` 中的包名和描述
7. 在根目录 `pyproject.toml` 中添加依赖引用

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
| `AGENT_NAME` | Agent 名称 | demo-price-finder |
| `SERVER_PORT` | 服务端口 | 8101 |
| `TEMPORAL_ENABLED` | Temporal 开关 | true |

## 调用方式

- **被 MainAgent 调用**：MainAgent 的 `call_demo_price_finder` 工具通过 A2A 协议调用本服务
- **独立访问**：启动前端连接 8101 端口直接对话

## 目录结构

```
server.py                 # 启动入口（通用模板，不需要修改）
.env.local                # 本地配置
prompts/                  # 提示词模板
  templates/
    system.md             # 系统提示词
src/                      # 业务代码
  app.py                  # Agent 工厂
  prompt_loader.py        # PromptLoader 实现
  tools/                  # 业务工具
  services/               # 业务服务
```
