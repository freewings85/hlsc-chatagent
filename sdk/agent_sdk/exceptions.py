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
    - update_workflow_state 调 Temporal update 报 timeout / connection / 其它错
    - 同一工具反复失败说明环境问题，继续重试只会浪费 LLM 调用

    Raise 后 agent loop 立刻终止，前端会收到 ERROR + CHAT_REQUEST_END 事件，
    日志里会标识为 "workflow unavailable" 而不是普通"agent loop 异常"。
    """


class TooManyToolErrorsError(AgentLoopError):
    """本轮累计 tool 错误超阈值，触发硬停。

    工具在自己判断后端失败的地方 `ctx.deps.tool_error_count += 1`；
    loop 在每轮 tool 执行完后检查 count >= deps.max_tool_errors，超阈值时
    raise 此异常。

    loop 的 outer catch 专门识别这个异常，**不走 LLM 生成最终回复**，直接
    emit 一段固定文本 "系统异常，请稍后重试" 给用户，止血用户体验。
    """
