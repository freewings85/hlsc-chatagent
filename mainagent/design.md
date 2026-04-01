# MainAgent 设计方案

## 产品定位

帮助用户制定省钱方案并完成下单服务。

## 两阶段设计：S1 体验 / S2 下单

### 为什么要分阶段

三层原因：

1. **用户体验** — 产品上线初期大量用户只是体验，不是真正要下单。对所有人走全流程（要 VIN、要位置、确认时间），体验用户会觉得繁琐
2. **商家保护** — 系统后台对接真实商家，S2 的工具会触发真实的商家交互（发预订、发竞价、推送信息）。未验证用户如果能触发这些操作，hacker 或破坏者会给商家带来大量骚扰，损害商家权益
3. **转化漏斗** — S1 引导用户了解省钱价值 → 用户建立信任后自然过渡到 S2 → 完成下单。S1/S2 分离本身就是转化路径

### S1 核心使命

**引导用户尽快确定省钱方法**，不是被动回答问题。

主线漏斗：弄清项目 → 展示省钱方法 → 确认省钱方式。不管用户从什么话题进来，agent 都要把对话往主线拉。

### 阶段定义

| | S1 体验模式 | S2 下单模式 |
|--|-----------|-----------|
| **目标** | 引导用户确定省钱方法，建立信任 | 收集精确信息，完成下单 |
| **用户画像** | 初次来、随便问问、未提供身份信息 | 下过单、提供过 VIN、明确要预约 |
| **Tools** | 查询搜索 + 信息采集 + confirm_saving_plan | S1 全部 + confirm_booking |
| **Skills** | saving-methods, platform-intro | saving-playbook, booking-execution |
| **AGENT.md** | AGENT_S1.md（主动引导，转化漏斗） | AGENT_S2.md（高效推进，先做再问） |

### S1 工具集

查询搜索（不触达商家）：
- classify_project — 粗粒度项目分类（归到大类，不调外部 API）
- search_shops — 搜索商户
- call_recommend_project — 推荐项目
- list_user_cars — 查用户车库

信息采集：
- ask_user_car_info — 引导用户提供车型/VIN
- ask_user_location — 引导用户提供位置
- geocode_location — 位置确认

升级触发：
- confirm_saving_plan — 确认省钱方案（内部触发 S2 升级）

### S2 工具集

S1 全部工具（除 classify_project / confirm_saving_plan）+：
- match_project — 精确项目匹配（调外部 API）
- call_query_codingagent — 复杂数据查询
- get_representative_car_model — 模糊匹配车型
- confirm_booking — 预订确认（触达商家）

### 省钱方式

1. **平台优惠方式** — 零部件九折、优惠券等平台提供的优惠，需确认项目
2. **保险竞价** — 保险类项目多商户竞价 PK
3. **商户自有优惠** — 部分商户有折扣、满减、会员价等活动
4. 用户不关心优惠 → 跳过省钱，引导提供车辆信息（硬信号）再进入 S2

## 阶段判断

### 判断流程

```
① UserStatService.get_user_stat(user_id) → 用户状态
② 硬信号命中？→ S2
③ 否则 → S1
```

Hook 只做这一件事：查硬信号，决定 S1/S2，加载对应的 tools + skills + AGENT.md。

### S2 硬信号（UserStatService，确定性）

- 用户历史下过单
- 提供过 VIN / 行驶证
- 绑定过车辆到平台
- 历史 session 中通过 confirm_saving_plan 升级过

### S1 → S2 升级的两条路径

**路径 A：确认省钱方式（confirm_saving_plan 工具触发）**

用户在 S1 漏斗中确认了省钱方式（平台优惠 / 保险竞价 / 商户优惠）→ S1 agent 调用 confirm_saving_plan → 内部调 upgrade_to_s2() 写入硬信号 → 下一轮自动 S2。

**路径 B：不需要优惠（硬信号触发）**

用户明确说不需要优惠 → S1 agent 引导用户提供车辆信息（VIN / 绑车）→ UserStatService 产生硬信号 → 下一轮自动 S2。

### 阶段切换

- S1 → S2：硬信号产生时，**下一轮生效**
- S2 不回退到 S1：一旦升级就保持

## 文件结构

```
mainagent/
├── stage_config.yaml      → S1/S2 的 tools + skills
├── prompts/templates/
│   ├── AGENT_S1.md        → S1（引导漏斗）
│   ├── AGENT_S2.md        → S2（全流程推进）
│   ├── SYSTEM.md
│   ├── SOUL.md
│   └── OUTPUT.md
├── src/
│   ├── app.py             → 注册工具 + StageHook
│   ├── business_map_hook.py → StageHook：查 UserStatService → 设置 tools/skills/stage
│   ├── hlsc_context.py
│   └── prompt_loader.py   → 根据 current_stage 选 AGENT.md
```

```
extensions/skills/
├── saving-methods/         → S1：省钱方式介绍
├── platform-intro/         → S1：话痨平台介绍
├── saving-playbook/        → S2：省钱下单全流程剧本
├── booking-execution/      → S2：预订执行流程
└── README.md
```
