# search_shops 工具升级设计

## 现状分析

### 当前 search_shops 能力
- ✅ 位置搜索（latitude/longitude + radius）
- ✅ 排序（distance/rating/tradingCount）
- ✅ 基础筛选（commercial_type, opening_hour, min_rating, min_trading_count）
- ❌ **语义查询**（如"有优惠的"、"口碑好的"）
- ❌ **跨数据源联合查询**（优惠 × 商户）
- ❌ **复杂条件组合**（优惠+项目+位置+价格）

### search_coupon 参考方案
search_coupon 的核心能力：
- `semantic_query` 参数：用户的自然语言偏好（"满减的、送洗车的"）
- **后端混合搜索**：结构化 filter + 向量语义搜索
- Milvus 中集成商户信息（11 字段）+ 向量索引
- 后端提取结构化条件（activity_category, city, shop_name 等）

---

## 升级方案

### 核心设计思路

**问题分析：**
- 用户搜商户的条件灵活，但不像搜优惠那样是"优惠+偏好"的二元结构
- search_shops 本质是**商户库搜索**，搜索空间 ~ 500 - 5000 个商户
- 搜优惠本质是**活动库搜索**，搜索空间 ~ 10,000+ 活动

**结论：**
1. **search_shops 和 search_coupon 是独立的工具**，负责不同的搜索空间
2. **"有优惠的店"是编排问题**，不是工具问题
   - 先 search_coupon 找优惠 → 提取 shop_ids → 再按条件查商户详情
   - 或在 orchestrator 层面并行执行两个工具，合并结果

---

### 方案 A：search_shops 轻量升级（推荐）

#### 工具参数设计

```python
async def search_shops(
    ctx: RunContext[AgentDeps],
    # 位置（必填或来自 context）
    latitude: Annotated[float, Field(description="纬度")],
    longitude: Annotated[float, Field(description="经度")],
    # 基础筛选
    shop_name: Annotated[str, Field(description="门店名称关键词")] = "",
    radius: Annotated[int, Field(description="搜索半径（米）")] = 10000,
    top: Annotated[int, Field(description="返回数量")] = 5,
    # 排序与过滤
    order_by: Annotated[str, Field(description="排序：distance/rating/tradingCount，可组合")] = "distance",
    commercial_type: Annotated[list[int] | None, Field(description="商户类型列表")] = None,
    project_ids: Annotated[str | None, Field(description="服务项目ID，逗号分隔")] = None,
    # 新增：语义查询
    semantic_query: Annotated[str, Field(description="自然语言偏好（如'口碑好的，周末开门的，有停车位的'）")] = "",
    # 其他过滤
    opening_hour: Annotated[str | None, Field(description="营业时间筛选，HH:MM")] = None,
    min_rating: Annotated[float | None, Field(description="最低评分")] = None,
    min_trading_count: Annotated[int | None, Field(description="最低成交量")] = None,
    province_id: Annotated[int | None, Field(description="省份ID")] = None,
    city_id: Annotated[int | None, Field(description="城市ID")] = None,
    district_id: Annotated[int | None, Field(description="区县ID")] = None,
    # 可选：按优惠过滤（需后端支持）
    shop_ids: Annotated[list[str] | None, Field(description="指定商户ID列表（来自 search_coupon）")] = None,
) -> str:
```

#### 关键变化

| 参数 | 现在 | 升级后 | 说明 |
|------|------|--------|------|
| `semantic_query` | ❌ | ✅ 新增 | 支持自然语言偏好，如"靠谱的、周末营业、有洗车的" |
| `shop_ids` | ❌ | ✅ 新增 | 允许指定商户ID列表（来自search_coupon结果） |
| 其他参数 | ✅ | ✅ 保持 | 向后兼容 |

**调用示例：**

