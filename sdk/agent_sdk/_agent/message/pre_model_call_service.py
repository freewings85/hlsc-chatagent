"""PreModelCallMessageService：每次 ModelRequestNode 前的消息处理管道。

封装设计文档 §3.3 中的处理流程：
  0a. invoked_skills inject — 已激活 skill 指令 → prepend（compact 安全）
  0b. skill_listing inject  — 可用 skill 列表 → prepend（Decision 2）
  1.  context injection     — AGENTS.md / MEMORY.md → prepend to [0]
  2.  attachment inject     — changed_files → append（compact 之前）
  3.  compact check         — microcompact 或 full compact
  4.  post-compact attach   — 若 full compact 产出了 attachments，重新注入

返回 PreModelCallResult：
  - model_messages   — 直接替换 run._graph_run.state.message_history
  - working_messages — 若 compact 发生，调用 MemoryMessageService.update() 持久化
  - compacted        — 是否发生了 compact
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage, ModelRequest, SystemPromptPart, UserPromptPart

from agent_sdk._agent.compact.compactor import CompactResult, Compactor
from agent_sdk._agent.message.attachment_collector import AttachmentCollector
from agent_sdk._agent.message.context_injector import (
    extract_dynamic_text,
    inject_context,
    wrap_system_reminder,
)

if TYPE_CHECKING:
    from agent_sdk._agent.skills.invoked_store import InvokedSkillStore
    from agent_sdk._agent.skills.registry import SkillRegistry

_SYSTEM_PROMPT_SOURCE = "system_prompt"
_SKILL_LISTING_SOURCE = "skill_listing"
_INVOKED_SKILLS_SOURCE = "invoked_skills"


@dataclass
class PreModelCallResult:
    """PreModelCallMessageService.handle() 的返回值。"""

    model_messages: list[ModelMessage]
    """直接传给 Pydantic AI（替换 run._graph_run.state.message_history）。"""

    working_messages: list[ModelMessage]
    """处理后的工作集。若 compact 发生，调用 MemoryMessageService.update() 持久化。"""

    compacted: bool
    """是否发生了 compact（调用方据此决定是否更新 MemoryMessageService）。"""

    dynamic_text: str = ""
    """动态 context 纯文本，由 loop 注入到发给 LLM 的最后一条消息。"""


def _remove_by_source(messages: list[ModelMessage], source: str) -> None:
    """in-place 移除指定 source 的 meta 消息。"""
    messages[:] = [
        msg for msg in messages
        if not (
            isinstance(msg, ModelRequest)
            and isinstance(msg.metadata, dict)
            and msg.metadata.get("source") == source
        )
    ]


def _make_meta_request(content: str, source: str) -> ModelRequest:
    """创建 is_meta=True 的 system-reminder 消息。"""
    return ModelRequest(
        parts=[UserPromptPart(content=wrap_system_reminder(content))],
        metadata={"is_meta": True, "source": source},
    )


class PreModelCallMessageService:
    """每次 ModelRequestNode 前调用，产出 model_messages。

    处理顺序（与设计文档 §3.3 及 Decision 2/3 一致）：
    0a. invoked_skills inject ← InvokedSkillStore.get_all()
    0b. skill_listing inject  ← SkillRegistry.format_listing()
    1.  context injection     ← inject_context()
    2.  attachment inject     ← AttachmentCollector.inject()（compact 之前）
    3.  compact check         ← Compactor.check()
    4.  post-compact attach   ← 若 full compact 产出了 attachments，重新注入
    """

    def __init__(
        self,
        compactor: Compactor,
        context_messages: list[ModelRequest],
        attachment_collector: AttachmentCollector,
        skill_registry: SkillRegistry | None = None,
        invoked_skill_store: InvokedSkillStore | None = None,
        system_prompt: str = "",
    ) -> None:
        self._compactor = compactor
        self._context_messages = context_messages
        self._attachment_collector = attachment_collector
        self._skill_registry = skill_registry
        self._invoked_skill_store = invoked_skill_store
        self._system_prompt = system_prompt
        # 场景允许的 skill 列表（None = 不限制）。由 loop 每轮从 deps 同步。
        self.allowed_skills: list[str] | None = None

    async def handle(self, messages: list[ModelMessage]) -> PreModelCallResult:
        """处理消息，返回 PreModelCallResult。

        不修改传入的 messages（创建新列表后 in-place 操作）。
        """
        working: list[ModelMessage] = list(messages)

        # 0b. skill_listing attachment（先插，让后续 0a 把 invoked_skills 推到 [0]）
        # 最终顺序：[0]=invoked_skills, [1]=skill_listing, [2]=context, ...
        _remove_by_source(working, _SKILL_LISTING_SOURCE)
        if self._skill_registry is not None:
            listing_attachment = self._build_skill_listing_attachment()
            if listing_attachment is not None:
                working.insert(0, listing_attachment)

        # 0a. invoked_skills attachment（compact 后 LLM 仍能看到已激活 skill 指令）
        # 插在 [0]，把 skill_listing 推到 [1]
        _remove_by_source(working, _INVOKED_SKILLS_SOURCE)
        if self._invoked_skill_store is not None:
            invoked_attachment = self._build_invoked_skills_attachment()
            if invoked_attachment is not None:
                working.insert(0, invoked_attachment)

        # 1. Context injection（AGENTS.md + MEMORY.md → prepend to [0]）
        inject_context(working, self._context_messages)

        # 1.5 System prompt injection → 始终在 [0]，确保 system prompt 在所有消息之前
        _remove_by_source(working, _SYSTEM_PROMPT_SOURCE)
        if self._system_prompt:
            working.insert(0, ModelRequest(
                parts=[SystemPromptPart(content=self._system_prompt)],
                metadata={"is_meta": True, "source": _SYSTEM_PROMPT_SOURCE},
            ))

        # 2. Attachment injection（changed_files → append，compact 之前）
        self._attachment_collector.inject(working, CompactResult())

        # 3. Compact check（可能 microcompact 或 full compact）
        compact_result: CompactResult = await self._compactor.check(working)

        # 4. 若 full compact 产出了 attachments（最近文件恢复等），重新注入
        if compact_result.compacted and compact_result.attachments:
            self._attachment_collector.inject(working, compact_result)

        # 提取动态 context 文本，交给 loop 注入到最后一条消息
        dynamic_text: str = extract_dynamic_text(self._context_messages)

        return PreModelCallResult(
            model_messages=working,
            working_messages=list(working),
            compacted=compact_result.compacted,
            dynamic_text=dynamic_text,
        )

    def _build_skill_listing_attachment(self) -> ModelRequest | None:
        """构建 available skills 的 system-reminder 附件（Decision 2）。

        格式：
          The following skills are available for use with the Skill tool:

          - skill_name: description - when_to_use
          ...
        """
        if self._skill_registry is None:
            return None
        listing: str = self._skill_registry.format_listing(filter_names=self.allowed_skills)
        if not listing:
            return None
        content = (
            "The following skills are available for use with the Skill tool:\n\n"
            + listing
        )
        return _make_meta_request(content, _SKILL_LISTING_SOURCE)

    def _build_invoked_skills_attachment(self) -> ModelRequest | None:
        """构建 invoked_skills 的 system-reminder 附件（Decision 3）。

        compact 后消息历史截断，此 attachment 确保 LLM 仍然遵守已激活的 skill 指令。

        格式：
          The following skills were invoked in this session.
          Continue to follow these guidelines:

          ### Skill: commit
          <SKILL.md content>

          ---
          ...
        """
        if self._invoked_skill_store is None:
            return None
        invoked = self._invoked_skill_store.get_all()
        if not invoked:
            return None

        # 只注入当前场景允许的 skills，避免跨场景干扰
        if self.allowed_skills is not None:
            allowed_set = set(self.allowed_skills)
            invoked = {k: v for k, v in invoked.items() if v.name in allowed_set}
            if not invoked:
                return None

        sections = [
            f"### Skill: {skill.name}\n\n{skill.content}"
            for skill in sorted(invoked.values(), key=lambda s: s.invoked_at)
        ]
        content = (
            "The following skills were invoked in this session. "
            "Continue to follow these guidelines:\n\n"
            + "\n\n---\n\n".join(sections)
        )
        return _make_meta_request(content, _INVOKED_SKILLS_SOURCE)
