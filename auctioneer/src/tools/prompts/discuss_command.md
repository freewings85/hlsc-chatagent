在询价途中向商户发出指令。两种模式：
- broadcast_only：仅广播消息，商户只需查看无需操作
- require_requote：要求商户重新报价（例如报价不合理或条件变更时）

参数说明：
- order_id: 服务订单 ID
- command: 指令类型（broadcast_only / require_requote）
- content: 附言内容，说明指令原因或补充信息

适用场景：报价不充分需要更多信息、需要通知商户最新情况、要求商户调整报价。