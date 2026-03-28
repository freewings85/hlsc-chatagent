# BusinessMapAgent 设计与实现方案

> **本文档目标读者**：接手实现的开发者或 AI Coding Agent。
> 文档包含完整的背景、设计决策、技术方案和实现指南，读完后应能独立完成开发。

---

## 0. 背景

### 0.1 业务场景

本项目是一个**汽车养车预订服务的 AI 对话系统**。车主通过对话告诉 AI 自己的需求（如"我车该保养了"），AI 引导车主走完整个业务流程：确认项目 → 沟通省钱方案 → 筛选商户 → 执行预订。

这个流程非常复杂——它不是线性的几个步骤，而是一棵**多层级业务树**：
- 第 1 层：大阶段（沟通需求、找商户、做预订）
- 第 2 层：各阶段下的子任务（确认项目、确认特殊需求、确认省钱方法……）
- 第 3+ 层：更细的场景分支（直接表达、模糊意图、症状描述……）
- 层级深度不固定，未来可能扩展到 4-5 层甚至更深

每个节点都有自己的业务指引（该怎么做）、待办事项（要做哪些事）、产出定义（做完了记录什么）、依赖关系和取消走向。

### 0.2 要解决的问题

**核心问题**：如何让 MainAgent（负责与用户对话的主 Agent）在每轮对话中，只看到当前相关的那一小块业务指引，而不是整棵业务树？

这就像一个复杂网站的"站内导航"——用户说了一句话，系统要快速定位到业务地图上的对应位置，把那一条路径上的指引切片提取出来给 MainAgent 参考。

**为什么不能简单处理**：
- **全塞 prompt**：业务树可能很大，全塞进去 token 爆炸，而且绝大部分内容与当前对话无关，是噪音
- **简单关键词搜索**：无法理解层级关系和上下文，搜到叶节点但丢了父节点的背景信息
- **知识图谱（KG）**：维护成本高，业务人员难以直接编辑，不适合快速迭代的业务流程（**已明确排除**）

### 0.3 解决思路

设计一个 **BusinessMapAgent**，作为 MainAgent 的"业务导航员"：
1. 业务地图用 **YAML 文件**存储，目录结构即树结构，业务人员可直接编辑
2. 一个**小模型 Agent** 负责在树上定位（输出节点 ID）
3. 一个**代码层**负责根据 ID 组装 Markdown 切片（确保内容零失真）
4. 切片通过 `request_context` 注入 MainAgent 的上下文

### 0.4 系统全景

```
用户消息
  │
  ▼
┌─────────────────────────────────────────────────┐
│ MainAgent（大模型，对话+执行+状态维护）           │
│                                                   │
│  ┌──────────────┐    ┌──────────────────────┐    │
│  │ 状态树        │    │ request_context       │    │
│  │ (Markdown)   │    │ ← 业务切片 Markdown   │    │
│  └──────┬───────┘    └──────────▲───────────┘    │
│         │ 压缩为简报            │ 注入            │
│         ▼                      │                  │
│  ┌──────────────┐    ┌────────┴─────────────┐    │
│  │ 自然语言简报  │───▶│ 代码层（内容组装）     │    │
│  └──────────────┘    └──────────▲───────────┘    │
│                                 │ 节点 ID         │
│                      ┌─────────┴────────────┐    │
│                      │ 小模型 Agent（定位）   │    │
│                      │ read 工具逐层读 YAML  │    │
│                      └──────────────────────┘    │
└─────────────────────────────────────────────────┘
                            │
                     ┌──────┴──────┐
                     │ business-map/ │ ← YAML 文件树
                     │ (文件系统)    │
                     └─────────────┘
```

### 0.5 现有代码库

本项目是一个 **Python monorepo**，使用 `uv` 管理依赖，基于 **Pydantic AI** 框架：

```
项目根/
├── sdk/agent_sdk/          # 通用 SDK（Agent、loop、deps、tools、A2A）
├── mainagent/src/          # HLSC 主 Agent 服务
│   ├── app.py              # create_agent_app()：工具注册入口
│   ├── hlsc_context.py     # HlscContextFormatter
│   └── tools/              # mainagent 自有工具
├── extensions/hlsc/        # 业务扩展包（tools、services、models）
│   └── tools/              # call_recommend_project 等
└── subagents/              # 独立子 Agent 进程（A2A 通信）
```

**关键集成点**（实现时需要修改或新增的地方）：

| 要做什么 | 涉及位置 |
|---------|---------|
| 创建业务地图 YAML 文件 | 新建 `business-map/` 目录（位置待定，可能在 `mainagent/` 或 `extensions/` 下） |
| 实现 YAML 树加载和遍历 | 新建模块，如 `sdk/agent_sdk/` 或 `extensions/hlsc/` 下 |
| 实现小模型 Agent | 新建模块，需要自己的 prompt 和 read 工具 |
| 实现代码层内容组装 | 新建模块，`assemble_slice` + `format_node` |
| 触发逻辑 | 修改 `mainagent/src/app.py` 或 hook 机制 |
| 切片注入 request_context | 利用现有 `context_formatter` 或 `request_context` 管道 |
| MainAgent 状态树维护 | 修改 MainAgent 的 prompt 和可能的 memory 机制 |

