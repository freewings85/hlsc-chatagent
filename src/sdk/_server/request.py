"""请求/响应模型"""

from pydantic import BaseModel

from src.sdk._common.request_context import RequestContext


class ChatRequest(BaseModel):
    """对话请求"""

    session_id: str
    message: str
    user_id: str = "anonymous"
    context: RequestContext | None = None


class StopRequest(BaseModel):
    """停止任务请求"""

    task_id: str


class AsyncChatRequest(BaseModel):
    """异步对话请求（结果通过 Kafka 推送）"""

    session_id: str
    message: str
    user_id: str = "anonymous"
    context: RequestContext | None = None


class InterruptReplyRequest(BaseModel):
    """interrupt 回复请求"""

    interrupt_key: str
    reply: str | dict = ""
