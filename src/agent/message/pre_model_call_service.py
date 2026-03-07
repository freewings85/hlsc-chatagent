"""PreModelCallMessageService：每次 ModelRequestNode 前的消息处理管道。

封装设计文档 §3.3 中的四步处理流程：
  1. context injection  — agent.md / memory.md → prepend to [0]
  2. attachment inject  — changed_files → append to end（compact 之前）
  3. compact check      — microcompact 或 full compact
  4. post-compact attach — 若 full compact 产出了 attachments，重新注入

返回 PreModelCallResult：
  - model_messages   — 直接替换 run._graph_run.state.message_history
  - working_messages — 若 compact 发生，调用 MemoryMessageService.update() 持久化
  - compacted        — 是否发生了 compact
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.messages import ModelMessage, ModelRequest

from src.agent.compact.compactor import CompactResult, Compactor
from src.agent.message.attachment_collector import AttachmentCollector
from src.agent.message.context_injector import inject_context


@dataclass
class PreModelCallResult:
    """PreModelCallMessageService.handle() 的返回值。"""

    model_messages: list[ModelMessage]
    """直接传给 Pydantic AI（替换 run._graph_run.state.message_history）。"""

    working_messages: list[ModelMessage]
    """处理后的工作集。若 compact 发生，调用 MemoryMessageService.update() 持久化。"""

    compacted: bool
    """是否发生了 compact（调用方据此决定是否更新 MemoryMessageService）。"""


class PreModelCallMessageService:
    """每次 ModelRequestNode 前调用，产出 model_messages。

    处理顺序（与设计文档 §3.3 及 Claude Code 源码顺序一致）：
    1. context injection  ← inject_context()
    2. attachment inject  ← AttachmentCollector.inject()（compact 之前）
    3. compact check      ← Compactor.check()
    4. post-compact attach ← 若 full compact 产出了 attachments，重新注入
    """

    def __init__(
        self,
        compactor: Compactor,
        context_messages: list[ModelRequest],
        attachment_collector: AttachmentCollector,
    ) -> None:
        self._compactor = compactor
        self._context_messages = context_messages
        self._attachment_collector = attachment_collector

    async def handle(self, messages: list[ModelMessage]) -> PreModelCallResult:
        """处理消息，返回 PreModelCallResult。

        不修改传入的 messages（创建新列表后 in-place 操作）。
        """
        working: list[ModelMessage] = list(messages)

        # 1. Context injection（agent.md + memory.md → prepend to [0]）
        inject_context(working, self._context_messages)

        # 2. Attachment injection（changed_files → append，compact 之前）
        self._attachment_collector.inject(working, CompactResult())

        # 3. Compact check（可能 microcompact 或 full compact）
        compact_result: CompactResult = await self._compactor.check(working)

        # 4. 若 full compact 产出了 attachments（最近文件恢复等），重新注入
        if compact_result.compacted and compact_result.attachments:
            self._attachment_collector.inject(working, compact_result)

        return PreModelCallResult(
            model_messages=working,
            working_messages=list(working),
            compacted=compact_result.compacted,
        )
