# GET /api/orders/{id}/timeline

获取工单的状态变更时间线。

## 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| id | string | 工单 ID |

## 返回

```json
{
  "order_id": "ORD-20260101-001",
  "events": [
    {"status": "pending", "timestamp": "2026-01-15T10:30:00Z", "operator": "系统"},
    {"status": "in_progress", "timestamp": "2026-01-15T11:00:00Z", "operator": "李师傅"},
    {"status": "completed", "timestamp": "2026-01-15T16:00:00Z", "operator": "李师傅"}
  ]
}
```
