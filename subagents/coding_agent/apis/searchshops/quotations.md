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
          "projectId": 1455,
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

### 使用场景

- 查指定商户的某个项目报价：传 `shopIds` + `projectIds`
- 对比多家商户的报价：传多个 `shopIds` + 同一个 `projectIds`
- 查商户所有项目报价：只传 `shopIds`，不传 `projectIds`

### 注意

- `shopIds` 必须来自商户搜索结果的真实 ID
- 某些商户可能没有某个项目的报价（`projects` 数组中不包含该项目）
- 计算"优惠后价格"时：先查报价（本接口），再查优惠（coupons.md），用代码计算差值
