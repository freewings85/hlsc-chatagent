# Extensions — 业务共享扩展

对 SDK 基础能力的业务扩展。不属于 SDK 内置，也不属于某个 agent 私有。各 agent 按需引用。

## 目录结构

```
extensions/
├── skills/          # 业务共享 skill（策略指令）
│   ├── confirm-car-model-id/
│   │   └── SKILL.md
│   └── confirm-location/
│       └── SKILL.md
└── tools/           # 业务共享 tool（API 封装）
    ├── search_projects.py
    ├── search_shops.py
    └── ...
```

## Skills vs Tools

- **Skill**：策略 — 教 LLM 在特定场景下怎么判断、怎么编排
- **Tool**：能力 — 一个具体的 API 调用或动作

## 依赖

- 依赖 `sdk`（editable），可使用 SDK 的 `call_interrupt`、`AgentDeps` 等能力
- 各 agent 通过 `pyproject.toml` 引用本包
