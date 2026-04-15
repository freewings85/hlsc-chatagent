"""PreModelCallMessageService：每次 ModelRequestNode 前的消息处理管道。

处理流程：
  0.  rerender request_context — 用 deps 最新值重渲 source=request_context 的占位
  1a. skill_listing inject     — 可用 skill 列表（元信息）→ prepend，稳定利于 cache
  1b. system_prompt inject     — 始终 [0]，cache breakpoint
  2.  static context injection — AGENTS.md / MEMORY.md → prepend 到 [0]
  3.  attachment inject        — changed_files → append（compact 之前）
  4.  compact check            — microcompact 或 full compact
  5.  post-compact attach      — 若 full compact 产出了 attachments，重新注入

返回 PreModelCallResult：
  - model_messages      — 直接替换 run._graph_run.state.message_history
  - working_messages    — 若 compact 发生，调用 MemoryMessageService.update() 持久化
  - compacted           — 是否发生了 compact
  - dynamic_text        — 动态 context 纯文本，由 loop 注入到最后一条 user message 的 parts
  - invoked_skills_tail — 已激活 skill 纯文本；仅 compact 触发那一轮非空，作为 compact
                          兜底（正常情况下 SKILL.md 在 skill tool result 里，对话历史自然带）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
_REQUEST_CONTEXT_SOURCE = "request_context"


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
    """动态 context 纯文本，由 loop 每轮注入到最后一条 user message 的 parts。"""

    invoked_skills_tail: str = ""
    """已激活 skill 纯文本；仅 compact 触发那一轮非空，compact 兜底用。"""


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

    处理顺序：
    0.  rerender request_context ← 用 deps 最新值重渲占位 ModelRequest
    1a. skill_listing inject     ← SkillRegistry.format_listing()（元信息，prepend 头部）
    1b. system_prompt inject     ← 始终 [0]
    2.  context injection        ← inject_context()（静态 AGENT.md/MEMORY.md）
    3.  attachment inject        ← AttachmentCollector.inject()（compact 之前）
    4.  compact check            ← Compactor.check()
    5.  post-compact attach      ← 若 full compact 产出了 attachments，重新注入
    6.  invoked_skills_tail      ← 仅 compact 发生时产出；不动消息，交给 loop 尾部注入
    """

    def __init__(
        self,
        compactor: Compactor,
        context_messages: list[ModelRequest],
        attachment_collector: AttachmentCollector,
        skill_registry: SkillRegistry | None = None,
        invoked_skill_store: InvokedSkillStore | None = None,
        system_prompt: str = "",
        context_formatter: Any | None = None,
        request_context: Any | None = None,
    ) -> None:
        self._compactor = compactor
        self._context_messages = context_messages
        self._attachment_collector = attachment_collector
        self._skill_registry = skill_registry
        self._invoked_skill_store = invoked_skill_store
        self._system_prompt = system_prompt
        # 场景允许的 skill 列表（None = 不限制）。由 loop 每轮从 deps 同步。
        self.allowed_skills: list[str] | None = None
        # request_context 渲染：每次 handle() 前跑 formatter，拿 deps 最新值
        # mutate context_messages 里 source=request_context 的 ModelRequest 的 parts
        self._context_formatter = context_formatter
        self._request_context = request_context

    async def handle(self, messages: list[ModelMessage], deps: Any | None = None) -> PreModelCallResult:
        """处理消息，返回 PreModelCallResult。

        不修改传入的 messages（创建新列表后 in-place 操作）。
        deps 由 loop 每次迭代传入，用于 request_context 重渲（读 deps.instruction 等最新值）。
        """
        # 0. 重渲 request_context（读 deps 最新值，mutate 占位 ModelRequest 的 parts）
        self._rerender_request_context(deps)

        working: list[ModelMessage] = list(messages)

        # 1a. skill_listing attachment（元信息，头部；allowed_skills 不变则 cache 友好）
        _remove_by_source(working, _SKILL_LISTING_SOURCE)
        if self._skill_registry is not None:
            listing_attachment = self._build_skill_listing_attachment()
            if listing_attachment is not None:
                working.insert(0, listing_attachment)

        # 2. Context injection（AGENTS.md + MEMORY.md → prepend to [0]）
        inject_context(working, self._context_messages)

        # 1b. System prompt injection → 始终在 [0]，确保 system prompt 在所有消息之前
        _remove_by_source(working, _SYSTEM_PROMPT_SOURCE)
        if self._system_prompt:
            working.insert(0, ModelRequest(
                parts=[SystemPromptPart(content=self._system_prompt)],
                metadata={"is_meta": True, "source": _SYSTEM_PROMPT_SOURCE},
            ))

        # 3. Attachment injection（changed_files → append，compact 之前）
        self._attachment_collector.inject(working, CompactResult())

        # 4. Compact check（可能 microcompact 或 full compact）
        compact_result: CompactResult = await self._compactor.check(working)

        # 5. 若 full compact 产出了 attachments（最近文件恢复等），重新注入
        if compact_result.compacted and compact_result.attachments:
            self._attachment_collector.inject(working, compact_result)

        # 6. invoked_skills_tail：仅 compact 触发那一轮注入（正常 tool result 里已带
        #    SKILL.md，靠对话历史自然可见；compact 压掉后才需要兜底）
        invoked_skills_tail: str = ""
        if compact_result.compacted:
            invoked_skills_tail = self._format_invoked_skills_text()

        # 提取动态 context 文本，交给 loop 注入到最后一条消息
        dynamic_text: str = extract_dynamic_text(self._context_messages)

        return PreModelCallResult(
            model_messages=working,
            working_messages=list(working),
            compacted=compact_result.compacted,
            dynamic_text=dynamic_text,
            invoked_skills_tail=invoked_skills_tail,
        )

    def _rerender_request_context(self, deps: Any | None) -> None:
        """每次 handle() 前重跑 formatter，把最新文本写到 source=request_context 的 ModelRequest。

        占位消息由 agent.run() 初始化时插入 context_messages。这里只 mutate parts。
        """
        if self._context_formatter is None:
            return
        fmt_input: Any = self._request_context if self._request_context is not None else {}
        context_text: str = self._context_formatter.format(fmt_input, deps=deps)
        for msg in self._context_messages:
            if (
                isinstance(msg, ModelRequest)
                and isinstance(msg.metadata, dict)
                and msg.metadata.get("source") == _REQUEST_CONTEXT_SOURCE
            ):
                msg.parts = [UserPromptPart(content=context_text)] if context_text else []
                return

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

    def _format_invoked_skills_text(self) -> str:
        """返回 invoked skills 的纯文本（不含 <system-reminder> 包裹，由 loop 的
        build_invoked_skills_part() 包）。

        compact 后消息历史截断，tool result 里的 SKILL.md 会被压掉，此文本追加到最后
        一条 user message 的 parts 作为 compact 兜底，确保 LLM 仍遵守已激活的 skill 指令。

        格式：
          The following skills were invoked in this session.
          Continue to follow these guidelines:

          ### Skill: commit
          <SKILL.md content>

          ---
          ...
        """
        if self._invoked_skill_store is None:
            return ""
        invoked = self._invoked_skill_store.get_all()
        if not invoked:
            return ""

        # 只注入当前场景允许的 skills，避免跨场景干扰
        if self.allowed_skills is not None:
            allowed_set = set(self.allowed_skills)
            invoked = {k: v for k, v in invoked.items() if v.name in allowed_set}
            if not invoked:
                return ""

        sections = [
            f"### Skill: {skill.name}\n\n{skill.content}"
            for skill in sorted(invoked.values(), key=lambda s: s.invoked_at)
        ]
        return (
            "The following skills were invoked in this session. "
            "Continue to follow these guidelines:\n\n"
            + "\n\n---\n\n".join(sections)
        )
