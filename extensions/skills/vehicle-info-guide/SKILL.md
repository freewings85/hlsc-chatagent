---
name: vehicle-info-guide
description: 车型信息不足时，按精度要求收集车辆信息。
when_to_use: 当前车型信息精度不足以支撑业务操作时使用（如缺少 car_model_id 或 vin_code）。
---

# 车型信息引导 Skill

## 何时触发

当你准备调用业务工具（报价、项目查询等）但发现车型信息不足时，执行本 skill 收集信息。

## 判断所需信息

- 只需要品牌和车系：洗车、通用咨询
- 需要精确车型和 `car_model_id`：常规保养、标准配件更换、一般报价
- 需要 `vin_code`：精准报价、配件兼容性校验、高风险维修

## 执行流程

### 核心规则

- 当前已知车型精度已满足业务步骤要求时，不要再次确认
- 当前已知车型精度不足时，使用 `ask_user_car_info` 收集，不要用纯文本反复追问
- 若业务步骤需要精确车型，返回结果中没有 `car_model_id` 但有可识别的车型描述，可调用 `fuzzy_match_car_info` 补齐 `car_model_id`
- 若业务步骤需要 VIN，必须拿到 `vin_code`；没有 `vin_code` 仍视为精度不足

### 只需品牌+车系

当前信息已满足时，直接继续，不再额外确认。

### 需要精确车型

当前信息不足时，调用 `ask_user_car_info` tool，传入 `required_precision="exact_model"`。

### 需要 VIN

当前信息不足时，调用 `ask_user_car_info` tool，传入 `required_precision="vin"`。

## 用户拒绝提供时

1. 告知精度不足可能导致报价不准、配件不匹配等风险
2. 降级到当前可获取的最高精度继续服务
3. 后续如需更高精度可再次引导

## 完成标准

- tool 返回了满足精度要求的车型信息 → 完成，继续业务流程
- 用户拒绝提供 → 已告知风险并降级 → 完成
