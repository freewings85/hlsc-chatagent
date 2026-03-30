# 业务地图设计方案：基于决策树的场景驱动对话管理

## 1. 核心概念

本方案采用**决策树（Decision Tree）**作为对话管理的核心结构。决策树是业界成熟的决策模型，广泛应用于客服系统、推荐引擎、医疗诊断等领域。在对话系统中，它用于将用户的当前状态和意图映射到最合适的处理场景。

与传统的意图分类或状态机不同，决策树的优势在于：
- **确定性**：给定相同输入，必然得到相同场景，可测试、可复现
- **可解释性**：每个决策都有明确的条件路径，出问题一眼看出走错了哪一步
- **可扩展性**：新增场景只需在树上加分支，不影响已有路径
- **混合判断**：同一棵树中可以混合使用确定性条件（槽位状态）和 AI 判断（意图标签）

## 2. 整体架构

```
用户消息
    │
    ▼
┌─────────────────────────────────────────────────┐
│  SceneOrchestrator（每轮请求前执行）               │
│                                                  │
│  ① 读取 SlotState（已收集了哪些信息）              │
│  ② 构建全部因子：                                  │
│     → slot 因子：从 SlotState 直读（零成本）        │
│     → 关键词因子：字符串匹配（零成本）              │
│     → BMA 因子：每轮全量调一次小模型求值             │
│  ③ 走完决策树 → 输出场景 ID                        │
│  ④ 加载场景配置（goal/tools/strategy）             │
│  ⑤ 设置 MainAgent 可用工具/Skill 列表（硬约束）    │
│  ⑥ 注入上下文（场景 + 槽位状态 + 策略）            │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  MainAgent（大模型）                              │
│                                                  │
│  在场景约束下与用户对话                             │
│  只能调用当前场景允许的工具/Skill                    │
│  按 strategy 指引的方式沟通                        │
│  通过 update_slots 更新槽位状态                     │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  下轮请求                                         │
│                                                  │
│  SlotState 已被 update_slots 更新                 │
│  决策树自动重新求值 → 路由到正确场景                 │
└─────────────────────────────────────────────────┘
```

## 3. 四大组件

### 3.1 BMA（意图标签提取器）

角色：小模型（gpt-4.1-mini），**每轮调用一次**，输出一组标签（bool + enum 混合）。

不做场景分类，不做导航，只回答标签判断问题。场景分类由决策树完成。

```
输入：用户消息 + 对话上下文摘要 + SlotState 摘要
输出：一组标签值（bool + enum 混合 JSON）
```

标签分为两类：

**bool 型标签**（yes/no 判断）：

| 标签 | 含义 |
|------|------|
| has_car_service | 涉及养车、保养、维修、车辆问题 |
| has_platform_question | 问平台是什么、九折怎么回事 |

**enum 型标签**（从枚举值中选一个）：

| 标签 | 选项 | 含义 |
|------|------|------|
| project_category | 保险/轮胎/机油保养/钣喷/洗车/检测/模糊/症状/无 | 用户提到的养车项目大类 |
| expression_clarity | specific/vague/symptom | 用户表达的具体程度 |
| secondary_category | 保险/轮胎/机油保养/钣喷/洗车/检测/无 | 次要项目大类 |

标签可按需扩展，每增加一个标签就是在 BMA prompt 中加一行问题。

BMA 一次调用同时回答 bool 和 enum 问题：

```json
{
  "has_car_service": true,
  "project_category": "轮胎",
  "expression_clarity": "specific",
  "secondary_category": null
}
```

### 3.2 决策树（Decision Tree）

#### 定义

决策树是一棵**有根节点的多层树**，用于将用户当前状态映射到具体的处理场景。

```
根节点（Root）
├── 条件节点（内部节点）
│   ├── 条件节点
│   │   ├── 叶节点 → 场景 A
│   │   └── 叶节点 → 场景 B
│   └── 叶节点 → 场景 C
├── 条件节点
│   └── ...
└── 叶节点 → 兜底场景
```

树中只有两种节点类型：

| 节点类型 | 作用 | 包含内容 |
|---------|------|---------|
| **条件节点**（内部节点） | 根据决策因子分流 | `if` 条件 + `children` 子节点列表 |
| **叶节点**（终端节点） | 确定处理场景 | `scene` 场景 ID |

#### 求值规则

1. 从根节点开始，按子节点**从上到下**依次匹配
2. 遇到条件节点：求值 `if` 条件
   - 命中 → 如果有 `scene` 则返回；如果有 `children` 则进入子树继续匹配
   - 未命中 → 跳过，看同层下一个节点
3. 遇到无条件的叶节点 → 直接返回（作为该层的兜底）
4. 条件求值按因子类型分层（详见"决策因子"章节）

#### 条件来源

