---
name: merchant-selection
description: 搜索、筛选、对比和确认服务商户，覆盖附近搜索、历史商户、老商户邀请入驻、管家默认商户、推荐优先级等场景。
when_to_use: 需要为车主找商户、比较商户、确认去哪家商户时使用。
---

# 商户选择 Skill（T5）

## 职责

根据项目类型、位置、消费偏好，搜索和筛选合适的服务商户，帮车主做出选择。

## 执行步骤

1. 判断当前需求类型，读取对应 reference：
   - 搜索附近商户 / 搜索范围策略：`read <skill-fs-dir>/references/商户搜索与范围策略.md`
   - 历史商户 / 老商户未入驻 / 邀请入驻：`read <skill-fs-dir>/references/老商户与邀请入驻.md`
   - 推荐优先级 / 管家默认商户：`read <skill-fs-dir>/references/推荐优先级与默认商户.md`
   - 多商户报价 / 替代方案：`read <skill-fs-dir>/references/报价比较与替代方案.md`
2. 需要位置信息时：
   - 用户已给出明确地名或区域描述 → 调用位置解析 tool 获取坐标
   - 用户没有提供位置信息 → 引导用户补充位置
3. 调用商户搜索 tool（推荐策略由 tool 入参和返回承载）
4. 需要查历史商户时调用历史商户查询 tool
5. 需要获取商户报价时调用报价查询 tool
6. 老商户未入驻时调用邀请入驻 tool 引导邀请

## Tools

- `geocode_location`：将用户描述的地址转为经纬度
- `ask_user_location`：引导用户提供位置信息
- `search_nearby_shops`（待注册）：按位置搜索附近商户，入参支持项目类型、保修状态等
- `get_visited_shops`：查询车主历史服务商户
- `get_project_price`：查询项目在附近门店的报价
- `invite_merchant`（待注册）：引导车主邀请老商户入驻平台

## 车型精度不足时的处理

若商户搜索、报价查询等相关 tool 返回 missing_fields 包含车型相关字段，
则回溯车型信息引导（vehicle-info-guide）。
T5 不自行静态判断哪些场景必须 VIN，由 tool 返回的业务事实裁决。

## 完成标准

- 车主已确认选定一家商户（选择后默认关注）
- 或车主明确表示暂不选定（保留候选列表）
