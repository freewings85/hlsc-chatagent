# SC-002: 语义搜索优惠

## 场景
多轮累积偏好：
- 轮 1："帮我看看换机油的优惠" → search_coupon
- 轮 2："要支付宝的活动" → 再次 search_coupon（semantic_query 累积）

## 预期
1. 轮 1 调用 search_coupon
2. 轮 2 再次调用 search_coupon，semantic_query 包含"支付宝"
