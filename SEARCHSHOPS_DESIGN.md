# searchshops 灵活查询能力设计方案

## 问题分析

### 现状限制

当前 `search_shops` 工具参数有限：
```python
- latitude, longitude  # 位置（必填）
- shop_name           # 名称过滤
- top, radius         # 范围限制
- order_by            # 单维排序（distance/rating/tradingCount）
- commercial_type     # 类型过滤
- opening_hour        # 营业时间
- project_ids         # 项目过滤
- min_rating          # 最低评分
- min_trading_count   # 最低成交量
```

无法处理的场景：
1. **多维组合条件** — "有洗车活动的商家" 需要跨优惠库
2. **条件交集** — "评分高 + 有优惠 + 距离近" 需要优先级排序
3. **复杂计算** — "用完优惠后最便宜" 需要价格计算逻辑
4. **动态权重** — 同一用户不同查询时，重要性顺序不同

### searchcoupons 参考方案的启示

searchcoupons 通过 `semantic_query` 参数处理灵活性：
```python
semantic_query="支付宝支付、送洗车的"
```
后端小模型从中提取结构化条件，结合 Milvus 混合搜索（向量语义 + 结构化过滤）。

---

## 推荐方案：方案 A + Agent 编排

### 核心设计思想

**不在工具层堆砌参数，而是：**
1. `search_shops` 保持精简（位置、范围、基础过滤）
2. 当需要跨数据源（商户 + 优惠）时，改为 **orchestrator 协调**：
   - 并行调 `search_shops` 和 `search_coupon`
   - Agent 在 prompt 层做结果合并和排序

**优势：**
- 工具接口简洁，不需频繁改造
- 充分利用 Pydantic AI 的并行调用能力（已原生支持）
- Agent 逻辑可靠，易于维护和扩展

---

## 方案详解

### 1️⃣ 扩展 search_shops 参数（V1.1 版本改造）

添加 `semantic_query` 参数，借鉴 searchcoupons：

```python
async def search_shops(
    ctx: RunContext[AgentDeps],
    latitude: float,
    longitude: float,
    # 既有参数...
    semantic_query: Annotated[str, Field(
        description="用户对商户的自然语言偏好描述"
    )] = "",
) -> str:
```

**后端处理策略：**
- 如果 `semantic_query` 为空 → 走现有逻辑（结构化过滤）
- 如果 `semantic_query` 不空 → 小模型从中提取关键特征（价格范围、项目、评分偏好等）

**Agent prompt 改进：**
```markdown
## 调用 search_shops 时的 semantic_query 组装

当用户提出灵活条件（"有洗车活动"、"综合最便宜"等）时：
- 回顾对话中用户提到的所有商户偏好（价格、项目、评分、距离等）
- 完整组装成自然语言描述，放入 semantic_query
- 例："价格便宜、有保养项目、评分高于4.0分的修理厂"
```

**示例：**
```python
# 用户："有洗车活动的商家有哪些"
search_shops(
    latitude=39.9,
    longitude=116.4,
    semantic_query="有洗车活动、做美容的"
)

# 用户："附近评分高、便宜、营业中的4S店"
search_shops(
    latitude=39.9,
    longitude=116.4,
    commercial_type=[4S店ID],
    order_by="rating",
    semantic_query="价格便宜、现在营业"
)
```

---

### 2️⃣ 需要跨数据源时：Orchestrator 协调

对于 **"有洗车活动的商家"** 这类涉及商户 + 优惠的查询：

**流程（并行执行）：**
```
T=0: Agent 在 searchshops 场景内判断需要跨数据源
     并行发起两个工具调用：
     - search_shops(semantic_query="有洗车项目的修理厂")
     - search_coupon(semantic_query="洗车活动")
     
T=1: 两个工具都返回
     → Agent 提取商户 ID 列表和优惠列表
     → 按优惠覆盖度和商户评分合并
     → 生成结果

T=2: 返回合并后的推荐方案
```

**实现方式（不改框架）：**
- searchshops 的 AGENT.md 明确指出：
  ```markdown
  ## 需要对比优惠时
  
  当用户问"有XXX活动的商家"或"最便宜的方案"时：
  - 识别出 semantic_query 中包含优惠关键词
  - 并行调 search_shops 和 search_coupon，各自搜索
  - 合并两个结果：按商户 ID 关联，标注优惠信息
  ```

---

### 3️⃣ 不新建 Collection，复用 coupon_vectors

**为什么：**
- coupon_vectors 已有 23 字段，包含 11 个商户冗余字段
- 已支持位置索引（shop_lat/shop_lng）
- 避免多 collection 管理复杂度

