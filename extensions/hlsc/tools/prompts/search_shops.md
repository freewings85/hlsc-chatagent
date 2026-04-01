按位置搜索附近的商户/门店，返回门店列表。

参数说明：
- latitude: 纬度（必填）
- longitude: 经度（必填）
- keyword: 商户名称关键词，仅用户明确按名称搜索时传入（如"途虎"、"张江汽修"）
- top: 返回数量，默认 5
- radius: 搜索半径（米），默认 10000
- order_by: 排序方式，支持 distance / rating / tradingCount，可组合如 "distance,rating"
- commercial_type: 商户类型列表，用户未指定时不传
- opening_hour: 营业时间筛选，格式 "HH:MM"
- province_id / city_id / district_id: 按省/市/区筛选
- address_name: 地址名称搜索（如"浦东"）
- package_ids: 服务项目ID，逗号分隔
- min_rating: 最低评分，仅用户明确给出具体数值时传入（如用户说"4.5分以上"）
- min_trading_count: 最低成交量，仅用户明确给出具体数值时传入（如用户说"成交100单以上"）

使用场景：
- "附近有什么店" → latitude, longitude（使用默认参数）
- "找个口碑好的店" → order_by="rating"
- "哪家修车靠谱" → order_by="tradingCount"
- "途虎养车" → keyword="途虎"
- "浦东的修车店" → address_name="浦东"
- "现在还营业的店" → opening_hour="14:30"（传入当前时间）
- "近一点的" → radius=3000
- "评分4.0以上的" → min_rating=4.0
- "找附近的4S店" → 传 commercial_type=[对应 typeId]
- "综合修理厂" → 传 commercial_type=[对应 typeId]
<!-- TODO: 商户类型 typeId 映射表待补充到 saving-playbook 商户选择 reference 中 -->

IMPORTANT: 此工具需要用户位置信息（latitude/longitude）才能搜索。如果没有位置信息，需先通过其他方式获取。

IMPORTANT: keyword、min_rating、min_trading_count 必须用户明确给出具体值时才传入，禁止根据模糊描述自行猜测填充。例如用户说"口碑好"不等于 min_rating=4.0，用户说"靠谱"不等于 min_trading_count=50。commercial_type 同理，用户未指定时不传。

## 换渠道省钱提示

搜索结果返回后，如果结果包含不同类型的商户（4S 店、连锁店、独立修理厂等），主动提醒用户：不同类型商户同一项目价差可能很大，尤其 6 年以上车辆从 4S 店转到独立修理厂可省 30%-50%。鼓励用户对比几家再做决定。