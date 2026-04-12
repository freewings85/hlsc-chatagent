"""请求/响应模型

编排模式下 orchestrator 的元数据（workflow_id / step_skeleton / current_step 等）
统一放在 context.orchestrator 里传入（见 mainagent/src/hlsc_context.py 的
OrchestratorContext），不污染 ChatRequest 顶层字段。

降级模式下 context.orchestrator 为 None 或不存在，和原来完全一致。
"""

from pydantic import BaseModel

from agent_sdk._common.request_context import RequestContext


class ChatRequest(BaseModel):
    """对话请求"""

    session_id: str
    message: str
    user_id: str = "anonymous"
    request_id: str | None = None
    """可选：orchestrator 侧传入的 request_id，不传时 SDK 自动生成"""
    context: RequestContext | None = None


class StopRequest(BaseModel):
    """停止任务请求"""

    task_id: str


class AsyncChatRequest(BaseModel):
    """异步对话请求（结果通过 Kafka 推送或 Orchestrator callback）"""

    session_id: str
    message: str
    user_id: str = "anonymous"
    request_id: str | None = None
    context: RequestContext | None = None
    callback_url: str | None = None
    """turn 结束后 try/finally 调的回调 URL。orchestrator 传 /internal/turn_callback，
    降级模式不传。不属于 OrchestratorContext（那是业务编排），这是 HTTP 层通信机制。"""


class InterruptReplyRequest(BaseModel):
    """interrupt 回复请求"""

    interrupt_key: str
    reply: str | dict = ""
