"""ContextInjector：将 is_meta 上下文消息注入到消息列表中。

分为两类：
- **静态 context**（AGENT.md、MEMORY.md）：合并为一条消息 prepend 到 [0]，利于 prompt cache
- **动态 context**（request_context、session_state）：由 loop 在发给 LLM 前注入到最后一条消息末尾，
  用 <system-reminder><dynamic-context> 标记包裹，持久化时剥离

参考 Claude Code 的注入机制 + prompt caching 优化。
"""

from __future__ import annotations

import re

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

# 合并后的 metadata 标记
_MERGED_META_SOURCE = "merged_context"

# 动态 context 的 source 标识（request_context、session_state）
_DYNAMIC_SOURCES: frozenset[str] = frozenset({"request_context", "session_state"})

# 动态 context 检测用的标记（用于测试断言）
DYNAMIC_CONTEXT_TAG = "## dynamic-context"

# strip 用的正则：匹配新格式（## dynamic-context）和旧格式（<dynamic-context>）
_STRIP_DYNAMIC_RE: re.Pattern[str] = re.compile(
    r"\n?<system-reminder>\n## dynamic-context\n.*?\n</system-reminder>"  # 新格式
    r"|"
    r"\n?(?:<system-reminder>\n?)?<dynamic-context>.*?</dynamic-context>\n?(?:</system-reminder>)?",  # 旧格式
    re.DOTALL,
)


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


def extract_dynamic_text(context_messages: list[ModelRequest]) -> str:
    """从 context_messages 中提取动态 context 的纯文本。"""
    _, dynamic_msgs = _split_context(context_messages)
    parts: list[str] = []
    for msg in dynamic_msgs:
        for part in msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                parts.append(part.content)
    return "\n\n".join(parts) if parts else ""


def build_dynamic_context_part(dynamic_text: str) -> UserPromptPart:
    """构建包含动态 context 的 UserPromptPart。

    格式：<system-reminder> + markdown ## dynamic-context 标题 + 内容
    作为最后一条消息的最后一个 part 追加，确保 LLM 始终能看到最新上下文。
    """
    content: str = wrap_system_reminder(
        f"## dynamic-context\n\n{dynamic_text}"
    )
    return UserPromptPart(content=content)


def inject_context(
    messages: list[ModelMessage],
    context_messages: list[ModelRequest],
) -> None:
    """将静态上下文注入到消息列表中（prompt cache 友好）。

    - 静态 context（AGENT.md、MEMORY.md）→ 合并为一条 prepend 到 [0]
    - 动态 context 不在此处注入（由 loop 在发给 LLM 前注入到 node.request）

    直接修改 messages 列表（in-place）。
    """
    # 移除旧的 merged context 和旧的 dynamic_context_fallback
    messages[:] = [
        msg for msg in messages
        if not (
            isinstance(msg, ModelRequest)
            and isinstance(msg.metadata, dict)
            and msg.metadata.get("source") in (_MERGED_META_SOURCE, "dynamic_context_fallback")
        )
    ]

    # 清理所有消息上残留的旧 dynamic-context，移除 strip 后变空的 part
    for msg in messages:
        if not isinstance(msg, ModelRequest):
            continue
        for part in msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                part.content = strip_dynamic_context(part.content)
        msg.parts[:] = [
            p for p in msg.parts
            if not (isinstance(p, UserPromptPart) and isinstance(p.content, str) and not p.content)
        ]

    static_msgs, _ = _split_context(context_messages)

    # 静态 context → prepend [0]（prompt cache 友好）
    merged: ModelRequest | None = merge_context_messages(static_msgs)
    if merged is not None:
        messages.insert(0, merged)


def strip_dynamic_context(text: str) -> str:
    """从文本中剥离 <dynamic-context> 块及其 <system-reminder> 外层包裹。

    兼容两种格式：
    - 旧格式：\\n<dynamic-context>...内容...</dynamic-context>
    - 新格式：<system-reminder>\\n<dynamic-context>...内容...</dynamic-context>\\n</system-reminder>

    用于持久化前清理，确保动态 context 不进审计日志。
    """
    return _STRIP_DYNAMIC_RE.sub("", text)
