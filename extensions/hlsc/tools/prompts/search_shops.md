按标准条件搜索商户，返回稳定的商户详情列表。

When to use:
- 需要按位置、距离、关键词、项目、评分、营业时间等标准条件搜索候选商户
- 需要返回普通商户清单，供后续确认、比较或推荐

Usage notes:
- 先确保已经有用户位置坐标；没有位置时不要硬搜
- 这是标准商户搜索工具，优先用于直接查询附近或指定范围内的候选商户
- 返回的是商户详情数据，不只是商户名称
- 如果任务需要复杂排序、聚合、价格比较或额外计算，改用 `call_query_codingagent`
- 用户未明确指定 project_ids 或 commercial_type 时，不要自行猜测填充
- `shop_name` 只用于明确的商户名称

返回结果中的每个商户通常包含：
- `shop_id`
- `name`
- `address`
- `province`
- `city`
- `district`
- `commercial_type`
- `latitude`
- `longitude`
- `distance_m`
- `distance`
- `rating`
- `trading_count`
- `phone`
- `tags`
- `opening_hours`
- `images`
