# 商户搜索 API

## POST ${SHOP_SEARCH_URL}/api/shop/search

搜索商户，支持语义查询 + 结构化过滤 + 位置过滤。

### 请求体

```json
{
  "semanticQuery": "汽车保养",       // 语义查询（可选）
  "topK": 10,                       // 返回数量（默认 10）
  "city": "上海",                    // 城市过滤（可选）
  "shopName": "途虎",               // 商户名模糊搜索（可选）
  "latitude": 31.23,                // 纬度（可选）
  "longitude": 121.47,              // 经度（可选）
  "radius": 20000                   // 搜索半径米（可选，不传默认 20000 即 20 公里）
}
```

### 响应

```json
{
  "status": 0,
  "result": {
    "shops": [
      {
        "shop_id": 101,
        "shop_name": "xxxxx",
        "shop_type": "汽车服务",
        "province": "上海市",
        "city_name": "上海市",
        "district": "静安区",
        "address": "xxxxx",
        "service_scope": "保养,轮胎,钣喷",
        "phone": "021-xxxxx",
        "opening_hours": "08:00-22:00",
        "shop_lat": 31.232,
        "shop_lng": 121.465,
        "rating": 4.8,
        "distance_km": 1.2,
        "score": 0.85
      }
    ]
  }
}
```

### 响应字段说明

- `shop_id` — 商户 ID
- `shop_name` — 商户名称
- `shop_type` — 商户类型（如"汽车服务"，逗号分隔）
- `service_scope` — 经营范围（逗号分隔，如"保养,轮胎,钣喷"）
- `rating` — 商户评分
- `distance_km` — 距离（公里），仅在请求传了 latitude + longitude 时返回
- `score` — 语义相关度分数，仅在传了 semanticQuery 时返回

### 使用场景

- 搜附近商户：传 `latitude` + `longitude` + `radius`
- 按名称搜商户：传 `shopName`
- 按城市搜商户：传 `city`
- 语义搜索（如"评价好的修理厂""做保养的4S店"）：传 `semanticQuery`
- 组合查询：以上参数可自由组合

### 注意

- 无语义查询时走纯结构化查询（不走向量搜索）
- `service_scope` 可用于判断商户是否提供某类服务
