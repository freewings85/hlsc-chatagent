按位置搜索附近的商户/门店，返回门店列表。

使用场景：
- "附近有什么店" → 不传 location（使用用户位置）
- "人民广场附近10公里" → location={"address": "人民广场", "radius": 10000}
- "淮海中路上的店" → location={"street": "淮海中路"}
- "静安区的4S店" → location={"district": "静安区"}, commercial_type=[对应 typeId]
- "评分4.0以上的" → min_rating=4.0
- "途虎养车" → shop_name="途虎"

IMPORTANT: shop_name、min_rating、min_trading_count 必须用户明确给出具体值时才传入，禁止根据模糊描述自行猜测填充。

## 换渠道省钱提示

搜索结果返回后，如果结果包含不同类型的商户（4S 店、连锁店、独立修理厂等），主动提醒用户：不同类型商户同一项目价差可能很大，尤其 6 年以上车辆从 4S 店转到独立修理厂可省 30%-50%。鼓励用户对比几家再做决定。
