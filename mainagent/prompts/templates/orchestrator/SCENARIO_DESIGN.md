# Orchestrator 多意图编排场景设计

## 编排原则速记

| 原则 | 说明 |
|------|------|
| **分析优先级** | platform（下单）> insurance（保险）> searchcoupons（优惠）> searchshops（找店） |
| **并行规则** | 无依赖的子任务同时 delegate |
| **依赖规则** | A 结果作为 B 输入时，等 A 完成后传给 B |
| **Context 传递** | delegate 时明确告知已知条件（车型、位置、项目等） |
| **结果合并** | 整合各子 agent 返回，组织统一回复给用户 |

---

## 8 个典型场景

### 场景 1：找店 + 查优惠（轻量级复合）

**用户消息**  
"北京朝阳区想做个保养，有什么优惠吗？"

**BMA 返回**  
```
[searchshops, searchcoupons]
```

**编排方案**  
- **并行执行**（无依赖）
  - Task A: searchshops → 搜周边修理店，收集 Where（朝阳区）
  - Task B: searchcoupons → 搜保养优惠，需要项目+位置

- **Context 传递**
  - searchcoupons 预先给 semantic_query="保养优惠"、已知位置坐标

- **结果合并方式**
  ```
  ✓ 周边 3 家店的对比（价格、评分）
  ✓ 对应这些店的优惠活动（如果有）
  → 完整决策：在哪家店做、用什么优惠、省多少钱
  ```

**依赖关系图**
```
用户输入
  ├─ searchshops (并行)
  │   └─ 搜店
  ├─ searchcoupons (并行)
  │   └─ 搜优惠
  └─ 合并 → 推荐优惠+店铺组合
```

---

### 场景 2：下单 + 查优惠（中等复合）

**用户消息**  
"我要在上海浦东换机油，有没有优惠能再省一点？"

**BMA 返回**  
```
[platform, searchcoupons]
```

**编排方案**  
- **串行执行**（有依赖）
  - Task A: platform 第一轮 → 匹配项目（机油更换）、搜店、得到参考价
  - Task B: searchcoupons 第二轮 → 使用 platform 返回的项目 ID，搜相关优惠

- **Context 传递**
  - platform delegate 时告知位置
  - platform 完成后，拿返回的 project_id 传给 searchcoupons

- **结果合并方式**
  ```
  ✓ 平台九折价格
  ✓ 匹配的商户优惠
  ✓ 方案对比：平台九折 vs 商户优惠 vs 组合省钱最多
  → 用户选择最优方案直接预订
  ```

**依赖关系图**
```
用户输入
  └─ platform (第一步)
      ├─ 匹配项目 → project_id
      └─ 搜店 → 参考价
           └─ searchcoupons (第二步，依赖 project_id)
                └─ 搜优惠
                     └─ 合并 → 省钱方案对比
```

**关键点**：platform 完成后立即 delegate searchcoupons，不等用户回应。

---

### 场景 3：下单 + 找店（中等复合）

**用户消息**  
"想在南京做大保养，你们平台上有哪些店？"

**BMA 返回**  
```
[platform, searchshops]
```

**编排方案**  
- **并行执行**（无依赖）
  - Task A: platform → 匹配项目、搜平台认可的店、给九折价格
  - Task B: searchshops → 搜全量商户、对比商户类型（4S/连锁/独立）

- **Context 传递**
  - 都告知位置（南京）
  - searchshops 作为补充视角

- **结果合并方式**
  ```
  ✓ 平台上的店 + 九折优惠方案
  ✓ 其他可选店 + 对比说明（4S 更贵但有质保，连锁店中等，独立厂最便宜）
  → 用户在两个维度做选择：是否用平台服务，选哪家店
  ```

**依赖关系图**
```
用户输入
  ├─ platform (并行)
  │   └─ 匹配大保养 → 九折方案
  ├─ searchshops (并行)
  │   └─ 商户对比
  └─ 合并 → 双视角决策
```

---

### 场景 4：找店 + 下单（中等复合）

**用户消息**  
"我在深圳想找一家靠谱的轮胎店，直接给我推荐吧。"

**BMA 返回**  
```
[searchshops, platform]
```

**编排方案**  
- **串行执行**（有依赖）
  - Task A: searchshops 优先 → 搜深圳周边轮胎店、展示对比
  - Task B: platform 后续 → 用户选定店后，进入平台预订流程

