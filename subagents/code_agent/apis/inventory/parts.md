# GET /api/inventory/parts

查询零件库存和价格。

## 参数（Query String）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 否 | 零件名称关键词 |
| part_no | string | 否 | 零件编号 |
| category | string | 否 | 分类：brake / engine / suspension / electrical / body |
| in_stock | bool | 否 | 仅显示有库存，默认 false |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |

## 返回

```json
{
  "items": [
    {
      "part_no": "BP-BOSCH-001",
      "name": "前刹车片（博世）",
      "category": "brake",
      "price": 380.00,
      "stock": 15,
      "supplier": "博世中国",
      "compatible_vehicles": ["大众帕萨特", "大众迈腾", "斯柯达速派"]
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

## 示例

```
GET /api/inventory/parts?category=brake&in_stock=true
```