条件中的决策因子有两类来源：
- **SlotState 条件**（确定性，零成本）：`slot.project_id != null`
- **Intent 条件**（AI 判断，BMA 提供）：`intent.has_car_service == true`

#### 树定义文件

决策树定义在 `extensions/business-map/scene_config.yaml` 的 `tree` 字段中。

**核心设计：intent 优先结构。** 先按当前用户意图路由，只有"无明确意图"时才按 slot 状态推进流程。这样即使用户在对话中途改变想法，BMA 识别出新意图后决策树自然路由到正确场景，无需专门的"意图变更"检测。

```yaml
tree:
  # 1. 紧急
  - if: intent.has_urgent
    scene: URGENT

  # 2. 有明确养车意图 → 按意图路由（不管 slot 有没有值）
  - if: intent.has_car_service
    children:
      - if: intent.project_category == "保险"
        scene: INSURANCE_PROJECT
      - if: intent.project_category == "症状"
        scene: SYMPTOM_DIAGNOSE
      - if: intent.expression_clarity == "specific"
        scene: DIRECT_PROJECT
      - if: intent.expression_clarity == "symptom"
        scene: SYMPTOM_DIAGNOSE
      - scene: FUZZY_PROJECT

  # 3. 问平台
  - if: intent.has_platform_question
    scene: PLATFORM_INQUIRY

  # 4. 没有明确意图 → 按 slot 状态推进
  - if: slot.project_id AND slot.saving_plan_type
    children:
      - if: NOT slot.merchant
        scene: FIND_MERCHANT
      - if: NOT slot.booking_time
        scene: CONFIRM_BOOKING
      - scene: COMPLETED

  - if: slot.project_id
    scene: SAVING_PLAN

  # 5. 兜底
  - scene: CASUAL_CHAT
```

求值逻辑：从上到下遍历，第一个命中的 `if` 进入其子树或返回 scene。子树内部同样从上到下。未命中任何条件时走最后的无条件 scene（兜底）。

**关键点**：intent 分支在 slot 分支之前。当用户说"还是换个轮胎吧"，BMA 识别出 `has_car_service=true`、`project_category=轮胎`，决策树优先走 intent 分支路由到正确场景，不会因为 slot 已有值而走错。

#### 决策因子（Decision Factor）

决策树每个节点的 `if` 条件依赖**决策因子**。因子分为两大类：

**槽位因子（Slot Factor）**：从 SlotState 直读，零成本，确定性，可累积。
**模型因子（Model Factor）**：需要 AI 或规则判断，每轮全量求值。

求值策略的核心原则：
1. **每轮全量求值**：slot 因子 + 关键词因子 + BMA 因子，一次性构建完整因子集
2. **BMA 每轮调用**：每轮全量收集所有 BMA 因子（bool + enum），一次调用批量求值
3. **用全部因子走完决策树** → 命中叶节点（场景 ID）
4. **场景内部的细分交给 skill 和工具处理**，不在决策树层面拆分

##### 槽位因子

从 SlotState 直读，零成本。随着对话推进，slot 不断被填充。当用户没有表达新意图时（BMA 判定 `has_car_service=false`），决策树跳过 intent 分支，仅靠 slot 因子就能到达正确的叶节点。

```yaml
# 槽位因子示例
slot.project_id         # 养车项目是否已确认
slot.saving_plan_type   # 省钱方案是否已选定
slot.merchant           # 商户是否已选定
slot.booking_time       # 预约时间是否已确认
```

##### 模型因子

模型因子按求值成本分两层：

| 层级 | 求值方式 | 成本 | 适用场景 |
|------|---------|------|---------|
| 关键词匹配 | 字符串匹配 | 零 | 明确的信号词（抛锚、事故、冒烟） |
| BMA 语义判断 | 小模型一次调用 | 低 | 需要理解语义（是否涉及养车、项目大类） |

关键词因子配置在 `scene_config.yaml` 的 `meta.factors.keyword_factors` 中：

```yaml
# 关键词因子（不需要 AI，字符串匹配即可）
keyword_factors:
  - name: intent.has_urgent
    keywords: [抛锚, 事故, 打不着火, 冒烟, 漏油严重]
```

BMA 语义因子配置在 `meta.factors.bma_factors` 中，支持两种值类型：

**bool 型**（yes/no 判断）：
```yaml
bma_factors:
  bool:
    - name: intent.has_car_service
      description: 用户消息是否涉及养车、保养、维修、车辆问题
    - name: intent.has_platform_question
      description: 用户是否在询问平台能力或九折机制
```

