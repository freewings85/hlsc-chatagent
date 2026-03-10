"""AgentMessage 类型转换 + 序列化单元测试"""

from __future__ import annotations

import json

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from src.agent.agent_message import (
    AgentMessage,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
    deserialize_agent_messages,
    from_model_messages,
    serialize_agent_messages,
    should_persist,
    to_model_messages,
)


# --------------------------------------------------------------------------- #
# from_model_messages
# --------------------------------------------------------------------------- #


class TestFromModelMessages:
    def test_user_prompt(self) -> None:
        msgs = [ModelRequest(parts=[UserPromptPart(content="你好")])]
        result = from_model_messages(msgs)
        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert result[0].content == "你好"
        assert result[0].tool_results == []

    def test_assistant_text(self) -> None:
        msgs = [ModelResponse(parts=[TextPart(content="你好，有什么可以帮你的？")])]
        result = from_model_messages(msgs)
        assert len(result) == 1
        assert isinstance(result[0], AssistantMessage)
        assert result[0].content == "你好，有什么可以帮你的？"
        assert result[0].tool_calls == []

    def test_assistant_tool_call(self) -> None:
        msgs = [ModelResponse(parts=[
            TextPart(content="我来读取文件"),
            ToolCallPart(
                tool_name="read",
                args='{"file_path": "/foo.py"}',
                tool_call_id="tc1",
            ),
        ])]
        result = from_model_messages(msgs)
        assert len(result) == 1
        am = result[0]
        assert isinstance(am, AssistantMessage)
        assert am.content == "我来读取文件"
        assert len(am.tool_calls) == 1
        assert am.tool_calls[0].tool_name == "read"
        assert am.tool_calls[0].tool_call_id == "tc1"
        assert '"file_path"' in am.tool_calls[0].args

    def test_tool_return(self) -> None:
        msgs = [ModelRequest(parts=[
            ToolReturnPart(tool_name="read", content="file content", tool_call_id="tc1"),
        ])]
        result = from_model_messages(msgs)
        assert len(result) == 1
        um = result[0]
        assert isinstance(um, UserMessage)
        assert um.content == ""
        assert len(um.tool_results) == 1
        assert um.tool_results[0].tool_name == "read"
        assert um.tool_results[0].content == "file content"

    def test_mixed_user_parts(self) -> None:
        """UserPromptPart + ToolReturnPart 在同一个 ModelRequest"""
        msgs = [ModelRequest(parts=[
            UserPromptPart(content="请继续"),
            ToolReturnPart(tool_name="bash", content="ok", tool_call_id="tc2"),
        ])]
        result = from_model_messages(msgs)
        assert len(result) == 1
        um = result[0]
        assert isinstance(um, UserMessage)
        assert um.content == "请继续"
        assert len(um.tool_results) == 1

    def test_skip_system_prompt_only(self) -> None:
        """只有 SystemPromptPart 的消息应被跳过"""
        msgs = [ModelRequest(parts=[SystemPromptPart(content="you are helpful")])]
        result = from_model_messages(msgs)
        assert len(result) == 0

    def test_skip_system_prompt_keep_user(self) -> None:
        """SystemPromptPart + UserPromptPart 混合时，跳过 system 保留 user"""
        msgs = [ModelRequest(parts=[
            SystemPromptPart(content="system"),
            UserPromptPart(content="hello"),
        ])]
        result = from_model_messages(msgs)
        assert len(result) == 1
        assert result[0].content == "hello"

    def test_retry_prompt(self) -> None:
        msgs = [ModelRequest(parts=[RetryPromptPart(content="请重试")])]
        result = from_model_messages(msgs)
        assert len(result) == 1
        assert "[retry]" in result[0].content

    def test_metadata_preserved(self) -> None:
        msgs = [ModelRequest(
            parts=[UserPromptPart(content="ctx")],
            metadata={"is_meta": True, "source": "agent_md"},
        )]
        result = from_model_messages(msgs)
        assert len(result) == 1
        um = result[0]
        assert isinstance(um, UserMessage)
        assert um.metadata["is_meta"] is True
        assert um.metadata["source"] == "agent_md"

    def test_full_session(self) -> None:
        """完整对话：user → assistant(tool_call) → user(tool_result) → assistant"""
        msgs = [
            ModelRequest(parts=[UserPromptPart(content="读取 /foo.py")]),
            ModelResponse(parts=[
                TextPart(content="好的"),
                ToolCallPart(tool_name="read", args='{"path": "/foo.py"}', tool_call_id="tc1"),
            ]),
            ModelRequest(parts=[
                ToolReturnPart(tool_name="read", content="print('hi')", tool_call_id="tc1"),
            ]),
            ModelResponse(parts=[TextPart(content="文件内容是 print('hi')")]),
        ]
        result = from_model_messages(msgs)
        assert len(result) == 4
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[1], AssistantMessage)
        assert isinstance(result[2], UserMessage)
        assert isinstance(result[3], AssistantMessage)

    def test_tool_call_args_dict(self) -> None:
        """ToolCallPart.args 是 dict 时，转为 JSON string"""
        msgs = [ModelResponse(parts=[
            ToolCallPart(tool_name="bash", args={"command": "ls"}, tool_call_id="tc1"),
        ])]
        result = from_model_messages(msgs)
        tc = result[0]
        assert isinstance(tc, AssistantMessage)
        assert '"command"' in tc.tool_calls[0].args


