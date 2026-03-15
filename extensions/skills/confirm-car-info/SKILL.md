---
name: confirm-car-info
description: 当需要 car_model_id 但不确定用哪个时，按场景判断如何获取车辆信息。
---

# 确认车辆信息

当你需要调用的工具要求 car_model_id 参数时，按以下场景判断如何获取：

## 场景判断

### 场景 1：request_context 有 current_car，用户没提到其他车
直接使用 request_context 中的 car_model_id，不需要调用任何工具。

### 场景 2：用户提到一个车型名（如"卡罗拉"、"宝马X3"），且不是指自己名下的车
调用 `fuzzy_match_car_info` 工具，传入车型关键词。
匹配结果返回后，用该 car_model_id 继续。

### 场景 3：request_context 没有 current_car，用户也没提到任何车型
调用 `ask_user_car_info` 工具，传入需要车辆信息的原因。
等待用户选择后，用返回的 car_model_id 继续。

### 场景 4：用户说"我的 xx 车"、"帮我那辆车查查"（指自己名下的车辆）
调用 `list_user_cars` 工具获取用户车库。
从列表中找到匹配的车辆，用该 car_model_id 继续。
如果列表中有多辆车且无法确定是哪辆，回复用户让其明确。

## 规则

1. 确认 car_model_id 后再调用业务工具，禁止编造 car_model_id
2. 场景 2 匹配结果要告知用户按哪个车型查询，并提示可修改
3. 一次对话中确认过的 car_model_id 可以复用，不需要重复确认
