# 商户类型知识

这份文档不是做实时商户搜索，而是解释商户类型的优缺点和适用场景。

## 接口

`http://127.0.0.1:9000/service_ai_datamanager/shop/getAllShopType`

## 什么时候用

- 想解释 4S、连锁、小店等差异
- 想做商户类型映射
- 想基于商户类型做推荐说明

## 入参

无

## 返回结果建议

```json
{
  "items": [
    {
      "shop_type_id": 34,
      "shop_type_name": "4S店",
      "advantages": "......",
      "disadvantages": "......",
      "suitable_scenes": "......",
      "summary": "......"
    }
  ]
}
```

## 当前任务最重要的返回信息

- `shop_type_id`
- `shop_type_name`
- `advantages`
- `disadvantages`
- `suitable_scenes`
- `summary`

## 使用说明

- 这是知识型接口，不是实时商户候选集接口
- 如果当前任务是“找附近哪些店”，不要先读这份文档
