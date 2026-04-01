---
name: insurance_bidding
description: 保险项目相关（竞价、预定、报价）
when_to_use: 保险相关项目需要多商户竞价报价时使用。
---

# 保险竞标预订 Skill

## 职责

保险项目专属竞标流程：车主发布项目需求，推送给多家商户，由商户竞价报价。

## 前置条件

- project_ids 已确认（保险相关项目），如果没有的话就用 1461
- shop_ids 已确认（参与竞价的商户范围）,如果没有的话，先调用`search_shops`，根据已确认的project_ids和radius=100000，获取shop_ids
- car_model_id 已确认,如果没有的话，先调用`collect_car_info`

## 执行步骤

1. **确认服务时间**：如果没有预约时间，先向用户询问确认时间
   - 阅读 `read <skill-fs-dir>/references/confirm-service-time.md`

2. **确认竞标信息**：调用 `confirm_booking(plan_mode="bidding", ...)` 将竞标信息发给前端确认
   - **不传 price**（由商户竞价决定）
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
         "booking_time": "这周末",
         "upload_image": true
       }
     }
     ```
   - 前端通过 `POST /chat/interrupt-reply` 回复纯文本

3. **判断用户回复**：阅读 `read <skill-fs-dir>/references/bidding-reply-judgment.md`，按规则判断意图并处理

## Tools

- `match_project`：匹配项目 ID
- `search_shops`：搜索参与竞价的商户
- `collect_car_info`：收集车型信息
- `confirm_booking`：汇总预订信息发给前端确认（interrupt），返回车主纯文本回复

## 完成标准

- 预订信息已确认（或取消），且结果已告知车主
