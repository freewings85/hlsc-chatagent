# GET /api/orders/stats

工单统计：按时间段汇总工单数量和金额。

## 参数（Query String）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date_from | string | 是 | 开始日期（YYYY-MM-DD） |
| date_to | string | 是 | 结束日期（YYYY-MM-DD） |
| group_by | string | 否 | 分组维度：day / week / month，默认 day |
| shop_id | string | 否 | 按门店筛选 |

## 返回

```json
{
  "summary": {
    "total_orders": 156,
    "completed_orders": 142,
    "total_revenue": 248600.00,
    "avg_order_amount": 1593.59
  },
  "groups": [
    {
      "period": "2026-01",
      "order_count": 78,
      "revenue": 124300.00
    },
    {
      "period": "2026-02",
      "order_count": 78,
      "revenue": 124300.00
    }
  ]
}
```

## 示例

```
GET /api/orders/stats?date_from=2026-01-01&date_to=2026-03-01&group_by=month
```