**现有 request_context 注入方式**：
- HTTP 请求 `context` 字段 → `agent.run(..., request_context=context)`
- 若有 `context_formatter`，格式化为文本，作为 `UserPromptPart` 注入模型消息链
- 同时挂在 `deps.request_context` 上供工具读取

**现有工具注册模式**：
- `mainagent/src/app.py` 中 `create_agent_app()` 用字典合并所有工具
- subagent 通过 `call_subagent`（A2A）作为普通 tool 挂接
- BusinessMapAgent **不是** A2A subagent，而是在 MainAgent 进程内调用的内部组件

---

## 1. 它是什么

整个系统分为两层：**小模型 Agent（定位）** 和 **代码层（组装）**。

- **小模型 Agent**：拥有 read 工具，逐层读取业务地图的 YAML 文件，在树上做关键词匹配定位。最终只输出**节点 ID**（一个或多个）。
- **代码层**：拿到节点 ID 后，沿树从根到该节点收集完整路径，读取每个节点的 description/checklist/output/depends_on/cancel_directions 等业务定义字段，组装成 Markdown 交给 MainAgent。

一句话定义：
- 小模型 Agent 负责"当前在业务地图上的**哪里**"（输出 ID）
- 代码层负责"那里**写了什么**"（组装内容）
- MainAgent 负责"接下来**怎么做**，做完**怎么记**"

## 2. 它不做什么

- 不和用户对话
- 不调用业务工具
- 不做执行动作
- 不维护 checklist 状态（done/pending/blocked）
- 不替 MainAgent 决定下一步先做哪项
- 不替 MainAgent 记录业务结果
- 不做自由发挥式的分析或解释

## 3. 为什么要拆成两层

业务地图是树状的，层级可能很深，体量可能很大。

**为什么不能全塞进 prompt**：token 爆炸，噪音太多。

**为什么小模型不能直接组装内容**：小模型容易编造、遗漏、改写 YAML 中的原始指引。内容组装交给代码后，输出的 Markdown 100% 来自 YAML 文件原文，零失真。

**为什么小模型需要是 Agent（带 read 工具）**：业务地图大小未知，树骨架可能塞不进一个 prompt。Agent 可以逐层读取 `_node.yaml`，每次只看当前层的 children 列表做导航决策，不需要一次加载全树。

**为什么不让 MainAgent 自己导航**：MainAgent 要处理对话、调工具、维护状态，再让它读业务地图文件导航容易丢失上下文。把导航剥离出来，MainAgent 只看到组装好的切片。

## 4. 核心原则

### 4.1 允许只命中浅层

用户第一句话通常不足以定位到叶子节点。例如"我想做个保养"只能稳定命中第 1 层，不能确定是"小保养"还是"大保养"。

这不是失败，而是正常结果。

BusinessMapAgent 不应该：
- 为了"看起来更完整"而硬猜更深的节点
- 把不确定的分支补全成确定路径

BusinessMapAgent 应该：
- 停在当前足够确定的最深层
- 输出当前层与上层的内容切片

### 4.2 渐进下钻

业务路径的下钻是渐进式的：

1. BusinessMapAgent 先输出当前能确定的浅层路径切片
2. MainAgent 根据当前层 todo 和缺失输入，继续向用户补事实
3. 运行状态更新后，再触发 BusinessMapAgent
4. BusinessMapAgent 基于新输入继续往更深层定位

不要求一轮定位到底。信息越多，定位越深；信息不足，就停住。

### 4.3 MainAgent 保留全部选择权

BusinessMapAgent 只提供"地图上写了什么"。

MainAgent 自己决定：
- 先推进哪个事项
- 是否继续澄清
- 是否切换阶段
- 执行后如何更新状态和结果

### 4.4 不猜不编

BusinessMapAgent 输出的内容必须来自业务地图 YAML 文件。不允许自行编造 description、补充 checklist、或对业务逻辑做推断。

## 5. 触发时机

BusinessMapAgent 不需要每轮都跑。在以下时机触发：

| 时机 | 说明 |
|------|------|
| 进入复杂业务流程 | 首次接触预订类需求，建立初始导航 |
| 用户目标明显变化 | 从"换机油"转向"查轮胎"，需要重新定位 |
| 当前阶段完成 | 需要切换到下一阶段 |
| MainAgent 补完关键信息 | 够条件下钻到更深层了 |
| MainAgent 推进受阻 | 不确定当前该往哪走 |

不触发的情况：
- 用户在回答简单问题（告知车型、确认时间）
- MainAgent 正在按已有切片顺序执行
- 闲聊、问候等非业务对话

## 6. 输入

### 6.1 聊天输入
- 当前用户消息
- 最近几轮必要历史

用途：定位当前对话落在业务地图的哪条路径。

### 6.2 当前运行状态（MainAgent 维护的，转换为简报传入）

MainAgent 内部维护一棵缩进 Markdown 状态树（详见第 12 节）。触发 BusinessMapAgent 前，MainAgent 将状态树压缩为一份**自然语言简报**传入：

```markdown
已完成：
- 确认养车项目 → 小保养（换机油+机滤）
- 确认特殊需求 → 已跳过，车主无特殊要求

当前在做：确认省钱方法 → 优惠券方案 → 确认车主偏好
```

