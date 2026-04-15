"""AgentMessage：扁平的消息类型，替代 Pydantic AI 的 ModelRequest/ModelResponse。

两种消息类型：
- UserMessage：用户消息（含工具结果返回）
- AssistantMessage：助手回复（含工具调用）

所有持久化和日志使用 AgentMessage。Pydantic AI 的 ModelMessage 只在 agent loop
内部使用（模型调用边界），通过 to_model_messages / from_model_messages 转换。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 数据类型
# --------------------------------------------------------------------------- #


class ToolCall(BaseModel):
    """Assistant 发起的工具调用。"""

    tool_name: str
    tool_call_id: str
    args: str  # JSON string


class ToolResult(BaseModel):
    """工具执行结果。"""

    tool_name: str
    tool_call_id: str
    content: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserMessage(BaseModel):
    """用户消息（含工具结果返回）。

    content: 用户文本（可为空，如纯 tool_results 返回时）
    tool_results: 工具执行结果列表
    metadata: 元信息（is_meta, source, is_compact_boundary, is_compact_summary 等）
    timestamp: ISO 格式时间戳
    """

    role: Literal["user"] = "user"
    content: str = ""
    tool_results: list[ToolResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=_now_iso)


class AssistantMessage(BaseModel):
    """助手回复（含工具调用）。"""

    role: Literal["assistant"] = "assistant"
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=_now_iso)


AgentMessage = UserMessage | AssistantMessage

AgentMessageListAdapter: TypeAdapter[list[AgentMessage]] = TypeAdapter(
    list[AgentMessage],
)


# --------------------------------------------------------------------------- #
# 转换函数
# --------------------------------------------------------------------------- #


def from_model_messages(messages: list[ModelMessage]) -> list[AgentMessage]:
    """ModelMessage 列表 → AgentMessage 列表。

    - SystemPromptPart 被跳过（由 Pydantic AI 自动注入，不属于对话内容）
    - 如果一个 ModelRequest 只包含 SystemPromptPart，则整个消息被跳过
    - tail reminder（<system-reminder> 包裹的 meta part）被跳过，不进审计日志；
      正常流程下 loop.py 已经在 LLM call 后 strip，这里是防御性兜底
    """
    from agent_sdk._agent.message.context_injector import is_tail_reminder_part

    result: list[AgentMessage] = []

    for msg in messages:
        if isinstance(msg, ModelRequest):
            content_parts: list[str] = []
            tool_results: list[ToolResult] = []

            for part in msg.parts:
                if isinstance(part, SystemPromptPart):
                    continue
                elif isinstance(part, UserPromptPart):
                    # 防御性兜底：loop.py 应该已经在 LLM call 后 strip 过，这里只是保险
                    if is_tail_reminder_part(part):
                        continue
                    text = part.content if isinstance(part.content, str) else str(part.content)
                    if text:
                        content_parts.append(text)
                elif isinstance(part, ToolReturnPart):
                    content = part.content if isinstance(part.content, str) else str(part.content)
                    tool_results.append(ToolResult(
                        tool_name=part.tool_name,
                        tool_call_id=part.tool_call_id or "",
                        content=content,
                    ))
                elif isinstance(part, RetryPromptPart):
                    retry_content = part.content if isinstance(part.content, str) else str(part.content)
                    content_parts.append(f"[retry] {retry_content}")

            # 跳过 SystemPromptPart-only 的消息
            if not content_parts and not tool_results:
                continue

            result.append(UserMessage(
                content="\n".join(content_parts),
                tool_results=tool_results,
                metadata=dict(msg.metadata) if msg.metadata else {},
            ))

        elif isinstance(msg, ModelResponse):
            content = ""
            tool_calls: list[ToolCall] = []

            for part in msg.parts:
                if isinstance(part, TextPart):
                    content += part.content
                elif isinstance(part, ToolCallPart):
                    args = part.args if isinstance(part.args, str) else json.dumps(part.args, ensure_ascii=False)
                    tool_calls.append(ToolCall(
                        tool_name=part.tool_name,
                        tool_call_id=part.tool_call_id or "",
                        args=args,
                    ))

            result.append(AssistantMessage(
                content=content,
                tool_calls=tool_calls,
                metadata=dict(msg.metadata) if msg.metadata else {},
            ))

    return result


def to_model_messages(messages: list[AgentMessage]) -> list[ModelMessage]:
    """AgentMessage 列表 → ModelMessage 列表（纯转换，不做校验）。"""
    result: list[ModelMessage] = []

    for msg in messages:
        if isinstance(msg, UserMessage):
            parts: list[UserPromptPart | ToolReturnPart | RetryPromptPart] = []
            if msg.content:
                parts.append(UserPromptPart(content=msg.content))
            for tr in msg.tool_results:
                parts.append(ToolReturnPart(
                    tool_name=tr.tool_name,
                    content=tr.content,
                    tool_call_id=tr.tool_call_id,
                ))
            if parts:
                result.append(ModelRequest(
                    parts=parts,  # type: ignore[arg-type]
                    metadata=msg.metadata if msg.metadata else None,
                ))

        elif isinstance(msg, AssistantMessage):
            parts_resp: list[TextPart | ToolCallPart] = []
            if msg.content:
                parts_resp.append(TextPart(content=msg.content))
            for tc in msg.tool_calls:
                parts_resp.append(ToolCallPart(
                    tool_name=tc.tool_name,
                    tool_call_id=tc.tool_call_id,
                    args=tc.args,
                ))
            if parts_resp:
                result.append(ModelResponse(
                    parts=parts_resp,  # type: ignore[arg-type]
                    metadata=msg.metadata if msg.metadata else None,
                ))

    return result


# --------------------------------------------------------------------------- #
# 过滤
# --------------------------------------------------------------------------- #


def should_persist(msg: AgentMessage) -> bool:
    """判断 AgentMessage 是否需要写入持久化存储。

    规则：
    - AssistantMessage → 永远存
    - UserMessage 非 is_meta → 永远存
    - is_meta=True → 只存 is_compact_summary=True
    """
    if isinstance(msg, AssistantMessage):
        return True
    # UserMessage
    if not msg.metadata.get("is_meta"):
        return True
    return bool(msg.metadata.get("is_compact_summary", False))


# --------------------------------------------------------------------------- #
# 消息交替校验（模型调用前）
# --------------------------------------------------------------------------- #


def validate_message_alternation(
    messages: list[ModelMessage],
    user_prompt: str | None = None,
) -> list[str]:
    """校验最终发送给模型的 ModelMessage 列表是否符合 LLM API 要求。

    应在所有处理（context injection、compact 等）完成后、模型调用前调用。

    校验两条规则：

    1. **角色交替**：user/assistant 严格交替，最后一条是 user
       - 连续的 ModelRequest 视为一个 user turn（Pydantic AI 会合并）
       - 连续的 ModelResponse 视为一个 assistant turn

    2. **tool_call ↔ tool_result 配对**：
       - 每个 ToolCallPart(tool_call_id=X) 必须有对应的 ToolReturnPart(tool_call_id=X)
       - 不允许悬挂的 tool_call（有调用没结果）
       - 不允许孤儿 tool_result（有结果没调用）
    """
    if not messages and not user_prompt:
        return ["消息列表为空"]

    errors: list[str] = []

    # ── 规则 1：角色交替 ──

    # 提取 role 序列（合并连续相同 role）
    roles: list[str] = []
    for msg in messages:
        role = "user" if isinstance(msg, ModelRequest) else "assistant"
        if not roles or roles[-1] != role:
            roles.append(role)

    # user_prompt 相当于最后追加一个 user turn
    if user_prompt:
        if not roles or roles[-1] != "user":
            roles.append("user")

    # 校验交替
    for i in range(1, len(roles)):
        if roles[i] == roles[i - 1]:
            errors.append(
                f"消息交替违规: 位置 {i-1} 和 {i} 都是 {roles[i]}"
            )

    # 校验最后一条是 user
    if roles and roles[-1] != "user":
        errors.append(f"最后一条消息应为 user，实际为 {roles[-1]}")

    # ── 规则 2：tool_call ↔ tool_result 配对 ──

    # 收集所有 tool_call_id（来自 ModelResponse 的 ToolCallPart）
    call_ids: set[str] = set()
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart) and part.tool_call_id:
                    call_ids.add(part.tool_call_id)

    # 收集所有 tool_result 的 tool_call_id（来自 ModelRequest 的 ToolReturnPart）
    result_ids: set[str] = set()
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart) and part.tool_call_id:
                    result_ids.add(part.tool_call_id)

    # 悬挂的 tool_call：有调用没结果
    dangling_calls = call_ids - result_ids
    if dangling_calls:
        errors.append(f"tool_call 缺少对应 tool_result: {dangling_calls}")

    # 孤儿 tool_result：有结果没调用
    orphan_results = result_ids - call_ids
    if orphan_results:
        errors.append(f"tool_result 缺少对应 tool_call: {orphan_results}")

    return errors


# --------------------------------------------------------------------------- #
# 序列化
# --------------------------------------------------------------------------- #


def serialize_single_agent_message(msg: AgentMessage) -> str:
    """将单条 AgentMessage 序列化为 JSON 字符串。"""
    return msg.model_dump_json()


def serialize_agent_messages(messages: list[AgentMessage]) -> str:
    """将 AgentMessage 列表序列化为 JSONL 字符串。每行一个 JSON 对象。"""
    lines: list[str] = []
    for msg in messages:
        json_str = msg.model_dump_json()
        lines.append(json_str)
    return "\n".join(lines) + "\n" if lines else ""


def deserialize_agent_messages(raw: str) -> list[AgentMessage]:
    """从 JSONL 字符串解析 AgentMessage 列表。每行一个 JSON 对象。"""
    messages: list[AgentMessage] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = AgentMessageListAdapter.validate_json(f"[{line}]")
            messages.extend(parsed)
        except Exception:
            logger.warning("跳过损坏的 JSONL 行（行长度 %d）", len(line))

    return messages
