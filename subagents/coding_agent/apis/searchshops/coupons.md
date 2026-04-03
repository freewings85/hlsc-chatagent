# 优惠活动查询 API

## POST ${COUPON_SEARCH_URL}/api/coupon/search

搜索商户的优惠活动（满减、折扣、赠送等）。

### 请求体

```json
{
  "projectIds": [5002],              // 项目 ID 列表（可选）
  "shopIds": [109, 102],             // 商户 ID 列表（可选）
  "city": "上海",                     // 城市（可选）
  "latitude": 31.23,                 // 纬度（可选）
  "longitude": 121.47,               // 经度（可选）
  "radius": 100000,                  // 搜索半径米（可选）
  "semanticQuery": "满减的活动",      // 语义查询（可选）
  "sortBy": "default",               // 排序：default / discount_amount / validity_end
  "topK": 20                         // 返回数量
}
```

### 响应

```json
{
  "status": 0,
  "result": {
    "shopActivities": [
      {
        "activity_id": 42,
        "activity_name": "春季保养促销",
        "shop_id": 109,
        "shop_name": "嘉定汽修",
        "activity_description": "保养8折，赠送玻璃水",
        "discount_amount": 80.0,
        "activity_category": "折扣",
        "validity_end": "2026-04-30",
        "address": "上海市嘉定区XX路",
        "phone": "021-12345678",
        "rating": 4.5
      }
    ]
  }
}
```

### 使用场景

- 查指定商户的优惠：传 `shopIds`
- 查指定项目的优惠：传 `projectIds`
- 查附近的优惠：传 `latitude` + `longitude` + `radius`
- 按优惠金额排序：`sortBy: "discount_amount"`

### 注意

- `discount_amount` 是优惠金额（元），用于计算"优惠后价格 = 原价 - discount_amount"
- 可以同时传 `projectIds` + `shopIds` 做精确查询
