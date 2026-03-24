根据车辆信息查询推荐养车项目，返回项目列表。

纯查询工具，不与用户交互。查询后需调 ask_user_select_project 展示给用户选择。

输入 vehicle_info 中所有字段可选：
- car_age_year: 车龄（年），默认 1 年
- mileage_km: 里程数（公里）
- car_model_id: 车型编码
- car_model_name: 车型名称