**使用方式：**
- searchcoupons：通过 semantic_query 在 coupon_vectors 搜优惠
- searchshops：如需查"有X活动的商家"，直接调 search_coupon 拿活动列表，再反向查商户

---

### 4️⃣ 小模型意图提取设计

从 semantic_query 中提取结构化条件，供后端 Milvus 混合搜索使用。

**提取字段（搜索模式识别）：**

**search_shops 的 semantic_query 提取：**
```json
{
  "price_range": "min_price, max_price",          // "便宜"、"500块以内"
  "project_keywords": ["项目名"],                  // "洗车"、"保养"
  "min_rating": float,                             // "评分高"、"4.5分以上"
  "shop_type_hint": "str",                         // "4S店"、"独立修理厂"
  "availability": "open_now/open_date",            // "现在营业"、"周末营业"
}
```

**search_coupon 的 semantic_query 提取：**
```json
{
  "discount_type": ["满减", "直扣", "代金券"],     // 优惠形式偏好
  "payment_method": ["支付宝", "微信"],             // 支付方式
  "coupon_keywords": ["送洗车", "送贴膜"],          // 赠品
  "min_discount_amount": float,                    // "至少优惠100块"
}
```

**实现方式：**
```python
# 后端 /api/extract-intent 接口
POST /api/extract-intent
{
    "semantic_query": "价格便宜、有保养项目、评分高于4.0分的修理厂",
    "intent_type": "shop"  # 或 "coupon"
}
→ {"price_range": [0, 800], "project_keywords": ["保养"], "min_rating": 4.0}
```

或者用现有的 datamanager 小模型（如果已有 intent 提取能力）。

---

## 4 个典型使用场景的处理流程

### 场景 1: 单条件搜索（"附近有什么店"）

```python
# Agent 调用
search_shops(latitude=39.9, longitude=116.4)

# 后端处理：简单过滤
→ 返回附近 5 家门店
```

---

### 场景 2: 多个单一条件组合（"4S店、评分高、距离近"）

```python
# Agent 调用
search_shops(
    latitude=39.9,
    longitude=116.4,
    commercial_type=[4S店ID],
    order_by="rating,distance",
    semantic_query="评分高、离我近的4S店"  # 可选，增强语义理解
)

# 后端处理：
# 1. 结构化过滤：commercial_type = 4S店 ID
# 2. 多维排序：rating desc, distance asc
# 3. 如有 semantic_query，小模型提取 min_rating、max_distance，加强过滤
→ 返回排序好的 4S 店列表
```

---

### 场景 3: 跨数据源（"有洗车活动的商家"）

```python
# Agent 在 searchshops 场景内，识别涉及优惠
# 并行调用两个工具：

# 工具 1
search_shops(
    latitude=39.9,
    longitude=116.4,
    semantic_query="做洗车服务的修理厂"
)

# 工具 2（新增调用，searchshops 场景现有）
search_coupon(
    latitude=39.9,
    longitude=116.4,
    project_ids=["洗车项目ID"],  # 从 semantic_query 提取或 match_project
    semantic_query="洗车活动"
)

# Agent 合并逻辑：
# 1. search_shops 返回 N 家商户（可能有洗车服务）
# 2. search_coupon 返回 M 个洗车优惠（附带 shop_id）
# 3. 关联：按 shop_id 匹配，标注"有优惠"
# 4. 按优惠幅度 + 评分排序
→ "XXX店、YYY店都有洗车优惠，以下是对比..."
```

---

### 场景 4: 复杂计算（"用完优惠后最便宜"）

```python
# Agent 在 searchshops 场景内协调：

# 第 1 步：获取项目基础价格（match_project）
match_project(car_model="...", project_name="保养")
→ {"project_id": "1234", "avg_price": 500}

# 第 2 步：并行查商户和优惠
search_shops(latitude=39.9, longitude=116.4, project_ids=["1234"])
search_coupon(latitude=39.9, longitude=116.4, project_ids=["1234"])

# 第 3 步：Agent 计算最终价格
for shop in shops:
    for coupon in coupons:
        if coupon.shop_id == shop.id:
            final_price = avg_price - coupon.discount
            shop.best_coupon = coupon
            shop.final_price = final_price

# 第 4 步：排序
shops.sort(key=lambda s: s.final_price)
→ "这家店用优惠后最便宜，XXX 元..."
```

---

## 改动清单

### 工具层（backend）

| 工具 | 改动 | 优先级 |
|------|------|--------|
| search_shops | 加 `semantic_query` 参数 + 小模型意图提取 | P1 |
| search_coupon | 已完成（参考方案） | ✅ |
| match_project | 现有工具，无需改 | - |
| collect_location | 现有工具，无需改 | - |

