Description:
根据项目、商户和语义条件查询可用的优惠活动，返回平台优惠和门店优惠两类。

Usage notes:
- 如果上下文中没shop_ids，先根据调用search_shops查询shop_ids
- activity_type_text 原样传入用户提到的优惠类型描述，不做加工。
- 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏。
