"""补充覆盖率缺口的测试"""

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from src.agent.compact.compactor import CompactResult, Compactor
from src.agent.compact.config import CompactConfig
from src.agent.compact.token_counter import estimate_part_tokens


class TestCompactorDisabled:

    @pytest.mark.asyncio
    async def test_auto_compact_disabled(self) -> None:
        """auto_compact_enabled=False 时直接返回空结果"""
        config = CompactConfig(auto_compact_enabled=False)
        compactor = Compactor(config=config)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="x" * 100_000)]),
        ]
        result = await compactor.check(messages)
        assert result.compacted is False
        assert result.layer == "none"


class TestMicrocompactEdgeCases:

    def test_no_tool_returns(self) -> None:
        """没有 tool_return 时 _microcompact 返回 0"""
        compactor = Compactor(config=CompactConfig())
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="hello")]),
            ModelResponse(parts=[TextPart(content="hi")]),
        ]
        assert compactor._microcompact(messages) == 0

    def test_all_within_keep_range(self) -> None:
        """tool_return 数 <= keep_n 时不替换"""
        config = CompactConfig(keep_recent_tool_results=5)
        compactor = Compactor(config=config)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[ToolReturnPart(
                tool_name="t", content="result", tool_call_id="c1",
            )]),
        ]
        assert compactor._microcompact(messages) == 0


class TestTokenCounterEdgeCases:

    def test_non_string_user_content(self) -> None:
        """UserPromptPart content 为列表时返回 100"""
        part = UserPromptPart(content=[{"type": "text", "text": "hello"}])
        tokens = estimate_part_tokens(part)
        assert tokens == 100

    def test_default_part_type(self) -> None:
        """未知 part 类型返回 50"""
        part = SystemPromptPart(content="test")
        tokens = estimate_part_tokens(part)
        assert tokens == 50

    def test_tool_return_non_string_content(self) -> None:
        """ToolReturnPart content 为非字符串时走 str() 转换"""
        part = ToolReturnPart(
            tool_name="test",
            content=["item1", "item2"],  # type: ignore[arg-type]
            tool_call_id="c1",
        )
        tokens = estimate_part_tokens(part)
        assert tokens > 0
