# GET /api/orders/{id}

获取工单详情，包含维修项目、使用零件、金额明细。

## 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| id | string | 工单 ID（如 ORD-20260101-001） |

## 返回

```json
{
  "id": "ORD-20260101-001",
  "status": "completed",
  "customer": {
    "id": "CUS-001",
    "name": "张三",
    "phone": "138****1234"
  },
  "vehicle": {
    "plate": "沪A12345",
    "brand": "大众",
    "model": "帕萨特 2020款",
    "vin": "LSVNV4189N2******"
  },
  "shop": {
    "id": "SHOP-001",
    "name": "张江汽修中心"
  },
  "items": [
    {
      "project_name": "更换刹车片",
      "labor_fee": 200.00,
      "parts": [
        {"name": "前刹车片（博世）", "quantity": 1, "unit_price": 380.00}
      ]
    },
    {
      "project_name": "四轮定位",
      "labor_fee": 100.00,
      "parts": []
    }
  ],
  "total_parts": 380.00,
  "total_labor": 300.00,
  "total_amount": 680.00,
  "created_at": "2026-01-15T10:30:00Z",
  "completed_at": "2026-01-15T16:00:00Z"
}
```

## 示例

```
GET /api/orders/ORD-20260101-001
```
