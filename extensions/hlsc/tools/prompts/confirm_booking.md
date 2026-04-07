在预订下单阶段使用。汇总所有已确认的预订信息，发送给前端让车主最终确认。

参数说明：
- plan_mode: 预订模式。standard（用户选了商户报价直接预订）或 commission（用户出一口价，委托推送给多家商户）
- project_ids: 项目 ID 列表（整数，必须来自 match_project 返回的真实 ID，严禁编造）
- shop_ids: 商户 ID 列表（整数，必须来自 search_shops 返回的真实 ID，严禁编造）
- car_model_id: 车型 ID（来自 collect_car_info / list_user_cars，项目不需要车型时传空字符串）
- booking_time: 到店时间，必须已向车主确认
- price: 预约价格，必须来自实际报价或车主出的一口价，不可编造
- coupon_ids: 优惠券 ID 列表，来自 search_coupon 返回，无优惠时传空列表
- remark: 车主备注信息，用户主动提出时填写（如"到了打电话""带上旧件"等）

IMPORTANT: 所有 ID 参数（project_ids、shop_ids、coupon_ids）必须来自工具返回的真实数据，严禁编造。
IMPORTANT: booking_time 和 price 必须已向车主确认过，不可自行假设。
