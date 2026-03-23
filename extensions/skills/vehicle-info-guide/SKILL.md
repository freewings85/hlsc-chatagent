---
name: vehicle-info-guide
description: 根据相关 tool/API 返回的车型精度要求和缺失字段，引导车主补充 VIN、精确车型或轮胎规格。
when_to_use: 相关 tool/API 返回结果表明当前车型信息精度不足（如 missing_fields 包含 vin/car_model_id/tire_spec，或 required_vehicle_precision 高于已有精度）时使用。
---

# 车型信息引导 Skill（T1）

## 职责

根据相关 tool/API 返回的车型精度要求（required_vehicle_precision）和缺失字段（missing_fields），
引导车主补充所需的车型信息。

## 精度等级定义（沟通框架，非判断依据）

以下分级仅用于向车主解释"为什么需要更详细的信息"，
**当前具体需要哪一级精度，由相关 tool/API 在运行时返回，skill 不自行静态判断。**

| 精度 | 内容 | 说明 |
|------|------|------|
| L1 简单车型 | 品牌+车系（如"宝马X3"） | 最基本的车型信息 |
| L2 精确车型 | 品牌+车系+年款+排量，必要时可带 car_model_id | 较精确的车型信息 |
| L3 VIN | 完整 17 位车架号 | 最精确，适用于精准报价、配件兼容性校验等 |

## 执行步骤

1. 先阅读本 skill 中与当前问题直接相关的 reference 文档：
   - VIN 价值和获取方式：`read <skill-fs-dir>/references/VIN价值说明与获取策略.md`
2. 读取触发本 skill 的 tool 返回结果中的 required_vehicle_precision 和 missing_fields
3. 如果已有车型信息满足要求，直接使用，不再追问
4. 如果需要补充信息，根据 missing_fields 选择引导策略：
   - 需要 VIN → 引导获取 VIN（三种获取策略）
   - 需要精确车型 → 引导补充品牌+车系+年款+排量
   - 需要轮胎规格 → 引导补充轮胎规格或拍照识别
5. 根据用户提供的信息，调用车型匹配、车辆列表查询、轮胎识别等相关 tool 获取结果

## Tools

- `fuzzy_match_car_info`：根据车主描述模糊匹配车型，获取 car_model_id
- `list_user_cars`：查看车主已绑定的车辆列表
- `ask_user_car_info`：引导车主提供更详细的车型信息
- `tire_image_recognize`（待注册）：轮胎照片识别规格

## 三种获取策略

1. **展示价值**：说明有 VIN 后的好处（精准报价、生命周期项目清单）
2. **引导上传**：提供上传链接，引导车主自行上传
3. **线下协助**：建议预约简单项目（如洗车），让商户师傅协助录入

## 降级路径

车主拒绝或无法提供所需信息时：
- 明确告知精度不足可能带来的风险
- 降级到当前可获取的最高精度继续服务
- 记录当前精度，后续如需升级可再次引导

## 完成标准

- 车型信息已满足触发 tool 返回的 required_vehicle_precision / missing_fields 要求
- 或车主明确拒绝提供更高精度信息，已告知风险并记录当前精度
