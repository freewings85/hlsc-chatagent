# Prompt 设计结论（V2）

本文档记录当前项目在系统提示词工程上的设计结论。目标是区分“稳定规则”和“动态业务状态”，保证可维护、可运营、可演进。

## 1. 分层原则

### 1.1 静态系统层（System Prompt 本体）

静态系统层放置低频变化、跨会话稳定的规则，直接进入 `system`。这部分是 Agent 的“长期行为宪法”。

### 1.2 动态注入层（Runtime Context）

动态注入层放置高频变化、用户级或运营级内容，不进入固定 `system prompt` 字符串，而是在运行时以 context / meta message / system-reminder 方式注入。

## 2. 文件分工

### 2.1 静态系统层文件

| 顺序 | 文件 | 职责 |
|------|------|------|
| 1 | `IDENTITY.md` | 角色身份、能力边界、服务范围 |
| 2 | `SOUL.md` | 语气风格、沟通纪律、拒绝风格（低频变化） |
| 3 | `SAFETY_POLICY.md` | 安全红线、风险处理、拒答与拉回 |
| 4 | `TOOL_POLICY.md` | 工具使用政策（先工具后结论、并行/串行原则、禁止猜测） |
| 5 | `TASK_POLICY.md` | 复杂任务推进规则（步骤化、状态更新、完成判定） |
| 6 | `OUTPUT_POLICY.md` | 输出规范（文本/卡片/spec、禁止泄露内部字段） |
| 7 | `CONTEXT_POLICY.md` | 运行时上下文消费规则（字段解释、缺失值处理原则） |

> 说明：`SOUL.md` 明确归入静态系统层，参考 Claude Code 的 tone/style 设计。

### 2.2 动态注入层内容

| 顺序 | 来源 | 职责 |
|------|------|------|
| 1 | `AGENT.md` | 业务编排核心：场景判定、流程策略、路由规则、5W+1H 执行框架 |
| 2 | `USER.md` | 用户画像（用户级） |
| 3 | `MEMORY.md` + `memory/YYYY-MM-DD.md` | 长短期记忆（用户级） |
| 4 | `request_context` | 当前请求态上下文（车辆、位置等） |
| 5 | skill listing | 当前可用技能清单 |
| 6 | invoked skills | 当前会话已激活技能指令 |

> 说明：`AGENT.md` 是运行时业务指令源，不是 system prompt 本体。

## 3. 注入顺序

推荐顺序如下：

1. 静态 system：`IDENTITY -> SOUL -> SAFETY_POLICY -> TOOL_POLICY -> TASK_POLICY -> OUTPUT_POLICY -> CONTEXT_POLICY`
2. 动态 context：`AGENT -> USER/MEMORY -> request_context -> skill listing/invoked skills`

## 4. 命名与迁移建议

为避免语义混乱，建议逐步将当前模板命名迁移为策略型命名：

| 现有文件 | 建议文件 |
|------|------|
| `TOOLS.md` | `TOOL_POLICY.md` |
| `TASK.md` | `TASK_POLICY.md` |
| `card.md` | `OUTPUT_POLICY.md` |
| `context.md` | `CONTEXT_POLICY.md` |
| `AGENTS.md` | `AGENT.md` |

并补充：

- `SAFETY_POLICY.md`（新增）

## 5. 与 Claude / OpenClaw 的对齐结论

1. `system prompt` 应尽量保持稳定，承载方法论和规则。
2. 可变信息（业务策略、记忆、技能状态）应走运行时注入，不混入固定 system 本体。
3. `SOUL.md` 作为风格规则可放静态层；`AGENT.md` 作为业务编排建议放动态层。

## 6. 后续落地范围

本结论用于指导后续两个方向：

1. 重写 `mainagent/prompts/templates/` 下各文件内容。
2. 调整 PromptLoader 拼接与动态注入逻辑（如需要）。