用途：
- "已完成"部分告诉 BusinessMapAgent 哪些分支已走完，不需要再定位过去
- "当前在做"告诉 BusinessMapAgent 上次停在哪条路径上，辅助定位

为什么不传结构化 JSON：
- BusinessMapAgent 是小模型，自然语言比 JSON 更容易理解
- 关键词直接匹配树节点的 name，不需要额外做 ID 映射
- 格式容错性高，不会因为 JSON 语法错误导致解析失败

### 6.3 业务地图
- BusinessMapAgent 拥有 read 工具，按需逐层读取
- 不全量加载，先定位大阶段，再下钻到对应分支

## 7. 业务地图 YAML 结构

### 7.1 目录约定

递归树形结构，不限层级深度：
- **有子节点** → 用目录，里面放 `_node.yaml`
- **没子节点** → 直接是 `.yaml` 文件

```
business-map/
├── _root.yaml
│
├── project-saving/
│   ├── _node.yaml
│   ├── confirm-project/
│   │   ├── _node.yaml
│   │   ├── direct-expression.yaml
│   │   ├── fuzzy-intent.yaml
│   │   └── symptom-based.yaml
│   ├── confirm-requirements.yaml
│   └── confirm-saving/
│       ├── _node.yaml
│       ├── coupon-path.yaml
│       └── bidding-path.yaml
│
├── merchant-search/
│   ├── _node.yaml
│   ├── search.yaml
│   ├── compare.yaml
│   └── confirm.yaml
│
└── booking/
    ├── _node.yaml
    └── ...
```

### 7.2 节点字段

节点的字段分为两类：**业务定义字段**（给 MainAgent 看的）和**导航结构字段**（给小模型 Agent 和代码层用的）。

#### 业务定义字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 可读标识（如 `confirm_project`） |
| `name` | 是 | 业务名称 |
| `depends_on` | 否 | 依赖的信息（不一定是其他 node，可以是数据、前置条件等） |
| `checklist` | 否 | 这个 node 需要完成的事项 |
| `output` | 否 | 这个 node 完成后的产出（MainAgent 据此知道该记录什么） |
| `cancel_directions` | 否 | 取消时不同原因对应的不同后果和走向 |
| `description` | 否 | 特殊说明（条件分支、跨节点引用、场景判断等） |

#### 导航结构字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `children` | 否 | 子节点列表（有则为中间节点，无则为叶节点） |
| `keywords` | 否 | 关键词列表，小模型 Agent 用来做定位匹配 |
| `path` | 否 | 子目录/文件路径（children 条目中使用） |
| `optional` | 否 | 是否可选 |

### 7.3 关键约束

**每个节点都必须有实质业务内容**。`description` 和 `checklist` 不能同时为空。因为小模型 Agent 可能在任意一层停下，代码层组装的切片只包含路径上各节点的内容。不允许只有 `children` 列表没有自身业务内容的空壳节点。

### 7.4 YAML 示例

#### `_root.yaml`

```yaml
id: root
name: 养车预订业务地图
description: |
  帮助车主完成从需求沟通到预订执行的完整流程。
  project_saving 和 merchant_search 可交叉进行。
  确认了项目就可以开始搜商户，不必等省钱方案完全敲定。
  booking 必须在前两阶段基本完成后启动。

children:
  - id: project_saving
    name: 沟通项目需求与省钱方案
    keywords: [保养, 维修, 换, 项目, 省钱, 优惠, 比价, 便宜]
    path: project-saving/

  - id: merchant_search
    name: 筛选匹配商户
    keywords: [找店, 商户, 附近, 推荐, 门店, 哪家, 靠谱]
    depends_on:
      - 需要已确认的养车项目（confirm_project 的 output）
    path: merchant-search/

  - id: booking
    name: 执行预订
    keywords: [预订, 下单, 约, 预约, 时间]
    depends_on:
      - 已确认的项目和省钱方案（project_saving 的 output）
      - 已选定的商户（merchant_search 的 output）
    path: booking/
```

#### 中间节点 `_node.yaml`（例：`project-saving/_node.yaml`）

```yaml
id: project_saving
name: 沟通项目需求与省钱方案

description: |
  本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。
  通常按确认项目 → 特殊需求 → 省钱方法顺序推进。
  车主急切时可加快节奏，特殊需求可简单确认后跳过。

checklist:
  - 确认车主的养车项目
  - 了解是否有特殊需求
  - 沟通省钱方法和偏好

output:
  - 已确认的养车项目列表
  - 特殊需求记录（如有）
  - 省钱方案偏好

cancel_directions:
  车主不想做了: 记录意向，结束流程
  车主要自己去店里问: 提供商户推荐后结束

children:
  - id: confirm_project
    name: 确认养车项目
    keywords: [保养, 换机油, 什么项目, 该做什么]
    path: confirm-project/

  - id: confirm_requirements
    name: 确认特殊需求
    keywords: [品牌, 全合成, 配件, 指定]
    optional: true

  - id: confirm_saving
    name: 确认省钱方法
    keywords: [省钱, 便宜, 优惠, 打折, 划算]
    depends_on:
      - 需要已确认的养车项目（confirm_project 的 output）
```

#### 更深的中间节点（例：`project-saving/confirm-project/_node.yaml`）

