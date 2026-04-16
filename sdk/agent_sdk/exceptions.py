"""Agent SDK 公开异常。

业务工具 raise 这些异常时，agent loop 会专门处理（更友好的日志、终止 loop 等）。
"""

from __future__ import annotations


class AgentLoopError(Exception):
    """业务工具触发的"应当结束本轮 agent loop"信号基类。

    SDK 在 agent loop 的 except 分支里专门 catch，写入有标识的日志。
    业务方应该 raise 子类（不要直接 raise AgentLoopError）。
    """


class WorkflowUnavailableError(AgentLoopError):
    """工作流后端不可用，本轮 agent loop 不应继续。

    典型场景：
    - report_to_workflow 调 Temporal update 报 timeout / connection / 其它错
    - 同一工具反复失败说明环境问题，继续重试只会浪费 LLM 调用

    Raise 后 agent loop 立刻终止，前端会收到 ERROR + CHAT_REQUEST_END 事件，
    日志里会标识为 "workflow unavailable" 而不是普通"agent loop 异常"。
    """