**enum 型**（从枚举值中选一个）：
```yaml
  enum:
    - name: intent.project_category
      description: 用户提到的养车项目大类
      options: [保险, 轮胎, 机油保养, 钣喷, 洗车, 检测, 模糊, 症状, 无]
    - name: intent.expression_clarity
      description: 用户表达的具体程度
      options: [specific, vague, symptom]
    - name: intent.secondary_category
      description: 次要项目大类（用户同时提到多个项目时）
      options: [保险, 轮胎, 机油保养, 钣喷, 洗车, 检测, 无]
```

BMA 一次调用同时回答 bool 和 enum 问题：

```json
{
  "has_car_service": true,
  "project_category": "轮胎",
  "expression_clarity": "specific",
  "secondary_category": null
}
```

##### 因子求值总结

```
每轮对话（全量求值）：
  ① slot 因子：从 SlotState 直读（零成本）
  ② 关键词因子：字符串匹配（零成本）
  ③ BMA 因子：每轮全量调一次小模型（bool + enum 混合，~2s）
  ④ 走完决策树 → 命中叶节点
```

**设计取舍**：当前方案每轮都调 BMA，换取实现简单和路由准确。intent 优先的决策树结构依赖每轮的 BMA 判断来正确处理意图变更场景。

> **Phase 2 优化**：当延迟不可接受时，可引入 Semantic Router 作为前置快速匹配层，80%+ 高频消息在亚毫秒内完成路由，BMA 只处理低置信度的 20%。详见第 8 章。

##### 决策树拆分原则

决策树只在**工具或策略不同**时拆场景。同类项目内部的细分（如轮胎下的换轮胎/补胎/动平衡）交给场景内部的 skill 和 match_project 工具处理。

```
✅ 决策树拆的（处理方式不同）：
  保险项目 → 需要保险专用工具、走理赔流程
  轮胎项目 → 需要 match_project、走常规流程
  症状描述 → 需要 diagnose-car、走诊断流程

❌ 决策树不拆的（处理方式相同，只是内容不同）：
  换轮胎 vs 补胎 vs 动平衡
  → 都用 match_project，都走确认流程
  → 合并为一个"轮胎项目"场景，内部由 skill 处理
```

### 3.3 场景配置（Scenes）

#### 节点定义

决策树中有两种节点——**条件节点**和**叶节点**，场景配置中定义的是叶节点指向的**场景**。

##### 条件节点（scene_config.yaml tree 字段）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `if` | string | 条件节点必填 | 条件表达式 |
| `scene` | string | 叶节点必填 | 场景 ID，指向 scenes 定义 |
| `children` | list | 分支节点必填 | 子节点列表 |
| `label` | string | 可选 | 调试标签，用于日志 |

三种写法互斥：

```yaml
# 叶节点：if + scene
- if: "slot.project_id AND NOT slot.saving_plan_type"
  scene: SAVING_PLAN
  label: 项目已确认待省钱方案

# 分支节点：if + children
- if: "NOT slot.project_id AND intent.has_car_service"
  label: 有养车意图分流
  children:
    - if: "intent.project_category == '轮胎'"
      scene: TIRE_PROJECT
    - scene: FUZZY_PROJECT

# 兜底节点：只有 scene（必须是同级最后一个）
- scene: CASUAL_CHAT
```

条件表达式语法：

```yaml
# 槽位因子
slot.project_id                              # 有值
NOT slot.project_id                          # 无值
slot.project_id AND slot.saving_plan_type    # 组合

# 模型因子（bool）
intent.has_car_service                       # == true
NOT intent.has_car_service                   # == false

# 模型因子（分类）
intent.project_category == "轮胎"

# 混合
NOT slot.project_id AND intent.has_car_service
```

运算符：`AND`、`OR`、`NOT`，优先级 `NOT > AND > OR`。

##### 场景节点（scene_config.yaml scenes 字段）

| 字段 | 类型 | 必填 | 消费方 | 说明 |
|------|------|------|--------|------|
| `id` | string | 是 | 代码 | 唯一标识，决策树叶节点引用 |
| `name` | string | 是 | 代码+LLM | 人类可读名称 |
| `stage` | string | 是 | 代码 | S1 / S2 / any |
| `goal` | string | 是 | LLM | 本场景的目标描述（自然语言） |
| `target_slots` | dict | 是 | 代码+LLM | 每个槽位的标签、必填性、收集方法 |
| `tools` | list[string] | 是 | 代码 | 可用工具列表（硬约束，不含连字符的函数工具） |
| `skills` | list[string] | 是 | 代码 | 可用 Skill 列表（含连字符的子 Agent 能力） |
| `exit_when` | string | 是 | 代码 | 退出条件（与条件节点相同的表达式语法） |
| `strategy` | string | 是 | LLM | 自然语言沟通策略 |

`next` 不需要定义——退出后由决策树重新求值自动确定下一个场景，场景之间解耦。

`target_slots` 是 dict 结构，每个槽位包含标签、必填性和收集方法：

