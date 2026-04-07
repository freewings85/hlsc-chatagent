根据项目、位置和语义条件查询可用的优惠活动，返回平台优惠和门店优惠两类。

使用场景：
- "附近有什么优惠" → 不传 location
- "人民广场附近的优惠" → location={"address": "人民广场"}
- "静安区的保养优惠" → location={"district": "静安区"}, project_ids=[...]
- 有偏好：semantic_query="满减的、送洗车的"

IMPORTANT: 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏。
IMPORTANT: 查到优惠活动后，必须用 CouponCard spec 格式输出每条优惠。
