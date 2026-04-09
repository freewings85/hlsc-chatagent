"""Compactor：两层递进压缩。

Layer 1 — Microcompact：替换旧 tool result 为占位符，不调 API。
Layer 2 — Full Compact：调 LLM 生成摘要 + 保留近期消息（参考 Claude Code）。

在每次 ModelRequestNode 前调用 check()，按需执行压缩。
压缩直接修改 message_history（工作副本），不影响 transcript。
compact 后同时将 boundary + summary 追加到 transcript（审计日志）。
check() 返回 CompactResult，包含压缩结果和需要恢复的附件。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from agent_sdk._agent.compact.config import CompactConfig
from agent_sdk._agent.compact.token_counter import (
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_part_tokens,
)

if TYPE_CHECKING:
    from agent_sdk._agent.message.history_message_loader import HistoryMessageLoader
    from agent_sdk._agent.message.transcript_service import TranscriptService

SummarizeFn = Callable[[list[ModelMessage]], Awaitable[str]]

logger = logging.getLogger(__name__)

# 工具结果被替换后的占位符
_PLACEHOLDER = "[工具结果已压缩，如需查看请重新调用工具]"

# Skill 和 read 类型的 tool result 压缩阈值更低（token 数），因为内容在文件系统可恢复
_LOW_THRESHOLD_TOOL_NAMES: frozenset[str] = frozenset({"Skill", "read_file"})
_LOW_THRESHOLD_TOKENS: int = 250  # 约 1000 字符 / 4


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
        transcript_service: TranscriptService | None = None,
        user_id: str = "",
        session_id: str = "",
        summarize_fn: SummarizeFn | None = None,
    ) -> None:
        self._config = config or CompactConfig()
        self._history_loader = history_loader
        self._transcript_service = transcript_service
        self._user_id = user_id
        self._session_id = session_id
        self._summarize_fn = summarize_fn

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

        # Layer 2: Full Compact（需要 summarize_fn 才执行）
        if total_tokens >= self._config.full_compact_threshold:
            if self._summarize_fn is not None:
                # 1. 确定保留近期消息的切分点
                cut_idx = self._find_keep_cutpoint(messages)
                to_summarize = messages[:cut_idx]
                to_keep = messages[cut_idx:]

                # 2. 只对旧消息生成摘要（如果没有旧消息则无需摘要）
                if to_summarize:
                    summary_text = await self._summarize_fn(to_summarize)
                else:
                    summary_text = ""

                # 3. 组装压缩后的消息列表
                post_tokens = estimate_messages_tokens(to_keep)

                # compact_boundary 标记（is_meta=False，写入 messages + transcript）
                boundary = ModelRequest(
                    parts=[UserPromptPart(content="[对话已压缩，以下为摘要]")],
                    metadata={
                        "is_compact_boundary": True,
                        "compact_info": {
                            "trigger": "auto",
                            "pre_tokens": total_tokens,
                            "tokens_saved": total_tokens - post_tokens,
                            "messages_summarized": len(to_summarize),
                            "messages_kept": len(to_keep),
                        },
                    },
                )
                # LLM 生成的摘要（is_meta=True + is_compact_summary=True）
                summary_msg = ModelRequest(
                    parts=[UserPromptPart(content=summary_text)],
                    metadata={"is_meta": True, "is_compact_summary": True},
                )

                messages.clear()
                messages.extend([boundary, summary_msg, *to_keep])

                logger.info(
                    "Full compact: 压缩 %d tokens → boundary + summary + %d 条近期消息 (%d tokens)",
                    total_tokens, len(to_keep), post_tokens,
                )

                # 持久化压缩后的工作副本
                if self._history_loader:
                    await self._history_loader.save(
                        self._user_id, self._session_id, messages,
                    )

                # 追加 boundary + summary 到 transcript（审计日志）
                if self._transcript_service:
                    from agent_sdk._agent.agent_message import UserMessage, from_model_messages
                    transcript_msgs = from_model_messages([boundary, summary_msg])
                    await self._transcript_service.append(
                        self._user_id, self._session_id, transcript_msgs,
                    )

                return CompactResult(
                    compacted=True,
                    layer="full",
                    tokens_saved=total_tokens - post_tokens,
                    pre_tokens=total_tokens,
                )
            else:
                logger.info(
                    "Full compact 需要触发 (tokens=%d, threshold=%d)，但 summarize_fn 未配置",
                    total_tokens, self._config.full_compact_threshold,
                )

        return CompactResult(pre_tokens=total_tokens)

    def _find_keep_cutpoint(self, messages: list[ModelMessage]) -> int:
        """确定 full compact 保留近期消息的切分点（参考 Claude Code f5Y/Gk8）。

        从后往前扫描，累加 token 数，直到满足：
        - token 数 >= keep_recent_min_tokens 且含文本消息数 >= keep_recent_min_messages
        - 或 token 数 >= keep_recent_max_tokens（硬上限）

        然后向前调整切分点，确保 tool_call/tool_result 配对不被拆开。

        返回切分索引：messages[:idx] 被摘要，messages[idx:] 被保留。
        """
        if not messages:
            return 0

        cfg = self._config
        token_sum = 0
        text_msg_count = 0
        cut_idx = len(messages)

        # 从后往前扫描
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            token_sum += estimate_message_tokens(msg)
            if self._has_text(msg):
                text_msg_count += 1

            cut_idx = i

            # 硬上限
            if token_sum >= cfg.keep_recent_max_tokens:
                break
            # 软条件
            if token_sum >= cfg.keep_recent_min_tokens and text_msg_count >= cfg.keep_recent_min_messages:
                break

        # 向前调整：确保 tool_call/tool_result 配对完整
        cut_idx = self._adjust_for_tool_pairs(messages, cut_idx)

        return cut_idx

    @staticmethod
    def _adjust_for_tool_pairs(messages: list[ModelMessage], cut_idx: int) -> int:
        """向前调整切分点，确保 keep 区域内的 tool_result 都有对应的 tool_call。

        如果 keep 区域（messages[cut_idx:]）里有 ToolReturnPart 引用了
        cut_idx 之前的 ToolCallPart，就把切分点向前移到包含那个 tool_call 的消息。
        """
        # 收集 keep 区域的 tool_result ids
        keep_result_ids: set[str] = set()
        for msg in messages[cut_idx:]:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart) and part.tool_call_id:
                        keep_result_ids.add(part.tool_call_id)

        if not keep_result_ids:
            return cut_idx

        # 收集 keep 区域的 tool_call ids
        keep_call_ids: set[str] = set()
        for msg in messages[cut_idx:]:
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart) and part.tool_call_id:
                        keep_call_ids.add(part.tool_call_id)

        # 找出 keep 区域里有 result 但没有 call 的 ids
        missing_call_ids = keep_result_ids - keep_call_ids
        if not missing_call_ids:
            return cut_idx

        # 向前搜索，把包含这些 tool_call 的消息也拉进 keep 区域
        for i in range(cut_idx - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart) and part.tool_call_id in missing_call_ids:
                        missing_call_ids.discard(part.tool_call_id)
                        cut_idx = i
            if not missing_call_ids:
                break

        return cut_idx

    @staticmethod
    def _has_text(msg: ModelMessage) -> bool:
        """判断消息是否包含文本内容（用于计数含文本消息）。"""
        if isinstance(msg, ModelRequest):
            return any(isinstance(p, (UserPromptPart, TextPart)) for p in msg.parts)
        if isinstance(msg, ModelResponse):
            return any(isinstance(p, TextPart) for p in msg.parts)
        return False

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

        # 3. 分两类计算：低阈值工具（Skill/read）和普通工具
        placeholder_tokens = len(_PLACEHOLDER) // 4
        low_threshold_replaceable: list[tuple[int, int, int]] = []
        normal_replaceable: list[tuple[int, int, int]] = []  # (msg_idx, part_idx, savings)

        for msg_idx, part_idx in to_replace:
            msg = messages[msg_idx]
            if not isinstance(msg, ModelRequest):  # pragma: no cover
                continue
            part = msg.parts[part_idx]
            if not isinstance(part, ToolReturnPart):  # pragma: no cover
                continue

            old_tokens = estimate_part_tokens(part)
            savings = old_tokens - placeholder_tokens
            if savings <= 0:
                continue

            if part.tool_name in _LOW_THRESHOLD_TOOL_NAMES:
                # Skill/read：超过低阈值就替换（内容在文件系统可恢复）
                if old_tokens > _LOW_THRESHOLD_TOKENS:
                    low_threshold_replaceable.append((msg_idx, part_idx, savings))
            else:
                normal_replaceable.append((msg_idx, part_idx, savings))

        # 4. 低阈值工具：直接替换（不受全局 min_savings_threshold 限制）
        total_savings: int = 0
        for msg_idx, part_idx, savings in low_threshold_replaceable:
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
            total_savings += savings

        # 5. 普通工具：累计节省量超过 min_savings_threshold 才替换
        normal_total = sum(s for _, _, s in normal_replaceable)
        if normal_total >= self._config.min_savings_threshold:
            for msg_idx, part_idx, savings in normal_replaceable:
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
                total_savings += savings

        return total_savings
