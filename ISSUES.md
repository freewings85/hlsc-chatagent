# ChatAgent 全项目审查问题清单

审查时间：2026-04-05
审查角色：架构师、提示词专家、挑战者、场景设计师、测试

---

## P0 — 必须修复

### P0-1: interrupt 无超时，session 假死+内存泄漏
- **发现者**: 挑战者
- **文件**: sdk/agent_sdk/_agent/interrupt.py:53-71
- **描述**: 内存模式下 `await event.wait()` 没有超时。用户关浏览器后 agent loop 永久挂起，_running_tasks 不释放
- **影响**: 内存泄漏 + session 假死
- **状态**: ✅ 已修复（commit 1629429）

### P0-2: BMA 每轮重分类，多轮业务流程断裂
- **发现者**: 挑战者
- **文件**: mainagent/src/business_map_hook.py:196-229
- **描述**: StageHook 每个请求都重新调 BMA /classify。用户说"好的"可能被重分类到 guide，前序收集的条件和工具集全变
- **影响**: 核心业务流程断裂
- **状态**: 待修复

### P0-3: 同 session 并发请求无锁保护
- **发现者**: 挑战者
- **文件**: sdk/agent_sdk/agent_app.py
- **描述**: /chat/stream 没有 per-session 锁，并发请求会导致 session_state 和消息历史互相覆盖
- **影响**: 数据竞争和丢失
- **状态**: 待修复

### P0-4: "洗车"等纯工时项目路由黑洞
- **发现者**: 提示词专家
- **文件**: BMA SYSTEM.md + guide/AGENT.md
- **描述**: BMA 规则"洗车不走 platform"返回空 → guide，但 guide 没有业务工具，用户卡死
- **影响**: 核心用户路径阻塞
- **状态**: 待修复

### P0-5: classify_project vs match_project 混用
- **发现者**: 提示词专家
- **文件**: searchshops/AGENT.md + saving-playbook/项目确认.md
- **描述**: searchshops 配了 classify_project 但 skill reference 引导用 match_project，LLM 可能调不存在的工具
- **影响**: 工具调用失败
- **状态**: 待修复

### P0-6: summarize_fn 用同一 agent 做摘要可能触发工具
- **发现者**: 架构师
- **文件**: sdk/agent_sdk/_agent/loop.py:181-191
- **描述**: compact 摘要用带 DynamicToolset 的 agent.run()，LLM 可能触发工具且 deps 为空值
- **影响**: compact 时崩溃或副作用
- **状态**: 待修复

### P0-7: _extract_recent_turns 类型错配
- **发现者**: 架构师
- **文件**: mainagent/src/business_map_hook.py:44-62
- **描述**: 尝试访问 AgentMessage 的 .parts 属性（不存在），部分消息被静默跳过，BMA 上下文不完整
- **影响**: BMA 分类精度受损
- **状态**: 待修复

### P0-8: saving-methods skill 可能不存在
- **发现者**: 提示词专家
- **文件**: searchcoupons/AGENT.md + guide/AGENT.md
- **描述**: 两个场景引用 saving-methods skill，但未确认 extensions/skills/saving-methods/ 目录是否存在
- **影响**: skill 读取失败
- **状态**: 待确认

---

## P1 — 建议尽快修复

### P1-1: delegate 子 agent session_state 单向复制
- **发现者**: 挑战者
- **文件**: extensions/hlsc/tools/delegate.py:206
- **描述**: 子 agent 的 update_session_state 不回传给父 orchestrator
- **状态**: 待修复

### P1-2: 价格查询工具不存在
- **发现者**: 架构师 + 提示词专家
- **文件**: saving-playbook/references/价格与优惠.md
- **描述**: confirm_booking 的 price 参数无可靠数据源，脚本 [待实现]
- **状态**: 待修复

### P1-3: token 估算中文偏差大
- **发现者**: 挑战者
- **文件**: sdk/agent_sdk/_agent/compact/token_counter.py:20
- **描述**: _CHARS_PER_TOKEN=4，中文实际约 1.5-2，compact 触发太晚
- **状态**: 待修复

