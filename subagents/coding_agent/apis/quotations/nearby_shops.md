# 附近商户报价

这份文档解决：
- 查附近商户报价
- 比较哪几家更便宜
- 按价格筛商户

不要用这份文档去做：
- 普通商户搜索
- 纯项目识别
- 只查行业行情参考价

## 接口

`${API_BASE_URL}/service_ai_datamanager/quotation/optimize/quotationByCarKeyNearby`

## 调用方式

- HTTP method：`POST`
- 参数位置：`JSON body`
- 不要把参数拼到 query string 里

## 什么时候用

- 已经有 `project_ids`
- 已经有 `car_model_id`
- 想查附近哪些商户能给出什么报价
- 想按价格排序或比较

## 入参

必填：
- `car_model_id`
- `project_ids`
- `longitude`
- `latitude`
- `distance_km`

可选：
- `shop_ids`

## 最小可运行请求示例

```json
{
  "car_model_id": "lavida_2021_15l",
  "project_ids": [516],
  "latitude": 31.287,
  "longitude": 121.327,
  "distance_km": 10
}
```

## 调用约束

- 这是报价接口，不是普通商户搜索接口
- 没有 `car_model_id` 时，不要调用这个接口去猜价格
- 如果任务只有“找附近门店”而没有确定车型，先走 `/apis/shops/search.md`
- 如果任务同时要求“最低价”但当前没有 `car_model_id`，应明确指出缺少报价前提，而不是编造价格结果

## 返回结构建议

默认不要直接回传原始的深层报价树，优先组织成：

```json
{
  "query": {
    "project_ids": [516],
    "car_model_id": "lavida_2021_15l",
    "distance_km": 10
  },
  "items": [
    {
      "shop": {
        "shop_id": 54,
        "shop_name": "某某门店",
        "address": "上海市...",
        "distance_m": 500,
        "rating": 4.5
      },
      "quotation": {
        "project_id": 516,
        "project_name": "前刹车片更换",
        "plan_name": "国货精品",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 60.06,
        "price_text": "¥60.06~¥60.06"
      }
    }
  ],
  "summary": {
    "total": 3
  }
}
```

## 当前任务最重要的返回信息

- `shop`
- `quotation.project_id`
- `quotation.project_name`
- `quotation.plan_name`
- `quotation.plan_type`
- `quotation.total_price`
- `quotation.price_text`

## 如果当前任务是价格比较

除了上面的基础结果，还要补：

```json
{
  "comparison_data": {
    "rank": 1,
    "comparison_basis": "按 total_price 升序",
    "price_gap": 20.0
  }
}
```

也就是说：
- 如果是按价格筛出来的商户，必须把价格依据带上
- 不要只返回商户名
- 如果接口没有返回任何 `items`，直接按“当前条件下无可比报价”处理，不要自己补造报价

## 什么时候才展开配件明细

只有当任务明确要比较：
- 配件品牌档次
- 配件价格构成
- 配件项明细
- OE 号

这时才进一步返回：
- `parts`
- `part_item`
- `related_oems`

默认不要展开。
