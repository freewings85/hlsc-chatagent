"""项目骨架验证：目录结构 + 核心模块可导入 + agent loop 可运行"""

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart

from src.agent.deps import AgentDeps, ToolFunc
from src.agent.loop import create_agent, run_agent_loop, AgentResult
from src.agent.model import create_model
from src.agent.toolset import get_tools
from src.config.settings import LLMConfig, StorageConfig, ServerConfig
from src.server.request import ChatRequest


# ---- Mock Model ----

def mock_weather_then_answer(
    messages: list[ModelMessage], info: object
) -> ModelResponse:
    """第1次返回 tool call，第2次返回文本"""
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                return ModelResponse(
                    parts=[TextPart(content=f"天气结果：{part.content}")]
                )
    return ModelResponse(
        parts=[ToolCallPart(tool_name="get_weather", args={"city": "上海"})]
    )


def mock_simple_text(
    messages: list[ModelMessage], info: object
) -> ModelResponse:
    """直接返回文本"""
    return ModelResponse(parts=[TextPart(content="你好，我是助手")])


# ---- Mock Tool ----

async def mock_get_weather(ctx: RunContext[AgentDeps], city: str) -> str:
    """获取天气"""
    ctx.deps.tool_call_count += 1
    result: str = f"{city}: 晴天 25°C"
    ctx.deps.last_tool_result = result
    return result


# ---- Tests ----

class TestConfig:
    """配置模块可实例化"""

    def test_llm_config(self) -> None:
        config: LLMConfig = LLMConfig()
        assert config.llm_type in ("azure", "openai", "")

    def test_storage_config(self) -> None:
        config: StorageConfig = StorageConfig()
        assert "sessions" in config.sessions_dir

    def test_server_config(self) -> None:
        config: ServerConfig = ServerConfig()
        assert config.port == 8100


class TestDeps:
    """AgentDeps 可实例化和修改"""

    def test_default(self) -> None:
        deps: AgentDeps = AgentDeps()
        assert deps.session_id == "default"
        assert deps.tool_call_count == 0

    def test_custom(self) -> None:
        deps: AgentDeps = AgentDeps(
            session_id="test-001",
            user_id="user-1",
            available_tools=["get_weather"],
        )
        assert deps.session_id == "test-001"
        assert "get_weather" in deps.available_tools


class TestRequest:
    """请求模型校验"""

    def test_chat_request(self) -> None:
        req: ChatRequest = ChatRequest(
            session_id="s1",
            message="hello",
            user_id="u1",
        )
        assert req.session_id == "s1"
        assert req.message == "hello"


class TestAgentLoop:
    """Agent Loop 核心验证"""

    @pytest.mark.asyncio
    async def test_simple_text_response(self) -> None:
        """无 tool call，直接返回文本"""
        model: FunctionModel = FunctionModel(mock_simple_text)
        agent = create_agent(model=model, system_prompt="你是助手")
        deps: AgentDeps = AgentDeps()

        result: AgentResult = await run_agent_loop(agent, "你好", deps)

        assert result.output == "你好，我是助手"
        assert "UserPromptNode" in result.nodes
        assert "End" in result.nodes
        assert result.tool_call_count == 0

    @pytest.mark.asyncio
    async def test_tool_call_flow(self) -> None:
        """tool call 流程：LLM → tool → LLM"""
        model: FunctionModel = FunctionModel(mock_weather_then_answer)
        agent = create_agent(model=model)
        deps: AgentDeps = AgentDeps(
            available_tools=["get_weather"],
            tool_map={"get_weather": mock_get_weather},
        )

        result: AgentResult = await run_agent_loop(agent, "上海天气", deps)

        assert result.tool_call_count == 1
        assert "上海" in deps.last_tool_result
        assert result.output != ""
        assert len(result.messages) > 0

    @pytest.mark.asyncio
    async def test_deps_modification_in_tool(self) -> None:
        """验证 tool 可以修改 deps 状态"""
        model: FunctionModel = FunctionModel(mock_weather_then_answer)
        agent = create_agent(model=model)
        deps: AgentDeps = AgentDeps(
            available_tools=["get_weather"],
            tool_map={"get_weather": mock_get_weather},
            tool_call_count=10,
        )

        result: AgentResult = await run_agent_loop(agent, "天气", deps)

        assert result.tool_call_count == 11

    @pytest.mark.asyncio
    async def test_message_history_returned(self) -> None:
        """验证 messages 被正确返回"""
        model: FunctionModel = FunctionModel(mock_simple_text)
        agent = create_agent(model=model)
        deps: AgentDeps = AgentDeps()

        result: AgentResult = await run_agent_loop(agent, "你好", deps)

        assert len(result.messages) >= 2  # 至少有 request + response
