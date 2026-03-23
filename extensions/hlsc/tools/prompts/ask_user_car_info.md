向用户请求提供车辆信息（car_model_id / car_model_name / vin_code），让用户选择或录入车型。

当car_precision 为 L2 或 L3，车型信息不足时，调用此工具收集车辆信息。

- car_precision=L2（需要精确车型）→ allow_select=true，用户可从车库选择或手动输入
- car_precision=L3（需要 VIN 码）→ allow_select=false，仅允许输入 VIN

用户完成选择后返回 car_model_id 和 car_model_name（L3 还会返回 vin_code）。
