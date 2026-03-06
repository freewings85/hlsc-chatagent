"""Compactor 测试"""

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from src.agent.compact.compactor import CompactResult, Compactor, _PLACEHOLDER
from src.agent.compact.config import CompactConfig
from src.agent.compact.token_counter import estimate_messages_tokens
from src.agent.message.history_message_loader import HistoryMessageLoader
from src.storage.local_backend import FilesystemBackend


def _make_tool_exchange(tool_name: str, result: str) -> list[ModelMessage]:
    """创建一组 tool call + tool return 消息。"""
    return [
        ModelResponse(parts=[ToolCallPart(
            tool_name=tool_name,
            args={"query": "test"},
            tool_call_id=f"call_{tool_name}",
        )]),
        ModelRequest(parts=[ToolReturnPart(
            tool_name=tool_name,
            content=result,
            tool_call_id=f"call_{tool_name}",
        )]),
    ]


class TestCompactConfig:

    def test_defaults(self) -> None:
        config = CompactConfig()
        assert config.effective_window == 180_000
        assert config.microcompact_threshold == 160_000
        assert config.full_compact_threshold == 167_000

    def test_custom(self) -> None:
        config = CompactConfig(context_window=100_000, output_reserve=10_000)
        assert config.effective_window == 90_000


class TestMicrocompact:

    def _make_compactor(self, **kwargs) -> Compactor:
        config = CompactConfig(**kwargs)
        return Compactor(config=config)

    @pytest.mark.asyncio
    async def test_no_compact_below_threshold(self) -> None:
        """token 数低于阈值时不压缩"""
        compactor = self._make_compactor()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="hello")]),
            ModelResponse(parts=[TextPart(content="hi")]),
        ]
        result = await compactor.check(messages)
        assert result.compacted is False

    @pytest.mark.asyncio
    async def test_microcompact_replaces_old_tool_results(self) -> None:
        """超过阈值时替换旧 tool result"""
        big_result = "x" * 100_000  # 约 25K tokens each
        messages: list[ModelMessage] = []

        # 5 个 tool exchange，总约 125K tokens
        for i in range(5):
            messages.extend(_make_tool_exchange(f"tool_{i}", big_result))

        # effective=120K, threshold=120K-1K=119K, 125K > 119K → 触发
        compactor = self._make_compactor(
            context_window=125_000,
            output_reserve=5_000,
            min_savings_threshold=1_000,
            keep_recent_tool_results=2,
        )

        total_before = estimate_messages_tokens(messages)
        result = await compactor.check(messages)

        assert result.compacted is True
        assert result.layer == "microcompact"
        assert result.tokens_saved > 0
        total_after = estimate_messages_tokens(messages)
        assert total_after < total_before

        # 最后 2 个 tool return 应该保持原样
        tool_returns = [
            p for m in messages if isinstance(m, ModelRequest)
            for p in m.parts if isinstance(p, ToolReturnPart)
        ]
        # 前 3 个被替换
        for tr in tool_returns[:3]:
            assert tr.content == _PLACEHOLDER
        # 后 2 个保持原样
        for tr in tool_returns[3:]:
            assert tr.content == big_result

    @pytest.mark.asyncio
    async def test_microcompact_preserves_tool_metadata(self) -> None:
        """压缩保留 tool_name 和 tool_call_id"""
        big_result = "y" * 200_000  # 约 50K tokens

        messages: list[ModelMessage] = []
        messages.extend(_make_tool_exchange("my_tool", big_result))
        messages.extend(_make_tool_exchange("other_tool", "small"))

        # effective=50K, threshold=50K-100=49900, 50005 > 49900 → 触发
        compactor = self._make_compactor(
            context_window=50_100,
            output_reserve=100,
            min_savings_threshold=100,
            keep_recent_tool_results=1,
        )

        await compactor.check(messages)

        # 第一个 tool return 被替换，但保留了 tool_name
        replaced = messages[1]
        assert isinstance(replaced, ModelRequest)
        part = replaced.parts[0]
        assert isinstance(part, ToolReturnPart)
        assert part.tool_name == "my_tool"
        assert part.tool_call_id == "call_my_tool"
        assert part.content == _PLACEHOLDER

    @pytest.mark.asyncio
    async def test_savings_below_threshold_no_replace(self) -> None:
        """节省量不够阈值时不替换"""
        small_result = "z" * 100  # 很小

        messages: list[ModelMessage] = []
        for i in range(5):
            messages.extend(_make_tool_exchange(f"tool_{i}", small_result))

        compactor = self._make_compactor(
            context_window=10_000,
            output_reserve=1_000,
            min_savings_threshold=50_000,  # 非常高的阈值
            keep_recent_tool_results=2,
        )

        result = await compactor.check(messages)
        assert result.compacted is False

        # 所有 tool return 保持原样
        tool_returns = [
            p for m in messages if isinstance(m, ModelRequest)
            for p in m.parts if isinstance(p, ToolReturnPart)
        ]
        for tr in tool_returns:
            assert tr.content == small_result


class TestCompactWithPersistence:

    @pytest.mark.asyncio
    async def test_microcompact_saves_to_file(self, tmp_path) -> None:
        """压缩后调用 history_loader.save() 持久化"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        big_result = "w" * 200_000
        messages: list[ModelMessage] = []
        for i in range(4):
            messages.extend(_make_tool_exchange(f"tool_{i}", big_result))

        # 先 append 原始消息
        await loader.append("u1", "s1", messages)

        # 4 × 200K chars ≈ 200K tokens, effective=200K, threshold=200K-100=199900
        compactor = Compactor(
            config=CompactConfig(
                context_window=200_100,
                output_reserve=100,
                min_savings_threshold=100,
                keep_recent_tool_results=1,
            ),
            history_loader=loader,
            user_id="u1",
            session_id="s1",
        )

        result = await compactor.check(messages)
        assert result.compacted is True
        assert result.layer == "microcompact"
        assert result.attachments == []

        # 重新从文件加载，验证压缩后的内容被持久化了
        loaded = await loader.load("u1", "s1")
        tool_returns = [
            p for m in loaded if isinstance(m, ModelRequest)
            for p in m.parts if isinstance(p, ToolReturnPart)
        ]
        # 前 3 个被替换
        compressed = [tr for tr in tool_returns if tr.content == _PLACEHOLDER]
        assert len(compressed) == 3
