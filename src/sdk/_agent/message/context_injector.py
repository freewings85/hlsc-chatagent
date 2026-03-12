"""ContextInjector：将 is_meta 上下文消息合并并注入到消息列表中。

参考 Claude Code 的注入机制：
- 多个来源的上下文合并为一条 user message
- 包裹 <system-reminder> 标签
- prepend 到 messages[0]
- 每次 ModelRequestNode 前重新注入（先清除旧的，再 prepend 新的）
"""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

# 合并后的 metadata 标记
_MERGED_META_SOURCE = "merged_context"


def wrap_system_reminder(content: str) -> str:
    """包裹 <system-reminder> 标签。在发送给 LLM 前的最后一步调用。"""
    return f"<system-reminder>\n{content}\n</system-reminder>"


def merge_context_messages(context_messages: list[ModelRequest]) -> ModelRequest | None:
    """将多个 is_meta 消息合并为一条，包裹 <system-reminder>。

    返回 None 表示没有上下文消息需要注入。
    """
    if not context_messages:
        return None

    parts: list[str] = []
    for msg in context_messages:
        for part in msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                parts.append(part.content)

    if not parts:
        return None

    merged_content: str = "\n\n".join(parts)
    wrapped: str = wrap_system_reminder(merged_content)

    return ModelRequest(
        parts=[UserPromptPart(content=wrapped)],
        metadata={"is_meta": True, "source": _MERGED_META_SOURCE},
    )


def inject_context(
    messages: list[ModelMessage],
    context_messages: list[ModelRequest],
) -> None:
    """将上下文消息注入到消息列表的 [0] 位置。

    - 先移除旧的 merged_context（如果有）
    - 合并新的 context_messages
    - prepend 到 messages[0]

    直接修改 messages 列表（in-place）。
    """
    # 移除旧的 merged context
    messages[:] = [
        msg for msg in messages
        if not (
            isinstance(msg, ModelRequest)
            and isinstance(msg.metadata, dict)
            and msg.metadata.get("source") == _MERGED_META_SOURCE
        )
    ]

    # 合并并注入新的
    merged: ModelRequest | None = merge_context_messages(context_messages)
    if merged is not None:
        messages.insert(0, merged)
