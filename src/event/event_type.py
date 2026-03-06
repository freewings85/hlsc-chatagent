"""事件类型枚举"""

import enum


class EventType(str, enum.Enum):
    """Agent 输出的事件类型。"""

    TEXT = "text"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ARGS = "tool_call_args"
    TOOL_RESULT = "tool_result"
    INTERRUPT = "interrupt"
    ERROR = "error"
    CHAT_REQUEST_END = "chat_request_end"
