为用户申领商户优惠活动，生成与商家的联系单。不是完整预订，只是告知商家用户想使用该优惠。

参数说明：
- activity_id: 优惠活动 ID（必填），必须来自 search_coupon 返回的真实 activity_id
- shop_id: 商户 ID（必填），必须来自 search_coupon 返回的真实 shop_id
- visit_time: 预计到店时间（必填），支持自然语言（如"明天下午3点"、"周六上午"），必须先向用户确认

返回：
- contact_order_id — 联系单编号
- shop_name — 商户名称
- activity_name — 优惠活动名称
- visit_time — 到店时间
- message — 确认信息

使用场景：
- 用户看完优惠后说"我要这个""帮我申请" → 确认到店时间后调用
- 生成联系单后告知用户"已帮您预约，商家会收到信息"

IMPORTANT: activity_id 和 shop_id 必须来自 search_coupon 的返回结果，不可编造。
IMPORTANT: 调用前必须向用户确认到店时间。
