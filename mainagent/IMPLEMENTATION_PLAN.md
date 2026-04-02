# 6 场景架构实施方案

## 架构概览

取消 S1/S2 阶段概念，改为 6 个平等场景，由 BMA 每轮分类路由。

```
用户消息 → Hook → BMA classify → scenes 列表
                                    │
                                    ├─ [] → guide（引导，有查询工具，无 confirm_booking）
                                    ├─ ["platform"] → platform（平台九折预订）
                                    ├─ ["searchshops"] → searchshops（找商户）
                                    ├─ ["searchcoupons"] → searchcoupons（找优惠）
                                    ├─ ["insurance"] → insurance（保险竞价）
                                    └─ 多个 → orchestrator（大管家，通过 delegate 协调子 agent）
```

## 目录结构

```
mainagent/prompts/templates/
├── SYSTEM.md                    # 共享基础
├── SOUL.md                      # 共享风格
├── guide/
│   ├── AGENT.md                 # 引导：澄清意图 + 试探性查询
│   └── OUTPUT.md                # 极简，无 spec 卡片
├── platform/
│   ├── AGENT.md                 # 平台九折预订流程
│   └── OUTPUT.md                # ProjectCard + AppointmentCard
├── searchshops/
│   ├── AGENT.md                 # 找商户、对比、给联系方式
│   └── OUTPUT.md                # ShopCard + invite_shop action
├── searchcoupons/
│   ├── AGENT.md                 # 找优惠、展示省钱方式
│   └── OUTPUT.md                # CouponCard + ShopCard
├── insurance/
│   ├── AGENT.md                 # 保险竞价全流程
│   └── OUTPUT.md                # 保险相关卡片
└── orchestrator/
    ├── AGENT.md                 # 大管家：意图判断 + delegate 分配
    └── OUTPUT.md                # 空（orchestrator 透传子 agent 输出）
```

## 配置文件 stage_config.yaml

```yaml
scenes:
  guide:
    prompt_parts: [SYSTEM.md, SOUL.md, guide/OUTPUT.md]
    agent_md: guide/AGENT.md
    tools:
      - classify_project
      - search_shops
      - search_coupon
      - list_user_cars
      - collect_car_info
      - collect_location
      - geocode_location
    skills:
      - saving-methods
      - platform-intro

  platform:
    prompt_parts: [SYSTEM.md, SOUL.md, platform/OUTPUT.md]
    agent_md: platform/AGENT.md
    tools:
      - match_project
      - search_shops
      - search_coupon
      - collect_car_info
      - collect_location
      - geocode_location
      - list_user_cars
      - confirm_booking
    skills:
      - saving-playbook

  searchshops:
    prompt_parts: [SYSTEM.md, SOUL.md, searchshops/OUTPUT.md]
    agent_md: searchshops/AGENT.md
    tools:
      - search_shops
      - collect_location
      - geocode_location
      - match_project
      - list_user_cars
      - confirm_booking
    skills:
      - saving-playbook

  searchcoupons:
    prompt_parts: [SYSTEM.md, SOUL.md, searchcoupons/OUTPUT.md]
    agent_md: searchcoupons/AGENT.md
    tools:
      - search_coupon
      - search_shops
      - classify_project
      - match_project
      - collect_location
      - geocode_location
      - list_user_cars
      - confirm_booking
    skills:
      - saving-playbook

  insurance:
    prompt_parts: [SYSTEM.md, SOUL.md, insurance/OUTPUT.md]
    agent_md: insurance/AGENT.md
    tools:
      - match_project
      - search_shops
      - collect_car_info
      - collect_location
      - geocode_location
      - list_user_cars
      - confirm_booking
    skills:
      - insurance-bidding

  orchestrator:
    prompt_parts: [SYSTEM.md, SOUL.md, orchestrator/OUTPUT.md]
    agent_md: orchestrator/AGENT.md
    tools:
      - delegate
    skills: []
```

