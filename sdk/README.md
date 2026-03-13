# Agent SDK

通用对话 Agent 框架，基于 Pydantic AI。提供 Agent 纯逻辑层和 AgentApp 部署容器。

## 安装

```bash
uv sync
```

## 核心 API

```python
from agent_sdk import Agent, AgentApp, AgentAppConfig
from agent_sdk import StaticPromptLoader, ToolConfig, SkillConfig
```

- **Agent** — 纯逻辑层：prompt 加载、工具注册、agent loop
- **AgentApp** — 部署容器：FastAPI + SSE + A2A + Temporal interrupt

## 目录结构

```
agent_sdk/
├── agent.py              # Agent 纯逻辑层
├── agent_app.py          # AgentApp 部署容器
├── config.py             # AgentAppConfig 等配置类
├── prompt_loader.py      # PromptLoader 协议
├── _agent/               # Agent 内部实现
│   ├── loop.py           # Pydantic AI agent loop
│   ├── deps.py           # AgentDeps 依赖注入
│   ├── tools/            # 内置工具（read/edit/bash/call_interrupt 等）
│   ├── skills/           # Skill 注册和执行
│   ├── compact/          # 上下文压缩
│   ├── memory/           # 记忆服务
│   ├── message/          # 消息持久化
│   └── prompt/           # 提示词构建
├── _server/              # HTTP API（管理接口）
├── _config/              # 配置和全局单例
├── _event/               # SSE 事件模型
├── _storage/             # 存储后端（fs/sqlite/s3）
└── _utils/               # 工具函数
```

## 测试

```bash
uv run pytest tests/ -v
```
