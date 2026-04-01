根据项目和商户查询可用的优惠活动，返回平台优惠和门店优惠两类。

参数说明：
- project_ids: 项目 ID 列表（必填），来自 classify_project 或 match_project 返回的 project_id
- shop_ids: 商户 ID 列表（可选），来自 search_shops 返回的 shop_id；未指定商户时不传或传空列表

返回：
- platformActivities — 平台优惠活动列表，每个包含 activity_id、activity_name、shop_id、shop_name、activity_description（使用限制说明）
- shopActivities — 门店优惠活动列表，格式同上

使用场景：
- 支持同时查多个项目的优惠，传入多个 project_id 即可一次返回所有结果
- 可同时传入 project_ids 和 shop_ids，查指定门店的优惠
- 帮用户对比不同门店优惠 → 分别传入不同 shop_ids 查询

IMPORTANT: project_ids 必须来自 classify_project 或 match_project 的返回结果，不可编造。
IMPORTANT: 注意向用户说明优惠活动的使用限制条件（activity_description 字段内容）。
IMPORTANT: 查到优惠活动后，必须用 CouponCard spec 格式输出每条优惠。