```yaml
target_slots:
  project_id:
    label: 养车项目ID
    required: true
    method: 调用 match_project 将用户描述匹配到标准项目
  project_name:
    label: 养车项目名称
    required: true
    method: 从 match_project 结果中获取
  vehicle_info:
    label: 车型信息
    required: conditional
    condition: match_project 返回的项目需要车型时
    method: 调用 ask_user_car_info 引导用户提供
```

三层配合：
- `goal` 给 LLM 全局理解（这个场景要达成什么）
- `target_slots.method` 告诉 LLM 每个信息怎么拿
- `strategy` 告诉 LLM 整体沟通方式

#### 注入 LLM 的效果

SceneOrchestrator 自动将场景配置 + SlotState 拼装成 LLM 上下文：

```
[当前场景] 直接表达项目
[目标] 把用户说出的项目名匹配到标准项目，确认后获取项目ID
[待收集信息]
  养车项目ID: (待收集) — 调用 match_project 匹配
  养车项目名称: (待收集) — 从匹配结果获取
  车型信息: 2021款大众朗逸 — 已有
[可用工具] match_project, ask_user_car_info
[策略] 用户已说出项目名，直接匹配确认。不要追问不必要的细节。
```

#### 场景定义文件

场景定义在 `extensions/business-map/scene_config.yaml` 的 `scenes` 字段中：

```yaml
stages:
  S1:
    name: 初步建立
    description: 确认养车项目和省钱方案
    slots:
      project_id: { required: true, label: 养车项目ID }
      project_name: { required: true, label: 养车项目名称 }
      vehicle_info: { required: conditional, label: 车型信息 }
      saving_plan_type: { required: true, label: 省钱方案类型 }

  S2:
    name: 执行落地
    description: 确认商户和时间，完成预订
    slots:
      merchant: { required: true, label: 选定商户 }
      location: { required: conditional, label: 用户位置 }
      booking_time: { required: true, label: 预约时间 }

scenes:

  # ── 跨阶段 ──

  URGENT:
    name: 紧急救援
    stage: any
    goal: 快速响应紧急情况，帮用户解决当前问题
    target_slots: {}
    tools: [search_shops]
    exit_when: 用户问题已处理
    strategy: |
      优先解决紧急问题，跳过省钱流程。
      帮用户找最近的店或叫救援。

  # ── S1 场景 ──

  CASUAL_CHAT:
    name: 闲聊
    stage: S1
    goal: 在自然交流中引导用户发现养车需求
    target_slots: {}
    tools: [platform-intro]
    exit_when: 用户提到养车相关话题
    strategy: |
      正常交流，每 2-3 轮穿插一次平台价值引导。
      不追问，等用户自己提起养车话题。

  PLATFORM_INQUIRY:
    name: 了解平台
    stage: S1
    goal: 建立平台认知，引导到养车需求
    target_slots: {}
    tools: [platform-intro]
    exit_when: 用户了解平台或提出项目需求
    strategy: |
      介绍平台能力和九折机制。
      介绍完自然过渡到需求询问。

  DIRECT_PROJECT:
    name: 直接表达项目
    stage: S1
    goal: 把用户说出的项目名匹配到标准项目，确认后获取项目ID
    target_slots:
      project_id:
        label: 养车项目ID
        required: true
        method: 调用 match_project 将用户描述匹配到标准项目
      project_name:
        label: 养车项目名称
        required: true
        method: 从 match_project 结果中获取
      vehicle_info:
        label: 车型信息
        required: conditional
        condition: match_project 返回的项目需要车型时
        method: 调用 ask_user_car_info 引导用户提供
    tools: [match_project, ask_user_car_info]
    exit_when: "slot.project_id"
    strategy: |
      用户已说出项目名，直接用 match_project 匹配确认。
      确认后询问车型（如需要）。
      不要追问不必要的细节。

  SYMPTOM_DIAGNOSE:
    name: 症状描述
    stage: S1
    goal: 根据用户描述的症状推断可能的养车项目
    target_slots:
      project_id:
        label: 养车项目ID
        required: true
        method: 调用 diagnose-car 分析症状，再用 match_project 匹配项目
      project_name:
        label: 养车项目名称
        required: true
        method: 从诊断和匹配结果中获取
    tools: [diagnose-car, knowledge_base_search, match_project]
    exit_when: "slot.project_id"
    strategy: |
      根据症状推断可能的项目。
      最多追问 2 轮细化症状描述。
      收束不了就建议到店检查。

  LIFECYCLE_PROJECT:
    name: 按生命周期沟通
    stage: S1
    goal: 根据车辆里程和保养历史推荐应做的养车项目
    target_slots:
      project_id:
        label: 养车项目ID
        required: true
        method: 结合车型和里程用 match_project 推荐项目
      project_name:
        label: 养车项目名称
        required: true
        method: 从推荐结果中获取
      vehicle_info:
        label: 车型信息
        required: true
        method: 调用 ask_user_car_info 获取精确车型
    tools: [match_project, ask_user_car_info, knowledge_base_search]
    exit_when: "slot.project_id"
    strategy: |
      结合里程和上次保养时间推荐应做项目。
      需要车型信息来精确推荐。

  FUZZY_PROJECT:
    name: 模糊意图
    stage: S1
    goal: 引导用户将模糊的养车需求具体化为明确的项目
    target_slots:
      project_id:
        label: 养车项目ID
        required: true
        method: 通过引导和 match_project 逐步收束到具体项目
      project_name:
        label: 养车项目名称
        required: true
        method: 从匹配结果中获取
    tools: [match_project, knowledge_base_search]
    exit_when: "slot.project_id"
    strategy: |
      引导用户具体化需求。
      提供常见项目选项让用户选。
      最多 2 轮引导，收束不了推荐最常见方案。

  SAVING_PLAN:
    name: 确认省钱方案
    stage: S1
    goal: 为已确认的项目选择合适的省钱方式
    target_slots:
      saving_plan_type:
        label: 省钱方案类型
        required: true
        method: 查询可选方案后与用户沟通选择
    tools: [saving-strategy-guide, check_coupon_eligibility, price-inquiry]
    exit_when: "slot.saving_plan_type"
    strategy: |
      查询该项目可选的省钱方案。
      向用户介绍各方案优劣并帮助选择。
      如超出能力边界，友好告别。

  # ── S2 场景 ──

  FIND_MERCHANT:
    name: 搜索商户
    stage: S2
    goal: 根据用户位置和项目需求找到合适的商户
    target_slots:
      merchant:
        label: 选定商户
        required: true
        method: 调用 search_shops 搜索后帮用户比较选择
      location:
        label: 用户位置
        required: conditional
        condition: 需要搜索附近商户时
        method: 调用 ask_user_location 获取位置
    tools: [merchant-search-and-confirm, search_shops, ask_user_location]
    exit_when: "slot.merchant"
    strategy: |
      根据用户位置搜索合适的商户。
      展示候选列表，帮用户比较选择。

  CONFIRM_BOOKING:
    name: 确认预订
    stage: S2
    goal: 汇总所有信息形成预订方案，用户确认后执行下单
    target_slots:
      booking_time:
        label: 预约时间
        required: true
        method: 与用户确认合适的到店时间
    tools: [booking-plan-builder, booking-execution, confirm_booking]
    exit_when: "slot.booking_time"
    strategy: |
      汇总项目、价格、商户、优惠信息形成预订方案。
      让用户确认后执行预订。
```