- **Context 传递**
  - searchshops 得到店铺列表
  - 等用户选店后，delegate platform 时告知 shop_id

- **结果合并方式**
  ```
  ✓ 搜店 → 对比 3-4 家轮胎店
  ✓ 用户选定 → 切换到平台预订
  ✓ 平台验证该店的轮胎项目、给九折价格、确认预订
  ```

**依赖关系图**
```
用户输入
  └─ searchshops (第一步)
      └─ 搜轮胎店 + 对比
           └─ 用户选店（shop_id）
                └─ platform (第二步，依赖 shop_id)
                     └─ 验证项目 + 给九折 + 确认预订
```

---

### 场景 5：下单 + 保险咨询（特殊复合）

**用户消息**  
"我车要做保养，同时想买保险，能一起处理吗？"

**BMA 返回**  
```
[platform, insurance]
```

**编排方案**  
- **并行执行**（完全无依赖）
  - Task A: platform → 保养下单全流程
  - Task B: insurance → 保险竞价流程

- **Context 传递**
  - 都传车型信息
  - platform 处理养车，insurance 处理保险

- **结果合并方式**
  ```
  ✓ 保养预订确认信息
  ✓ 保险竞价结果 → 最优赠返条件
  → 两个独立流程，并行走完，各自确认
  ```

**依赖关系图**
```
用户输入
  ├─ platform (并行)
  │   └─ 保养下单
  ├─ insurance (并行)
  │   └─ 保险竞价
  └─ 合并 → 两个确认消息
```

**关键点**：两个流程完全独立，最后各自给出确认，用户可分别操作。

---

### 场景 6：找优惠 + 保险（特殊复合）

**用户消息**  
"我想看看有什么优惠活动，也想知道买保险最便宜的方案。"

**BMA 返回**  
```
[searchcoupons, insurance]
```

**编排方案**  
- **并行执行**（无依赖）
  - Task A: searchcoupons → 搜养车优惠
  - Task B: insurance → 保险竞价

- **Context 传递**
  - searchcoupons 可能需要用户明确项目和位置
  - insurance 需要车型

- **结果合并方式**
  ```
  ✓ 养车优惠列表
  ✓ 保险最优方案
  → 两个独立主题，分别呈现
  ```

**依赖关系图**
```
用户输入
  ├─ searchcoupons (并行)
  │   └─ 搜优惠
  ├─ insurance (并行)
  │   └─ 保险竞价
  └─ 合并 → 两个优惠主题
```

---

### 场景 7：三路并行（重度复合）

**用户消息**  
"北京通州，想找一家店做保养，有优惠最好，同时我也想买保险，怎么省钱？"

**BMA 返回**  
```
[platform, searchshops, searchcoupons, insurance]
```

**编排方案**  
- **分层执行**
  - 第一层（并行）
    - Task A: searchshops → 搜通州周边店
    - Task B: searchcoupons → 搜保养优惠
    - Task C: insurance → 保险竞价
  - 第二层（串行，依赖 Task A）
    - Task D: platform → 可选，用户选定店后深化下单流程

- **Context 传递**
  - searchshops/searchcoupons 都给位置（通州）
  - insurance 给车型
  - platform 可能在用户选店后 delegate（取决于用户反馈）

- **结果合并方式**
  ```
  ✓ 周边店 + 对应优惠 + 省钱金额
  ✓ 保险最优方案
  → 完整省钱全景：养车选店省多少，优惠再省多少，保险另外省多少
  → 用户综合决策
  ```

**依赖关系图**
```
用户输入
  ├─ searchshops (第一层，并行)
  │   └─ 搜店
  ├─ searchcoupons (第一层，并行)
  │   └─ 搜优惠
  ├─ insurance (第一层，并行)
  │   └─ 保险竞价
  └─ platform (可选第二层，用户选店后)
      └─ 确认平台九折预订
           └─ 合并 → 全景省钱方案
```

**关键点**：
- 前三个 delegate 立即并行，不等用户选择
- platform 可能在用户反馈后才 delegate（看用户是否选平台的店）
- 或者立即 delegate platform 做预热，用户可随时切换

---

### 场景 8：优惠驱动的店铺下单链路（高意图明确）

