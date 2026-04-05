"""ContextInjector：将 is_meta 上下文消息注入到消息列表中。

分为两类：
- **静态 context**（AGENT.md、MEMORY.md）：合并为一条消息 prepend 到 [0]，利于 prompt cache
- **动态 context**（request_context、session_state）：追加到最后一条 user message 末尾，
  用 DYNAMIC_CONTEXT 标记包裹，持久化时剥离

参考 Claude Code 的注入机制 + prompt caching 优化。
"""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

# 合并后的 metadata 标记
_MERGED_META_SOURCE = "merged_context"

# 动态 context 的 source 标识（request_context、session_state）
_DYNAMIC_SOURCES: frozenset[str] = frozenset({"request_context", "session_state"})

# 动态 context 在 user message 中的包裹标记
DYNAMIC_CONTEXT_START = "\n<dynamic-context>"
DYNAMIC_CONTEXT_END = "</dynamic-context>"


def wrap_system_reminder(content: str) -> str:
    """包裹 <system-reminder> 标签。在发送给 LLM 前的最后一步调用。"""
    return f"<system-reminder>\n{content}\n</system-reminder>"


def _is_dynamic(msg: ModelRequest) -> bool:
    """判断 context_message 是否是动态内容。"""
    if not isinstance(msg.metadata, dict):
        return False
    return msg.metadata.get("source", "") in _DYNAMIC_SOURCES


def _split_context(
    context_messages: list[ModelRequest],
) -> tuple[list[ModelRequest], list[ModelRequest]]:
    """将 context_messages 拆分为静态和动态两组。"""
    static: list[ModelRequest] = []
    dynamic: list[ModelRequest] = []
    for msg in context_messages:
        if _is_dynamic(msg):
            dynamic.append(msg)
        else:
            static.append(msg)
    return static, dynamic


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


def _extract_dynamic_text(dynamic_messages: list[ModelRequest]) -> str:
    """从动态 context messages 中提取纯文本。"""
    parts: list[str] = []
    for msg in dynamic_messages:
        for part in msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                parts.append(part.content)
    return "\n\n".join(parts) if parts else ""


def inject_context(
    messages: list[ModelMessage],
    context_messages: list[ModelRequest],
) -> None:
    """将上下文消息注入到消息列表中（prompt cache 友好）。

    - 静态 context（AGENT.md、MEMORY.md）→ 合并为一条 prepend 到 [0]
    - 动态 context（request_context、session_state）→ 追加到最后一条 user message 末尾

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

    static_msgs, dynamic_msgs = _split_context(context_messages)

    # 静态 context → prepend [0]（prompt cache 友好）
    merged: ModelRequest | None = merge_context_messages(static_msgs)
    if merged is not None:
        messages.insert(0, merged)

    # 动态 context → 追加到最后一条 user message
    dynamic_text: str = _extract_dynamic_text(dynamic_msgs)
    if dynamic_text:
        _append_dynamic_to_last_user_message(messages, dynamic_text)


def _append_dynamic_to_last_user_message(
    messages: list[ModelMessage],
    dynamic_text: str,
) -> None:
    """将动态 context 追加到最后一条 user message 的 content 末尾。

    用 DYNAMIC_CONTEXT 标记包裹，持久化时可识别并剥离。
    """
    wrapped: str = f"{DYNAMIC_CONTEXT_START}\n{dynamic_text}\n{DYNAMIC_CONTEXT_END}"

    # 从后往前找最后一条包含 UserPromptPart 的 ModelRequest
    for i in range(len(messages) - 1, -1, -1):
        msg: ModelMessage = messages[i]
        if not isinstance(msg, ModelRequest):
            continue
        # 跳过 is_meta 消息
        if isinstance(msg.metadata, dict) and msg.metadata.get("is_meta"):
            continue
        for part in msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                # 先剥离旧的 dynamic context，再追加新的（防止多轮重复追加）
                part.content = strip_dynamic_context(part.content) + wrapped
                return

    # 没找到 user message（不应该发生），退化为独立消息 prepend
    fallback: ModelRequest = ModelRequest(
        parts=[UserPromptPart(content=wrap_system_reminder(dynamic_text))],
        metadata={"is_meta": True, "source": "dynamic_context_fallback"},
    )
    messages.append(fallback)


def strip_dynamic_context(text: str) -> str:
    """从文本中剥离 <dynamic-context> 标记及其内容。

    用于持久化前清理，确保动态 context 不进审计日志。
    """
    start_idx: int = text.find(DYNAMIC_CONTEXT_START)
    if start_idx == -1:
        return text
    end_idx: int = text.find(DYNAMIC_CONTEXT_END, start_idx)
    if end_idx == -1:
        return text[:start_idx]
    return text[:start_idx] + text[end_idx + len(DYNAMIC_CONTEXT_END):]
