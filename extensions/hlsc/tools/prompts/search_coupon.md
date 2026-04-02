根据项目、位置和语义条件查询可用的优惠活动，返回平台优惠和门店优惠两类。

参数说明：
- project_ids: 项目 ID 列表（可选），来自 classify_project。无明确项目时传 null
- shop_ids: 商户 ID 列表（可选），未指定商户时传空列表
- city: 城市名称（可选），用于按地域筛选（如"北京"）
- latitude: 用户纬度（可选），来自 geocode_location 返回，配合 radius 做距离筛选
- longitude: 用户经度（可选），来自 geocode_location 返回
- radius: 搜索半径（米，可选），如 5000 表示 5 公里。需配合 latitude/longitude
- semantic_query: 用户对优惠的自然语言偏好描述（可选）。调用前回顾对话中用户提到的所有优惠偏好，完整组装到此参数。例如"支付宝支付的满减活动、送洗车的"
- sort_by: 排序方式 — default（默认热度）/ discount_amount（优惠金额）/ validity_end（即将过期优先）
- top_k: 返回数量上限，默认 10

返回：
- platformActivities — 平台优惠活动列表
- shopActivities — 门店优惠活动列表
- 每条包含 coupon_id、coupon_name、shop_id、shop_name、coupon_description、address、phone、rating

使用场景：
- 有项目：search_coupon(project_ids=["换机油ID"], top_k=10)
- 有项目+偏好：search_coupon(project_ids=["轮胎ID"], semantic_query="满减的、送洗车的")
- 按城市查：search_coupon(city="北京", top_k=10)
- 附近查：search_coupon(project_ids=["洗车ID"], latitude=39.9, longitude=116.4, radius=5000)

IMPORTANT: 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏。
IMPORTANT: 查到优惠活动后，必须用 CouponCard spec 格式输出每条优惠。
IMPORTANT: 用户提到"附近""周边"时，先调 collect_location + geocode_location 获取坐标，再传 latitude/longitude/radius。