### Agent 层

| 文件 | 改动 | 说明 |
|------|------|------|
| searchshops/AGENT.md | 扩展至 150+ 行 | 新增"跨数据源"和"多条件组合"的编排指导 |
| searchshops/OUTPUT.md | 新增"结果合并"章节 | 如何展示跨数据源的查询结果 |
| search_shops.md（工具提示） | 新增 semantic_query 示例 | 让 Agent 理解如何组装 semantic_query |

### 配置层

```yaml
# stage_config.yaml - searchshops 场景
searchshops:
  tools:
    - search_shops        # 已有
    - search_coupon       # 新增！用于跨数据源查询
    - collect_location    # 已有
    - geocode_location    # 已有
    - match_project       # 已有
    - list_user_cars      # 已有
    - update_session_state # 已有
```

---

## 架构对比总结

| 方案 | 工具层改造 | Agent 层 | 后端复杂度 | 推荐度 |
|------|-----------|---------|-----------|--------|
| **方案 A** | search_shops 加 semantic_query | 编排逻辑清晰 | 低（只需小模型提取） | ⭐⭐⭐⭐⭐ |
| 方案 B | 不改工具 | prompt 合并结果 | 低 | ⭐⭐（不够灵活） |
| 方案 C | search_shops 加 semantic_query | 同 A | 高（新 collection） | ⭐⭐⭐ |

**推荐方案 A 的理由：**
1. **复用现有能力** — searchcoupons 已验证 semantic_query 方案
2. **充分利用框架** — Pydantic AI 原生支持并行调用，无需改框架层
3. **扩展灵活** — Agent prompt 改造 > 后端 API 改造，迭代快
4. **降低成本** — 不新建 collection，milvus schema 管理简洁

---

## 实施路线图

### Phase 1: 基础能力（1 周）
- [ ] search_shops 加 `semantic_query` 参数
- [ ] 后端小模型意图提取接口
- [ ] 搜索服务集成小模型提取结果

### Phase 2: Agent 编排逻辑（1 周）
- [ ] searchshops/AGENT.md 扩展（依赖矩阵、编排示例）
- [ ] searchshops/OUTPUT.md 新增结果合并规则
- [ ] search_shops.md 工具提示补充 semantic_query 示例

### Phase 3: 测试验证（1 周）
- [ ] 4 个典型场景手工测试
- [ ] 小模型意图提取准确度验证
- [ ] 并行调用性能检查

### Phase 4: 迭代优化（按需）
- [ ] semantic_query 效果不满意时，改用模型微调
- [ ] 新增其他高频查询模式
- [ ] 支持更复杂的排序逻辑（e.g. 多维加权排序）

---

## 常见问题

### Q1: 为什么不直接改 search_shops，加所有参数？

**A:** 参数爆炸会导致：
- Agent 难以选择正确的参数组合
- 工具维护成本高（每增一个参数需要更新 prompt、后端 API）
- 无法处理"参数优先级动态变化"的场景

semantic_query 让 Agent 用自然语言表达意图，由小模型智能解读。

### Q2: semantic_query 和结构化参数冲突了怎么办？

**A:** 优先级规则：
```
1. 结构化参数（commercial_type、project_ids）优先，精确匹配
2. semantic_query 补充，增强语义理解和排序权重
3. 冲突时，后端日志记录，定期分析改进
```

### Q3: 为什么不像 platform 场景直接用 orchestrator？

**A:** 
- searchshops 场景本身就设计用于查商户，不需要 BMA 分类和多场景协调
- searchshops 内部可以自主决定是否需要跨数据源查询
- orchestrator 适合 BMA 返回多个场景时的场景协调

### Q4: 小模型意图提取的准确度如何保证？

**A:**
- V1 版本用现有文本相似度（不用模型），快速验证
- V2 版本根据实际效果，如有需要：
  - 微调小模型（用 CTF 数据标注）
  - 或集成大模型的 semantic 理解能力
  - 定期分析"用户意图 vs 提取结果"的偏差

---

## 总结

**核心方案：**
- ✅ search_shops 加 semantic_query 参数（工具层最小改动）
- ✅ searchshops 场景自主协调是否需要跨数据源查询（Agent 编排）
- ✅ 不新建 collection，复用 coupon_vectors（存储层无改动）
- ✅ 小模型意图提取从 semantic_query 提取结构化条件（后端低成本能力）

**预期效果：**
用户任意组合条件查询商户，Agent 智能理解意图并调用合适的工具组合，最终返回综合优化的方案（考虑距离、评分、价格、优惠等多维因素）。

