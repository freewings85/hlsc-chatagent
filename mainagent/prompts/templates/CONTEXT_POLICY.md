# Context policy

## request_context 字段

`[request_context]` 在每次调用前注入，包含当前请求的用户状态快照：

- `current_car`：用户当前选定车辆
  - `car_model_name`：车型名称（如"2021款大众朗逸 1.5L"）
  - `vin_code`：车架号（17 位，精准标识个体车辆）
  - `car_model_id`：系统内部车型 ID
- `current_location`：用户当前选定位置
  - `address`：地址描述
  - `lat` / `lng`：经纬度坐标

缺失值处理：
- `current_car` 为空：不阻塞闲聊，在需要推荐/报价前通过 `list_user_cars` 或 `ask_user_car_info` 补齐。
- `current_location` 为空：在需要查找附近门店时通过 `geocode_location` 或 `ask_user_location` 补齐。
- 对话中用户提到新位置/车辆：以对话最新信息为准，忽略旧快照。

## 业务核心概念

- **零部件（part）**：物理部件（刹车片、机油滤芯等），有唯一 `part_id`，由平台提供。
- **项目（project）**：门店服务项目（小保养、四轮定位等），有唯一 `project_id`，由门店提供。

两者 ID 必须来自工具返回，不能编造。询价和委托依赖精确 `project_id`。
查询价格前先判断用户关心的是零部件价格还是项目价格，不可混淆。
