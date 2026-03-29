"""BusinessMapAgent 导航定位测试：使用 FunctionModel mock 验证逐层查询 + ID 输出。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from agent_sdk import Agent, ToolConfig
from agent_sdk._agent.deps import AgentDeps
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel
from agent_sdk.prompt_loader import StaticPromptLoader
from hlsc.services.business_map_service import BusinessMapService

# 业务地图 YAML 目录
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent
_BUSINESS_MAP_DIR: Path = _PROJECT_ROOT / "extensions" / "business-map" / "data"


# ── 辅助函数 ──

def _load_service() -> BusinessMapService:
    """加载真实业务地图到 service。"""
    svc: BusinessMapService = BusinessMapService()
    svc.load(_BUSINESS_MAP_DIR)
    return svc


def _create_tools(service: BusinessMapService) -> dict[str, Any]:
    """创建注入了 service 的工具函数。"""
    import importlib

    gbc_mod = importlib.import_module("src.tools.get_business_children")
    gbn_mod = importlib.import_module("src.tools.get_business_node")

    gbc_mod.set_service(service)
    gbn_mod.set_service(service)

    return {
        "get_business_children": gbc_mod.get_business_children,
        "get_business_node": gbn_mod.get_business_node,
    }


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    """收集事件队列中的所有事件。"""
    events: list[EventModel] = []
    while True:
        item: EventModel | None = await queue.get()
        if item is None:
            break
        events.append(item)
    return events


# ── Mock 模型：模拟逐层查询后输出节点 ID ──

def _mock_navigate_to_project_saving(
    messages: list[ModelMessage], info: object
) -> ModelResponse:
    """模拟导航到 project_saving：
    第 1 步：调用 get_business_children("root")
    第 2 步：根据返回结果输出 project_saving
    """
    # 检查是否已有 tool-return
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                # 已经拿到子节点列表，直接输出 ID
                return ModelResponse(parts=[TextPart(content="project_saving")])
    # 首次调用：先查根节点子节点
    return ModelResponse(
        parts=[ToolCallPart(tool_name="get_business_children", args={"node_id": "root"})]
    )


async def _mock_stream_navigate_to_project_saving(
    messages: list[ModelMessage], info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """流式版本。"""
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                yield "project_saving"
                return
    yield {0: DeltaToolCall(name="get_business_children", json_args='{"node_id": "root"}')}


def _mock_navigate_deep(messages: list[ModelMessage], info: object) -> ModelResponse:
    """模拟深度导航到 symptom_based 叶节点：
    第 1 步：get_business_children("root") → 选 project_saving
    第 2 步：get_business_children("project_saving") → 选 confirm_project
    第 3 步：get_business_children("confirm_project") → 选 symptom_based
    第 4 步：输出 symptom_based
    """
    tool_return_count: int = 0
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                tool_return_count += 1

    if tool_return_count == 0:
        return ModelResponse(
            parts=[ToolCallPart(tool_name="get_business_children", args={"node_id": "root"})]
        )
    elif tool_return_count == 1:
        return ModelResponse(
            parts=[ToolCallPart(tool_name="get_business_children", args={"node_id": "project_saving"})]
        )
    elif tool_return_count == 2:
        return ModelResponse(
            parts=[ToolCallPart(tool_name="get_business_children", args={"node_id": "confirm_project"})]
        )
    else:
        return ModelResponse(parts=[TextPart(content="symptom_based")])


async def _mock_stream_navigate_deep(
    messages: list[ModelMessage], info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """流式版本。"""
    tool_return_count: int = 0
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                tool_return_count += 1

    if tool_return_count == 0:
        yield {0: DeltaToolCall(name="get_business_children", json_args='{"node_id": "root"}')}
    elif tool_return_count == 1:
        yield {0: DeltaToolCall(name="get_business_children", json_args='{"node_id": "project_saving"}')}
    elif tool_return_count == 2:
        yield {0: DeltaToolCall(name="get_business_children", json_args='{"node_id": "confirm_project"}')}
    else:
        yield "symptom_based"


def _mock_navigate_multi_path(messages: list[ModelMessage], info: object) -> ModelResponse:
    """模拟多路径定位：输出 confirm_saving, search（两个不同分支）。
    第 1 步：get_business_children("root")
    第 2 步：输出多个 ID
    """
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                return ModelResponse(parts=[TextPart(content="confirm_saving, search")])
    return ModelResponse(
        parts=[ToolCallPart(tool_name="get_business_children", args={"node_id": "root"})]
    )


async def _mock_stream_navigate_multi_path(
    messages: list[ModelMessage], info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """流式版本。"""
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                yield "confirm_saving, search"
                return
    yield {0: DeltaToolCall(name="get_business_children", json_args='{"node_id": "root"}')}


def _mock_stop_at_parent(messages: list[ModelMessage], info: object) -> ModelResponse:
    """模拟停在父节点：不确定该走哪个子节点，输出父节点 ID。
    第 1 步：get_business_children("root") → 选 project_saving
    第 2 步：get_business_children("project_saving") → 不确定，输出 project_saving
    """
    tool_return_count: int = 0
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                tool_return_count += 1

    if tool_return_count == 0:
        return ModelResponse(
            parts=[ToolCallPart(tool_name="get_business_children", args={"node_id": "root"})]
        )
    elif tool_return_count == 1:
        return ModelResponse(
            parts=[ToolCallPart(tool_name="get_business_children", args={"node_id": "project_saving"})]
        )
    else:
        # 不确定该走哪个子节点，停在父节点
        return ModelResponse(parts=[TextPart(content="project_saving")])


async def _mock_stream_stop_at_parent(
    messages: list[ModelMessage], info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """流式版本。"""
    tool_return_count: int = 0
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                tool_return_count += 1

    if tool_return_count == 0:
        yield {0: DeltaToolCall(name="get_business_children", json_args='{"node_id": "root"}')}
    elif tool_return_count == 1:
        yield {0: DeltaToolCall(name="get_business_children", json_args='{"node_id": "project_saving"}')}
    else:
        yield "project_saving"


# ── 测试类 ──

class TestBusinessMapNavigator:
    """BusinessMapAgent 导航定位测试。"""

    @pytest.fixture(autouse=True)
    def setup_service(self) -> None:
        """每个测试前加载 BusinessMapService。"""
        self.service: BusinessMapService = _load_service()
        self.tools: dict[str, Any] = _create_tools(self.service)

    def _make_agent(self, model: FunctionModel) -> Agent:
        """创建测试用 Agent。"""
        return Agent(
            prompt_loader=StaticPromptLoader("你是业务地图定位器。"),
            tools=ToolConfig(manual=self.tools),
            model=model,
            agent_name="business_map_agent",
        )

    @pytest.mark.asyncio
    async def test_shallow_navigation(self) -> None:
        """浅定位：用户消息匹配顶层分支，输出父节点 ID。"""
        model: FunctionModel = FunctionModel(
            _mock_navigate_to_project_saving,
            stream_function=_mock_stream_navigate_to_project_saving,
        )
        agent: Agent = self._make_agent(model)
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter: EventEmitter = EventEmitter(queue)

        result: str | None = await agent.run(
            "我车该保养了",
            user_id="test-user",
            session_id="test-session",
            emitter=emitter,
        )

        assert result is not None
        assert "project_saving" in result

    @pytest.mark.asyncio
    async def test_deep_navigation(self) -> None:
        """深定位：逐层查询到叶节点 symptom_based。"""
        model: FunctionModel = FunctionModel(
            _mock_navigate_deep,
            stream_function=_mock_stream_navigate_deep,
        )
        agent: Agent = self._make_agent(model)
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter: EventEmitter = EventEmitter(queue)

        result: str | None = await agent.run(
            "我轮胎有点磨损不知道要不要换",
            user_id="test-user",
            session_id="test-session",
            emitter=emitter,
        )

        assert result is not None
        assert "symptom_based" in result

    @pytest.mark.asyncio
    async def test_multi_path_navigation(self) -> None:
        """多路径定位：输出多个不同分支的节点 ID。"""
        model: FunctionModel = FunctionModel(
            _mock_navigate_multi_path,
            stream_function=_mock_stream_navigate_multi_path,
        )
        agent: Agent = self._make_agent(model)
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter: EventEmitter = EventEmitter(queue)

        result: str | None = await agent.run(
            "保养项目定了帮我找个附近的店",
            user_id="test-user",
            session_id="test-session",
            emitter=emitter,
        )

        assert result is not None
        assert "confirm_saving" in result
        assert "search" in result

    @pytest.mark.asyncio
    async def test_stop_at_parent(self) -> None:
        """停在父节点：不确定该走哪个子节点时停住。"""
        model: FunctionModel = FunctionModel(
            _mock_stop_at_parent,
            stream_function=_mock_stream_stop_at_parent,
        )
        agent: Agent = self._make_agent(model)
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter: EventEmitter = EventEmitter(queue)

        result: str | None = await agent.run(
            "我车需要做点什么",
            user_id="test-user",
            session_id="test-session",
            emitter=emitter,
        )

        assert result is not None
        assert "project_saving" in result


class TestBusinessMapTools:
    """工具函数单元测试：验证 tool 正确调用 BusinessMapService。"""

    @pytest.fixture(autouse=True)
    def setup_service(self) -> None:
        """每个测试前加载 BusinessMapService。"""
        import importlib

        self.service: BusinessMapService = _load_service()
        gbc_mod = importlib.import_module("src.tools.get_business_children")
        gbn_mod = importlib.import_module("src.tools.get_business_node")

        gbc_mod.set_service(self.service)
        gbn_mod.set_service(self.service)

    @pytest.mark.asyncio
    async def test_get_business_children_root(self) -> None:
        """get_business_children("root") 返回顶层子节点列表。"""
        from src.tools.get_business_children import get_business_children

        # 创建 mock RunContext
        deps: AgentDeps = AgentDeps(session_id="test-session", request_id="test-req")
        ctx: Any = type("MockCtx", (), {"deps": deps})()

        result: str = await get_business_children(ctx, node_id="root")

        assert "子节点" in result
        assert "project_saving" in result or "沟通项目" in result

    @pytest.mark.asyncio
    async def test_get_business_children_nonexistent(self) -> None:
        """get_business_children 对不存在的 node_id 返回错误信息。"""
        from src.tools.get_business_children import get_business_children

        deps: AgentDeps = AgentDeps(session_id="test-session", request_id="test-req")
        ctx: Any = type("MockCtx", (), {"deps": deps})()

        result: str = await get_business_children(ctx, node_id="nonexistent_node")

        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_get_business_node_valid(self) -> None:
        """get_business_node 返回有效节点的导航信息。"""
        from src.tools.get_business_node import get_business_node

        deps: AgentDeps = AgentDeps(session_id="test-session", request_id="test-req")
        ctx: Any = type("MockCtx", (), {"deps": deps})()

        result: str = await get_business_node(ctx, node_id="root")

        assert "root" in result or "养车" in result

    @pytest.mark.asyncio
    async def test_get_business_node_nonexistent(self) -> None:
        """get_business_node 对不存在的 node_id 返回错误信息。"""
        from src.tools.get_business_node import get_business_node

        deps: AgentDeps = AgentDeps(session_id="test-session", request_id="test-req")
        ctx: Any = type("MockCtx", (), {"deps": deps})()

        result: str = await get_business_node(ctx, node_id="nonexistent_node")

        assert "不存在" in result
