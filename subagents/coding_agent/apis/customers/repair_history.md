# GET /api/customers/{id}/repair_history

获取客户的维修历史记录。

## 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| id | string | 客户 ID |

## 参数（Query String）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date_from | string | 否 | 开始日期（YYYY-MM-DD） |
| date_to | string | 否 | 结束日期（YYYY-MM-DD） |

## 返回

```json
{
  "customer_id": "CUS-001",
  "records": [
    {
      "order_id": "ORD-20260101-001",
      "date": "2026-01-15",
      "shop_name": "张江汽修中心",
      "projects": ["更换刹车片", "四轮定位"],
      "total_amount": 680.00,
      "vehicle_plate": "沪A12345"
    }
  ],
  "total": 5
}
```
