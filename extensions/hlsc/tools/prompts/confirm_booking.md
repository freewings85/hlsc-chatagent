在预订下单阶段使用。

参数说明：
- plan_mode: 预订模式
- project_ids: 项目 ID 列表（整数，必须来自 match_project / classify_project 返回的真实 ID，严禁编造）
- shop_ids: 商户 ID 列表（整数，必须来自 search_shops 返回的真实 ID，严禁编造）
- car_model_id: 车型 ID
- price: 预约价格，必须来自实际报价，不可编造，必须大于0
- booking_time: 到店时间，必须已向车主确认
