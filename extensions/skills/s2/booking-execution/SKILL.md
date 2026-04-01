---
name: booking-execution
description: 车主提出预订意向后，按 plan_mode 分流——标准预订、委托预订走不同执行路径。
when_to_use: 车主表示要预订、下单、约服务，或已确认方案准备执行时使用。
---

# 预订执行 Skill

## 职责

从车主提出预订意向开始，按 plan_mode 分流到不同执行路径。

## 执行步骤

1. 判断 plan_mode（由 agent 根据用户选择自动确定）
2. 按模式分流：
   - **standard**（标准预订）→ 用户选择某个商户的报价直接预订
   - **commission**（委托预订）→ 车主出一口价，委托推送给多家商户
   - 保险项目竞标 → 使用 `publish-bidding` skill（不在本 skill 处理）

## 标准预订流程

用户选择某个商户的报价直接预订：

1. 如果没有预约时间，先向用户询问确认时间：阅读 `read <skill-fs-dir>/references/confirm-service-time.md`
2. 调用 `confirm_booking` 将预订信息发给前端确认
3. **判断用户回复**：阅读 `read <skill-fs-dir>/references/booking-reply-judgment.md`，按规则判断意图并处理

## 委托预订流程

车主出一口价，委托推送给多家商户：

1. 如果没有预约时间，先向用户询问确认时间：阅读 `read <skill-fs-dir>/references/confirm-service-time.md`
2. 如果没有一口价，先向用户询问期望价格
3. 调用 `confirm_booking` 将预订信息发给前端确认
4. **判断用户回复**：阅读 `read <skill-fs-dir>/references/booking-reply-judgment.md`，按规则判断意图并处理

## Tools

- `confirm_booking`：汇总预订信息发给前端，返回车主原始回复文本

## 完成标准

- 预订信息已确认（或取消），且结果已告知车主