```yaml
id: confirm_project
name: 确认养车项目

description: |
  把车主的表述匹配到具体的养车项目。
  大部分情况能快速通过，不需要过度追问。

checklist:
  - 识别车主描述对应的项目类型
  - 匹配到具体项目
  - 获得车主确认

output:
  - 已确认的养车项目名称
  - 项目对应的标准服务内容

cancel_directions:
  车主不确定要做什么: 引导到 fuzzy_intent 场景
  车主想先了解价格: 跳转到 confirm_saving 节点

children:
  - id: direct_expression
    name: 直接表达场景
    keywords: [换机油, 做保养, 换轮胎, 换刹车片]

  - id: fuzzy_intent
    name: 模糊意图场景
    keywords: [该保养了, 跑了很久, 不知道该做什么]

  - id: symptom_based
    name: 症状描述场景
    keywords: [异响, 抖动, 故障灯, 漏油]
```

#### 叶节点（例：`project-saving/confirm-project/fuzzy-intent.yaml`）

```yaml
id: fuzzy_intent
name: 模糊意图场景

description: |
  车主没有直接说项目名称，但提供了里程、时间、使用场景等间接信息。
  车主只是觉得"该保养了"，但不确定具体做什么。
  结合里程和上次保养间隔推荐合适项目。
  如果无法判断，简单问一句即可，不要连续追问。

depends_on:
  - 车型信息
  - 里程或上次保养时间

checklist:
  - 结合里程和保养间隔推荐项目
  - 简单确认即可

output:
  - 推荐的养车项目

cancel_directions:
  车主仍然不确定: 建议车主到店检查，提供商户推荐
```

## 8. 小模型 Agent 的工作过程

### 8.1 逐层定位

Agent 拥有 read 工具，逐层读取 YAML 文件做导航。它只关注每个文件中的导航结构字段（`id`、`name`、`keywords`、`children`），**不需要理解 `description`、`checklist`、`output`、`depends_on`、`cancel_directions` 等业务定义字段**。

```
1. 读 _root.yaml → 看 children 的 id/name/keywords
2. 结合聊天关键词 + 状态简报 → 选择进入哪个分支
3. 读该分支的 _node.yaml → 看 children
4. 继续向下匹配
5. 能确定就继续深入，不确定就停下
6. 输出：最终定位到的节点 ID（一个或多个）
```

每轮最多 3-4 次 read。

### 8.2 Agent 的输出

Agent 只输出节点 ID，不输出任何内容。

单路径：
```
fuzzy_intent
```

多路径（不同分支都匹配）：
```
project_saving, merchant_search
```

停在父节点（子节点分不清）：
```
confirm_project
```

### 8.3 多路径命中规则

| 情况 | 处理 |
|------|------|
| 多个匹配在同一条路径上（祖先-后代） | 输出最深的那个 ID |
| 多个匹配在不同分支上 | 输出多个 ID，逗号分隔 |
| 同一父节点下分不清哪个子节点 | 输出父节点 ID |

核心规则：**能确定就往下走，不确定就停住，绝不硬猜。**

## 9. 代码层的内容组装

Agent 输出节点 ID 后，代码层负责组装 MainAgent 看到的 Markdown。

### 9.1 组装逻辑

```python
def assemble_slice(tree: BusinessMap, node_ids: list[str]) -> str:
    """根据节点 ID 列表，组装从根到每个节点的完整路径切片"""
    seen_ids: set[str] = set()
    sections: list[str] = []
    
    for i, node_id in enumerate(node_ids):
        node: TreeNode = tree.find(node_id)
        path: list[TreeNode] = tree.path_from_root(node)
        
        for ancestor in path:
            if ancestor.id in seen_ids:
                continue
            seen_ids.add(ancestor.id)
            sections.append(format_node(ancestor))
        
        if i < len(node_ids) - 1:
            sections.append("---")
    
    depth: int = max(
        len(tree.path_from_root(tree.find(nid))) for nid in node_ids
    ) - 1
    header: str = f"定位深度：{depth}"
    if len(node_ids) > 1:
        header += "（多路径）"
    
    return header + "\n\n" + "\n\n".join(sections)


def format_node(node: TreeNode) -> str:
    """把单个节点的 YAML 内容格式化为一段 Markdown"""
    parts: list[str] = [f"### {node.name}"]
    
    if node.description:
        parts.append(node.description.strip())
    if node.checklist:
        parts.append("待办：")
        for item in node.checklist:
            parts.append(f"- {item}")
    if node.output:
        parts.append("产出：")
        for item in node.output:
            parts.append(f"- {item}")
    if node.depends_on:
        parts.append("依赖：")
        for dep in node.depends_on:
            parts.append(f"- {dep}")
    if node.cancel_directions:
        parts.append("取消走向：")
        for reason, direction in node.cancel_directions.items():
            parts.append(f"- {reason} → {direction}")
    
    return "\n".join(parts)
```

### 9.2 组装保证

- **零失真**：Markdown 中的所有文本直接来自 YAML 文件原文
- **格式稳定**：每个节点一个 `###` 段落，层数不限
- **去重**：多路径命中时，共同祖先只输出一次
- **可测试**：给定节点 ID，输出完全确定，可以写单元测试

## 10. 最终输出格式（代码层组装结果）

