# System Prompt 模板设计

系统提示词按关注点拆分为多个文件，由 PromptLoader 按固定顺序拼接后传给 LLM。

## 命名规范

参考 OpenClaw / Claude Code 社区规范：

- **大写 `.md`**（`IDENTITY.md`、`SOUL.md`）— 通用角色级文件，跨项目可复用的命名规范
- **小写 `.md`**（`card.md`）— 业务特有的机制文件

## 文件结构与拼接顺序

### 静态模板（每个 agent 项目自行决定内容和顺序）

| 顺序 | 文件 | 职责 | 对应 OpenClaw |
|------|------|------|--------------|
| 1 | `IDENTITY.md` | 角色声明、服务领域、职责边界 | IDENTITY.md |
| 2 | `SOUL.md` | 沟通风格、工作方式、拒绝策略 | SOUL.md |
| 3 | `TOOLS.md` | 工具使用策略、task 工具说明 | TOOLS.md |
| 4 | `TASK.md` | 多步骤任务的 plan.md 跟踪机制 | — |
| 5 | `SKILL.md` | Skill 系统的触发和执行规则 | — |
| 6 | `card.md` | 卡片数据的展示规则（业务特有） | — |

### 动态内容（运行时注入，PromptLoader 负责）

| 顺序 | 来源 | 职责 | 对应 OpenClaw |
|------|------|------|--------------|
| 7 | `AGENTS.md` | 业务规则、领域知识 | AGENTS.md |
| 8 | `MEMORY.md` | 跨会话的用户偏好和上下文 | USER.md + MEMORY.md |
| 9 | system-reminder | Skill 列表、MCP 工具状态等 | — |

## 设计原则

1. **从抽象到具体**：身份 → 人格 → 工具 → 流程 → 机制 → 业务
2. **静态与动态分离**：模板文件是代码的一部分（git 管理），动态内容来自 backend
3. **每个 agent 自主决定**：拼接哪些文件、什么顺序，由各 agent 的 `prompt_loader.py` 控制
4. **Prompt Cache 友好**：稳定内容在前（IDENTITY/SOUL 很少变），动态内容在后
5. **subagent 不注入全部**：子 agent 只用自己的简短 prompt，不继承主 agent 的系统提示词