### 3.4 Skill

Skill 的角色是**场景内部的执行指南**。场景配置定义"做什么"和"用什么工具"，Skill 文档定义"具体怎么做"。

当场景的 strategy 足够清晰时，不需要 Skill。
当场景内部有复杂的执行逻辑时，strategy 引用 Skill 文档。

```
skills/
├── platform-intro/              ← CASUAL_CHAT、PLATFORM_INQUIRY 使用
├── diagnose-car/                ← SYMPTOM_DIAGNOSE 使用
├── saving-strategy-guide/       ← SAVING_PLAN 使用
│   └── references/
│       ├── 九折方案.md
│       ├── 优惠券方案.md
│       └── 竞价方案.md
├── merchant-search-and-confirm/ ← FIND_MERCHANT 使用
├── booking-plan-builder/        ← CONFIRM_BOOKING 使用
└── booking-execution/           ← CONFIRM_BOOKING 使用
```

## 4. SlotState

SlotState 是持久化的槽位状态，每个 session 一份，驱动决策树求值。

```json
{
  "slots": {
    "project_id": null,
    "project_name": "小保养（换机油+机滤）",
    "vehicle_info": "2021款大众朗逸 1.5L",
    "saving_plan_type": null,
    "merchant": null,
    "location": "浦东张江",
    "booking_time": null
  },
  "scene_history": [
    {"scene": "CASUAL_CHAT", "turns": 2},
    {"scene": "DIRECT_PROJECT", "turns": 3}
  ]
}
```

更新方式：
- **主要方式**：MainAgent 调用 `update_slots` 工具显式更新（当业务状态变化时）
- 用户确认项目、选择方案、选定商户等场景 → 更新对应槽位值
- 用户改变主意 → 清除旧值（如 `update_slots({"project_id": null, "project_name": null})`）
- 下一轮请求时决策树重新求值，自动路由到正确场景

## 5. 注入 LLM 的上下文格式