# --------------------------------------------------------------------------- #
# to_model_messages
# --------------------------------------------------------------------------- #


class TestToModelMessages:
    def test_user_message(self) -> None:
        msgs: list[AgentMessage] = [UserMessage(content="你好")]
        result = to_model_messages(msgs)
        assert len(result) == 1
        req = result[0]
        assert isinstance(req, ModelRequest)
        assert len(req.parts) == 1
        assert isinstance(req.parts[0], UserPromptPart)
        assert req.parts[0].content == "你好"

    def test_user_with_tool_results(self) -> None:
        msgs: list[AgentMessage] = [UserMessage(
            tool_results=[
                ToolResult(tool_name="read", tool_call_id="tc1", content="file data"),
            ],
        )]
        result = to_model_messages(msgs)
        assert len(result) == 1
        req = result[0]
        assert isinstance(req, ModelRequest)
        assert isinstance(req.parts[0], ToolReturnPart)
        assert req.parts[0].tool_name == "read"
        assert req.parts[0].content == "file data"

    def test_assistant_message(self) -> None:
        msgs: list[AgentMessage] = [AssistantMessage(content="ok")]
        result = to_model_messages(msgs)
        assert len(result) == 1
        resp = result[0]
        assert isinstance(resp, ModelResponse)
        assert isinstance(resp.parts[0], TextPart)
        assert resp.parts[0].content == "ok"

    def test_assistant_with_tool_calls(self) -> None:
        msgs: list[AgentMessage] = [AssistantMessage(
            content="我来看",
            tool_calls=[ToolCall(tool_name="read", tool_call_id="tc1", args='{"path": "/a"}')],
        )]
        result = to_model_messages(msgs)
        resp = result[0]
        assert isinstance(resp, ModelResponse)
        assert len(resp.parts) == 2
        assert isinstance(resp.parts[0], TextPart)
        assert isinstance(resp.parts[1], ToolCallPart)

    def test_metadata_preserved(self) -> None:
        msgs: list[AgentMessage] = [UserMessage(
            content="ctx",
            metadata={"is_meta": True, "source": "merged_context"},
        )]
        result = to_model_messages(msgs)
        req = result[0]
        assert isinstance(req, ModelRequest)
        assert req.metadata == {"is_meta": True, "source": "merged_context"}

    def test_empty_messages_skipped(self) -> None:
        """空 UserMessage（无 content 无 tool_results）不产出 ModelMessage"""
        msgs: list[AgentMessage] = [UserMessage()]
        result = to_model_messages(msgs)
        assert len(result) == 0

    def test_empty_assistant_skipped(self) -> None:
        """空 AssistantMessage（无 content 无 tool_calls）不产出 ModelMessage"""
        msgs: list[AgentMessage] = [AssistantMessage()]
        result = to_model_messages(msgs)
        assert len(result) == 0


# --------------------------------------------------------------------------- #
# 往返转换
# --------------------------------------------------------------------------- #


