---
name: insurance-bidding
description: 保险项目竞标预订 — 确认预订信息、创建订单、返回 order_id 给前端。
when_to_use: 保险相关项目需要多商户竞价报价时使用。
---

# 保险竞标预订 Skill

## 职责

保险项目专属竞标流程：确认竞标信息 → 创建订单 → 返回 order_id 卡片。

## 前置条件（LLM 在调用前需确保）

- project_ids 已确认（保险相关项目），如果没有的话就用 1461
- shop_ids 已确认（参与竞价的商户范围）,如果没有的话，先调用`search_shops`，根据已确认的project_ids和radius=100000，获取shop_ids
- car_model_id 已确认,如果没有的话，先调用`collect_car_info`

## 执行步骤

1. 收集前置条件（project_ids、shop_ids、car_model_id），缺失的通过对应工具获取
2. 收集完成后，调用脚本执行确认和创建订单：

```
invoke_skill("insurance-bidding:confirm_information", args='{"project_ids":[1461],"shop_ids":[87,88],"car_model_id":"bmw-325li-2024","booking_time":"这周末"}')
```

## 脚本执行流程（confirm_information 自动处理）

1. **confirm_booking 中断**：向前端发送预订确认卡片，等待用户回复
   - 前端收到的 interrupt 数据结构：
     ```json
     {
       "type": "confirm_booking",
       "question": "请确认以下预订信息：",
       "booking_params": {
         "plan_mode": "bidding",
         "project_ids": [1461],
         "shop_ids": [87, 88],
         "car_model_id": "bmw-325li-2024",
         "booking_time": "",
         "upload_image": true
       }
     }
     ```
   - 前端通过 `POST /chat/interrupt-reply` 回复纯文本

2. **判断用户回复**：确认 → 创建订单 / 取消 → 结束 / 其他 → 返回给 LLM 处理

3. **创建订单**：调用 `POST /serviceorder/create` 创建报价单

4. **返回 order_created 卡片**：前端据此获取 order_id

## Tools

- `search_shops`：搜索参与竞价的商户
- `collect_car_info`：收集车型信息

## 完成标准

- 订单已创建，order_created 卡片已返回给前端
- 或车主取消了竞标预订