```
[当前场景] 直接表达项目
[目标] 收集以下信息：养车项目ID、养车项目名称
[已有信息]
  养车项目ID: (待收集)
  养车项目名称: (待收集)
  车型信息: 2021款大众朗逸 1.5L
  省钱方案: (待收集)
  商户: (待收集)
[可用工具] match_project, ask_user_car_info
[策略]
  用户已说出项目名，直接用 match_project 匹配确认。
  确认后询问车型（如需要）。
  不要追问不必要的细节。
```

## 6. 多分类命中（Multi-Intent）

用户消息可能同时涉及多个分类。例如"我想换个轮胎，顺便保养一下"同时命中轮胎和机油保养。

### 处理方式

BMA 返回**主分类 + 次分类**：

```json
{
  "has_car_service": true,
  "project_category": "轮胎",
  "secondary_category": "机油保养"
}
```

决策树按**主分类**路由到场景。次分类写入 SlotState 作为上下文，场景内部一并处理：

```
决策树 → 路由到"轮胎项目"场景（按主分类）
场景内 → LLM 看到 slot.secondary_category = "机油保养"
       → 两个项目一起确认
```

### 设计原则

- 决策树一次只走一条路径，不返回多个场景
- 多意图的处理交给场景内部的 LLM（它能看到完整的用户消息和 slot 上下文）
- 次分类信息不丢弃，通过 SlotState 传递给场景

## 7. 意图变更处理

### 问题

当 SlotState 已有值时（如 `project_name = "小保养"`），用户说"还是换个轮胎吧"，需要正确路由到新的项目确认场景，而不是继续推进旧的流程。

### 解决方式：intent 优先自然路由

**不需要专门的意图变更检测机制。** 通过决策树的 **intent 优先结构** + MainAgent 的 **update_slots 工具**，意图变更被自然处理：

1. **决策树 intent 优先**：intent 分支在 slot 分支之前。当用户表达新意图时，BMA 识别出 `has_car_service=true`，决策树优先走 intent 分支，不会因为 slot 已有值而走错。

2. **LLM 通过 update_slots 更新槽位**：MainAgent 在对话中识别到用户改变想法时，调用 `update_slots` 清除旧值（如 `update_slots({"project_id": null, "project_name": null})`）。

3. **第二轮自动修正**：即使第一轮路由不完美，update_slots 清除旧 slot 后，下一轮决策树重新求值会自动路由到正确场景。

### 示例

```
当前 SlotState: { project_id: "502", project_name: "小保养" }
用户说："还是换个轮胎吧"

第一轮：
  BMA 输出: { has_car_service: true, project_category: "轮胎",
              expression_clarity: "specific" }
  决策树: intent.has_car_service → project_category=轮胎 不匹配
        → expression_clarity=specific → DIRECT_PROJECT ✅
  MainAgent 在 DIRECT_PROJECT 场景中：
    → 识别到用户要换项目
    → 调用 update_slots({"project_id": null, "project_name": null})
    → 开始匹配新项目"轮胎"

第二轮（如果第一轮未完成匹配）：
  SlotState: { project_id: null, project_name: null }
  决策树重新求值 → 自动路由到正确场景
```

### 设计原则

- **无需 `has_intent_change` 因子**：intent 优先结构让决策树天然处理意图变更
- **无需 `changed_slots` 字段**：LLM 通过 update_slots 工具自行判断和清除旧值
- **两轮收敛**：即使第一轮路由不完美，第二轮必然正确（因为 slot 已被清除，intent 已被识别）
- **简化 BMA**：BMA 只需判断当前消息的意图标签，不需要对比历史状态做变更检测

## 8. 当前实现方案

### 8.1 当前架构：BMA 每轮调用 + 决策树

当前实现采用两层结构，每轮必调 BMA：

```
用户消息
    │
    ├── slot 因子：从 SlotState 直读（0ms）
    ├── 关键词因子：字符串匹配（0ms）
    └── BMA 因子：调 Azure OpenAI gpt-4.1-mini（~2s）
    │       全量收集所有 bool + enum 因子
    │       使用 response_format: json_object 结构化输出
    │
    ▼ 全部因子就绪
    │
    决策树求值（确定性，0ms）
    │   用 slot 因子 + 关键词因子 + BMA 因子走决策树
    │   命中叶节点 → 场景 ID
    ▼
加载场景配置 → 注入 MainAgent
```

### 8.2 BMA 结构化输出

BMA 使用 Azure OpenAI 的 `response_format: { type: json_object }` 能力，强制返回符合格式的 JSON：

```json
{
  "has_car_service": true,
  "project_category": "轮胎",
  "expression_clarity": "specific",
  "has_platform_question": false,
  "secondary_category": null
}
```

System prompt 从 `subagents/business_map_agent/prompts/System.md` 加载，定义了标签提取规则和示例。

### 8.3 实现细节