### 10.1 格式规则

输出是一段 Markdown，由路径上每个节点的内容段落依次组成。

- 开头一行标注定位深度
- 每个节点一个 `###` 段落
- 段落内包含该节点的 description、checklist、output、depends_on、cancel_directions
- 有多少层就有多少段，不硬编码层级名称
- 多路径命中时用 `---` 分隔，共同根只出一次
- 全部使用业务语言，不暴露内部 id 或文件路径

### 10.2 示例：浅定位（第 1 层）

用户说："我车该保养了，想省点钱"
定位路径：root → project_saving

```markdown
定位深度：1

### 养车预订业务地图
帮助车主完成从需求沟通到预订执行的完整流程。
project_saving 和 merchant_search 可交叉进行。
确认了项目就可以开始搜商户，不必等省钱方案完全敲定。
booking 必须在前两阶段基本完成后启动。

### 沟通项目需求与省钱方案
本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。
通常按确认项目 → 特殊需求 → 省钱方法顺序推进。
车主急切时可加快节奏，特殊需求可简单确认后跳过。

待办：
- 确认车主的养车项目
- 了解是否有特殊需求
- 沟通省钱方法和偏好

产出：
- 已确认的养车项目列表
- 特殊需求记录（如有）
- 省钱方案偏好

取消走向：
- 车主不想做了 → 记录意向，结束流程
- 车主要自己去店里问 → 提供商户推荐后结束
```

### 10.3 示例：深定位（第 3 层）

用户说："凯美瑞跑了5万公里，上次5000公里前保养的"
定位路径：root → project_saving → confirm_project → fuzzy_intent

```markdown
定位深度：3

### 养车预订业务地图
帮助车主完成从需求沟通到预订执行的完整流程。
project_saving 和 merchant_search 可交叉进行。
确认了项目就可以开始搜商户，不必等省钱方案完全敲定。
booking 必须在前两阶段基本完成后启动。

### 沟通项目需求与省钱方案
本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。
通常按确认项目 → 特殊需求 → 省钱方法顺序推进。
车主急切时可加快节奏，特殊需求可简单确认后跳过。

待办：
- 确认车主的养车项目
- 了解是否有特殊需求
- 沟通省钱方法和偏好

产出：
- 已确认的养车项目列表
- 特殊需求记录（如有）
- 省钱方案偏好

取消走向：
- 车主不想做了 → 记录意向，结束流程
- 车主要自己去店里问 → 提供商户推荐后结束

### 确认养车项目
把车主的表述匹配到具体的养车项目。
大部分情况能快速通过，不需要过度追问。

待办：
- 识别车主描述对应的项目类型
- 匹配到具体项目
- 获得车主确认

产出：
- 已确认的养车项目名称
- 项目对应的标准服务内容

取消走向：
- 车主不确定要做什么 → 引导到模糊意图场景
- 车主想先了解价格 → 跳转到确认省钱方法节点

### 模糊意图场景
车主没有直接说项目名称，但提供了里程、时间、使用场景等间接信息。
车主只是觉得"该保养了"，但不确定具体做什么。
结合里程和上次保养间隔推荐合适项目。
如果无法判断，简单问一句即可，不要连续追问。

依赖：
- 车型信息
- 里程或上次保养时间

待办：
- 结合里程和保养间隔推荐项目
- 简单确认即可

产出：
- 推荐的养车项目

取消走向：
- 车主仍然不确定 → 建议车主到店检查，提供商户推荐
```

### 10.4 示例：多路径命中

用户说："行就这个吧，帮我找个附近便宜的店"
定位路径：同时命中 project_saving 和 merchant_search

```markdown
定位深度：1（多路径）

### 养车预订业务地图
帮助车主完成从需求沟通到预订执行的完整流程。
project_saving 和 merchant_search 可交叉进行。
确认了项目就可以开始搜商户，不必等省钱方案完全敲定。
booking 必须在前两阶段基本完成后启动。

---

### 沟通项目需求与省钱方案
本阶段目标是把车主模糊的养车需求收束成明确的项目和省钱方案。
通常按确认项目 → 特殊需求 → 省钱方法顺序推进。

待办：
- 确认车主的养车项目
- 了解是否有特殊需求
- 沟通省钱方法和偏好

产出：
- 已确认的养车项目列表
- 特殊需求记录（如有）
- 省钱方案偏好

---

### 筛选匹配商户
根据车主的项目和偏好搜索匹配的商户。
通常先搜索，再比较，最后确认选择。

依赖：
- 需要已确认的养车项目（confirm_project 的 output）

待办：
- 搜索匹配商户
- 比较商户
- 确认商户选择
```

## 11. 深树场景下的渐进下钻

假设业务树有 5 层，用户第一句话只能定位到第 1 层。

### 11.1 第一轮

用户："我想做个保养，顺便看看哪家划算"

**BusinessMapAgent**：只命中 `project_saving`（第 1 层），输出根 + 第 1 层内容。不硬猜更深的节点。

**MainAgent**：看到浅层切片，这不是失败。按当前层 todo 开始向用户补事实（车型？上次保养？）。

### 11.2 第二轮

用户补充："凯美瑞，上次保养是5000公里前"

