"""ContextInjector：管理 is_meta 上下文和 tail reminder 的生命周期。

**两类 context**：
- **静态 context**（AGENT.md、MEMORY.md）：合并为一条 ModelRequest prepend 到 [0]，
  利于 prompt cache；`metadata.is_meta=True`
- **动态 tail reminder**（dynamic-context / invoked-skills 等）：作为 UserPromptPart
  追加到"最后一条真实 user message"的 parts 列表末尾，用 `<system-reminder>` 包裹

**Tail reminder 生命周期**（由 loop.py 驱动）：
  LLM 调用前：loop.py 用 `build_*_part()` 构建 part 并 append 到 node.request.parts
  LLM 调用后：loop.py 调 `strip_tail_reminders()` 从整个 message_history 剥离所有 tail reminder
  持久化时：`from_model_messages()` 同样用 `is_tail_reminder_part()` 跳过残留

**关键不变式**：
- 任何 UserPromptPart 内容是完整 `<system-reminder>\\n...\\n</system-reminder>` 包裹 =
  临时 meta tail injection
- 独立的 meta ModelRequest（`metadata.is_meta=True`，如 skill_listing / system_prompt）
  走 `_remove_by_source` 管，不在 strip_tail_reminders 范围内

参考 Claude Code 的注入机制 + prompt caching 优化。
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

# 合并后的 metadata 标记
_MERGED_META_SOURCE = "merged_context"

# 动态 context 的 source 标识（request_context、session_state）
_DYNAMIC_SOURCES: frozenset[str] = frozenset({"request_context", "session_state"})

# 测试/调试用：tail reminder 的 markdown section 标题
DYNAMIC_CONTEXT_TAG = "## dynamic-context"
INVOKED_SKILLS_TAG = "## invoked-skills"


# ── system-reminder 包裹 ──────────────────────────────────

def wrap_system_reminder(content: str) -> str:
    """包裹 <system-reminder> 标签。在发送给 LLM 前的最后一步调用。"""
    return f"<system-reminder>\n{content}\n</system-reminder>"


# ── tail reminder 识别与清理 ──────────────────────────────

def is_tail_reminder_part(part: Any) -> bool:
    """判断 part 是否是 tail reminder（追加到真实 user message 的临时 meta part）。

    识别规则：UserPromptPart 且内容完整包裹在 `<system-reminder>\\n...\\n</system-reminder>`
    里。所有 `build_*_part()` 产出的 part 都满足；真实用户输入不会匹配。
    """
    if not isinstance(part, UserPromptPart):
        return False
    content: Any = part.content
    if not isinstance(content, str):
        return False
    return (
        content.startswith("<system-reminder>\n")
        and content.rstrip().endswith("</system-reminder>")
    )


def strip_tail_reminders(messages: list[ModelMessage]) -> None:
    """从所有真实 user message 的 parts 列表里剥离 tail reminder parts。

    - 独立 meta ModelRequest（`metadata.is_meta=True`，如 skill_listing / system_prompt
      / merged_context）**整条跳过**，不动；这类靠 `_remove_by_source` 管理
    - 普通 user message 的 parts 按 `is_tail_reminder_part` 过滤

    典型调用点：
    - loop.py 每次 LLM call 后（对称：append → LLM → strip）
    - 持久化相关路径也可作为防御性兜底
    """
    for msg in messages:
        if not isinstance(msg, ModelRequest):
            continue
        if isinstance(msg.metadata, dict) and msg.metadata.get("is_meta"):
            continue
        msg.parts[:] = [p for p in msg.parts if not is_tail_reminder_part(p)]


# ── tail reminder 构造 ────────────────────────────────────

def build_dynamic_context_part(dynamic_text: str) -> UserPromptPart:
    """构建 dynamic-context 的 UserPromptPart（追加到最后一条 user message）。

    包含每轮可能变的上下文：orchestrator instruction、session_state 摘要等。
    """
    content: str = wrap_system_reminder(f"{DYNAMIC_CONTEXT_TAG}\n\n{dynamic_text}")
    return UserPromptPart(content=content)


def build_invoked_skills_part(skills_text: str) -> UserPromptPart:
    """构建 invoked-skills 的 UserPromptPart（追加到最后一条 user message）。

    仅在 compact 触发的那一轮注入一次 —— 正常情况下 skill tool result 里已带
    SKILL.md 全文，靠对话历史自然可见；compact 把 tool result 压掉后要兜底。
    """
    content: str = wrap_system_reminder(f"{INVOKED_SKILLS_TAG}\n\n{skills_text}")
    return UserPromptPart(content=content)


# ── context_messages（meta 占位）操作 ────────────────────

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


def inject_context(
    messages: list[ModelMessage],
    context_messages: list[ModelRequest],
) -> None:
    """将静态上下文注入到消息列表中（prompt cache 友好）。

    - 静态 context（AGENT.md、MEMORY.md）→ 合并为一条 prepend 到 [0]
    - 动态 context（dynamic-context / invoked-skills）不在此处注入；由 loop 在发给
      LLM 前用 `build_*_part()` append 到 node.request.parts，LLM 返回后再
      `strip_tail_reminders()` 清理

    直接修改 messages 列表（in-place）。
    """
    # 移除旧的 merged context（要用最新 static_msgs 重建）
    messages[:] = [
        msg for msg in messages
        if not (
            isinstance(msg, ModelRequest)
            and isinstance(msg.metadata, dict)
            and msg.metadata.get("source") in (_MERGED_META_SOURCE, "dynamic_context_fallback")
        )
    ]

    static_msgs, _ = _split_context(context_messages)

    # 静态 context → prepend [0]（prompt cache 友好）
    merged: ModelRequest | None = merge_context_messages(static_msgs)
    if merged is not None:
        messages.insert(0, merged)
