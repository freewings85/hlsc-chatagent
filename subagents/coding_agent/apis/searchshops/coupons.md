# 优惠活动查询 API

## POST ${COUPON_SEARCH_URL}/api/coupon/search

搜索商户的优惠活动（满减、折扣、赠送等）。支持语义查询 + 结构化过滤 + 位置过滤。

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
  "sortBy": "default",               // 排序方式（见下方说明）
  "topK": 20                         // 返回数量
}
```

### sortBy 排序方式

- `default` — 保持 Milvus RRF 分数排序（默认）
- `promo_value` — 按优惠金额降序（优惠最大的排前面）
- `validity_end` — 按过期时间升序（最快过期的排前面）
- `rating` — 按商户评分降序
- `distance` — 按距离升序（需传 latitude + longitude）

### 响应

```json
{
  "status": 0,
  "result": {
    "shopActivities": [
      {
        "activity_id": 42,
        "activity_name": "保养套餐九折优惠",
        "shop_id": 109,
        "shop_name": "xxxxx",
        "activity_description": "机油机滤更换享九折",
        "promo_value": 40.0,
        "relative_amount": 0.9,
        "activity_category": "保养优惠",
        "validity_end": "2026-12-31",
        "address": "上海市静安区xxxxx",
        "phone": "021-xxxxx",
        "rating": 4.8,
        "opening_hours": "08:00-22:00",
        "distance_km": 1.2
      }
    ]
  }
}
```

### 响应字段说明

- `promo_value` — 实际优惠值（元），商家设置的具体优惠金额，可能为 0（未设置）
- `relative_amount` — 相对优惠强度（0~1），如 0.9 表示九折，可能为 0（未设置）
- `distance_km` — 距离（公里），仅在请求传了 latitude + longitude 时返回

### 使用场景

- 查指定商户的优惠：传 `shopIds`
- 查指定项目的优惠：传 `projectIds`
- 查附近的优惠：传 `latitude` + `longitude` + `radius`
- 语义搜索：传 `semanticQuery`（如"送洗车的活动""支付宝支付的"）
- 按优惠金额排序：`sortBy: "promo_value"`

### 注意

- 可以同时传 `projectIds` + `shopIds` 做精确查询
- `promo_value` 和 `relative_amount` 都可能为 0，计算优惠后价格时需判断
