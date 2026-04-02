更新会话状态。当通过工具调用获得关键信息（项目、商户、车型等）后，用此工具记录已确认的信息，后续轮次可直接使用，避免重复查询。

使用时机：
- 调用 match_project 返回结果后 → 记录 project_id, project_name
- 调用 search_shops 用户选定商户后 → 记录 shop_id, shop_name
- 用户确认车型后 → 记录 car_model_id, car_model_name
- 用户确认到店时间后 → 记录 booking_time
- 获取优惠券后 → 记录 coupon_id
- 获取位置后 → 记录 location

参数 updates 是一个字典，key 是字段名，value 是值。value 为 null 表示清除该字段。