**BusinessMapAgent**：基于新信息下钻到 `confirm_project → fuzzy_intent`（第 3 层），输出根 + 第 1 层 + 第 2 层 + 第 3 层。

**MainAgent**：看到更细的切片，包含"结合里程和保养间隔推荐项目"的指引，于是调用 match_project 匹配。

### 11.3 第三轮

用户确认项目，说"帮我找个附近的店"

**BusinessMapAgent**：项目已确认（从运行状态中看到），用户意图转向商户搜索。输出 merchant_search 分支的切片。

**MainAgent**：看到商户搜索切片，开始获取位置、搜索商户。

**整个过程是渐进收敛的**，BusinessMapAgent 每次只定位到能确定的层级，MainAgent 补充信息后再下钻。

## 12. MainAgent 状态维护

MainAgent 不维护整棵业务地图的状态，只维护**当前任务实例的运行态**。

### 12.1 状态格式：缩进 Markdown 树

使用缩进式 Markdown 清单，层级用缩进表达，状态用标记，产出用 `→` 内联。这棵树随着对话推进**渐进生长**——走到哪，展开到哪。

状态标记：`[完成]` / `[跳过]` / `[进行中]` / `[ ]`（未开始）
当前焦点：`← 当前`
产出结果：`→` 后面直接写

#### 初始态（刚进入，BusinessMapAgent 给了第一层切片）

```markdown
- [ ] 沟通项目需求与省钱方案
- [ ] 筛选匹配商户
- [ ] 执行预订
```

#### 开始推进后（确认项目中）

```markdown
- [进行中] 沟通项目需求与省钱方案
  - [进行中] 确认养车项目 ← 当前
  - [ ] 确认特殊需求
  - [ ] 确认省钱方法
- [ ] 筛选匹配商户
- [ ] 执行预订
```

#### 深入到第 3 层（项目确认走完，省钱方法正在推进）

```markdown
- [进行中] 沟通项目需求与省钱方案
  - [完成] 确认养车项目 → 小保养（换机油+机滤），project_id: proj_xiaobaoyang
    - [完成] 模糊意图场景 → 结合里程推荐，匹配成功
  - [跳过] 确认特殊需求 → 车主无特殊要求
  - [进行中] 确认省钱方法
    - [进行中] 优惠券方案
      - [完成] 检查优惠券可用性 → 9折券可用，预计节省40-60元
      - [进行中] 确认车主偏好 ← 当前
- [ ] 筛选匹配商户
- [ ] 执行预订
```

#### 跨阶段后（省钱确认完，进入商户筛选）

```markdown
- [完成] 沟通项目需求与省钱方案
  - [完成] 确认养车项目 → 小保养（换机油+机滤），project_id: proj_xiaobaoyang
    - [完成] 模糊意图场景 → 结合里程推荐，匹配成功
  - [跳过] 确认特殊需求 → 车主无特殊要求
  - [完成] 确认省钱方法 → 使用平台9折优惠券
    - [完成] 优惠券方案
      - [完成] 检查优惠券可用性 → 9折券可用
      - [完成] 确认车主偏好 → 用户选择9折券
- [进行中] 筛选匹配商户
  - [进行中] 搜索商户 ← 当前
  - [ ] 比较商户
  - [ ] 确认商户选择
- [ ] 执行预订
```

### 12.2 为什么用 Markdown 而不是 JSON

| | 缩进 Markdown | 嵌套 JSON |
|---|---|---|
| 层级表达 | 缩进天然表达父子关系 | 需要嵌套对象，层深了容易出错 |
| 产出记录 | `→` 内联，简洁 | 需要单独的 `outputs` 字段 |
| LLM 维护可靠性 | 高（编辑文本） | 低（JSON 层深后括号容易乱） |
| 可读性 | 一眼看出全局进度和当前位置 | 需要展开多层才能理解 |

### 12.3 传给小模型 Agent 的简报

MainAgent 内部维护完整的状态树，但传给小模型 Agent 的是一份压缩简报：

```
完整状态树（MainAgent 内部）          简报（传给小模型 Agent）

- [进行中] 沟通项目需求...           已完成：
  - [完成] 确认项目 → 小保养         - 确认养车项目 → 小保养
  - [跳过] 特殊需求                  - 确认特殊需求 → 已跳过
  - [进行中] 省钱方法                - 检查优惠券可用性 → 9折券可用
    - [进行中] 优惠券
      - [完成] 检查可用性            当前在做：
      - [进行中] 确认偏好 ← 当前     确认省钱方法 → 优惠券方案 → 确认车主偏好
```

简报规则：
- "已完成"列出所有 `[完成]` 节点的标题和产出
- "当前在做"用 `→` 串联从最近的顶层节点到 `← 当前` 的路径
- 不包含 `[ ]`（未开始）的节点
- 不包含内部 ID 或结构化数据

### 12.4 协作约束

1. MainAgent 持有真实运行状态（缩进 Markdown 树）
2. 触发时，MainAgent 将状态树压缩为自然语言简报
3. 小模型 Agent 读取简报 + 逐层读业务地图 → 输出节点 ID
4. 代码层根据 ID 组装 Markdown 切片
5. 切片注入 MainAgent 的 request_context
6. MainAgent 基于切片 + 自己的判断执行
7. MainAgent 执行后更新状态树（标记完成、记录产出、展开子项）