**SceneOrchestrator**（`mainagent/src/business_map_hook.py`）：
- 作为 BeforeAgentRunHook 在每轮请求前执行
- 读取 SlotState，截取最近对话历史
- 调用 BusinessAgent `/classify` HTTP 端点
- 构建 SceneContext，设置 allowed_skills

**BusinessAgent /classify**（`subagents/business_map_agent/src/classify.py`）：
- 加载 `scene_config.yaml` 配置
- 构建 slot 因子、关键词因子
- 每轮全量调 LLM 求值所有 BMA 因子
- 走完决策树，返回场景配置

**配置文件**（`extensions/business-map/scene_config.yaml`）：
- `meta.factors`：因子声明（slot / keyword / BMA）
- `tree`：决策树定义
- `scenes`：场景配置

### 8.4 Phase 2 优化方向

当延迟不可接受时，可引入 **Semantic Router** 作为前置快速匹配层：

```
用户消息
    │
    ▼
[Phase 2] Semantic Router（embedding 匹配，<5ms）
    │   80%+ 消息在这里直接命中场景
    │   高置信度 → 直接返回场景 ID
    │   低置信度 ↓
    ▼
[当前] BMA 结构化输出（小模型，~2s）+ 决策树
```

每个场景预存 5-10 条典型话术的 embedding 向量，用户消息进来后做余弦相似度匹配。可引入开源 `aurelio-labs/semantic-router` 或自建简易版。

**并行拆分调用**（Phase 2）：当 BMA 因子数量超过阈值时，按决策树层级拆分为多组并行调用。配置已预留在 `scene_config.yaml` 的 `bma_config` 中。

### 8.5 延迟对比

| 方案 | 首轮延迟 | 后续延迟 | 状态 |
|------|---------|---------|------|
| 旧版（BMA 逐层导航） | 10-15s | 10-15s | 已废弃 |
| **当前（BMA 全量分类 + 决策树）** | **2-3s** | **2-3s** | **已实现** |
| Phase 2（Semantic Router + BMA 兜底） | <5ms（80%）/ 2-3s（20%） | <5ms（95%） | 待实现 |

## 9. 三层防线

```
第一层：目标（不变的）
    → 让用户形成可执行的服务订单

第二层：约束（少量的，硬性的）
    → 工具列表管控：场景外的工具不可用
    → 决策树兜底：未识别的情况走 CASUAL_CHAT

第三层：场景策略（多的，指导性的）
    → 每个场景的 strategy 指导 LLM 怎么沟通
    → Skill 文档提供详细执行指南
    → LLM 在约束内保留自主判断权
```

场景枚举覆盖 80% 高频路径，约束兜底处理 20% 边缘情况。

## 10. 文件结构

```
extensions/business-map/
├── design.md                  # 本设计文档
├── scene_config.yaml          # 统一配置（因子声明 + 决策树 + 场景定义）
├── intent_keywords.yaml       # 关键词因子配置（被 scene_config.yaml 引用）
└── （旧版文件过渡期保留）
    ├── convert_tree.py
    └── AllTree.yaml

subagents/business_map_agent/
├── src/classify.py            # /classify 端点（因子求值 + 决策树 + 场景返回）
└── prompts/System.md          # BMA 意图标签提取 System Prompt

mainagent/src/
├── business_map_hook.py       # SceneOrchestrator（调 /classify，注入场景上下文）
└── app.py                     # 注册 update_slots 工具
```

## 附录：业界参考与对标

### A. 大规模意图分类的生产实践

#### NatWest 银行（1600+ 意图，Amazon Lex）

采用**联邦架构**：Gateway Bot 粗分到 5-10 个大类 → Lambda 路由到子 Bot → 子 Bot 在 20-50 个意图内细分。Amazon Lex 推荐每个 Bot 最多 20-50 个意图。

**启示**：首轮分类应分步——先粗分大类，再细分。把 20+ 分类问题拆成 3 类 + 5 类。

