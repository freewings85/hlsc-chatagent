轮询收集商户报价。每次调用返回新增的报价和整体进度。

参数说明：
- task_id: 竞标任务 ID（来自 submit_inquiry 返回）
- total_merchants: 参与竞标的商户总数

返回 new_quotes（本次新增报价）、total_responded（已回复总数）、all_done（是否全部回复）。