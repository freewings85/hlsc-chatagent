# System Prompt 模板设计

系统提示词按关注点拆分为多个文件，由 PromptBuilder 按固定顺序拼接后传给 LLM。

## 设计参考

- **Claude Code**：按功能拆分（main → tone-and-style → doing-tasks → tool-usage-policy → task-management），每个文件职责单一
- **OpenClaw**：按抽象层次拆分（SOUL → AGENTS → TOOLS → IDENTITY → USER → MEMORY），从"我是谁"到"具体怎么做"

我们取两者之长：按层次组织，每层职责单一。

## 文件结构与拼接顺序

### 静态模板（代码内，每次请求都注入）

| 顺序 | 文件 | 层次 | 职责 | 参考来源 |
|------|------|------|------|---------|
| 1 | `identity.md` | 身份 | 我是谁、服务什么场景、核心价值观 | OpenClaw SOUL.md + Claude Code main-system-prompt |
| 2 | `behavior.md` | 行为 | 沟通风格、工作方式、专业客观性 | Claude Code tone-and-style + OpenClaw SOUL.md vibe |
| 3 | `tool-policy.md` | 工具 | 工具使用策略（并行规则、task 工具说明） | Claude Code tool-usage-policy |
| 4 | `task-management.md` | 流程 | 多步骤任务的 plan.md 跟踪机制 | Claude Code task-management |
| 5 | `skill.md` | 机制 | Skill 系统的触发和执行规则 | 自有设计 |
| 6 | `card.md` | 机制 | 卡片数据的展示规则 | 自有设计 |

### 动态内容（运行时注入，PromptBuilder 负责）

| 顺序 | 来源 | 层次 | 职责 | 参考来源 |
|------|------|------|------|---------|
| 7 | `agent.md` | 项目配置 | 业务规则、领域知识、行为覆写 | Claude Code CLAUDE.md / OpenClaw AGENTS.md |
| 8 | `memory.md` | 用户记忆 | 跨会话的用户偏好和上下文 | OpenClaw USER.md + MEMORY.md |
| 9 | system-reminder | 运行时 | Skill 列表、MCP 工具状态等 | Claude Code system-reminder |

## 设计原则

1. **从抽象到具体**：身份 → 行为 → 工具 → 流程 → 机制，越往后越具体
2. **静态与动态分离**：模板文件是代码的一部分（git 管理），动态内容来自 backend
3. **每个文件可独立理解**：不依赖其他文件的上下文，方便单独维护和测试
4. **Prompt Cache 友好**：稳定内容在前（identity/behavior 很少变），动态内容在后
5. **subagent 不注入全部**：子 agent 只用自己的简短 prompt（task.py），不继承主 agent 的系统提示词（参考 Claude Code 设计）
