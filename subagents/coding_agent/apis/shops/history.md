# 用户商户历史

这份文档解决：
- 查用户最近服务过的商户
- 查用户历史上服务过的商户

不要用这份文档去做：
- 附近商户搜索
- 报价比较
- 商户类型知识解释

## 一、最近服务商户

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/shop/getLatestVisitedShops`

### 什么时候用

- 任务关注“最近一次”服务关系
- 想知道用户最新服务过哪家商户
- 想优先看最近关系商户

### 入参

必填：
- `user_id`
- `top`

### 返回结果建议

```json
{
  "query": {
    "user_id": "10001",
    "mode": "latest"
  },
  "items": [
    {
      "shop": {
        "shop_id": 46,
        "shop_name": "大威车友汽修",
        "address": "虹桥机场",
        "phone": "15988888888"
      },
      "relation_data": {
        "last_order_code": "YUN-1234560003",
        "last_order_time": "2026-03-17 15:18:30"
      }
    }
  ]
}
```

### 当前任务最重要的返回信息

- `shop`
- `last_order_code`
- `last_order_time`

## 二、历史服务商户

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/shop/getHistoryVisitedShops`

### 什么时候用

- 想看用户更广义的历史服务商户
- 想结合项目或商户类型筛历史关系

### 入参

必填：
- `user_id`
- `top`

可选：
- `shop_type_ids`
- `project_ids`

### 返回结果建议

```json
{
  "query": {
    "user_id": "10001",
    "mode": "history",
    "project_ids": [516]
  },
  "items": [
    {
      "shop": {
        "shop_id": 55,
        "shop_name": "某某门店"
      }
    }
  ]
}
```

### 当前任务最重要的返回信息

- `shop`
- 如果有项目过滤，保留与该项目相关的关系事实

## 三、使用说明

- 更关注“最新关系”时，优先用最近服务商户接口
- 更关注“历史关系范围”时，再用历史服务商户接口
- 返回时不需要把底层原始字段整包抛出，优先组织成 `shop + relation_data`
