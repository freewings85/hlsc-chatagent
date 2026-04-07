根据项目、位置和语义条件查询可用的优惠活动，返回平台优惠和门店优惠两类。

注意事项：
- location 用法同 search_shops：address 确定搜索中心，city/district/street 做区域过滤
- 用户指定了具体地址时传 location.address，不需要调 collect_user_location
- 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏
- 查到优惠活动后，必须用 CouponCard spec 格式输出每条优惠
