将用户说的关键词匹配为系统中的养车服务项目，返回 `project_id`、项目名称和 `required_precision`。当用户提到服务项目名称（如"洗车"、"四轮定位"、"保养"）时调用此工具。

返回结果为匹配的项目列表，每个项目包含 `required_precision` 字段：
- `none` — 不需要车型信息
- `basic` — 需要基础车型信息
- `exact_model` — 需要精确车型和 `car_model_id`
- `vin` — 需要 `vin_code`

根据匹配结果处理：
- 匹配到 1 个 → 直接使用该 project_id
- 匹配到多个 → 告知用户匹配结果，让用户确认具体是哪个项目
- 无匹配 → 告知用户未找到相关项目

后续查行情价、门店报价等操作前，按 `required_precision` 收集车型信息。

IMPORTANT: project_id 必须来自本工具的返回结果，不可编造。注意区分零部件（配件）和项目（服务），本工具只匹配项目。
