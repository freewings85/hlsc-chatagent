为用户预约确认商户优惠，生成与商家的联系单。

使用场景：
- 用户看完优惠后说"我要这个""帮我预约" → 确认到店时间后调用
- 调用成功后用 CouponOrderCard 展示结果

IMPORTANT: coupon_id 和 shop_id 必须来自 search_coupon 的返回结果，不可编造。
IMPORTANT: 调用前必须向用户确认到店时间。