参考：[NatWest Case Study](https://aws.amazon.com/blogs/contact-center/simplifying-banking-self-service-at-natwest-using-amazon-connect-and-amazon-lex/)

#### Dialogflow CX（Flow-Scoped NLU）

每个 Flow 有独立的 NLU 模型，只对当前 Flow 内的意图做分类。用户进入某个 Flow 后，分类范围大幅缩小。Google 推荐每个 Flow 处理 5-15 个意图。

**启示**：slot 状态进入某个分支后，BMA 只需在该分支内的少量场景中分类，与我们的"slot 因子先缩小范围"策略一致。

#### Rasa CALM（Hybrid LLM + NLU）

使用**共存路由器**：IntentBasedRouter（快速确定性）和 LLMBasedRouter（不确定时兜底）。LLM 路由的 prompt 比完整处理短 10 倍，成本低 200 倍。关键机制：**路由粘性**——一旦路由决策做出，保持到当前 flow 结束，不每轮重新分类。

**启示**：slot 因子填上后不再需要 BMA 重新分类，与 Rasa 的路由粘性原则一致。

参考：[Rasa CALM](https://rasa.com/calm), [Rasa Coexistence Routers](https://rasa.com/docs/reference/config/components/coexistence-routers/)

### B. 分类性能研究

#### Amazon "Intent Detection in the Age of LLMs"（EMNLP 2024）

- LLM 做大规模分类（50+ 类）时性能明显下降
- Claude v3 Haiku：F1=0.736，延迟 1.7-11.8 秒
- SetFit（轻量分类器）：F1=0.600，延迟 ~30ms
- **混合方案**：SetFit 主分类 + LLM 低置信度兜底，精度只差 ~2%，延迟减少 ~50%

**启示**：BMA 小模型的因子数量应控制在 5-8 个以内。超过时考虑加中间层或用轻量分类器前置。

参考：[论文](https://arxiv.org/html/2410.01627v1)

#### AAAI 2025 "Balancing Accuracy and Efficiency"

部署在 8 个多语言市场，237-481 个意图：
- **符号压缩**：将冗长意图标签压缩为短标签，准确率提升 5.09%
- **层级文本分类（HTC）**：按分类树的层级做分步分类，效果优于扁平分类
- **生产部署**：轻量 ONNX 模型在 8 核 CPU 上仅需 80ms

**启示**：验证了"树形分步分类优于扁平一次性分类"的结论。

参考：[论文](https://arxiv.org/html/2411.12307v1)

### C. 可引入的技术方案

#### Semantic Router（语义路由）

开源项目 `aurelio-labs/semantic-router`，将每个场景的典型表达做 embedding，用余弦相似度直接匹配。95% 的消息可在亚毫秒级完成路由，不需要调 LLM。

**可应用场景**：作为 BMA 前置的零成本快速匹配层。我们现有的 `intent_keywords.yaml` 是简化版，可升级为 embedding 版本。

参考：[GitHub](https://github.com/aurelio-labs/semantic-router)

#### RAG-Enhanced Intent Classification（REIC，EMNLP 2025）

构建（示例话术, 场景ID）的向量索引，推理时检索最相似的示例投票分类。添加新场景只需加示例，不需要重新训练。

**可应用场景**：当场景数量超过 50 时，替代 BMA 做分类。

参考：[论文](https://arxiv.org/abs/2506.00210)

#### 结构化输出（Structured Output）

Anthropic 和 OpenAI 都支持 schema 约束的 JSON 输出。当前已使用 Azure OpenAI 的 `response_format: json_object` 实现，BMA 返回 `{"project_category": "轮胎", "has_car_service": true}` 格式的结构化 JSON。

**当前状态**：已实现。消除了旧版 `_parse_node_ids()` 的正则清洗逻辑。

### D. 分层路由架构参考

业界共识的**分层级联**模式：

```
用户消息
    │
    ▼
[Tier 0] 关键词/规则匹配 ──→ 命中 → 直接路由（~0ms）     ✅ 已实现
    │ 未命中
    ▼
[Tier 1] 语义路由（embedding）──→ 高置信度 → 路由（~1-5ms） Phase 2
    │ 低置信度
    ▼
[Tier 2] 轻量分类器（BERT/SetFit）──→ 高置信度 → 路由     Phase 3
    │ 低置信度
    ▼
[Tier 3] LLM 分类（BMA）──→ 路由（~2s）                   ✅ 已实现
```

当前实现了 Tier 0（关键词因子）和 Tier 3（BMA 结构化输出 + 决策树）。当前方案每轮都走 Tier 3，未来可按需引入 Tier 1（语义路由）跳过 BMA 调用来优化延迟。

### E. 相关框架对标

| 框架 | 路由方式 | 与我们的对应关系 |
|------|---------|---------------|
| LangGraph | StateGraph 条件边 | ≈ 决策树 + slot 条件 |
| Pydantic AI Graph | 类型标注定义转移 | ≈ 决策树叶节点指向场景 |
| Rasa CALM | Flow + LLMCommandGenerator | ≈ 场景配置 + BMA |
| Amazon Lex | Gateway Bot + 子 Bot 联邦 | ≈ 粗分类 + 细分类 |
| Dialogflow CX | Flow-Scoped NLU | ≈ slot 缩小分类范围 |
| OpenAI Swarm | Triage Agent + Handoff | ≈ BMA 路由 + 场景切换 |

参考：[LangGraph](https://github.com/langchain-ai/langgraph), [Pydantic AI Graph](https://ai.pydantic.dev/graph/), [Semantic Kernel Roadmap](https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-roadmap-h1-2025/)