**用户消息**  
"我看到有个轮胎优惠，想直接在你们平台预订，但不确定这家店靠不靠谱，能帮我对比一下吗？"

**BMA 返回**  
```
[searchcoupons, platform, searchshops]
```

**编排方案**  
- **串行流程**
  - Task A: searchcoupons 第一步 → 取出用户看到的优惠信息
  - Task B: searchshops 并行 → 搜该店的其他评价、对比其他店
  - Task C: platform 最后一步 → 用户选定后进入平台预订

- **Context 传递**
  - searchcoupons 可能需要从 session 恢复优惠
  - searchshops 拿到 coupon 的 shop_id 后搜该店详情 + 对比店
  - platform 拿确认的 shop_id 走预订

- **结果合并方式**
  ```
  ✓ 优惠详情（金额、条件、使用期限）
  ✓ 该店评价 + 对比店列表
  ✓ 用户信心后 → 平台九折预订
  ```

**依赖关系图**
```
用户输入
  └─ searchcoupons (第一步)
      ├─ 确认优惠信息 + shop_id
      └─ searchshops (第二步，依赖 shop_id)
          ├─ 该店详情 + 对比店
          └─ platform (第三步，用户确认后)
              └─ 平台预订流程
                   └─ 合并 → 优惠+对比+预订
```

---

### 场景 9：保险理赔咨询（单一场景边界）

**用户消息**  
"我的保险理赔有问题，想了解一下处理流程。"

**BMA 返回**  
```
[insurance]
```

**编排方案**  
- **不需要 orchestrator**，直接进 insurance 场景
  
- 如果 BMA 同时返回了 guide 或其他不相关的场景，orchestrator 可简单过滤：
  ```
  只 delegate insurance，忽略其他
  ```

**（此场景仅作参考，实际 BMA 应该只返回 insurance）**

---

### 场景 10：修复用户的高价下单决策（特殊复合）

**用户消息**  
"我刚在 A 店报价 3000 块做大保养，觉得可能贵了。你们平台有没有更便宜的方案？"

**BMA 返回**  
```
[platform, searchshops, searchcoupons]
```

**编排方案**  
- **分层执行**
  - 第一层（并行）
    - Task A: platform → 九折大保养方案（一般会便宜 10%）
    - Task B: searchshops → 其他店铺对比（可能便宜 30%-50%）
    - Task C: searchcoupons → 现有优惠活动（额外省钱）

- **Context 传递**
  - 都告知大保养需求
  - 可以明确告知"用户当前报价 3000"作为参考

- **结果合并方式**
  ```
  ✓ 平台九折：3000 × 90% = 2700 + 返佣优惠
  ✓ 其他店报价：2000-2500（可能便宜 33%）
  ✓ 优惠活动：可能额外减 100-300
  → 完整对比表：原价、平台、替代店、最终方案
  ```

**依赖关系图**
```
用户输入（已有报价 3000）
  ├─ platform (并行)
  │   └─ 九折方案 → 2700
  ├─ searchshops (并行)
  │   └─ 替代店对比
  ├─ searchcoupons (并行)
  │   └─ 优惠补充
  └─ 合并 → 省钱方案排序
```

---

## 编排决策矩阵

| 场景 | 子任务 1 | 子任务 2 | 子任务 3 | 依赖 | 并行 | 关键 Context |
|------|---------|---------|---------|------|------|-------------|
| 1 | searchshops | searchcoupons | - | 无 | ✓ | 位置、项目 |
| 2 | platform | searchcoupons | - | A→B | - | project_id 传递 |
| 3 | platform | searchshops | - | 无 | ✓ | 位置 |
| 4 | searchshops | platform | - | A→B | - | shop_id 传递 |
| 5 | platform | insurance | - | 无 | ✓ | 车型分离 |
| 6 | searchcoupons | insurance | - | 无 | ✓ | 位置、项目 |
| 7 | searchshops | searchcoupons | insurance | 无 | ✓✓✓ | 位置、车型 |
| 8 | searchcoupons | searchshops | platform | A→B→C | - | coupon_id、shop_id |
| 10 | platform | searchshops | searchcoupons | 无 | ✓✓ | 项目、参考价 |

---

## Orchestrator 的实现建议

### 1. 并行 Delegate 模板

