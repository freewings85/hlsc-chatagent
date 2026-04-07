按位置搜索附近的商户/门店，返回门店列表。

注意事项：
- location 中 address 和 city/district/street 可组合使用：address 确定搜索中心点，city/district/street 做区域过滤
- 用户指定了具体地址时传 location.address，系统自动解析经纬度，不需要调 collect_user_location
- 用户没指定地址且没有用户位置时，才需要先调 collect_user_location 获取位置
- shop_name、min_rating 等条件参数必须用户明确给出具体值时才传入，禁止根据模糊描述自行猜测填充

## 换渠道省钱提示

搜索结果返回后，如果结果包含不同类型的商户（4S 店、连锁店、独立修理厂等），主动提醒用户：不同类型商户同一项目价差可能很大，尤其 6 年以上车辆从 4S 店转到独立修理厂可省 30%-50%。鼓励用户对比几家再做决定。