## delegate 工具设计

```python
async def delegate(
    ctx: RunContext[AgentDeps],
    agent_name: str,    # "platform" | "searchshops" | "searchcoupons" | "insurance"
    task: str,          # 具体任务描述
    context: str = "",  # 上下文摘要（orchestrator 组织）
) -> str:
    """委派任务给专业 agent，返回执行结果。"""
    # 1. 从 _config_loader 读取对应场景配置
    # 2. 构建完整 system prompt（prompt_parts + agent_md 拼接）
    # 3. 创建临时 Agent 实例（该场景的 prompt + tools）
    # 4. 用 context + task 作为输入，静默运行（不流式、不 interrupt）
    # 5. 返回文本结果
```

不能 delegate 给 guide 和 orchestrator 自身。

## 需要改动的文件

### 核心路由层
| 文件 | 改动 |
|------|------|
| business_map_hook.py | 重写：去掉 S1/S2，直接 BMA → scene → 加载配置 |
| prompt_loader.py | 重写：按 prompt_parts 列表 + agent_md 拼接 |
| stage_config.yaml | 重写：扁平 scenes 结构 |
| deps.py | 去掉 current_stage，保留 current_scene + current_scene_agent_md |
| app.py | 注册 delegate 工具，清理旧 imports |

### 新建文件
| 文件 | 说明 |
|------|------|
| extensions/hlsc/tools/common/delegate.py | delegate 工具实现 |
| extensions/hlsc/tools/prompts/delegate.md | delegate 工具 prompt |
| 6 个场景目录各 2 个文件（AGENT.md + OUTPUT.md） | 共 12 个文件 |

### 删除文件
| 文件 | 理由 |
|------|------|
| AGENT_S1.md | 被 guide/AGENT.md 替代 |
| AGENT_S2.md | 被各场景 AGENT.md 替代 |
| AGENT_S2_saving.md | 被 searchcoupons/AGENT.md 替代 |
| AGENT_S2_shop.md | 被 searchshops/AGENT.md 替代 |
| AGENT_S2_insurance.md | 被 insurance/AGENT.md 替代 |
| AGENT_S2_none.md | 被 guide/AGENT.md 替代 |
| extensions/hlsc/tools/s1/proceed_to_booking.py | BMA 路由替代升级机制 |
| extensions/hlsc/tools/s1/classify_project.py | guide 场景用 classify_project（common 或保留 s1） |

### 清理
| 项 | 说明 |
|----|------|
| UserStatService | 简化或删除（BMA 替代 S1/S2 判断）|
| OUTPUT.md（Jinja2 版） | 删除，各场景有自己的 OUTPUT.md |
| deps.current_stage | 删除 |
| deps.system_prompt_override | 评估是否还需要 |

## AGENT.md 四段式模板

每个场景的 AGENT.md 遵循统一结构：

```markdown
## 使命
（1-2 句，聚焦当前场景的核心任务）

## 能力边界
（3-5 条，明确能做什么、不能做什么）

## 推进原则
（3-5 条，本场景特有的行为准则）

## 可用 skill
（列出本场景可激活的 skill 及触发条件）
```

## 安全边界

- guide 没有 confirm_booking（不能触达商家）
- 其他 4 个业务场景有 confirm_booking
- orchestrator 没有 confirm_booking（通过 delegate 间接调用，子 agent 在静默模式下不能 interrupt）
- confirm_booking 的 interrupt 保护仍然有效（前端弹确认卡片）

## 测试要点

1. BMA 分类：各种用户输入 → 正确场景
2. Hook 路由：scenes 列表 → 正确配置加载
3. delegate 工具：orchestrator → 子 agent → 返回结果
4. prompt 加载：prompt_parts + agent_md 正确拼接
5. 场景切换：连续对话中场景变化时行为正常
6. 安全：guide 不能调 confirm_booking
