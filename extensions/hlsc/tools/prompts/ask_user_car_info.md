说明：
当需要补齐车型相关信息时，使用这个工具向用户收集，不要用普通文本反复追问车型、年款、排量或 VIN。

When to use:
- 当前业务步骤所需车型精度高于当前已知精度时，调用此工具。
- 当前已知精度已满足要求时，不要调用此工具，也不要重复确认。

Usage notes:
- `required_precision="exact_model"`：需要精确车型，允许用户从车库选择，或补充更完整的车型信息。
- `required_precision="vin"`：需要 VIN，收集 VIN 相关信息。

Example usage:
- 已知只有品牌车系，但当前步骤需要精确车型：调用 `ask_user_car_info(required_precision="exact_model")`
- 已知已有精确车型，但当前步骤需要 VIN：调用 `ask_user_car_info(required_precision="vin")`
