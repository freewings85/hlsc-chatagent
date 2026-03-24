按位置搜索附近的汽修/养车门店，返回门店列表（含距离、评分、成交量等信息）。

参数说明：
- latitude: 纬度（必填）
- longitude: 经度（必填）
- keyword: 搜索关键词，如门店名称、品牌、服务类型（"刹车专修"、"途虎"、"洗车"）
- top: 返回数量，默认 5
- radius: 搜索半径（米），默认 10000
- order_by: 排序方式，支持 distance / rating / tradingCount，可组合如 "distance,rating"
- commercial_type: 商户类型列表，如 [1,2,3]（1=汽修门店）
- opening_hour: 营业时间筛选，格式 "HH:MM"
- province_id / city_id / district_id: 按省/市/区筛选
- address_name: 地址名称搜索（如"浦东"）
- package_ids: 服务项目ID，逗号分隔
- min_rating: 最低评分（如 4.0）
- min_trading_count: 最低成交量（如 50）

使用场景：
- "附近有什么修车的店" → latitude, longitude（使用默认参数）
- "找个口碑好的店" → order_by="rating", min_rating=4.0
- "哪家修车靠谱" → order_by="tradingCount", min_trading_count=50
- "能洗车的店" → keyword="洗车"
- "途虎养车" → keyword="途虎"
- "浦东的修车店" → address_name="浦东"
- "现在还营业的店" → opening_hour="14:30"（传入当前时间）
- "近一点的" → radius=3000

IMPORTANT: 此工具需要用户位置信息（latitude/longitude）才能搜索。如果没有位置信息，需先通过其他方式获取。