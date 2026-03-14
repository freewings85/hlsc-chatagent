# GET /api/inventory/suppliers

查询供应商列表及评级。

## 参数（Query String）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 否 | 供应商名称关键词 |
| category | string | 否 | 供应品类筛选 |

## 返回

```json
{
  "items": [
    {
      "id": "SUP-001",
      "name": "博世中国",
      "rating": 4.8,
      "categories": ["brake", "electrical"],
      "contact": "021-5555-0001"
    }
  ],
  "total": 8
}
```
