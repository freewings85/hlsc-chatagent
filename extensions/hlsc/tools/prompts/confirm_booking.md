booking-execution skill 内部使用的工具，不要直接调用。必须通过 booking-execution skill 流程触发。

参数说明：
- plan_mode: 预订模式
- project_ids: 项目 ID 列表
- shop_ids: 商户 ID 列表
- car_model_id: 车型 ID
- price: 预约价格，必须来自 query_shop_price的返回结果中的实际价格，不可编造,必须大于0
- booking_time: 到店时间，必须已向车主确认
- remark: 备注，默认为空，车主可在确认时补充