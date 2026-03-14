# SDK Backend 重构 + 初始化统一

## 问题一：backend 职责混淆

当前一个 `deps.backend` 同时服务两件事：

| 用途 | 谁用 | 隔离需求 |
|------|------|----------|
| 消息持久化、transcript、memory、skill invoked store | SDK 内部 | 按 user/session 隔离 |
| read/write/edit/bash/glob/grep 工具 | LLM agent | mainagent 要隔离，subagent 要读项目文件 |

### 解法：拆成两个 backend

| 名称 | root | 用途 |
|------|------|------|
| `inner_storage_backend` | `USER_FS_DIR`（如 `data`） | SDK 内部：消息、transcript、memory、invoked skill store |
| `fs_tools_backend` | 可配置（mainagent=`data/{user}/{session}`，subagent=`.`） | fs 工具（read/write/edit/bash 等） |

- `AGENT_FS_DIR`（`.chatagent`）保持不变：skill 文件加载、MCP 配置
- Skill 加载用 `Path.read_text()` 直接读文件，不走 backend
- Prompt 模板同理

### 触发场景

code_agent（subagent）需要 `read("apis/index.md")` 读项目文件，但当前 read 工具的 backend root 指向 `data/` 或 session 目录，读不到项目文件。

## 问题二：两条并行初始化链

`Agent.run()` 和 `run_main_agent()` 大量重复：

| 初始化步骤 | `Agent.run()` (agent.py) | `run_main_agent()` (loop.py) |
|---|---|---|
| prompt 加载 | ✅ line 175 | ✅ line 564 |
| model 构建 | ✅ line 178 | 外部传入 |
| 工具构建 | ✅ line 181 | 外部传入 |
| deps 创建 | ✅ line 187（session backend） | 外部传入 |
| compactor | ✅ line 211 | ✅ line 583 |
| skill 加载 | ✅ line 240 | ✅ line 591 |
| PreModelCallService | ✅ line 252 | ✅ line 602 |
| MCP 加载 | ✅ line 264 | ✅ line 612 |
| 历史加载 | ✅ line 271 | ✅ line 616 |

### 谁调 `run_main_agent()`

- `_server/a2a_adapter.py:154` — A2A 请求
- `_server/app.py:188,339` — HTTP `/chat/stream` 和 `/chat/async`
- `_engine/task_worker.py:95` — Kafka task worker

### 谁调 `Agent.run()`

- `agent_app.py` 通过 `_a2a_agent_factory` 间接用（但 factory 只创建 agent+deps，最终还是调 `run_main_agent`）

### 解法方向

统一为一条初始化路径。`Agent.run()` 应该是唯一入口，内部调 `run_agent_loop()`。外部调用方（A2A adapter、app.py、task_worker）不再直接调 `run_main_agent()`，改为调 `Agent.run()`。

## 待实施

- [ ] 拆分 `inner_storage_backend` 和 `fs_tools_backend`
- [ ] 统一 `Agent.run()` 和 `run_main_agent()` 为一条路径
- [ ] `_a2a_agent_factory` 的 system prompt 加载问题（当前只支持 StaticPromptLoader 的 `_prompt` 属性，TemplatePromptLoader 需要调 `_load_system_prompt()`，已临时修复）