```python
# 场景 1、3、5、6、7：并行任务
await delegate([
    ("searchshops", context_with_location),
    ("searchcoupons", context_with_project),
    ("insurance", context_with_car_model),  # 可选
])
→ 等所有返回后合并
```

### 2. 串行 Delegate 模板

```python
# 场景 2：platform 先，结果传给 searchcoupons
result_a = await delegate("platform", context)
project_id = extract_project_id(result_a)

result_b = await delegate("searchcoupons", {
    **context,
    "project_id": project_id,
})
→ 合并两个结果
```

### 3. 分层 Delegate 模板

```python
# 场景 7：第一层并行，第二层可选
results_layer1 = await delegate([
    ("searchshops", context),
    ("searchcoupons", context),
    ("insurance", context),
])

# 等用户选店后，可选第二层
if user_selected_shop:
    result_layer2 = await delegate("platform", {
        **context,
        "shop_id": selected_shop_id,
    })
    merge(results_layer1, result_layer2)
```

### 4. 结果合并策略

**并行场景合并**（场景 1、3、5、6、7）
```
1. 标题：完整问题总结
2. 各子任务结果单独呈现（分块）
3. 建议/对比（整合视角）
4. 用户下一步选项（直接链路）
```

**串行场景合并**（场景 2、4、8、10）
```
1. 第一个结果作为基础
2. 第二个结果作为深化/补充
3. 最终方案推荐（综合排序）
4. 用户直接行动链路
```

---

## 关键规则补充

### Context 传递清单

- **位置**（必传给 searchshops、searchcoupons）
  - 来源优先级：request_context > session_state > 用户提及
  - 需要经纬度 + 地名

- **项目**（必传给 platform、searchcoupons）
  - 来源：BMA 分类结果 或 session_state 复用
  - 格式：项目名称 或 project_id

- **车型**（必传给 platform、insurance）
  - 来源：session_state 或 collect_car_info
  - 需要清晰的车型 ID 和展示名

- **店铺**（必传给 platform）
  - 来源：searchshops 的返回结果
  - 需要 shop_id + 店名

- **优惠**（必传给 platform、searchcoupons 的书写确认）
  - 来源：searchcoupons 返回的 coupon_id + shop_id
  - 不能生造，必须来自本轮搜索结果

### 何时不用 Orchestrator

- BMA 返回 1 个场景 → 直接进该场景
- BMA 返回空 → 进 guide
- BMA 返回的全是非业务场景（如都是 guide）→ 进 guide

### 何时需要二次 Delegate

场景 2、4、8 等串行场景，常见：
- 第一个任务完成 → 等用户确认 → 第二个任务
- 或者第一个任务自动触发第二个（推荐用并行替代，如果可能）

---

## 合并结果的文案策略

### 找店 + 查优惠 的合并文案

```
你在 [地点] 想做 [项目]。我搜了一下：

📍 周边 3 家店对比：
- [店 1]：评分 4.8/5，[价格范围]，距离 [km]
- [店 2]：评分 4.5/5，[价格范围]，距离 [km]  
- [店 3]：评分 4.2/5，[价格范围]，距离 [km]

💰 对应这些店的优惠：
- [店 1] 有「春季保养 9 折」，可再省 [金额]
- [店 2] 没有当前优惠
- [店 3] 有「新客首单 8 折」，可再省 [金额]

✅ 我的建议：[店 1] + [优惠名] = 最终最便宜方案

你想选哪家店？
```

### 下单 + 查优惠 的合并文案

```
你想做 [项目]。我有 2 套方案给你对比：

方案 A - 平台九折预订：
- 价格：[参考价] × 90% = [九折价]
- 店：[平台认可的店]
- 额外优惠：[优惠名] 可再减 [金额]
- 最终价格：[最终价]

方案 B - 其他商户优惠：
- 店：[最便宜的店]
- 优惠：[优惠名] 直接 [折扣]
- 最终价格：[最终价]

✅ 推荐：方案 A 安心有保障，或方案 B 最便宜

你选哪一个？
```

---

## 下一步

1. **实现 delegate 的并行/串行调用** → 根据场景类型选择调用模式
2. **设计 context 传递的字段规范** → 明确每个场景需要的输入
3. **编写合并逻辑的模板代码** → 避免重复
4. **测试覆盖** → 每个场景至少 1 个真实用户消息
