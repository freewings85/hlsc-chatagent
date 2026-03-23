---
name: vehicle-info-guide
description: 车型信息不足时，按精度要求收集车辆信息。
when_to_use: 当前车型信息精度不足以支撑业务操作时使用（如缺少 car_model_id 或 vin_code）。
---

# 车型信息引导 Skill

## 何时触发

当你准备调用业务工具（报价、项目查询等）但发现车型信息不足时，执行本 skill 收集信息。

## 判断所需精度

| 精度 | 含义 | 典型场景 |
|------|------|----------|
| L1 | 品牌+车系（如"宝马X3"） | 洗车、通用咨询 |
| L2 | 品牌+车系+年款+排量 + car_model_id | 常规保养、标准配件更换、一般报价 |
| L3 | 完整 17 位 VIN 码 | 精准报价、配件兼容性校验、高风险维修 |

## 执行流程

按所需精度，选择**一种**方式收集信息：

### L1：只需品牌+车系

直接询问用户车型关键词，调用 `fuzzy_match_car_info` tool 匹配。

### L2：需要精确车型

调用 `ask_user_car_info` tool，传入 `allow_select=true`：
- 前端展示车库选择 + 手动输入两种方式
- tool 返回 `car_model_id` + `car_model_name`

### L3：需要 VIN 码

调用 `ask_user_car_info` tool，传入 `allow_select=false`：
- 前端仅展示 VIN 输入方式，不允许从车库选择
- tool 返回 `car_model_id` + `car_model_name` + `vin_code`

## 用户拒绝提供时

1. 告知精度不足可能导致报价不准、配件不匹配等风险
2. 降级到当前可获取的最高精度继续服务
3. 后续如需更高精度可再次引导

## 完成标准

- tool 返回了满足精度要求的车型信息 → 完成，继续业务流程
- 用户拒绝提供 → 已告知风险并降级 → 完成