```python
# 场景 1：口碑好的、周末开门的店
search_shops(
    latitude=39.9,
    longitude=116.4,
    semantic_query="口碑好的，周末营业的",
    opening_hour="09:00",
    order_by="rating"
)

# 场景 2：找有换机油优惠的店
# 步骤 A：先找优惠
coupons = search_coupon(
    project_ids=["1001"],  # 换机油
    semantic_query="满减的",
    top_k=20
)  # 返回中包含 shop_ids
coupon_shop_ids = [c["shop_id"] for c in coupons]

# 步骤 B：再查这些店的详情 + 额外条件
shops = search_shops(
    latitude=39.9,
    longitude=116.4,
    shop_ids=coupon_shop_ids,
    semantic_query="4S店、口碑好的",
    order_by="rating,distance"
)

# 场景 3：附近有什么靠谱的修理厂（有项目+偏好）
search_shops(
    latitude=39.9,
    longitude=116.4,
    project_ids="1001,1002",  # 保养、轮胎
    semantic_query="独立修理厂、评分高、成交量大",
    order_by="tradingCount,rating",
    commercial_type=[3],  # 独立修理厂 typeId
    radius=5000
)
```

---

### 方案 B：重度整合（不推荐，复杂度高）

如果要让 search_shops 本身支持跨优惠搜索，需要：

1. **创建商户 Milvus collection**
   - 字段：商户基本信息 + **关联的优惠列表**
   - 索引：位置、评分、商户类型、是否有优惠
   - 成本：维护复杂，数据同步负担大

2. **后端小模型意图提取**
   - semantic_query → structured filter（项目ID、优惠类型、商户类型等）
   - 模型：需要调用小模型接口

3. **搜索服务改造**
   - 支持 semantic_query 的向量搜索
   - 支持跨字段排序（距离 + 优惠额 + 评分）

**成本 vs 收益：**
- ❌ 维护两套 Milvus collection（优惠 + 商户）
- ❌ 增加后端复杂度
- ✅ 单次 RPC 获取答案
- ❌ 但用户场景多数是"先看优惠再选店"，不是"找店优先"

**结论：** 不推荐，用方案 A + 编排足够。

---

## 后端改造清单

### 阶段 1：轻量支持（V1）

#### shop_service.get_nearby_shops 改造

**新增参数：**
```python
async def get_nearby_shops(
    # 现有参数保持不变
    lat: float,
    lng: float,
    keyword: str = "",
    top: int = 5,
    radius: int = 10000,
    order_by: str = "distance",
    # ...
    
    # 新增参数
    semantic_query: str = "",              # 自然语言查询
    shop_ids: list[str] | None = None,    # 指定商户ID列表
    # ...
) -> dict:
```

**实现策略：**

1. **shop_ids 指定列表时**
   - 直接查库 WHERE shop_id IN (shop_ids)
   - 返回这些店的详情
   - 按 semantic_query + order_by 重排序

2. **semantic_query 处理（初版）**
   - 关键词匹配：提取字段 + 匹配
     - "口碑好" → min_rating = 4.0
     - "成交多" / "靠谱" → min_trading_count = 50
     - "周末营业" → opening_hour 过滤
     - "4S店" / "连锁" / "独立修理厂" → commercial_type 过滤
     - "有停车位" → 在 tags/service_scope 中搜索 "停车"
     - "有洗车" → 在 tags 中搜索 "洗车"

   - 没有匹配字段时 → 忽略（不报错）

3. **返回字段（保持现有）**
   - shop_id, name, address, distance, rating, trading_count
   - phone, tags, opening_hours, images, latitude, longitude

**后端改动最小化：**
- ✅ 只改 shop_service.get_nearby_shops
- ✅ 关键词提取用简单的字符串匹配（不需要 ML 模型）
- ✅ 不新建 collection，不改 Milvus

### 阶段 2：向量增强（V2，可选）

如果需要更好的语义理解：

1. **后端小模型意图提取**
   ```python
   def extract_shop_intent(semantic_query: str) -> dict:
       """用小模型抽取结构化条件
       返回：{
           "commercial_types": ["4S店", "连锁店"],
           "min_rating": 4.5,
           "min_trading_count": 50,
           "services": ["轮胎更换", "保养"],
           "attributes": ["停车位", "24小时"]
       }
       """
   ```

