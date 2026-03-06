"""Compactor：两层递进压缩。

Layer 1 — Microcompact：替换旧 tool result 为占位符，不调 API。
Layer 2 — Full Compact：调 LLM 生成摘要，替换全部消息。

在每次 ModelRequestNode 前调用 check()，按需执行压缩。
压缩直接修改 message_history（工作副本），不影响 transcript。
check() 返回 CompactResult，包含压缩结果和需要恢复的附件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
)

from src.agent.compact.config import CompactConfig
from src.agent.compact.token_counter import (
    estimate_messages_tokens,
    estimate_part_tokens,
)

if TYPE_CHECKING:
    from src.agent.message.history_message_loader import HistoryMessageLoader

logger = logging.getLogger(__name__)

# 工具结果被替换后的占位符
_PLACEHOLDER = "[工具结果已压缩，如需查看请重新调用工具]"


@dataclass
class CompactResult:
    """压缩结果。

    compacted: 是否执行了压缩
    layer: 执行的压缩层级
    tokens_saved: 估算节省的 token 数
    pre_tokens: 压缩前总 token 数
    attachments: full compact 后需要恢复的上下文消息（microcompact 为空）
    """

    compacted: bool = False
    layer: str = "none"  # "none" / "microcompact" / "full"
    tokens_saved: int = 0
    pre_tokens: int = 0
    attachments: list[ModelRequest] = field(default_factory=list)


class Compactor:
    """两层递进压缩器。

    持有 history_loader 引用，compact 后调用 save() 覆写 messages.jsonl。
    """

    def __init__(
        self,
        config: CompactConfig | None = None,
        history_loader: HistoryMessageLoader | None = None,
        user_id: str = "",
        session_id: str = "",
    ) -> None:
        self._config = config or CompactConfig()
        self._history_loader = history_loader
        self._user_id = user_id
        self._session_id = session_id

    async def check(self, messages: list[ModelMessage]) -> CompactResult:
        """检查并执行压缩。

        直接修改 messages 列表（in-place）。
        返回 CompactResult 描述压缩结果和需要恢复的附件。
        """
        if not self._config.auto_compact_enabled:
            return CompactResult()

        total_tokens = estimate_messages_tokens(messages)

        # Layer 1: Microcompact
        if self._config.microcompact_enabled and total_tokens >= self._config.microcompact_threshold:
            savings = self._microcompact(messages)
            if savings > 0:
                logger.info(
                    "Microcompact: 节省约 %d tokens (总计 %d → %d)",
                    savings, total_tokens, total_tokens - savings,
                )

                # 持久化压缩后的工作副本
                if self._history_loader:
                    await self._history_loader.save(
                        self._user_id, self._session_id, messages,
                    )

                return CompactResult(
                    compacted=True,
                    layer="microcompact",
                    tokens_saved=savings,
                    pre_tokens=total_tokens,
                )

        # Layer 2: Full Compact
        if total_tokens >= self._config.full_compact_threshold:
            # TODO: 调用 LLM 生成摘要，替换消息
            # 实现后返回 CompactResult(layer="full", attachments=[...])
            # attachments 包含需要恢复的上下文：最近读过的文件、任务状态等
            logger.info(
                "Full compact 需要触发 (tokens=%d, threshold=%d)，但尚未实现",
                total_tokens, self._config.full_compact_threshold,
            )

        return CompactResult(pre_tokens=total_tokens)

    def _microcompact(self, messages: list[ModelMessage]) -> int:
        """Layer 1: 替换旧 tool result 为占位符。

        保留最近 N 个完整 tool result，替换更早的。
        直接修改 messages 列表中的消息（in-place）。
        返回估算节省的 token 数。
        """
        # 1. 收集所有 tool return 的位置
        tool_return_positions: list[tuple[int, int]] = []  # (msg_idx, part_idx)
        for msg_idx, msg in enumerate(messages):
            if not isinstance(msg, ModelRequest):
                continue
            for part_idx, part in enumerate(msg.parts):
                if isinstance(part, ToolReturnPart):
                    tool_return_positions.append((msg_idx, part_idx))

        if not tool_return_positions:
            return 0

        # 2. 保留最近 N 个，替换更早的
        keep_n = self._config.keep_recent_tool_results
        to_replace = tool_return_positions[:-keep_n] if keep_n > 0 else tool_return_positions

        if not to_replace:
            return 0

        # 3. 先计算潜在节省量
        placeholder_tokens = len(_PLACEHOLDER) // 4
        replaceable: list[tuple[int, int, int]] = []  # (msg_idx, part_idx, savings)

        for msg_idx, part_idx in to_replace:
            msg = messages[msg_idx]
            if not isinstance(msg, ModelRequest):
                continue
            part = msg.parts[part_idx]
            if not isinstance(part, ToolReturnPart):
                continue

            old_tokens = estimate_part_tokens(part)
            savings = old_tokens - placeholder_tokens
            if savings > 0:
                replaceable.append((msg_idx, part_idx, savings))

        total_savings = sum(s for _, _, s in replaceable)
        if total_savings < self._config.min_savings_threshold:
            return 0  # 节省不够，不替换

        # 4. 确认值得，执行替换
        for msg_idx, part_idx, _ in replaceable:
            msg = messages[msg_idx]
            assert isinstance(msg, ModelRequest)
            part = msg.parts[part_idx]
            assert isinstance(part, ToolReturnPart)

            msg.parts[part_idx] = ToolReturnPart(
                tool_name=part.tool_name,
                content=_PLACEHOLDER,
                tool_call_id=part.tool_call_id,
                timestamp=part.timestamp,
            )

        return total_savings
