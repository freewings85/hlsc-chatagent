# 商户项目报价查询 API

## POST ${DATA_MANAGER_URL}/service_ai_datamanager/shop/getCommercialPackages

查询指定商户的项目报价，用于比价、计算优惠后价格等场景。

### 请求体

```json
{
  "shopIds": [52, 55],          // 商户 ID 列表（必填）
  "projectIds": [1455]          // 项目 ID 列表（可选，不传则返回商户所有项目报价）
}
```

### 响应

```json
{
  "status": 0,
  "result": [
    {
      "shopId": 55,
      "shopName": "xxxxx",
      "shopType": [4, 3, 2],
      "projects": [
        {
          "sourceId": 1455,
          "projectId": 1456,
          "projectName": "xxxxx",
          "priceType": 1,
          "priceStringObject": {
            "price": 120,
            "conditionPrices": null,
            "minPrice": null,
            "maxPrice": null
          }
        }
      ]
    }
  ]
}
```

### priceType 价格类型

| priceType | 含义 | 有效字段 |
|-----------|------|---------|
| 1 | 准确价格 | `price`（单一价格） |
| 2 | 条件价格 | `conditionPrices`（数组，每项含 `price` + `condition`） |
| 3 | 区间价格 | `minPrice` + `maxPrice` |

### conditionPrices 示例（priceType=2）

```json
"conditionPrices": [
  {"price": 3600, "condition": "2.2t重量以下"},
  {"price": 4600, "condition": "2.2t-4.0t重量"},
  {"price": 5600, "condition": "4.0t-10.0t长度10米以内"}
]
```

### 响应字段说明

- `sourceId` — 查询时传入的项目 ID（如"洗车"的 ID）
- `projectId` — 实际匹配到的子项目 ID（如"普洗""精洗"的 ID）
- 一个 sourceId 可能对应多个 projectId（父项目展开为子项目）
- 比价时按 sourceId 分组，每个子项目独立比价

### 使用场景

- 查指定商户的某个项目报价：传 `shopIds` + `projectIds`
- 对比多家商户的报价：传多个 `shopIds` + 同一个 `projectIds`
- 查商户所有项目报价：只传 `shopIds`，不传 `projectIds`

### 比价代码示例

不同商户的 priceType 可能不同（固定/条件/区间），比价时用以下代码提取可比价格并排序：

```python
def get_comparable_price(project):
    """从单个项目报价中提取可比价格和展示标签。

    返回 (comparable_price, display_label)
    - comparable_price: float，用于排序
    - display_label: str，展示给用户的价格描述
    """
    ps = project["priceStringObject"]
    pt = project["priceType"]
    if pt == 1:  # 准确价格
        return ps["price"], f'{ps["price"]}元'
    if pt == 3:  # 区间价格
        return ps["minPrice"], f'{ps["minPrice"]}元起（{ps["minPrice"]}-{ps["maxPrice"]}元）'
    if pt == 2:  # 条件价格
        lowest = min(ps["conditionPrices"], key=lambda x: x["price"])
        return lowest["price"], f'{lowest["price"]}元起（{lowest["condition"]}）'
    return float("inf"), "暂无报价"


# 比价流程：从 getCommercialPackages 响应中提取并排序
# 注意：用 sourceId 匹配查询的项目，projectId 是实际子项目
target_source_id = 1101  # 查询时传入的项目 ID
results = []
for shop in response_data["result"]:
    for proj in shop["projects"]:
        if proj["sourceId"] == target_source_id:
            price, label = get_comparable_price(proj)
            results.append({
                "shopId": shop["shopId"],
                "shopName": shop["shopName"],
                "price": price,
                "label": label,
                "priceType": proj["priceType"],
            })

results.sort(key=lambda x: x["price"])

# 输出示例：
# 1. 小拇指快修 329元
# 2. 精典汽车 359元
# 3. 拖车服务 3600元起（2.2t重量以下）
```

如果排序结果中有非准确价格（priceType != 1），结尾附一句：
"部分价格与车型/车况相关，提供车型信息可获得更精确的报价对比"

### 注意

- `shopIds` 必须来自商户搜索结果的真实 ID
- 某些商户可能没有某个项目的报价（`projects` 数组中不包含该项目）
- 计算"优惠后价格"时：先查报价（本接口），再查优惠（coupons.md），用代码计算差值
