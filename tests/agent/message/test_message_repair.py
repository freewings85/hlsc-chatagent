"""message_repair 单元测试。"""

from __future__ import annotations

import pytest

from src.sdk._agent.agent_message import (
    AgentMessage,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
)
from src.sdk._agent.message.message_repair import (
    _CANCELLED_CONTENT,
    find_missing_tool_call_ids,
    find_tool_results_in_transcript,
    repair_messages,
)


class TestFindMissingToolCallIds:
    def test_no_messages(self) -> None:
        assert find_missing_tool_call_ids([]) == {}

    def test_no_tool_calls(self) -> None:
        msgs: list[AgentMessage] = [
            UserMessage(content="hello"),
            AssistantMessage(content="hi"),
        ]
        assert find_missing_tool_call_ids(msgs) == {}

    def test_paired_tool_call(self) -> None:
        """tool_call 和 tool_result 配对完整，无缺失。"""
        msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
            AssistantMessage(content="今天是晴天"),
        ]
        assert find_missing_tool_call_ids(msgs) == {}

    def test_single_missing(self) -> None:
        """一个 tool_call 缺少 tool_result。"""
        msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
        ]
        assert find_missing_tool_call_ids(msgs) == {"c1": "weather"}

    def test_multiple_missing(self) -> None:
        """一条 assistant 有多个 tool_calls，全部缺少 result。"""
        msgs: list[AgentMessage] = [
            UserMessage(content="查天气和新闻"),
            AssistantMessage(
                content="",
                tool_calls=[
                    ToolCall(tool_name="weather", tool_call_id="c1", args="{}"),
                    ToolCall(tool_name="news", tool_call_id="c2", args="{}"),
                ],
            ),
        ]
        missing = find_missing_tool_call_ids(msgs)
        assert missing == {"c1": "weather", "c2": "news"}

    def test_partial_missing(self) -> None:
        """多个 tool_calls，部分有 result 部分缺失。"""
        msgs: list[AgentMessage] = [
            AssistantMessage(
                content="",
                tool_calls=[
                    ToolCall(tool_name="weather", tool_call_id="c1", args="{}"),
                    ToolCall(tool_name="news", tool_call_id="c2", args="{}"),
                ],
            ),
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
        ]
        assert find_missing_tool_call_ids(msgs) == {"c2": "news"}


class TestFindToolResultsInTranscript:
    def test_found_in_transcript(self) -> None:
        transcript: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
        ]
        found = find_tool_results_in_transcript(transcript, {"c1"})
        assert "c1" in found
        assert found["c1"].content == "晴天"

    def test_not_found_in_transcript(self) -> None:
        transcript: list[AgentMessage] = [
            UserMessage(content="hello"),
            AssistantMessage(content="hi"),
        ]
        found = find_tool_results_in_transcript(transcript, {"c1"})
        assert found == {}

    def test_partial_found(self) -> None:
        """transcript 里只有部分缺失的 result。"""
        transcript: list[AgentMessage] = [
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
        ]
        found = find_tool_results_in_transcript(transcript, {"c1", "c2"})
        assert "c1" in found
        assert "c2" not in found


class TestRepairMessages:
    def test_no_repair_needed(self) -> None:
        """没有缺失，返回原列表。"""
        msgs: list[AgentMessage] = [
            UserMessage(content="hello"),
            AssistantMessage(content="hi"),
        ]
        result = repair_messages(msgs, None)
        assert result is msgs

    def test_repair_from_transcript(self) -> None:
        """从 transcript 找回缺失的 tool_result。"""
        msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
        ]
        transcript: list[AgentMessage] = [
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
        ]
        result = repair_messages(msgs, transcript)
        assert result is not msgs
        assert len(result) == 3  # original 2 + 1 repair msg
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert len(repair_msg.tool_results) == 1
        assert repair_msg.tool_results[0].content == "晴天"
        assert repair_msg.metadata.get("is_repair") is True

    def test_repair_virtual(self) -> None:
        """transcript 中也没找到，补虚拟 result。"""
        msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
        ]
        result = repair_messages(msgs, None)
        assert len(result) == 3
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert repair_msg.tool_results[0].content == _CANCELLED_CONTENT
        assert repair_msg.tool_results[0].tool_name == "weather"
        assert repair_msg.metadata.get("is_repair") is True

    def test_repair_mixed(self) -> None:
        """部分从 transcript 找回，部分虚拟补齐。"""
        msgs: list[AgentMessage] = [
            AssistantMessage(
                content="",
                tool_calls=[
                    ToolCall(tool_name="weather", tool_call_id="c1", args="{}"),
                    ToolCall(tool_name="news", tool_call_id="c2", args="{}"),
                ],
            ),
        ]
        transcript: list[AgentMessage] = [
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
        ]
        result = repair_messages(msgs, transcript)
        assert len(result) == 2  # original 1 + 1 repair msg
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert len(repair_msg.tool_results) == 2

        results_by_id = {tr.tool_call_id: tr for tr in repair_msg.tool_results}
        assert results_by_id["c1"].content == "晴天"
        assert results_by_id["c2"].content == _CANCELLED_CONTENT

    def test_repair_multiple_assistant_messages(self) -> None:
        """多条 assistant 消息各有悬挂的 tool_call。"""
        msgs: list[AgentMessage] = [
            UserMessage(content="问题1"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="t1", tool_call_id="c1", args="{}")],
            ),
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="t1", tool_call_id="c1", content="r1")],
            ),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="t2", tool_call_id="c2", args="{}")],
            ),
            # c2 的 result 缺失
        ]
        result = repair_messages(msgs, None)
        assert len(result) == 5  # original 4 + 1 repair
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert repair_msg.tool_results[0].tool_call_id == "c2"
        assert repair_msg.tool_results[0].content == _CANCELLED_CONTENT
