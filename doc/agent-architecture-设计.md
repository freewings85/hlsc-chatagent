# Agent 架构设计

## 三层能力体系

| 层 | 是什么 | 谁决定流程 | 适用场景 |
|---|---|---|---|
| Tool | LLM 调的一个函数 | LLM 自己编排 | 单次 API 调用 |
| Skill | 注入给 LLM 的策略指令 | Skill 脚本指导，LLM 灵活执行 | 需要引导策略的场景 |
| Subagent | 独立的 agent 进程 | Subagent 自己 | 需要独立知识库或工具集 |

### 判断标准

- **Tool**：封装一个 API/能力，LLM 决定何时调、调几次、怎么组合
- **Skill**：教 LLM 在特定场景下的策略（什么时候追问、什么时候直接查、什么时候推荐）
- **Subagent**：满足以下任一条件：
  - 有独立知识库（诊断知识库、API 文档）
  - 中间过程用户不需要看到（只返回最终结论）
  - 需要独立执行环境（k8s Pod）

## 目录结构

```
com.celiang.hlsc.service.ai.chatagent/
├── sdk/                  # 框架（read/write/bash/interrupt 等内置工具）
├── commontools/          # 业务共享工具（search_projects/search_shops 等）
├── mainagent/            # 主 Agent
├── subagents/
│   ├── code_agent/       # 复杂数据查询（API 文档 + 编程执行 + k8s）
│   └── diagnose_agent/   # 故障诊断（诊断知识库 + 多轮推理）
├── web/                  # 前端
└── deploy/               # 部署配置
```

## 业务场景映射

### "我想洗个车" → skill + tool

**第一轮**：
1. Skill（项目定位引导）指导 LLM 判断意图
2. LLM 调 `search_projects("洗车")` → 返回 [普洗, 精洗]
3. 展示 ProjectCard，"您想要哪种？"

**第二轮**：
1. 用户选"普洗"
2. LLM 调 `search_shops(普洗id, lat, lng)` → 返回门店列表
3. 展示 ShopCard，"需要预约吗？"

### "帮我找补胎和四轮定位一起做的商家" → tool

1. LLM 调 `search_projects("补胎")` + `search_projects("四轮定位")` → 得到两个 projectId
2. LLM 调 `search_shops([补胎id, 定位id], lat, lng)` → 返回同时能做两个项目的门店
3. 展示 ShopCard（含 items 明细 + 合计价格）

### "车子抖是什么问题" → subagent

1. mainagent 调 `call_subagent(diagnose_agent, "车子抖")`
2. diagnose_agent 内部：查知识库 → 多轮推理 → 排除法
3. 返回最终结论："可能是四轮定位或轮胎动平衡问题"
4. mainagent 展示结论 + 推荐相关项目

### 复杂数据查询 → subagent

1. mainagent 调 `call_subagent(code_agent, "张三上月工单总金额")`
2. code_agent 内部：读 API 文档 → 写代码 → k8s 执行
3. 返回查询结果

## 卡片体系（5 种）

| 卡片 | 形态 | 场景 |
|------|------|------|
| RecommendCard | 圆盘/宫格 | 推荐浏览（"有什么服务"） |
| ProjectCard | 列表 | 搜索结果（普洗/精洗） |
| ShopCard | 列表 | 门店选择（含单/多项目价格） |
| AppointmentCard | 单卡 | 确认预约 |
| CouponCard | 单卡 | 优惠信息 |

按**用户决策阶段**划分，不是按数据类型。

## Skill 设计原则

Skill 不是固定剧本，是**策略指令**。可以包含场景判断逻辑：

```markdown
# 项目定位 Skill

## 场景判断
- 意图明确（"洗车"）→ 直接调 search_projects
- 意图模糊（"车子抖"）→ 追问 1 个关键问题后再搜
- 浏览（"有什么服务"）→ RecommendCard

## 规则
- 最多追问 1 轮
- 追问时同时给出可能选项
```

## commontools vs SDK tools vs MCP

| | SDK tools | commontools | MCP |
|---|---|---|---|
| 位置 | `sdk/agent_sdk/_agent/tools/` | `commontools/` | 独立进程 |
| 性质 | 框架能力 | 业务共享 | 跨项目/跨语言 |
| 例子 | read/write/bash | search_projects/search_shops | 浏览器操作、外部 SaaS |
| 引用方式 | SDK 内置 | editable 依赖 | MCP 协议连接 |
