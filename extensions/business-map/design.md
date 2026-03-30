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
│  ② 决策树"边走边求值"：                            │
│     → 遇到 slot 条件 → 直接判断（零成本）           │
│     → 遇到关键词条件 → 直接判断（零成本）           │
│     → 遇到需要 AI 的条件 → 暂停，收集待求因子       │
│     → 调一次 BMA 批量求值（最多一次）               │
│     → 继续走完决策树 → 输出场景 ID                  │
│  ③ 加载场景配置（goal/tools/strategy）             │
│  ④ 设置 MainAgent 可用工具列表（硬约束）           │
│  ⑤ 注入上下文（场景 + 槽位状态 + 策略）            │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  MainAgent（大模型）                              │
│                                                  │
│  在场景约束下与用户对话                             │
│  只能调用当前场景允许的工具/Skill                    │
│  按 strategy 指引的方式沟通                        │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  SceneOrchestrator（每轮请求后执行）               │
│                                                  │
│  ⑦ 从对话结果中提取槽位更新                        │
│  ⑧ 更新 SlotState                               │
│  ⑨ 下轮请求时决策树自动重新求值                     │
└─────────────────────────────────────────────────┘
```

## 3. 四大组件

### 3.1 BMA（意图标签提取器）

角色：小模型（gpt-4.1-mini），每轮调用一次，输出一组 bool 标签。

不做场景分类，不做导航，只回答 yes/no 问题。场景分类由决策树完成。

```
输入：用户消息 + 对话上下文摘要
输出：MessageIntent（一组 bool 标签）
```

意图标签定义：

| 标签 | 含义 |
|------|------|
| has_car_service | 涉及养车、保养、维修、车辆问题 |
| has_direct_project | 明确说出了项目名称（换机油、做保养） |
| has_symptom | 描述故障症状（车抖、异响、亮灯） |
| has_lifecycle_info | 提到里程、车龄、上次保养时间 |
| has_platform_question | 问平台是什么、九折怎么回事 |
| has_intent_change | 改变之前的决定（算了、不做了、换一个） |
| has_urgent | 紧急情况（抛锚、事故） |
| has_merchant_need | 提到找店、商户、附近 |
| has_price_question | 问价格、报价 |

标签可按需扩展，每增加一个标签就是在 BMA prompt 中加一行 yes/no 问题。

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

决策树定义文件：`extensions/business-map/decision_tree.yaml`

```yaml
decision_tree:
  # ── 优先级最高：跨阶段场景 ──
  - if: intent.has_urgent
    scene: URGENT
  - if: intent.has_intent_change
    scene: INTENT_CHANGE

  # ── S2：项目和省钱方案都已确认 ──
  - if: slot.project_id AND slot.saving_plan_type
    children:
      - if: NOT slot.merchant
        scene: FIND_MERCHANT
      - if: NOT slot.booking_time
        scene: CONFIRM_BOOKING
      - scene: COMPLETED

  # ── S1：项目已确认，省钱方案未定 ──
  - if: slot.project_id AND NOT slot.saving_plan_type
    scene: SAVING_PLAN

  # ── S1：项目未确认，有养车意图 ──
  - if: NOT slot.project_id AND intent.has_car_service
    children:
      - if: intent.has_direct_project
        scene: DIRECT_PROJECT
      - if: intent.has_symptom
        scene: SYMPTOM_DIAGNOSE
      - if: intent.has_lifecycle_info
        scene: LIFECYCLE_PROJECT
      - scene: FUZZY_PROJECT

  # ── S1：项目未确认，无养车意图 ──
  - if: NOT slot.project_id AND intent.has_platform_question
    scene: PLATFORM_INQUIRY

  # ── 兜底 ──
  - scene: CASUAL_CHAT