2. **可选：在 Milvus 中为商户的 tags/service_scope 建向量索引**
   - 让"有停车位的、能换轮胎的"语义匹配更准

---

## 工具接口文档更新

### search_shops.md 更新

```markdown
按位置和条件搜索附近的商户/门店，返回门店列表。

## 参数说明

### 位置信息（必填）
- **latitude**: 纬度
- **longitude**: 经度
- **radius**: 搜索半径（米），默认 10000

### 基础搜索
- **shop_name**: 门店名称关键词，仅用户明确按名称搜索时传入
- **project_ids**: 服务项目 ID，逗号分隔（用户说"找能做保养、轮胎的店"时传入）

### 排序和过滤
- **order_by**: 排序方式，支持 distance / rating / tradingCount，可组合如 "rating,distance"
- **commercial_type**: 商户类型列表（4S 店、连锁店、独立修理厂等）
- **opening_hour**: 营业时间筛选，格式 "HH:MM"（如"14:30"）
- **min_rating**: 最低评分（仅用户明确给出具体数值时传入）
- **min_trading_count**: 最低成交量（仅用户明确给出具体数值时传入）

### 语义查询和指定列表
- **semantic_query**: 用户对商户的自然语言偏好描述（如"口碑好的，周末营业，有停车位的"）
  - 支持的关键词：口碑好、成交多、靠谱、4S 店、连锁店、独立修理厂、周末营业、停车位、洗车等
  - 调用前回顾对话中用户提到的所有商户偏好，完整组装到此参数

- **shop_ids**: 指定商户 ID 列表（来自 search_coupon 结果，用户想在有优惠的店中筛选时使用）
  - 若传入此参数，仅搜索这些商户，忽略 latitude/longitude/radius

## 返回数据

```json
{
  "total": 5,
  "shops": [
    {
      "shop_id": "100001",
      "name": "途虎养车浦东店",
      "address": "浦东新区世纪大道 100 号",
      "province": "上海市",
      "city": "上海市",
      "district": "浦东新区",
      "commercial_type": 2,
      "latitude": 31.2304,
      "longitude": 121.5001,
      "distance": "2.5km",
      "distance_m": 2500,
      "rating": 4.7,
      "trading_count": 1250,
      "phone": "021-12345678",
      "tags": ["保养", "轮胎", "洗车", "停车位"],
      "opening_hours": "09:00-21:00",
      "images": [...]
    }
  ]
}
```

## 使用场景

### 基础场景
- "附近有什么店" → latitude, longitude（使用默认参数）
- "找个口碑好的店" → order_by="rating"
- "哪家店靠谱" → order_by="tradingCount"
- "途虎养车" → shop_name="途虎"
- "浦东的修车店" → address_name="浦东"

### 语义场景
- "找个好口碑的、周末开门的店" → semantic_query="口碑好的，周末营业"，order_by="rating"
- "附近有什么4S店" → semantic_query="4S店"，commercial_type=[对应ID]
- "独立修理厂便宜，找个靠谱的" → semantic_query="独立修理厂，成交量大"，order_by="tradingCount"

### 跨优惠场景
- 用户说"有优惠的店"
  - 步骤 1：调 search_coupon 找优惠 → 获取 shop_ids
  - 步骤 2：调 search_shops(shop_ids=shop_ids, semantic_query="...") 添加额外条件
  - 示例：有保养优惠的4S店 → search_shops(shop_ids=coupon_shops, semantic_query="4S店")

## 重要规则

1. **keyword、min_rating、min_trading_count 的使用规则**
   - 只在用户明确给出具体值时传入
   - 禁止根据模糊描述自行猜测填充
   - 例：用户说"口碑好"不等于 min_rating=4.0，应该用 order_by="rating" 代替

2. **semantic_query 的组装**
   - 调用前回顾本次对话中用户提到的所有商户条件偏好
   - 完整组装成自然语言描述
   - 例：用户说"评分高、支持停车、周末开门" → semantic_query="评分高的，有停车位，周末营业"

3. **位置 vs 商户列表**
   - 传了 shop_ids，会忽略 latitude/longitude/radius
   - 不传 shop_ids，必须有 latitude/longitude
```

