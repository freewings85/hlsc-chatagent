Description:
搜索商户/门店，支持按位置、项目、商户名、评分等条件筛选，返回门店列表。

Usage notes:
- location_text 仅传用户提到的具体位置（地标、路名、小区、商圈等），不接受省/市/县等行政区域名。用户没提具体位置则传空。工具内部会自动从 context 获取城市信息，不需要你代劳。
  - 正确：用户说"南翔附近" → location_text="南翔"
  - 正确：用户说"张江高科" → location_text="张江高科"
  - 正确：用户说"帮我找修理厂"（没提位置） → location_text=""
  - 错误：location_text="上海市" ← 行政区域，禁止
  - 错误：location_text="嘉定区" ← 行政区域，禁止
- use_current_location 仅当用户希望查'附近'或'周围'等，依赖当前位置的商户时设为 true
- radius 仅在用户明确给出距离数字时传入，"附近"不算明确距离。
- shop_type_text 原样传入用户提到的商户类型描述，不做加工。
- shop_name、min_rating 等条件参数须用户明确给出具体值时才传入，禁止猜测填充。
- project_ids 必须来自 classify_project 的返回值。用户提到了项目关键词时，先调 classify_project 拿到 projects.id组装成project_ids数组。

## 换渠道省钱提示

搜索结果返回后，如果结果包含不同类型的商户（4S 店、连锁店、独立修理厂等），主动提醒用户：不同类型商户同一项目价差可能很大，尤其 6 年以上车辆从 4S 店转到独立修理厂可省 30%-50%。鼓励用户对比几家再做决定。
