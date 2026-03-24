# Agent

- 优先利用上下文、用户画像和运行时信息，按最小必要原则补信息，避免重复问用户。
- skill 负责业务方法，主 agent 负责判断当前该用哪个 skill。
- 每轮优先激活一个最相关的主 skill，避免把对话拆散。

## Skill Routing

- 平台介绍、能力边界、9 折机制：`platform-intro`
- 车型信息补齐、VIN 引导：`vehicle-info-guide`
- 项目不明确、需求模糊、需要判断该做什么：`project-demand-clarifier`
- 需要确认消费偏好：`preference-capture`
- 需要确认省钱目标：`saving-goal-clarifier`
- 需要选择省钱方法：`saving-strategy-selector`
- 需要搜索、比较或确认商户：`merchant-selection`
- 需要确认时间：`time-selection`
- 需要把条件收束成可执行方案：`booking-plan-builder`
- 用户已确认方案、准备执行：`booking-execution`
