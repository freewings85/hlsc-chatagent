# GET /api/customers/search

搜索客户。

## 参数（Query String）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 否 | 姓名、手机号、车牌号模糊搜索 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |

## 返回

```json
{
  "items": [
    {
      "id": "CUS-001",
      "name": "张三",
      "phone": "138****1234",
      "vehicle_count": 2,
      "total_orders": 5,
      "last_visit": "2026-02-20"
    }
  ],
  "total": 3
}
```
