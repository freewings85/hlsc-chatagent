"""message_repair：加载时检测并修复 messages.jsonl 中的 tool_call/tool_result 配对问题。

修复流程：
1. 扫描 messages 中所有 tool_call_id 和 tool_result 的 tool_call_id
2. 找出悬挂的 tool_call（有 call 没 result）
3. 如果有悬挂 → 从 transcript.jsonl 中按 id 查找缺失的 tool_result
4. 找到了 → 补到 messages 末尾
5. 还是没找到 → 补虚拟 tool_result（标记 is_repair）
6. 覆写修复后的 messages.jsonl
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.sdk._agent.agent_message import (
    AgentMessage,
    AssistantMessage,
    ToolResult,
    UserMessage,
    deserialize_agent_messages,
)

if TYPE_CHECKING:
    from src.sdk._common.filesystem_backend import BackendProtocol

logger = logging.getLogger(__name__)

# 虚拟补齐的工具结果内容
_CANCELLED_CONTENT = "[工具调用已取消，结果不可用]"


def find_missing_tool_call_ids(messages: list[AgentMessage]) -> dict[str, str]:
    """找出 messages 中有 tool_call 但没有对应 tool_result 的 id。

    返回 {tool_call_id: tool_name} 字典。
    """
    # 收集所有 tool_call_id → tool_name
    call_map: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, AssistantMessage):
            for tc in msg.tool_calls:
                if tc.tool_call_id:
                    call_map[tc.tool_call_id] = tc.tool_name

    # 收集所有 tool_result 的 tool_call_id
    result_ids: set[str] = set()
    for msg in messages:
        if isinstance(msg, UserMessage):
            for tr in msg.tool_results:
                if tr.tool_call_id:
                    result_ids.add(tr.tool_call_id)

    # 返回悬挂的 tool_call
    missing = {k: v for k, v in call_map.items() if k not in result_ids}
    return missing


def find_tool_results_in_transcript(
    transcript: list[AgentMessage],
    missing_ids: set[str],
) -> dict[str, ToolResult]:
    """从 transcript 中按 tool_call_id 查找缺失的 tool_result。"""
    found: dict[str, ToolResult] = {}
    for msg in transcript:
        if isinstance(msg, UserMessage):
            for tr in msg.tool_results:
                if tr.tool_call_id in missing_ids:
                    found[tr.tool_call_id] = tr
    return found


def repair_messages(
    messages: list[AgentMessage],
    transcript: list[AgentMessage] | None,
) -> list[AgentMessage]:
    """修复 messages 中的 tool_call/tool_result 配对问题。

    返回修复后的消息列表（如果无需修复则返回原列表）。
    """
    missing = find_missing_tool_call_ids(messages)
    if not missing:
        return messages

    logger.warning("检测到 %d 个悬挂的 tool_call: %s", len(missing), list(missing.keys()))

    # 尝试从 transcript 中查找
    found_from_transcript: dict[str, ToolResult] = {}
    if transcript is not None:
        found_from_transcript = find_tool_results_in_transcript(
            transcript, set(missing.keys()),
        )
        if found_from_transcript:
            logger.info(
                "从 transcript 中找回 %d 个 tool_result: %s",
                len(found_from_transcript), list(found_from_transcript.keys()),
            )

    # 分类：从 transcript 找到的 vs 需要虚拟补齐的
    still_missing = {k: v for k, v in missing.items() if k not in found_from_transcript}

    # 构造补齐的 tool_results
    repair_results: list[ToolResult] = []

    # 从 transcript 找回的
    for tr in found_from_transcript.values():
        repair_results.append(tr)

    # 虚拟补齐的
    for tool_call_id, tool_name in still_missing.items():
        logger.warning(
            "tool_call %s (%s) 在 transcript 中也未找到，补虚拟 result",
            tool_call_id, tool_name,
        )
        repair_results.append(ToolResult(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            content=_CANCELLED_CONTENT,
        ))

    if not repair_results:
        return messages  # pragma: no cover — 防御性

    # 补齐：追加一条 UserMessage 包含所有缺失的 tool_results
    repair_msg = UserMessage(
        content="",
        tool_results=repair_results,
        metadata={"is_repair": True},
    )
    repaired = list(messages)
    repaired.append(repair_msg)

    logger.info(
        "消息修复完成：从 transcript 找回 %d 个，虚拟补齐 %d 个",
        len(found_from_transcript), len(still_missing),
    )
    return repaired


async def load_transcript(
    backend: BackendProtocol,
    user_id: str,
    session_id: str,
) -> list[AgentMessage] | None:
    """加载 transcript.jsonl。加载失败返回 None（不影响主流程）。"""
    from src.sdk._agent.message.history_message_loader import _transcript_path

    path = _transcript_path(user_id, session_id)
    try:
        if not await backend.aexists(path):
            return None
        responses = await backend.adownload_files([path])
        resp = responses[0]
        if resp.error is not None or resp.content is None:
            return None
        raw = resp.content.decode("utf-8").strip()
        if not raw:
            return None
        return deserialize_agent_messages(raw)
    except Exception:
        logger.warning("加载 transcript 失败，跳过修复", exc_info=True)
        return None