关键红线：
- 小模型 Agent 只输出节点 ID，不输出内容、不做判断
- 代码层组装的内容 100% 来自 YAML 原文
- MainAgent 的状态不受小模型影响
- 后续节点应依赖状态树中的真实产出，而不是依赖模型短期记忆

## 13. 风险与缓解

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 定位错误 | 小模型把对话匹配到错误的节点 ID | 充分覆盖 keywords；用状态简报辅助定位；prompt 强调"不确定就停在父节点" |
| 输出了不存在的 ID | 小模型编造了一个业务地图中没有的 ID | 代码层校验 ID 是否存在于树中，不存在则忽略或 fallback |
| 树太深导致输出过长 | 5 层路径拼出来的 Markdown 太长 | 控制合理深度（建议 4-5 层以内）；深层可合并为单个叶节点 |
| 中间节点内容空洞 | 停在某层但该层没有有用信息 | 设计约束：每个节点必须有 description + checklist |
| 指引与 Skill 冲突 | 切片内容和 Skill 内部流程不一致 | 切片只写业务策略和判断依据，Skill 管执行细节和工具调用 |
| 节点产出丢失 | MainAgent 忘记记录某个节点的产出 | prompt 中强调：每完成一个节点必须更新状态树 |
| 多路径输出混淆 | MainAgent 分不清两条路径的内容 | 代码层用 `---` 明确分隔，共同祖先去重 |

## 14. 设计决策记录

本方案经过多轮迭代，以下记录关键决策及其理由，帮助实现者理解"为什么是这样"而不是"那样"。

### 14.1 为什么不用知识图谱（KG）

| 维度 | KG | YAML 文件树 |
|------|-----|-------------|
| 编辑门槛 | 需要图数据库 + 专用工具 | 文本编辑器即可 |
| 版本管理 | 需要额外方案 | Git 天然支持 |
| 业务迭代速度 | 改图谱结构成本高 | 改 YAML 文件成本极低 |
| 运维依赖 | 需要部署图数据库服务 | 无额外依赖，文件系统即可 |

业务流程变化快，需要业务人员能直接编辑。YAML 文件 + 目录结构是最低门槛的方案。

### 14.2 为什么小模型只输出 ID，不输出内容

早期方案让小模型读 YAML 后自行组装 Markdown 输出。问题：
- 小模型容易**遗漏** YAML 中的关键字段（如 `cancel_directions`）
- 小模型容易**改写**原文措辞（如把"不要过度追问"改成"可以多问几个问题"）
- 小模型可能**编造**不存在的业务指引

改为"ID only + 代码组装"后：
- 小模型的任务极简：关键词匹配 → 输出 ID，错误空间大幅缩小
- 代码层组装 100% 来自 YAML 原文，可写单元测试验证

### 14.3 为什么小模型是 Agent（带 read 工具）而不是简单 LLM 调用

业务地图大小未知。如果整棵树骨架能塞进一个 prompt，简单 LLM 调用即可。但现实中：
- 树可能有几十甚至上百个节点
- 每个节点的 keywords 加起来 token 量不可控
- Agent 模式可以逐层读取，每次只看当前层的 children，按需深入

### 14.4 为什么用 Markdown 而不是 JSON 作为输出格式

指 BusinessMapAgent → MainAgent 的切片格式和 MainAgent 内部状态格式。

| 维度 | Markdown | JSON |
|------|----------|------|
| LLM 生成可靠性 | 高，自由文本 | 低，层深后括号/引号容易乱 |
| 层级表达 | `###` 标题 + 缩进自然表达 | 嵌套对象，读起来费劲 |
| 内容丰富度 | 可内嵌任意文本段落 | 字段值只能是字符串，丢失格式 |
| 任意深度支持 | `###` 段落数量随深度线性增长 | 嵌套层数越深越难维护 |

### 14.5 为什么不让 Navigator 做业务判断

早期方案中 Navigator 不仅定位，还给出"建议下一步做 X"这类指令。问题：
- **角色越位**：MainAgent 才是对话的主控者，让小模型做判断等于让"导航仪"替代"司机"
- **信息不对称**：小模型看不到完整对话历史和工具返回结果，判断依据不充分
- **责任不清**：出错时无法判定是 Navigator 建议错了还是 MainAgent 执行错了

最终 Navigator 的职责被严格限定为"在业务地图上定位"，所有执行决策归 MainAgent。

### 14.6 为什么 MainAgent 状态用自然语言简报传给小模型

MainAgent 的完整状态树是一棵带缩进的 Markdown 树（可能很长）。直接传给小模型的问题：
- 小模型 context window 有限
- 结构化文本需要小模型理解缩进层级语义
- 大量 `[ ]`（未开始）节点是噪音

转换为自然语言简报后：
- 只保留"已完成"和"当前在做"，信息密度高
- 小模型只需做文本理解，不需要解析结构
- 简报由 MainAgent（大模型）生成，质量有保障

## 15. 实现路线图

以下是建议的实现顺序。每个 Phase 可独立测试，前一个 Phase 的产物是后一个的输入。

### Phase 1：业务地图基础设施

**目标**：能加载和遍历 YAML 业务树。

