生成联系单，让商户主动联系用户。不是预订下单，是告知商户"这位用户有需求，请联系他"。

参数说明：
- shop_id: 商户 ID（必填），必须来自 search_shops 返回的真实 shop_id
- shop_name: 商户名称（必填），必须来自 search_shops 返回的真实名称
- visit_time: 预计到店时间（必填），支持自然语言（"上午""下午""明天下午3点"），后端解析

返回：
- order_id — 联系单编号
- shop_name — 商户名称
- visit_time — 预约时间

使用场景：
- 用户选好商户后说"帮我联系一下""让他们给我打电话""就这家" → 确认到店时间后调用
- 调用成功后用 ContactOrderCard 展示结果

IMPORTANT: shop_id 必须来自 search_shops 的返回结果，不可编造。
IMPORTANT: 调用前必须向用户确认到店时间。
