# GET /api/customers/{id}/vehicles

获取客户名下的车辆列表。

## 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| id | string | 客户 ID |

## 返回

```json
{
  "customer_id": "CUS-001",
  "vehicles": [
    {
      "plate": "沪A12345",
      "brand": "大众",
      "model": "帕萨特 2020款",
      "vin": "LSVNV4189N2******",
      "mileage": 45000
    }
  ]
}
```