```

求值逻辑：从上到下遍历，第一个命中的 `if` 进入其子树或返回 scene。子树内部同样从上到下。未命中任何条件时走最后的无条件 scene（兜底）。

#### 决策因子（Decision Factor）

决策树每个节点的 `if` 条件依赖**决策因子**。因子分为两大类：

**槽位因子（Slot Factor）**：从 SlotState 直读，零成本，确定性，可累积。
**模型因子（Model Factor）**：需要 AI 或规则判断，每轮按需求值。

求值策略的核心原则：
1. **先走槽位因子** → 缩小到某个分支（零成本、确定性）
2. **再看该分支需要哪些模型因子** → 一次 BMA 调用批量求值
3. **用全部因子走完决策树** → 命中叶节点（场景 ID）
4. **场景内部的细分交给 skill 和工具处理**，不在决策树层面拆分

##### 槽位因子

从 SlotState 直读，零成本。随着对话推进，slot 不断被填充，槽位因子越来越多，决策树靠 slot 条件就能到达叶节点，越来越少需要模型因子。

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
| 关键词匹配 | 字符串匹配 | 零 | 明确的信号词（抛锚、算了） |
| BMA 语义判断 | 小模型一次调用 | 低 | 需要理解语义（是否涉及养车） |

关键词因子配置在 `intent_keywords.yaml` 中：

```yaml
# 关键词因子（不需要 AI，字符串匹配即可）
has_urgent: [抛锚, 事故, 打不着火, 冒烟, 漏油严重]
has_intent_change: [算了, 不做了, 改成, 换个, 不想, 还是别]
has_price_question: [多少钱, 价格, 报价, 费用, 贵不贵]
has_merchant_need: [找店, 找个店, 附近, 门店, 商户, 哪家]
```

BMA 语义因子支持两种值类型：

**bool 型**（yes/no 判断）：
```yaml
has_car_service: 用户消息是否涉及养车、保养、维修、车辆问题
has_platform_question: 用户是否在询问平台能力或九折机制
```

**分类型**（从枚举值中选一个）：
```yaml
project_category:
  type: enum
  options: [保险, 轮胎, 机油保养, 钣喷, 洗车, 检测, 模糊, 症状, 无]
  description: 用户提到的养车项目大类

expression_clarity:
  type: enum
  options: [specific, vague, symptom]
  description: 用户表达的具体程度
```

BMA 一次调用同时回答 bool 和分类问题：

```json
{
  "has_car_service": true,
  "project_category": "轮胎",
  "expression_clarity": "specific"
}
```

##### 因子求值总结

```
每轮对话：
  ① 槽位因子全部求值（零成本）
  ② 沿决策树走 slot 分支，缩小范围
  ③ 遇到模型因子 → 先看关键词能否判断
  ④ 关键词不够 → 收集该分支所有需要的 BMA 因子
  ⑤ 一次 BMA 调用批量求值（bool + 分类混合）
  ⑥ 走完决策树 → 命中叶节点
```

越往后 slot 越满，需要 BMA 的场景越少：

| 对话阶段 | 需要 BMA | 原因 |
|---------|---------|------|
| 首轮（slot 全空） | 是（一次调用） | 需要判断用户意图和项目大类 |
| 项目已确认 | 通常不需要 | slot 因子直接定位到 SAVING_PLAN |
| 项目+省钱都确认 | 通常不需要 | slot 因子直接定位到 FIND_MERCHANT |
| 中途改主意 | 关键词判断 | "算了""不做了"关键词命中 |

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

#### 边走边求值（Lazy Evaluation）

决策树不需要预先求值所有因子。采用**边走边求值**策略：

```
开始遍历决策树
  │
  ├→ 遇到 slot 条件（如 slot.project_id）
  │   → 直接从 SlotState 判断，继续走
  │
  ├→ 遇到关键词条件（如 intent.has_urgent）
  │   → 关键词匹配判断，继续走
  │
  ├→ 遇到语义条件（如 intent.has_car_service）
  │   → 暂停遍历
  │   → 收集当前路径上所有未知的语义因子
  │   → 调一次 BMA，批量求值
  │   → 继续走完决策树
  │
  └→ 到达叶节点 → 返回场景 ID
