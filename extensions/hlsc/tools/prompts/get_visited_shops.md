查询用户去过的商户（上次去过或历史去过），返回商户详情列表。

参数说明：
- query_type: 查询类型
  - "latest": 上次去过的商户（默认 top=1）
  - "history": 历史去过的商户（默认 top=5）
- top: 返回数量
- commercial_type: 商户类型ID列表（仅 history 模式有效），如 [1,2] 表示只查洗车店和修理厂
- package_ids: 项目包ID列表（仅 history 模式有效），如 [100,200] 表示只查做过这些项目的商户

使用场景：
- "上次去的那家店叫什么" → query_type="latest", top=1
- "我之前去过哪些店" → query_type="history", top=5
- "最近去的那家修理厂" → query_type="latest", top=1
- "我去过的洗车店有哪些" → query_type="history", commercial_type=[对应类型ID]
- "做过保养的门店" → query_type="history", package_ids=[对应项目ID]

返回字段：
- shop_id, name: 商户ID和名称
- address: 完整地址（省市区+详细地址）
- phone: 联系电话
- rating: 评分
- trading_count: 成交量
- service_scope: 服务范围标签列表
- commercial_type: 商户类型
- opening_hours: 营业时间
- longitude, latitude: 经纬度
- packages: 服务项目列表（如有）
- last_order_code, last_order_time: 上次订单编号和时间（仅 latest 模式）

IMPORTANT: 此工具自动使用当前登录用户的身份查询，无需额外提供用户信息。