---
name: saving-strategy-selector
description: 从 6 种核心省钱方法中选择并组合适合当前项目的方法，辅以行情参考判断边界。
when_to_use: 省钱目标已确认，需要选择具体的省钱方法和组合策略时使用。
---

# 省钱方法选择 Skill（T4）

## 职责

根据已确认的省钱目标（T3）、项目类型（T3）和消费偏好（T2），从 6 种方法中选择最优组合。

## 执行步骤

1. 先阅读与当前情况相关的 reference：
   - `read <skill-fs-dir>/references/优惠方法与9折规则.md`
   - `read <skill-fs-dir>/references/谈判与竞标规则.md`（如涉及谈判/竞标类方法）
   - `read <skill-fs-dir>/references/配件档次切换规则.md`（如涉及配件降档）
   - `read <skill-fs-dir>/references/省钱行情参考.md`（了解行情边界）
   - `read <skill-fs-dir>/references/组合策略与不可实现边界.md`
2. 判断每种方法是否适用——具体 eligibility 由 tool/API 最终裁决，skill 不写死静态规则
3. 排除互斥方法，组合可叠加方法
4. 如车主目标不可实现，直接反馈
5. 如选择了谈判/竞标类方法，委托 negotiation-bidding-agent subagent

## 6 种方法速查

| 方法 | 说明 | 备注 |
|------|------|------|
| A. 找优惠 | 10元普惠券、"话痨AI预订9折"（主推，对未入驻老商户也适用） | 优先检查 |
| B. 切换商户 | 找更低价类型商户，或同类多商户报价对比 | 需 T5 配合 |
| C. 切换配件档次 | 原厂 > 配套国际 > 国货精品 > 杂牌 | 需确认车主接受度 |
| D. 话痨代谈判 | 通常适用于9折项目，最终以 tool/API eligibility 为准；多轮，价格可变 | → negotiation-bidding-agent |
| E. 一口价竞标 | 车主出一口价，多商户抢单，价格不变 | → negotiation-bidding-agent |
| F. 保险特殊谈判 | 话痨代与商户谈判更多赠送或更多返现 | → negotiation-bidding-agent |

行情参考（非独立方法，用于判断边界）：见 `省钱行情参考.md`

## 未实现能力（设计预留）

- negotiation-bidding-agent：执行方法 D/E/F，subagent 未实现

## 完成标准

- 已选定 1 种或多种省钱方法组合
- 互斥方法已排除
- 如需谈判/竞标，已明确后续委托 subagent
- 如目标不可实现，已直接反馈车主
