"""请求/响应模型"""

from typing import Any

from pydantic import BaseModel

from agent_sdk._common.request_context import RequestContext


# ── Orchestrator 编排字段（所有 ChatRequest 共享的可选字段）──
#
# 这些字段在降级模式（ChatManager 直连）下全部为 None，此时 Agent 走现有 AGENT.md
# 自驱逻辑，update_session_state 工具退化为本地状态管理。
#
# Orchestrator 编排模式下所有字段必须非 None：
# - workflow_id / orchestrator_url：update_session_state 工具用来回调 /internal/advance_step
# - step_skeleton / current_step / completed_steps / session_state / step_pending_fields:
#   注入到 system prompt 让 Agent 看到全局骨架和当前聚焦
# - available_tools：按 step tools 白名单过滤
# - callback_url：try/finally 兜底通知 turn 结束
#
# 为了前端/SDK 向后兼容，这些字段都是 Optional。


class ChatRequest(BaseModel):
    """对话请求"""

    session_id: str
    message: str
    user_id: str = "anonymous"
    context: RequestContext | None = None

    # ── Orchestrator 编排字段（可选，降级模式下全部为 None）──
    request_id: str | None = None
    scenario: str | None = None
    workflow_id: str | None = None
    step_skeleton: list[dict[str, Any]] | None = None
    current_step: dict[str, Any] | None = None
    completed_steps: list[str] | None = None
    session_state: dict[str, Any] | None = None
    step_pending_fields: list[str] | None = None
    available_tools: list[str] | None = None
    callback_url: str | None = None
    orchestrator_url: str | None = None


class StopRequest(BaseModel):
    """停止任务请求"""

    task_id: str


class AsyncChatRequest(BaseModel):
    """异步对话请求（结果通过 Kafka 推送或 Orchestrator callback）"""

    session_id: str
    message: str
    user_id: str = "anonymous"
    context: RequestContext | None = None

    # ── Orchestrator 编排字段（可选，和 ChatRequest 一致）──
    request_id: str | None = None
    scenario: str | None = None
    workflow_id: str | None = None
    step_skeleton: list[dict[str, Any]] | None = None
    current_step: dict[str, Any] | None = None
    completed_steps: list[str] | None = None
    session_state: dict[str, Any] | None = None
    step_pending_fields: list[str] | None = None
    available_tools: list[str] | None = None
    callback_url: str | None = None
    orchestrator_url: str | None = None


class InterruptReplyRequest(BaseModel):
    """interrupt 回复请求"""

    interrupt_key: str
    reply: str | dict = ""
