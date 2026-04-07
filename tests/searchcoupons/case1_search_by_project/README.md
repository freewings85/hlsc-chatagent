# SC-001: 按项目查优惠

## 场景
用户问"换机油有优惠吗"，验证 classify_project + search_coupon 全链路。

## 预期
1. 调用 classify_project（关键词"机油"）
2. 调用 search_coupon（带 project_ids）
3. 返回机油保养相关优惠活动
