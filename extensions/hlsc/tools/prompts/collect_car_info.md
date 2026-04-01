此工具会向用户展示一个车辆信息收集界面（选车/输入 VIN），由用户在界面上操作完成信息填写，返回用户填写的结果。

需要车辆信息时，直接调用此工具。不要用文字问用户"请提供车型"或"要我帮你填写吗"。

required_precision 参数：
- `exact_model` — 需要精确车型（品牌、车系、年款）
- `vin` — 需要 VIN 码

常见调用场景：
- 保险竞价需要车辆信息 → 调用 collect_car_info(required_precision="exact_model")
- 查询精确报价需要车型 → 调用 collect_car_info(required_precision="exact_model")
- 需要 VIN 码 → 调用 collect_car_info(required_precision="vin")
- 上下文中已有车辆信息 → 不需要调用
