---
name: insurance_bidding
description: 保险项目相关
when_to_use: 保险相关项目需要多商户竞价报价时使用。
---

# 保险竞标预订 Skill

## 职责

保险项目专属竞标流程：车主发布项目需求，推送给多家商户，由商户竞价报价。

## 前置条件

- project_ids 已确认（保险相关项目），如果没有的话调用`match_project`
- shop_ids 已确认（参与竞价的商户范围）,如果没有的话，先调用`search_shops`，根据已确认的project_ids和radius=100000，获取shop_ids
- car_model_id 已确认,如果没有的话，先调用`collect_car_info`

## 执行步骤

1. **确认服务时间**：如果没有预约时间，先向用户询问确认时间
   - 阅读 `read <skill-fs-dir>/references/confirm-service-time.md`

2. **确认竞标信息**：调用 `confirm_booking` 将预订信息发给前端确认

3. **判断用户回复**：阅读 `read <skill-fs-dir>/references/bidding-reply-judgment.md`，按规则判断意图并处理

## Tools

- `match_project`
- `search_shops`
- `collect_car_info`
- `confirm_booking`：汇总预订信息发给前端确认，返回车主原始回复文本

## 完成标准

- 预订信息已确认（或取消），且结果已告知车主
