Description:
为用户领取商户优惠活动，生成与商家的联系单。

Usage notes:
- 用户看完优惠后说"我要这个""帮我领取" → 调用
- 调用成功后用 CouponOrderCard 展示结果
- coupon_id 和 shop_id 必须来自 search_coupon 的返回结果，不可编造
