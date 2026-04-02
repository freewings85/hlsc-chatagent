为用户申领商户优惠，生成与商家的联系单。不是完整预订，只是告知商家用户想使用该优惠。

参数说明：
- coupon_id: 优惠券 ID（必填），必须来自 search_coupon 返回的真实 coupon_id
- shop_id: 商户 ID（必填），必须来自 search_coupon 返回的真实 shop_id
- visit_time: 预约到店时间（必填），支持自然语言（如"明天下午3点"、"周六上午"），必须先向用户确认

返回：
- order_id — 联系单编号
- visit_time — 预约时间

使用场景：
- 用户看完优惠后说"我要这个""帮我申请" → 确认到店时间后调用
- 调用成功后用 CouponOrderCard 展示结果（order_id + shop_name + coupon_name + visit_time）

IMPORTANT: coupon_id 和 shop_id 必须来自 search_coupon 的返回结果，不可编造。
IMPORTANT: 调用前必须向用户确认到店时间。