```

**核心优化：大部分轮次不需要调 BMA。**

| 用户状态 | 需要求值的因子 | 是否调 BMA |
|---------|--------------|-----------|
| 项目已确认，问优惠 | 只需 slot 因子 | 不调 |
| 用户说"算了不做了" | 关键词命中 has_intent_change | 不调 |
| 全空，用户说"你好" | 关键词未命中 → 需 has_car_service | 调，问 1 个因子 |
| 全空，用户说"车有点抖" | 需 has_car_service + has_symptom | 调，问 2 个因子 |

### 3.3 场景配置（Scenes）

#### 节点定义

决策树中有两种节点——**条件节点**和**叶节点**，场景配置中定义的是叶节点指向的**场景**。

##### 条件节点（decision_tree.yaml）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `if` | string | 条件节点必填 | 条件表达式 |
| `scene` | string | 叶节点必填 | 场景 ID，指向 scenes.yaml |
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

##### 场景节点（scenes.yaml）

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

场景定义文件：`extensions/business-map/scenes.yaml`

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

  INTENT_CHANGE:
    name: 用户改变意图
    stage: any
    goal: 确认用户的新意图，重置受影响的槽位
    target_slots: {}
    tools: []
    exit_when: 确认用户新意图
    strategy: |
      确认用户确实要改变。
      重置受影响的槽位。
      不要反复劝说。

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
- **主要方式**：SceneOrchestrator 后置 Hook 从工具调用结果中自动提取
- **辅助方式**：MainAgent 调用 update_slot 工具显式更新（复杂场景）

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

## 7. 意图变更感知（Intent Change Detection）

### 问题

当 SlotState 已有值时（如 `project_name = "小保养"`），用户说"还是换个轮胎吧"，决策树的 slot 分支会把用户直接路由到下游场景（如 SAVING_PLAN），而不是回到项目确认场景。

原因：决策树看到 `slot.project_id` 有值就认为项目已确认，但用户实际在**改变**之前的选择。

### 解决方式

**BMA 必须接收当前 SlotState 摘要作为输入**，才能判断用户是否在改变已有选择。

BMA 输入扩展：

```
用户消息："还是换个轮胎吧"
当前已确认信息：project_name=小保养, saving_plan_type=未确认
```

BMA 输出扩展：

```json
{
  "has_car_service": true,
  "has_intent_change": true,
  "changed_slots": ["project_id", "project_name"],
  "project_category": "轮胎"
}
```

- `has_intent_change`：用户是否在改变之前已确认的选择（BMA 对比用户消息和当前 slot 来判断）
- `changed_slots`：哪些 slot 需要重置

### SceneOrchestrator 处理流程

```
① 读 SlotState
② 调 BMA（传入用户消息 + SlotState 摘要）
③ 如果 has_intent_change == true：
   → 重置 changed_slots 对应的 slot 值
   → 用重置后的 SlotState 走决策树
④ 走决策树 → 命中正确场景
```

### 示例

```
当前 SlotState: { project_id: "502", project_name: "小保养" }
用户说："还是换个轮胎吧"

BMA 输出:
  { has_intent_change: true, changed_slots: ["project_id", "project_name"],
    project_category: "轮胎" }

SceneOrchestrator:
  → 重置: { project_id: null, project_name: null }
  → 决策树: slot.project_id 为空 → has_car_service → project_category=轮胎
  → 命中: TIRE_PROJECT ✅
```

### 设计原则

- BMA 的 `has_intent_change` 判断依赖 SlotState 上下文，不能只看用户消息
- 关键词（"算了""不做了"）可以作为快捷触发，但语义层面的变更（"还是换个..."）需要 BMA 理解
- slot 重置是**选择性的**：只重置用户改变的部分，不清空所有状态

## 8. 推荐实现方案：三层级联 + 并行优化

### 8.1 级联路由架构

场景路由采用三层级联，逐层兜底：

```
用户消息
    │
    ▼
[层级1] Semantic Router（embedding 匹配，<5ms）
    │   80%+ 消息在这里直接命中场景
    │   高置信度 → 直接返回场景 ID
    │   低置信度 ↓
    ▼
[层级2] BMA 结构化输出（小模型，~2s）
    │   一次调用批量求值所有需要的因子
    │   返回结构化 JSON，无需正则解析
    │   因子数量过多时并行拆分调用
    │
    ▼
[层级3] 决策树求值（确定性，0ms）
    │   用 slot 因子 + 模型因子走决策树
    │   命中叶节点 → 场景 ID
    ▼
加载场景配置 → 注入 MainAgent
```

### 8.2 Semantic Router（层级1）

每个场景预存 5-10 条典型话术的 embedding 向量，用户消息进来后做余弦相似度匹配：

```
"我想换个机油"  → similarity → DIRECT_PROJECT (0.95) ✅ 直接命中
"你好"          → similarity → 最高 0.3，低置信度 → 交给层级2
```

优势：
- 80%+ 的消息在亚毫秒内解决，不调任何模型
- 添加新场景只需加几条示例话术，不改代码
- 现有 `intent_keywords.yaml` 可作为初始示例来源

实现路径：可引入开源 `aurelio-labs/semantic-router` 或自建简易版。

### 8.3 BMA 结构化输出（层级2）

Semantic Router 低置信度时调用 BMA。改进点：

**结构化输出**：使用 Structured Output 能力，强制 BMA 返回符合 schema 的 JSON：

```json
{
  "has_car_service": true,
  "project_category": "轮胎",
  "expression_clarity": "specific",
  "has_intent_change": false,
  "secondary_category": null
}
```

彻底消除现有 `_parse_node_ids()` 的正则清洗逻辑。

**并行拆分调用**：当需要求值的因子数量超过阈值（可配置，默认 10）时，按决策树层级拆分为多组，并行调用：

```
需要求值的因子：15 个
配置阈值：10 个/次