class TestRoundTrip:
    def test_roundtrip_simple(self) -> None:
        """AgentMessage → ModelMessage → AgentMessage 往返一致"""
        original: list[AgentMessage] = [
            UserMessage(content="你好"),
            AssistantMessage(content="你好！"),
        ]
        model_msgs = to_model_messages(original)
        recovered = from_model_messages(model_msgs)
        assert len(recovered) == 2
        assert recovered[0].content == "你好"
        assert recovered[1].content == "你好！"

    def test_roundtrip_tool_session(self) -> None:
        original: list[AgentMessage] = [
            UserMessage(content="读文件"),
            AssistantMessage(
                content="好的",
                tool_calls=[ToolCall(tool_name="read", tool_call_id="tc1", args='{"path": "/x"}')],
            ),
            UserMessage(
                tool_results=[ToolResult(tool_name="read", tool_call_id="tc1", content="data")],
            ),
            AssistantMessage(content="文件内容是 data"),
        ]
        model_msgs = to_model_messages(original)
        recovered = from_model_messages(model_msgs)
        assert len(recovered) == 4
        assert isinstance(recovered[0], UserMessage)
        assert isinstance(recovered[1], AssistantMessage)
        assert recovered[1].tool_calls[0].tool_name == "read"
        assert isinstance(recovered[2], UserMessage)
        assert recovered[2].tool_results[0].content == "data"

    def test_roundtrip_metadata(self) -> None:
        original: list[AgentMessage] = [
            UserMessage(
                content="context info",
                metadata={"is_meta": True, "source": "agent_md"},
            ),
        ]
        model_msgs = to_model_messages(original)
        recovered = from_model_messages(model_msgs)
        assert recovered[0].metadata["is_meta"] is True
        assert recovered[0].metadata["source"] == "agent_md"


# --------------------------------------------------------------------------- #
# should_persist
# --------------------------------------------------------------------------- #


class TestShouldPersist:
    def test_assistant_always_persists(self) -> None:
        assert should_persist(AssistantMessage(content="hi")) is True

    def test_user_non_meta_persists(self) -> None:
        assert should_persist(UserMessage(content="hello")) is True

    def test_user_meta_not_persist(self) -> None:
        msg = UserMessage(content="ctx", metadata={"is_meta": True})
        assert should_persist(msg) is False

    def test_user_meta_compact_summary_persists(self) -> None:
        msg = UserMessage(
            content="summary",
            metadata={"is_meta": True, "is_compact_summary": True},
        )
        assert should_persist(msg) is True

    def test_compact_boundary_persists(self) -> None:
        msg = UserMessage(
            content="[对话已压缩]",
            metadata={"is_compact_boundary": True},
        )
        assert should_persist(msg) is True


# --------------------------------------------------------------------------- #
# 序列化 / 反序列化
# --------------------------------------------------------------------------- #


class TestSerialization:
    def test_serialize_roundtrip(self) -> None:
        messages: list[AgentMessage] = [
            UserMessage(content="你好"),
            AssistantMessage(content="你好！"),
        ]
        raw = serialize_agent_messages(messages)
        recovered = deserialize_agent_messages(raw)
        assert len(recovered) == 2
        assert recovered[0].content == "你好"
        assert recovered[1].content == "你好！"

    def test_serialize_with_tools(self) -> None:
        messages: list[AgentMessage] = [
            AssistantMessage(
                content="ok",
                tool_calls=[ToolCall(tool_name="bash", tool_call_id="tc1", args='{"cmd": "ls"}')],
            ),
            UserMessage(
                tool_results=[ToolResult(tool_name="bash", tool_call_id="tc1", content="file.py")],
            ),
        ]
        raw = serialize_agent_messages(messages)
        recovered = deserialize_agent_messages(raw)
        assert len(recovered) == 2
        assert isinstance(recovered[0], AssistantMessage)
        assert recovered[0].tool_calls[0].tool_name == "bash"
        assert isinstance(recovered[1], UserMessage)
        assert recovered[1].tool_results[0].content == "file.py"

    def test_serialize_with_metadata(self) -> None:
        messages: list[AgentMessage] = [
            UserMessage(
                content="ctx",
                metadata={"is_meta": True, "source": "test"},
            ),
        ]
        raw = serialize_agent_messages(messages)
        recovered = deserialize_agent_messages(raw)
        assert recovered[0].metadata["is_meta"] is True

    def test_serialize_empty(self) -> None:
        assert serialize_agent_messages([]) == ""

    def test_deserialize_empty(self) -> None:
        assert deserialize_agent_messages("") == []
        assert deserialize_agent_messages("   \n  \n") == []

    def test_deserialize_malformed_line_skipped(self) -> None:
        raw = '{"role": "user", "content": "ok"}\n{broken json\n{"role": "assistant", "content": "hi"}\n'
        result = deserialize_agent_messages(raw)
        assert len(result) == 2

    def test_jsonl_format(self) -> None:
        """每行一个 JSON 对象"""
        messages: list[AgentMessage] = [
            UserMessage(content="a"),
            AssistantMessage(content="b"),
        ]
        raw = serialize_agent_messages(messages)
        lines = [l for l in raw.strip().split("\n") if l.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "role" in parsed


