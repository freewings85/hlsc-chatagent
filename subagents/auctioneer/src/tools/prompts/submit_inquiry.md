发布竞标请求到多家商户，通知商户参与报价。

参数说明：
- project_ids: 项目 ID 列表
- shop_ids: 参与竞标的商户 ID 列表
- car_model_id: 车型 ID
- price: 车主出的一口价

返回 task_id 用于后续轮询报价。