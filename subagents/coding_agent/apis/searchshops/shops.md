# 商户搜索 API

## POST ${SHOP_SEARCH_URL}/api/shop/search

搜索商户，支持语义查询 + 结构化过滤 + 位置过滤 + 排序。

### 请求体

```json
{
  "semanticQuery": "洗车",           // 语义查询（可选）
  "topK": 10,                       // 返回数量（默认 10）
  "locationText": "南京西路",        // 位置描述（可选，原样传用户的位置描述）
  "city": "上海",                    // 城市过滤（可选，不需要带"市"）
  "shopName": "途虎",               // 商户名模糊搜索（可选）
  "shopTypeText": "4S店",           // 商户类型文本（可选，后端 RAG 匹配为 code 过滤）
  "latitude": 31.23,                // 纬度（可选）
  "longitude": 121.47,              // 经度（可选）
  // "radius": 搜索半径（米）。除非用户明确指定了距离，否则坚决不要传此参数
  "minRating": 4.0,                 // 最低评分（可选）
  "openingTime": "14:30",           // 营业时间点筛选（可选，格式 HH:MM，筛选该时间还在营业的商户）
  "sortBy": "default"               // 排序方式（可选，见下方说明）
}
```

### sortBy 排序方式

- `default` — 保持搜索相关度排序（默认）
- `distance` — 按距离升序（需传 latitude + longitude）
- `rating` — 按评分降序
- `trading_count` — 按交易量降序

### 响应

```json
{
  "status": 0,
  "result": {
    "shops": [
      {
        "shop_id": 101,
        "shop_name": "xxxxx",
        "short_name": "xxx",
        "shop_type": "4S店,综合修理厂",
        "province": "上海市",
        "city_name": "上海市",
        "district": "浦东新区",
        "address": "xxxxx路xxxxx号",
        "service_scope": "保养,轮胎,钣喷",
        "phone": "021-xxxxx",
        "licensing": "xxxxx",
        "specialty": "xxxxx",
        "guarantee": "xxxxx",
        "trading_count": 1200.0,
        "enable": 1,
        "opening_start": "08:00",
        "opening_end": "22:00",
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

- `shop_id` — 商户 ID（整数）
- `shop_name` — 商户名称
- `short_name` — 商户简称
- `shop_type` — 商户类型（逗号分隔，如"4S店,综合修理厂"）
- `service_scope` — 经营范围（逗号分隔，如"保养,轮胎,钣喷"）
- `licensing` — 品牌授权
- `specialty` — 特色服务
- `guarantee` — 服务保障
- `trading_count` — 交易量（浮点数）
- `enable` — 启用状态（搜索结果默认只返回启用的）
- `opening_start` — 营业开始时间（HH:MM）
- `opening_end` — 营业结束时间（HH:MM）
- `rating` — 商户评分（浮点数）
- `distance_km` — 距离（公里），仅在请求传了 latitude + longitude 时返回
- `score` — 语义相关度分数，仅在传了 semanticQuery 时返回
