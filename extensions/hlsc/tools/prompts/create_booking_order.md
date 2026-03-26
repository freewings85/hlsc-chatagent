汇总预订信息并展示给车主确认，等待车主回复。本工具不直接创建订单，真实下单由前端完成。

参数说明：
- plan_mode: 预订模式（必填），取值：transition（过渡型）/ standard（标准）/ bidding（竞标）/ insurance（保险竞标）/ butler（管家服务）/ package（打包拆解）
- project_ids: 项目 ID 列表，必须来自 match_project 工具的返回结果，不可编造
- shop_ids: 商户 ID 列表，必须来自 search_nearby_shops 或 get_visited_shops 的返回结果
- car_model_id: 车型 ID，来自上下文
- price: 预订价格，来自报价查询结果
- booking_time: 到店时间（必填），必须先向车主确认后填入。支持具体日期时间、时间范围、或"由商户排期"（仅当车主明确表示时间灵活时）

返回值为车主的原始回复文本，由 skill 判断意图并决定下一步。

IMPORTANT: 调用前必须已与车主确认到店时间（或车主明确表示时间灵活）。如果还没确认时间，先询问车主，不要直接调用。
IMPORTANT: project_ids 和 shop_ids 必须来自前序工具的返回结果，不可自行编造。