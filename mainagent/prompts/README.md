# Prompt 设计结论（V3）

当前版本采用四层结构，不再拆分多个 policy 文件。

## 1. 设计目标

- system 层保持稳定、清晰、可维护
- agent 层只负责业务编排，不承载大段业务知识
- 业务方法论下沉到 skills / references / tool 返回
- 避免 system prompt 膨胀和规则重复

## 2. 文件分工

### 2.1 静态系统层

| 顺序 | 文件 | 职责 |
|------|------|------|
| 1 | `IDENTITY.md` | 角色身份、能力边界、平台定位 |
| 2 | `SOUL.md` | 说话风格、对话习惯、好坏表达示例 |
| 3 | `SYSTEM.md` | 稳定运行规则：安全、上下文、工具、任务、输出、主动性 |

### 2.2 动态编排层

| 顺序 | 文件 | 职责 |
|------|------|------|
| 1 | `AGENT.md` | 业务编排：当前阻塞项判断、工作流、skill 路由、subagent 使用原则 |

### 2.3 运行时注入内容

| 顺序 | 来源 | 职责 |
|------|------|------|
| 1 | 用户画像 / memory | 用户历史偏好、车辆、长期信息 |
| 2 | `request_context` | 当前请求态上下文（车型、位置等） |
| 3 | skill listing | 当前可用技能清单 |
| 4 | invoked skills | 当前会话已激活技能指令 |

## 3. 注入顺序

当前推荐顺序：

1. 静态 system：`IDENTITY -> SOUL -> SYSTEM`
2. 动态 context：`AGENT -> 用户画像/记忆 -> request_context -> skill listing/invoked skills`

## 4. 分层原则

- `IDENTITY.md` 只回答“你是谁、做什么、不做什么”
- `SOUL.md` 只回答“你怎么说话”
- `SYSTEM.md` 只回答“你怎么工作”
- `AGENT.md` 只回答“这一轮该怎么编排”

不应放进主 prompt 的内容：

- 详细业务方法论
- 长篇业务案例库
- 复杂流程图和内部编号体系
- 依赖具体 tool 名字的细碎业务细则

这些内容应下沉到 skills / references / tool API。

## 5. 与 Claude Code 的对齐结论

- `AGENT.md` 更接近 Claude Code 的 `CLAUDE.md`，但必须保持薄，不做大而全业务手册。
- `SYSTEM.md` 负责稳定规则，类似 Claude 的 system layer。
- 业务知识不堆在 system 里，而是按需通过 skill 加载。

## 6. 维护建议

- 新增稳定规则：优先改 `SYSTEM.md`
- 新增语气/表达要求：改 `SOUL.md`
- 新增身份/边界：改 `IDENTITY.md`
- 新增业务编排原则或 skill 路由：改 `AGENT.md`
- 新增业务方法论：优先新增或修改 skill，不扩写主 prompt
