Description:
根据项目、商户和语义条件查询可用的优惠活动。

Usage notes:
- project_ids 必须来自 classify_project 的返回值。用户提到了项目关键词时，先调 classify_project 拿到 projects.id组装成project_ids数组。
- semantic_query 只放优惠偏好关键词（如"保养""洗车""便宜"），**严禁**放地址/位置信息（如"南翔""上海"）和价格相关信息（如"200块左右" "1000元以内"）。
- 如果用户提到了位置相关（如"附近有什么优惠"），必须先调 search_shops 查到 shop_ids，再把 shop_ids 传给本工具。不要把地址放进 semantic_query。
  - 正确：先 search_shops → 得到 shop_ids → search_coupon(shop_ids=[87,88])
  - 错误：search_coupon(semantic_query=["南翔", "保养"]) ← 禁止把地址放入 semantic_query
- 如果上下文中已有 shop_ids（来自 search_shops 或 session_state），直接传入。
- 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏。