---

## search_shops vs search_coupon 的关系

| 维度 | search_coupon | search_shops |
|------|---------------|--------------|
| **搜索对象** | 优惠活动库 | 商户库 |
| **搜索空间大小** | 10,000+ | 500-5,000 |
| **主要参数** | project_ids, semantic_query | latitude/longitude, semantic_query |
| **返回内容** | 优惠信息 + 商户ID | 商户详情 |
| **跨越场景** | "有满减活动的保养优惠吗？" | "哪家店有优惠且口碑好？" |

**编排关系：**

```
用户说："找个有优惠的修理厂，口碑好的"
       ↓
   分解为两个工具调用（并行或序列）：
   ├─ search_coupon(project_ids=["修理"], semantic_query="...")
   │  → 返回 [优惠1(shop_id=A), 优惠2(shop_id=B), ...]
   └─ search_shops(shop_ids=[A, B, ...], semantic_query="口碑好的", order_by="rating")
      → 返回 [店A(rating=4.8), 店B(rating=4.5), ...]
       ↓
   合并展示：店A有3个优惠（省X元），店B有1个优惠（省Y元）
```

**总结：** 两个工具各司其职，在编排层（orchestrator/BMA）合并结果。

---

## 实现建议

### Phase 1：最小化版本（1 周）
- ✅ search_shops 添加 semantic_query 参数
- ✅ 后端关键词匹配（不需要 ML）
- ✅ 添加 shop_ids 参数，支持指定商户列表
- ✅ 更新文档和 prompt

### Phase 2：可选增强（2 周）
- 💡 后端小模型意图提取（semantic_query → structured filter）
- 💡 编排示例：优惠 + 商户的合并查询流程

### Phase 3：可选优化（4 周）
- 💡 商户 Milvus collection（如有其他需求）
- 💡 向量索引 (tags 的语义匹配)

---

## 回答核心问题

### Q1：search_shops 工具参数怎么设计？加 semantic_query？
**A：** ✅ 加 semantic_query + shop_ids。参见方案 A 的工具签名。

### Q2：如何支持"有优惠的店"这种跨数据源查询？
**A：** 在编排层（orchestrator）：
1. search_coupon 查优惠 → 提取 shop_ids
2. search_shops(shop_ids=...) 查商户详情
3. 合并两个结果展示

### Q3：后端需要什么改造？
**A：** 改造 shop_service.get_nearby_shops：
- 新增 semantic_query, shop_ids 参数
- 实现关键词匹配（简单字符串搜索，不需要 ML）
- 不新建 collection，不需大改

### Q4：小模型意图提取的字段列表？
**A：** Phase 1 用关键词硬编码，Phase 2 可加小模型。字段包括：
- commercial_types: ["4S店", "连锁店", "独立修理厂"]
- min_rating, min_trading_count
- services: ["保养", "轮胎", "洗车"]
- attributes: ["停车位", "24小时"]
- working_time: ["周末", "夜间"]

### Q5：返回数据应该包含哪些字段？
**A：** 保持现有，新增 semantic_query 调用时可考虑：
- ✅ 现有：shop_id, name, address, distance, rating, trading_count, phone, tags, opening_hours, images
- 💡 可选：优惠相关字段（如果是从 search_coupon 指定的 shop_ids，可在编排层补充）

---

## 总结

**方案 A（推荐）的优势：**
1. 工具设计简洁：只加两个参数
2. 后端改动最小：shop_service 简单改造
3. 不新增复杂依赖：不需要 Milvus 改造、不需要 ML 模型
4. 编排灵活：跨优惠的查询在 orchestrator 层组合
5. 向后兼容：现有调用不受影响

**推进路线：**
```
Week 1 (开发):
  - search_shops 添加参数
  - 后端关键词匹配
  - 文档更新

Week 2 (测试验证):
  - 集成测试
  - 场景验证
  - 文档完善
  
可选 Week 3+ (优化):
  - 小模型意图提取
  - 性能优化
```
