根据项目、位置和语义条件查询可用的优惠活动，返回平台优惠和门店优惠两类。

参数说明：
- location: 位置条件（LocationFilter 对象，可选）。不传则使用用户当前位置
  - address: 中心地址，用于范围搜索
  - radius: 搜索半径（米），需要有中心点：指定 address 或用户已有位置
  - city: 城市过滤（如"上海"）
  - district: 区过滤
  - street: 路名过滤
- project_ids: 项目 ID 列表（可选），来自 classify_project。无明确项目时传 null
- shop_ids: 商户 ID 列表（可选），未指定商户时传空列表
- date: 查询日期（YYYY-MM-DD，可选），默认当天
- semantic_query: 用户对优惠的自然语言偏好描述。调用前回顾对话中用户提到的所有优惠偏好，完整组装到此参数
- sort_by: 排序方式 — default / promo_value / validity_end / rating / distance
- top_k: 返回数量上限，默认 10

返回：
- platformActivities — 平台优惠活动列表
- shopActivities — 门店优惠活动列表

使用场景：
- "附近有什么优惠" → 不传 location
- "人民广场附近的优惠" → location={"address": "人民广场"}
- "静安区的保养优惠" → location={"district": "静安区"}, project_ids=[...]
- 有偏好：semantic_query="满减的、送洗车的"

IMPORTANT: 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏。
IMPORTANT: 查到优惠活动后，必须用 CouponCard spec 格式输出每条优惠。
