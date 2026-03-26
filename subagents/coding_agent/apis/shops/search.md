# 商户搜索与详情

这份文档解决两类任务：

1. 按位置、范围、项目等条件搜索候选商户
2. 已经有 `shop_id` 后，补充商户详情

不要用这份文档去做：
- 用户历史商户查询
- 商户类型知识解释
- 报价比较

## 一、标准商户搜索

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/shop/getNearbyShops`

### 调用方式

- HTTP method：`POST`
- 参数位置：`JSON body`
- 不要把参数拼到 query string 里
- `order_by` 传字符串，推荐值：`"distance"`、`"rating"`、`"distance,rating"`

### 什么时候用

- 想找附近能做某个项目的商户
- 想按距离、评分、营业时间、关键词等标准条件筛商户
- 想返回普通候选商户清单

### 入参

必填：
- `latitude`
- `longitude`
- `top`

可选：
- `shop_type_ids`
- `shop_ids`
- `keyword`
- `project_ids`
- `radius_m`
- `province_id`
- `city_id`
- `district_id`
- `address_name`
- `opening_hour`
- `platform_activity_id`
- `min_trading_count`
- `min_rating`
- `order_by`

### 最小可运行请求示例

```json
{
  "latitude": 31.287,
  "longitude": 121.327,
  "top": 10,
  "project_ids": [546, 547],
  "radius_m": 20000,
  "min_rating": 4.5,
  "order_by": "distance,rating"
}
```

### 调用约束

- 这是标准商户搜索接口，返回商户候选集，不直接返回报价
- 即使任务里提到了“最低价”，只要没有 `car_model_id`，也不要把这个接口误当成报价接口
- 如果只是为了拿候选门店，再交给上层做筛选，优先用这个接口
- 如果同时需要真实报价比较，先确认是否已经有 `car_model_id`；没有就不要硬调用报价接口
- `order_by` 虽然 mock 兼容数组，但文档约定统一传字符串，避免 agent 自己发明新格式

### 返回结构建议

如果当前任务只是普通商户搜索，优先组织成下面这种结果：

```json
{
  "query": {
    "project_ids": [516],
    "latitude": 31.28,
    "longitude": 121.32,
    "radius_m": 10000,
    "order_by": ["distance", "rating"]
  },
  "items": [
    {
      "shop": {
        "shop_id": 48,
        "shop_name": "某某门店",
        "shop_type_id": 34,
        "shop_type_name": "4S店",
        "address": "上海市嘉定区...",
        "province": "上海市",
        "city": "上海城区",
        "district": "普陀区",
        "latitude": 31.287737,
        "longitude": 121.326912,
        "distance_m": 216,
        "rating": 4.6,
        "trading_count": 120,
        "phone": "17522536027",
        "opening_hours": "09:00-18:00",
        "tags": ["洗车", "保养"]
      }
    }
  ],
  "summary": {
    "total": 12
  }
}
```

### 当前任务最重要的返回信息

- `shop_id`
- `shop_name`
- `shop_type_id`
- `address`
- `latitude`
- `longitude`
- `distance_m`
- `rating`
- `trading_count`
- `phone`
- `opening_hours`
- `tags`

### 使用说明

- `project_ids` 是按项目限制商户搜索的关键条件
- `distance_m` 建议统一使用米
- `order_by` 建议直接表达排序依据，例如 `distance,rating`
- 如果只是普通候选集搜索，不要在这里把报价树一起展开
- 如果返回 `items=[]`，应直接按“当前条件下没有命中商户”理解，不要自己补造门店数据

## 二、按商户 id 查询详情

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/shop/getShopsById`

### 调用方式

- HTTP method：`POST`
- 参数位置：`JSON body`

### 什么时候用

- 已经有一个或多个 `shop_id`
- 需要补商户详情
- 不需要再做附近搜索

### 入参

必填：
- `shop_ids`

### 最小可运行请求示例

```json
{
  "shop_ids": [101, 102]
}
```

### 返回结构建议

仍然组织成 `shop` 基础对象即可，不需要单独发明另一套结构。

### 当前任务最重要的返回信息

- `shop_id`
- `shop_name`
- `shop_type_id`
- `address`
- `phone`
- `opening_hours`
- `latitude`
- `longitude`
- `rating`
- `trading_count`
- `tags`

## 三、和其他文档的关系

- 需要查用户历史商户：
  - 读 `/apis/shops/history.md`
- 需要解释商户类型：
  - 读 `/apis/shops/types.md`
- 需要比较报价：
  - 读 `/apis/quotations/nearby_shops.md`
