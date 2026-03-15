# 请求上下文

每次对话中会通过 [request_context] 提供用户当前的车辆和位置信息。

## 字段说明

- current_car(car_model_id, car_model_name, vin_code) — 用户当前设置的车辆
- current_location(address, lat, lng) — 用户当前位置

字段值为"(未设置)"时表示用户未提供该信息。

## 使用规则

需要 car_model_id 或 location 时，参考 confirm-car-info / confirm-location skill 的指引。
