Description:
根据项目、商户和语义条件查询可用的优惠活动。

Usage notes:
- semantic_query 只放优惠偏好关键词（如"保养""洗车""便宜"），**严禁**放地址/位置信息（如"南翔""上海"）。
- 如果用户提到了位置（如"南翔附近有什么优惠"），必须先调 search_shops 查到 shop_ids，再把 shop_ids 传给本工具。不要把地址放进 semantic_query。
  - 正确：先 search_shops(location_text="南翔") → 得到 shop_ids → search_coupon(shop_ids=[87,88])
  - 错误：search_coupon(semantic_query=["南翔", "保养"]) ← 禁止把地址放入 semantic_query
- 如果上下文中已有 shop_ids（来自 search_shops 或 session_state），直接传入。
- 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏。
