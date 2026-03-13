"""Task 工具测试：子 agent 通过 run_agent_loop 引擎运行"""

import asyncio

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.task import task, _resolve_subagent_tools
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType


# ── Mock 工具 ──────────────────────────────────────────────────────────────

async def mock_read(ctx: RunContext[AgentDeps], path: str) -> str:
    """Mock read 工具"""
    return f"文件内容: {path}"


async def mock_write(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
    """Mock write 工具"""
    return f"已写入: {path}"


async def mock_get_weather(ctx: RunContext[AgentDeps], city: str) -> str:
    """Mock get_weather 工具"""
    return f"{city}: 晴天 25°C"


# ── 辅助函数 ──────────────────────────────────────────────────────────────

def _make_parent_deps(
    tools: dict | None = None,
    session_id: str = "test-session",
    user_id: str = "test-user",
    emitter: EventEmitter | None = None,
) -> AgentDeps:
    """构建父 agent 的 deps（模拟 task 工具被调用时的上下文）。"""
    tool_map = tools or {
        "read": mock_read,
        "write": mock_write,
        "get_weather": mock_get_weather,
        "task": task,
        "Skill": lambda ctx: "skill",
    }
    return AgentDeps(
        session_id=session_id,
        user_id=user_id,
        available_tools=list(tool_map.keys()),
        tool_map=tool_map,
        emitter=emitter,
    )


def _make_run_context(deps: AgentDeps) -> RunContext[AgentDeps]:
    """构建 RunContext mock。"""
    # RunContext 通常由 Pydantic AI 内部创建，这里简单 mock
    from unittest.mock import MagicMock
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    """收集 queue 中的所有事件（非阻塞）。"""
    events: list[EventModel] = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is None:
            break
        events.append(item)
    return events


# ── 测试 ──────────────────────────────────────────────────────────────────


class TestResolveSubagentTools:
    """工具继承策略"""

    def test_general_excludes_task_and_skill(self) -> None:
        deps = _make_parent_deps()
        tools = _resolve_subagent_tools(deps, "general")
        assert "task" not in tools
        assert "Skill" not in tools
        assert "read" in tools
        assert "write" in tools
        assert "get_weather" in tools

    def test_plan_additionally_excludes_write_tools(self) -> None:
        deps = _make_parent_deps()
        tools = _resolve_subagent_tools(deps, "plan")
        assert "task" not in tools
        assert "Skill" not in tools
        assert "write" not in tools
        assert "edit" not in tools
        assert "read" in tools
        assert "get_weather" in tools


class TestTaskToolValidation:
    """Task 工具参数校验"""

    @pytest.mark.asyncio
    async def test_invalid_subagent_type(self) -> None:
        deps = _make_parent_deps()
        ctx = _make_run_context(deps)
        result = await task(ctx, "test", "do something", subagent_type="invalid")
        assert "错误" in result
        assert "invalid" in result


class TestSubAgentLoop:
    """子 agent 通过 run_agent_loop 引擎运行"""

    @pytest.mark.asyncio
    async def test_sub_agent_returns_result(self) -> None:
        """子 agent 运行完成后返回结果文本"""
        # 使用 FunctionModel mock LLM
        def simple_response(messages: list[ModelMessage], info: object) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="子 agent 分析完成")])

        async def simple_stream(messages: list[ModelMessage], info: AgentInfo):
            for chunk in ["子 agent ", "分析", "完成"]:
                yield chunk

        from unittest.mock import patch
        model = FunctionModel(simple_response, stream_function=simple_stream)

        # 创建 emitter 来捕获事件
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(emitter=emitter)
        ctx = _make_run_context(deps)

        # patch create_model 让子 agent 使用我们的 mock model
        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            result = await task(ctx, "分析任务", "分析代码结构", subagent_type="general")

        assert "子 agent 分析完成" in result

    @pytest.mark.asyncio
    async def test_sub_agent_events_have_correct_agent_name(self) -> None:
        """子 agent 的事件携带正确的 agent_name"""
        def simple_response(messages: list[ModelMessage], info: object) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="完成")])

        async def simple_stream(messages: list[ModelMessage], info: AgentInfo):
            yield "完成"

        from unittest.mock import patch
        model = FunctionModel(simple_response, stream_function=simple_stream)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(emitter=emitter)
        ctx = _make_run_context(deps)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            await task(ctx, "test", "do something", subagent_type="plan")

        events = await _collect_events(queue)
        # 子 agent 事件的 agent_name 应该是 "plan"
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) > 0
        for e in text_events:
            assert e.agent_name == "plan"

    @pytest.mark.asyncio
    async def test_sub_agent_does_not_emit_chat_request_end(self) -> None:
        """子 agent 不发送 CHAT_REQUEST_END（那是主 agent 的生命周期事件）"""
        def simple_response(messages: list[ModelMessage], info: object) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        async def simple_stream(messages: list[ModelMessage], info: AgentInfo):
            yield "ok"

        from unittest.mock import patch
        model = FunctionModel(simple_response, stream_function=simple_stream)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(emitter=emitter)
        ctx = _make_run_context(deps)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            await task(ctx, "test", "do something")

        events = await _collect_events(queue)
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 0

    @pytest.mark.asyncio
    async def test_sub_agent_does_not_close_emitter(self) -> None:
        """子 agent 不关闭父 emitter"""
        def simple_response(messages: list[ModelMessage], info: object) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        async def simple_stream(messages: list[ModelMessage], info: AgentInfo):
            yield "ok"

        from unittest.mock import patch
        model = FunctionModel(simple_response, stream_function=simple_stream)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(emitter=emitter)
        ctx = _make_run_context(deps)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            await task(ctx, "test", "do something")

        # emitter 不应该被关闭（_closed = False）
        assert not emitter._closed

    @pytest.mark.asyncio
    async def test_sub_agent_with_tool_call(self) -> None:
        """子 agent 能执行工具调用"""
        def tool_then_text(messages: list[ModelMessage], info: object) -> ModelResponse:
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        return ModelResponse(parts=[TextPart(content=f"结果：{part.content}")])
            return ModelResponse(parts=[ToolCallPart(tool_name="read", args={"path": "/tmp/test.txt"})])

        async def tool_then_text_stream(messages: list[ModelMessage], info: AgentInfo):
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        for chunk in ["结果：", part.content]:
                            yield chunk
                        return
            yield {0: DeltaToolCall(name="read", json_args='{"path": "/tmp/test.txt"}')}

        from unittest.mock import patch
        model = FunctionModel(tool_then_text, stream_function=tool_then_text_stream)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(emitter=emitter)
        ctx = _make_run_context(deps)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            result = await task(ctx, "读文件", "读取 /tmp/test.txt", subagent_type="general")

        assert "文件内容" in result

        events = await _collect_events(queue)
        event_types = [e.type for e in events]
        # 应有 tool_result 事件
        assert EventType.TOOL_RESULT in event_types

    @pytest.mark.asyncio
    async def test_sub_agent_error_returns_error_message(self) -> None:
        """子 agent 内部异常时返回错误消息（不崩溃主 agent）"""
        async def bad_stream(messages, info):
            raise RuntimeError("sub agent exploded")
            yield "never"  # type: ignore[misc]  # noqa: E501

        from unittest.mock import patch
        model = FunctionModel(stream_function=bad_stream)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(emitter=emitter)
        ctx = _make_run_context(deps)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            result = await task(ctx, "test", "do something")

        # task 工具捕获异常，返回错误消息
        assert "子 agent 执行失败" in result
        assert "sub agent exploded" in result

    @pytest.mark.asyncio
    async def test_sub_agent_session_id_matches_parent(self) -> None:
        """子 agent 的事件 session_id 与父 agent 一致（同一会话）"""
        def simple_response(messages: list[ModelMessage], info: object) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        async def simple_stream(messages: list[ModelMessage], info: AgentInfo):
            yield "ok"

        from unittest.mock import patch
        model = FunctionModel(simple_response, stream_function=simple_stream)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(session_id="parent-session-123", emitter=emitter)
        ctx = _make_run_context(deps)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            await task(ctx, "test", "do something")

        events = await _collect_events(queue)
        for e in events:
            assert e.session_id == "parent-session-123"

    @pytest.mark.asyncio
    async def test_sub_agent_without_emitter(self) -> None:
        """父 agent 没有 emitter 时子 agent 仍能正常运行（事件丢弃）"""
        def simple_response(messages: list[ModelMessage], info: object) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="完成")])

        async def simple_stream(messages: list[ModelMessage], info: AgentInfo):
            yield "完成"

        from unittest.mock import patch
        model = FunctionModel(simple_response, stream_function=simple_stream)

        deps = _make_parent_deps(emitter=None)
        ctx = _make_run_context(deps)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            result = await task(ctx, "test", "do something")

        assert "完成" in result

    @pytest.mark.asyncio
    async def test_sub_agent_transcript_path_isolated(self) -> None:
        """子 agent 的 transcript 写入 subagents/{agent_id}/ 路径，不与主 agent 混合"""
        def simple_response(messages: list[ModelMessage], info: object) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="isolated transcript")])

        async def simple_stream(messages: list[ModelMessage], info: AgentInfo):
            yield "isolated transcript"

        from unittest.mock import patch, AsyncMock

        model = FunctionModel(simple_response, stream_function=simple_stream)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(session_id="parent-sess", emitter=emitter)
        ctx = _make_run_context(deps)

        # Capture transcript_service.append calls to verify session_id
        append_calls: list[tuple[str, str]] = []
        original_append = None

        async def capture_append(user_id: str, session_id: str, messages: list) -> None:
            append_calls.append((user_id, session_id))
            if original_append is not None:
                await original_append(user_id, session_id, messages)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            with patch(
                "agent_sdk._agent.message.transcript_service.TranscriptService.append",
                side_effect=capture_append,
            ):
                await task(ctx, "test", "do something", subagent_type="plan")

        # transcript 应写入 subagents/ 子路径，不是 parent-sess
        assert len(append_calls) > 0, "应有 transcript append 调用"
        for user_id, session_id in append_calls:
            assert "subagents/" in session_id, \
                f"transcript session_id 应包含 'subagents/'，实际: {session_id}"
            assert session_id.startswith("parent-sess/subagents/plan-"), \
                f"transcript 路径格式错误: {session_id}"
