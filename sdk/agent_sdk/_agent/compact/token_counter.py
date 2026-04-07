"""Token 估算工具。

使用字符数 / 4 做粗略估算，足够用于压缩阈值判断。
未来可替换为 tiktoken 精确计算。
"""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

# 粗略估算：1 token ≈ 2 字符（中文约 1.5 字符/token，英文约 4，取偏安全值）
_CHARS_PER_TOKEN = 2


def estimate_tokens(text: str) -> int:
    """估算文本的 token 数。"""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def estimate_part_tokens(part: object) -> int:
    """估算单个 part 的 token 数。"""
    if isinstance(part, (TextPart, UserPromptPart)):
        content = part.content
        if isinstance(content, str):
            return estimate_tokens(content)
        return 100  # 非文本内容（图片等）给一个估算值
    if isinstance(part, ToolCallPart):
        args_str = str(part.args) if part.args else ""
        return estimate_tokens(part.tool_name) + estimate_tokens(args_str)
    if isinstance(part, ToolReturnPart):
        content = part.content
        if isinstance(content, str):
            return estimate_tokens(content)
        return estimate_tokens(str(content))
    return 50  # 其他 part 类型给默认值


def estimate_message_tokens(msg: ModelMessage) -> int:
    """估算单条消息的 token 数。"""
    total = 0
    if isinstance(msg, (ModelRequest, ModelResponse)):
        for part in msg.parts:
            total += estimate_part_tokens(part)
    return max(1, total)


def estimate_messages_tokens(messages: list[ModelMessage]) -> int:
    """估算消息列表的总 token 数。"""
    return sum(estimate_message_tokens(m) for m in messages)
