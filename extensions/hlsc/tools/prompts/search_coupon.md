Description:
根据项目、位置和语义条件查询可用的优惠活动，返回平台优惠和门店优惠两类。

Usage notes:
- location_text 原样传入用户提到的位置描述，不做拆解加工。
- use_current_location 仅在使用 context 中用户已有定位时设为 true。
- radius 仅在用户明确给出距离数字时传入。
- 调用前回顾本次对话中用户提到的所有优惠偏好，完整组装 semantic_query，不要遗漏。
- 查到优惠活动后，必须用 CouponCard spec 格式输出每条优惠。
