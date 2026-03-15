# query-part-price API 参考

## search_parts.py 返回格式

```json
{
  "keyword": "刹车片",
  "parts": {
    "exact": [
      {"part_id": 123, "name": "前刹车片"}
    ],
    "fuzzy": [
      {"part_id": 456, "name": "后刹车片"},
      {"part_id": 789, "name": "刹车盘"}
    ]
  }
}
```

- exact: 精确匹配（名称完全匹配或高度相似）
- fuzzy: 模糊匹配（语义相近的候选）

## get_part_price.py 返回格式

```json
{
  "part_list": [
    {
      "primary_part_id": 123,
      "primary_part_name": "前刹车片",
      "items": [
        {"ai_repair_type": "INTERNATIONAL_BRAND", "price": 380.0, "ware_id": 1001},
        {"ai_repair_type": "DOMESTIC_QUALITY", "price": 220.0, "ware_id": 1002},
        {"ai_repair_type": "ORIGINAL", "price": 580.0, "ware_id": 1003}
      ]
    }
  ]
}
```

- ai_repair_type 含义：
  - INTERNATIONAL_BRAND: 国际大厂
  - DOMESTIC_QUALITY: 国产品质
  - ORIGINAL: 原厂
- price: 零部件价格（元），仅配件，不含工时
