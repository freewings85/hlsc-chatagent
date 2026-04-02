为用户预约确认商户优惠，生成与商家的联系单。

参数说明：
- coupon_id: 优惠券 ID（必填），必须来自 search_coupon 返回的真实 coupon_id
- shop_id: 商户 ID（必填），必须来自 search_coupon 返回的真实 shop_id
- visit_time: 预约到店时间（必填），支持自然语言表达，原样传给后端：
  - "上午" → 后端默认 10:00
  - "下午" → 后端默认 15:00
  - "明天下午3点" "周六上午" → 后端解析具体时间
  - 不需要 agent 转换格式

返回：
- order_id — 联系单编号
- visit_time — 预约时间

使用场景：
- 用户看完优惠后说"我要这个""帮我预约" → 确认到店时间后调用
- 调用成功后用 CouponOrderCard 展示结果

IMPORTANT: coupon_id 和 shop_id 必须来自 search_coupon 的返回结果，不可编造。
IMPORTANT: 调用前必须向用户确认到店时间。
