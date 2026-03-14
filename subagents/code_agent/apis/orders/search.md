# GET /api/orders/search

按条件搜索工单，支持分页。

## 参数（Query String）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 工单状态：pending / in_progress / completed / cancelled |
| customer_id | string | 否 | 客户 ID |
| shop_id | string | 否 | 门店 ID |
| date_from | string | 否 | 开始日期（YYYY-MM-DD） |
| date_to | string | 否 | 结束日期（YYYY-MM-DD） |
| keyword | string | 否 | 关键词搜索（匹配工单描述、车牌号） |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20，最大 100 |

## 返回

```json
{
  "items": [
    {
      "id": "ORD-20260101-001",
      "customer_name": "张三",
      "vehicle": "沪A12345 大众帕萨特 2020款",
      "status": "completed",
      "total_amount": 1580.00,
      "shop_name": "张江汽修中心",
      "created_at": "2026-01-15T10:30:00Z",
      "completed_at": "2026-01-15T16:00:00Z",
      "description": "更换刹车片+四轮定位"
    }
  ],
  "total": 156,
  "page": 1,
  "page_size": 20
}
```

## 示例

```
GET /api/orders/search?status=completed&date_from=2026-01-01&date_to=2026-01-31&page_size=50
```

查询 2026 年 1 月所有已完成的工单。
