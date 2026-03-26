引导车主邀请未入驻的老商户加入话痨说车平台。

PREREQUISITE — 调用本工具前必须满足以下条件，缺一不可：
1. 已调用 `search_shops` 工具，以商户名称作为 keyword 参数进行搜索
2. `search_shops` 返回结果为空（未找到该商户）

如果尚未调用 search_shops，必须先调用 search_shops，不得直接调用本工具。

When to use:
- 用户明确提到一个特定商户名称（如"朱德保修理厂"、"老王汽修"）
- 已通过 search_shops 搜索该商户名，确认平台上没有该商户
- 需要引导车主邀请该商户入驻

When NOT to use:
- 用户只是在泛泛地找商户（如"附近有什么修车的"），不是找特定商户
- 尚未调用 search_shops 搜索过该商户名
- search_shops 已经返回了匹配的商户结果

调用后：
- 使用返回的信息，配合 invite_shop action 围栏引导车主完成邀请
- 告知车主入驻后预订可享受话痨预订9折优惠