### P1-4: 4 个 AGENT.md 结构不统一
- **发现者**: 提示词专家
- **描述**: guide 缺失败处理/路径偏离，searchshops/searchcoupons 缺独立失败处理段
- **状态**: 待修复

### P1-5: 项目确认多匹配处理三处矛盾
- **发现者**: 提示词专家
- **文件**: 项目确认.md vs platform/AGENT.md vs match_project.md
- **描述**: "直接选最常见" vs "列出让用户选" vs "能推断就直接选"
- **状态**: 待修复

### P1-6: update_session_state 代码签名 vs prompt 中 addresses 结构不一致
- **发现者**: 提示词专家
- **文件**: update_session_state.py Field description vs .md prompt
- **描述**: 代码写 latitude/longitude/name，prompt 只写 name
- **状态**: 待修复

### P1-7: delegate 子 agent 不加载 skill references
- **发现者**: 架构师
- **文件**: extensions/hlsc/tools/delegate.py:158-165
- **描述**: 子 agent StaticPromptLoader 不支持 skill 文件系统
- **状态**: ✅ 确认无问题 — 子 agent 共享父 fs_tools_backend，skill_registry 从同目录自动加载

### P1-8: prompt_loader _TEMPLATES_DIR 相对路径依赖 CWD
- **发现者**: 架构师
- **文件**: mainagent/src/prompt_loader.py:21
- **状态**: 待修复

### P1-9: stage_config.yaml 三处独立解析无统一管理
- **发现者**: 架构师
- **文件**: business_map_hook.py + prompt_loader.py + delegate.py
- **状态**: 待修复

### P1-10: insurance 场景 bash 工具隐式依赖 SDK 内置
- **发现者**: 架构师
- **文件**: stage_config.yaml:73 + app.py
- **状态**: 待修复

### P1-11: 商户选择.md "复杂查询 [待实现]" 但 coding agent 已接入
- **发现者**: 提示词专家
- **文件**: saving-playbook/references/商户选择.md:43
- **状态**: 待修复

### P1-12: bidding 模式无 prompt 入口
- **发现者**: 提示词专家
- **文件**: confirm_booking PlanMode vs 预订下单.md
- **描述**: 代码支持 bidding 但没有场景描述触发条件
- **状态**: 待修复

### P1-13: create_contact_order prompt 缺 shop_name 参数
- **发现者**: 提示词专家
- **文件**: create_contact_order.md
- **状态**: 待修复

### P1-14: guide 场景是死胡同
- **发现者**: 挑战者
- **描述**: guide 只有 list_user_cars + update_session_state，无法推进任何业务
- **状态**: ✅ 确认无问题 — guide 负责引导分流，BMA 小模型负责意图识别路由到业务场景，不是死胡同

### P1-15: orchestrator delegate 并行时 SSE 事件混乱
- **发现者**: 挑战者
- **文件**: extensions/hlsc/tools/delegate.py:185-198
- **描述**: 多个子 agent 共享 emitter，TEXT 事件交错
- **状态**: 待修复

---

## P2 — 改进建议

### P2-1: session_state 无大小限制和 schema 约束
### P2-2: address_resolver 每次创建新 httpx.AsyncClient
### P2-3: guide 缺 classify_project 工具（多一轮延迟）
### P2-4: orchestrator 串行编排无框架级保障
### P2-5: session_state shallow merge 可能丢数据
### P2-6: coupon_ids 默认值用 mutable []
### P2-7: DEBUG 日志用 log_info 级别
### P2-8: 术语不一致（项目/project, packageId/projectId）
### P2-9: AGENT.md 与 tool prompt 重复 address 参数描述
### P2-10: BMA 规则缺编号 9
### P2-11: Temporal workflow task_timeout 默认 10 秒太短
### P2-12: 两套 FastAPI 应用定义逻辑重复
