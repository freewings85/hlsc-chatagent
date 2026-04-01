booking-execution skill 竞标模式专用工具。用户确认竞标预订后调用此工具启动多商户竞价。

调用时机：竞标预订（plan_mode=bidding）流程中，用户确认预订信息后调用。

参数说明：
- order_id: 服务订单 ID

工具行为：
1. 调用 auctioneer 服务启动竞价工作流
2. 返回 auction_start 卡片（含 task_id），前端收到后自行轮询进度

返回值：auction_start 卡片（含 task_id 和 order_id），或错误信息。
