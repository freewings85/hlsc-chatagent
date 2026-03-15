---
name: confirm-location
description: 当需要 lon/lat 但不确定用哪个位置时，按场景判断如何获取位置信息。
---

# 确认位置信息

当你需要调用的工具要求 lon/lat 参数时，按以下场景判断如何获取：

## 场景判断

### 场景 1：request_context 有 current_location，用户没指定其他位置
直接使用 request_context 中的 lat/lng，不需要调用任何工具。

### 场景 2：用户指定了一个位置（如"静安"、"浦东张江"）
调用 `geocode` 工具，传入地名。
如果地理编码结果明确，直接使用返回的 lat/lng。
如果结果模糊（多个候选），调用 `ask_user_location` 让用户选择。

### 场景 3：request_context 没有 current_location，用户也没提到位置
调用 `ask_user_location` 工具，让用户提供位置。
等待用户选择后，用返回的 lat/lng 继续。

## 规则

1. 确认 lat/lng 后再调用业务工具，禁止编造坐标
2. 一次对话中确认过的位置可以复用，不需要重复确认