**新建文件**（建议位置）：
- `extensions/hlsc/business_map/model.py` — `TreeNode`、`ChildRef` 等 Pydantic 模型
- `extensions/hlsc/business_map/loader.py` — `BusinessMap` 类（加载、查找、路径计算）
- `extensions/hlsc/business_map/` 目录的 `__init__.py`
- `business-map/` — 示例 YAML 文件（按第 7 节目录约定）
- `tests/test_business_map_loader.py` — 单元测试

**要做的事**：

1. 定义 `TreeNode` 数据模型（Pydantic BaseModel）
   - 字段对应 7.2 节定义的业务定义字段 + 导航结构字段
   - `cancel_directions: dict[str, str] | None`
   - `children: list[ChildRef] | None`（ChildRef 包含 id, name, keywords, path, optional, depends_on）

2. 实现 `BusinessMap` 类
   - `load(root_dir: str | Path)` → 递归读取 YAML 目录树，构建内存中的树
   - `find(node_id: str) -> TreeNode` → 按 ID 查找节点（加载时建好 ID → node 的索引）
   - `path_from_root(node: TreeNode) -> list[TreeNode]` → 返回从根到该节点的路径
   - 加载时校验：ID 全局唯一、必填字段存在、`description` 和 `checklist` 不能同时为空

3. 创建示例 YAML 文件（按第 7.4 节示例内容）

4. 编写单元测试（加载、查找、路径、校验失败场景）

**验收标准**：`uv run pytest tests/test_business_map_loader.py` 全绿。

### Phase 2：代码层内容组装

**目标**：给定节点 ID 列表，输出格式正确的 Markdown 切片。

**新建文件**：
- `extensions/hlsc/business_map/assembler.py` — `assemble_slice()` + `format_node()`
- `tests/test_business_map_assembler.py`

**要做的事**：

1. 实现 `assemble_slice()` 和 `format_node()`（参考第 9 节伪代码）
2. 实现 ID 校验：不存在的 ID 忽略或返回 fallback 提示
3. 编写单元测试：浅定位、深定位、多路径、去重、非法 ID

**验收标准**：输出与第 10 节三个示例一致（可做 snapshot 测试）。

### Phase 3：小模型 Agent

**目标**：接收聊天输入 + 状态简报，输出节点 ID。

**新建文件**：
- `extensions/hlsc/business_map/navigator_agent.py` — 小模型 Agent 定义
- `extensions/hlsc/business_map/prompts/navigator_system.md` — system prompt
- `tests/test_navigator_agent.py`

**要做的事**：

1. 编写 system prompt
   - 明确角色：你是一个业务地图定位器
   - 输入说明：会收到用户消息和状态简报
   - 工具说明：你有一个 read_yaml 工具，用来读取 YAML 文件
   - 输出格式：只输出逗号分隔的节点 ID，不输出任何其他内容
   - 核心规则：能确定就往下走，不确定就停住，绝不硬猜
   - few-shot 示例

2. 实现 Agent（使用 Pydantic AI Agent）
   - 挂载 read 工具（限制只能读 `business-map/` 目录下的 YAML 文件）
   - 解析输出为 `list[str]`

3. 编写测试（FunctionModel mock 测试工具调用流程）

### Phase 4：MainAgent 集成

**目标**：在 MainAgent 对话循环中按需触发 BusinessMapAgent。

**修改文件**：
- `mainagent/src/app.py` — 注册触发 hook 或修改流程
- `mainagent/prompts/templates/AGENT.md` — 增加状态树维护和切片理解的指引

**新建文件**：
- `extensions/hlsc/business_map/trigger.py` — 触发判断逻辑
- `extensions/hlsc/business_map/briefing.py` — 状态树 → 简报压缩
- `extensions/hlsc/business_map/orchestrator.py` — 编排完整流程

**要做的事**：

1. 实现触发判断（第 5 节规则）
2. 实现状态树 → 简报压缩（第 12.3 节规则）
3. 编排完整流程（第 12.4 节协作约束）
4. 修改 MainAgent prompt

### Phase 5：端到端验证

对照第 11 节的场景做人工验证或自动化测试：
1. 浅定位 → 渐进下钻（3 轮对话）
2. 多路径命中
3. 取消场景
4. 大树性能（50+ 节点）

## 16. 术语表

| 术语 | 含义 |
|------|------|
| **MainAgent** | 与用户直接对话的主 Agent（大模型），负责执行和状态维护 |
| **BusinessMapAgent** | 本文档设计的业务导航系统，包含小模型 Agent + 代码层 |
| **小模型 Agent** | BusinessMapAgent 中负责定位的 LLM Agent，只输出节点 ID |
| **代码层** | BusinessMapAgent 中负责内容组装的确定性代码，不涉及 LLM |
| **业务地图** | YAML 文件树，存储完整的业务流程定义 |
| **切片** | 从根到目标节点路径上所有节点内容组装成的 Markdown 文本 |
| **状态树** | MainAgent 维护的缩进 Markdown 清单，记录当前任务进度 |
| **简报** | 状态树的压缩版（自然语言），传给小模型 Agent 辅助定位 |
| **request_context** | Pydantic AI 框架中注入额外上下文的机制 |
| **A2A** | Agent-to-Agent 通信协议，BusinessMapAgent **不**使用此模式（进程内调用） |