拆分（按决策树层级）：
  BMA 调用 A（并行）：粗分类因子
    has_car_service、project_category、has_platform_question、has_urgent
  BMA 调用 B（并行）：细分类因子
    expression_clarity、has_symptom、has_lifecycle_info、has_direct_project

总耗时：max(A, B) ≈ 2s，不是串行的 4s
```

A 的结果决定走哪个大分支，B 的结果决定大分支内的子节点。B 的结果可能用不上（如 A 判定 `has_car_service=false`），但并行执行不浪费时间，只浪费少量 token。

配置方式：

```yaml
# intent_tags.yaml
bma_config:
  max_factors_per_call: 10
  parallel_enabled: true

  groups:
    - name: coarse
      factors: [has_car_service, project_category, has_platform_question, has_urgent]
    - name: fine
      factors: [expression_clarity, has_symptom, has_lifecycle_info, has_direct_project]
```

### 8.4 并行处理优化

除了 BMA 拆分并行外，其他预处理也可并行执行：

```
用户消息进来
    │
    ├── 并行 A：Semantic Router 匹配（<5ms）
    ├── 并行 B：关键词因子匹配（<1ms）
    ├── 并行 C：读 SlotState（<1ms）
    └── 并行 D：实体提取（项目关键词、时间、地点，可选）
    │
    ▼ 全部完成
    │
    如果 Semantic Router 高置信度 → 直接命中（完成，<5ms）
    如果不确定 → 调 BMA（可能并行拆分，~2s）
    │
    ▼
    决策树求值 → 命中场景
```

### 8.5 各方案延迟对比

| 方案 | 首轮延迟 | 后续延迟 | 准确率 |
|------|---------|---------|--------|
| 现有（每轮 BMA 逐层导航） | 10-15s | 10-15s | 80-90% |
| BMA 结构化分类（不导航） | 2-3s | 0-2s | 85-95% |
| Semantic Router + BMA 兜底 | <5ms（80%）/ 2-3s（20%） | <5ms（95%） | 90-95% |
| 全套级联 + 并行 | <5ms-3s | <5ms | 95%+ |

**推荐实施路径**：
1. 先做 BMA 结构化输出（改动最小，立即见效）
2. 验证后加 Semantic Router（覆盖高频场景）
3. 延迟不可接受时加并行拆分

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
├── decision_tree.yaml         # 决策树定义
├── scenes.yaml                # 场景配置（stages + scenes）
├── intent_tags.yaml           # BMA 意图标签定义
└── （旧版文件过渡期保留）
    ├── convert_tree.py
    ├── AllTree.yaml
    └── intent_keywords.yaml
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

Anthropic 和 OpenAI 都支持 schema 约束的 JSON 输出。如果 BMA 使用结构化输出，可以强制返回 `{"project_category": "轮胎", "has_car_service": true}` 格式，完全消除解析层的正则清洗逻辑。

**可应用场景**：替代当前 `_parse_node_ids()` 的 60+ 行正则解析。

### D. 推荐的分层路由架构

业界共识的**分层级联**模式：

```
用户消息
    │
    ▼
[Tier 0] 关键词/规则匹配 ──→ 命中 → 直接路由（~0ms）
    │ 未命中
    ▼
[Tier 1] 语义路由（embedding）──→ 高置信度 → 路由（~1-5ms）
    │ 低置信度
    ▼
[Tier 2] 轻量分类器（BERT/SetFit）──→ 高置信度 → 路由（~30-80ms）
    │ 低置信度
    ▼
[Tier 3] LLM 分类（BMA）──→ 路由（~200-2000ms）
```

我们当前实现了 Tier 0（关键词）和 Tier 3（BMA）。未来可按需引入 Tier 1（语义路由）和 Tier 2（轻量分类器）来优化延迟和成本。

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
