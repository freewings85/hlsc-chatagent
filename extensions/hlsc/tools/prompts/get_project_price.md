查询指定项目在附近门店的报价，返回门店列表及各方案价格。

需要 project_ids（项目 ID 列表）、car_model_id（车型编码）、lat/lng（经纬度）。
如果 request_context 中有这些信息且用户没指定新的，直接使用。

支持过滤和排序：
- distance_km: 搜索距离范围（公里），默认 10
- min_rating: 最低评分（如 4.8），不设则不过滤
- shop_ids: 指定门店 ID 列表，不设则搜索所有门店
- sort_by: 排序方式 — distance（按距离，默认）/ rating（按评分）/ price（按价格）

报价分为三个档次：国际大厂、国产品质、原厂。

IMPORTANT: project_ids 必须来自 match_project 工具的返回结果，不可编造。
