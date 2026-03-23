---
name: booking-plan-builder
description: 判断预订模式（过渡型/标准/竞标/保险/管家/打包），汇总前置任务结果生成可执行的预订方案。
when_to_use: 前置任务核心信息已收集（或部分收集），需要整合成预订方案供车主确认时使用。
---

# 预订方案制定 Skill（T7）

## 职责

判断当前应进入哪种预订模式（plan_mode），组织对应的方案结构，
检查前置任务完成状态，生成可执行预订方案。

## 6 种预订模式

| plan_mode | 模式 | 说明 |
|-----------|------|------|
| transition | T7-A 过渡型预订 | 前置条件不全时的变通方案 |
| standard | T7-B 标准预订 | 购券 → 形成订单 → 推送商户 |
| bidding | T7-C 一口价竞标 | 仅9折项目，多商户抢单 |
| insurance | T7-D 保险特殊竞标 | 保险品类特殊谈判返现 |
| butler | T7-E 管家服务预订 | 到期提醒 + 默认商户 |
| package | T7-F 打包目标拆解 | 总目标拆成多个子预订 |

## plan_mode 确认流程（三步）

1. 模型根据当前前置任务状态初判 plan_mode
2. 调用预订校验相关 tool（只读）确认券型可用性和模式适配性
3. 根据校验结果最终确认 plan_mode

plan_mode 不应只靠模型凭感觉判断，必须有 tool 参与校验。
T7 只做方案制定和校验，**不执行任何有副作用的动作**（购券、下单、推送等留给 T8）。

## 执行步骤

1. 初判 plan_mode 后，读取对应 reference：
   - 过渡型：`read <skill-fs-dir>/references/T7-A-过渡型预订方案.md`
   - 标准：`read <skill-fs-dir>/references/T7-B-标准预订流程.md`
   - 竞标：`read <skill-fs-dir>/references/T7-C-一口价竞标预订.md`
   - 保险：`read <skill-fs-dir>/references/T7-D-保险特殊竞标.md`
   - 管家：`read <skill-fs-dir>/references/T7-E-管家服务预订.md`
   - 打包：`read <skill-fs-dir>/references/T7-F-打包目标拆解.md`
2. 检查前置任务的完成状态，如有缺失项提示车主补充
3. 调用预订校验 tool（只读）校验券型适用性和模式适配性
4. 最终确认 plan_mode，生成方案呈现给车主确认
5. **车主确认方案后，进入执行阶段**（购券、下单、推送等动作全部在 T8 完成）

## T7/T8 动作边界

- T7 只做：校验 + 方案组装 + 呈现给车主确认
- T8 才做：购券、下单、推送等有副作用的动作
- T7 中调用的 tool 全部是只读的，不产生任何业务副作用

## 车型精度不足时的处理

若方案校验过程中 tool 返回 missing_fields 包含车型相关字段，
则回溯车型信息引导（vehicle-info-guide）。
T7 不自行判断车型精度规则，由 tool 返回的业务事实裁决。

## Tools（T7 只使用只读工具）

- `check_coupon_eligibility`（待注册）：只读校验券型适用性 + 模式适配性，不产生副作用

## Subagents

- negotiation-bidding-agent（未实现）：竞标和谈判执行
- execution-planner-agent（未实现）：复杂执行编排

## 完成标准

- plan_mode 已确认
- 完整方案已生成（项目+商户+时间+费用+省钱方法+券型）
- 方案已呈现给车主，等待确认
