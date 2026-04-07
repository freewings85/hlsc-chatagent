# SC-003: 预订优惠

## 场景
多轮：查优惠 → 选优惠 + 时间 → book_coupon/apply_coupon。

## 预期
1. 轮 1：search_coupon 返回优惠
2. 轮 2：用户选优惠并给时间 → 调用 book_coupon 或 apply_coupon
