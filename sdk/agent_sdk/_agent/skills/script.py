"""SkillScript：Python 实现的技能脚本，支持 LangGraph 风格的 checkpoint interrupt。

核心思路：
- interrupt() 不暂停协程，而是抛异常终止当前 run
- 状态存入 checkpoint，下次 run 从断点恢复
- script.run() 每次从头执行，已回答的 interrupt 直接返回缓存值

使用方式：
    class MyScript(SkillScript):
        name = "my-skill"

        async def run(self, ctx: SkillContext) -> str:
            answer = await ctx.interrupt("ask_name", {
                "type": "input",
                "question": "你叫什么名字？",
            })
            return f"你好，{answer}！"
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, NoReturn

from agent_sdk._agent.deps import AgentDeps


class SkillInterrupt(Exception):
    """skill script 中断异常 — ctx.interrupt() 抛出，由 executor 捕获。

    携带当前 state 快照和前端展示数据，executor 负责持久化和事件发射。
    """

    def __init__(
        self,
        *,
        interrupt_id: str,
        data: dict[str, Any],
        state: dict[str, Any],
        answered: dict[str, str],
    ) -> None:
        super().__init__(f"SkillInterrupt: {interrupt_id}")
        self.interrupt_id: str = interrupt_id
        self.data: dict[str, Any] = data
        self.state: dict[str, Any] = state
        self.answered: dict[str, str] = answered


@dataclass
class SkillContext:
    """技能脚本的执行上下文。

    提供 state 累积 + interrupt 中断/恢复能力。
    """

    state: dict[str, Any] = field(default_factory=dict)
    """累积状态，每次 interrupt 时存入 checkpoint。"""

    deps: AgentDeps = field(default_factory=AgentDeps)
    """Agent 依赖（emitter、session_id 等）。"""

    _answered: dict[str, str] = field(default_factory=dict)
    """已回答的 interrupt：interrupt_id → 用户回复。"""

    _pending_interrupt_id: str | None = None
    """本次 resume 对应的 interrupt id。"""

    _resume_reply: str | None = None
    """本次 resume 的用户回复文本。"""

    async def interrupt(self, interrupt_id: str, data: dict[str, Any]) -> str:
        """LangGraph 风格中断：首次抛异常终止 run，resume 时返回用户回复。

        三路分支：
        1. interrupt_id 已在 _answered 中 → 返回缓存值（replay 跳过）
        2. interrupt_id == _pending 且有 resume_reply → 记录并返回（resume 命中）
        3. 其他 → 抛 SkillInterrupt 终止当前 run

        Args:
            interrupt_id: 唯一标识此中断点，同一 script 内不可重复。
            data: 发给前端的数据（type、question 等，前端自定义渲染）。

        Returns:
            用户的回复文本。

        Raises:
            SkillInterrupt: 首次到达此中断点时抛出。
        """
        # 分支 1：已回答 → 直接返回
        if interrupt_id in self._answered:
            return self._answered[interrupt_id]

        # 分支 2：resume 命中 → 记录并返回
        if (
            self._pending_interrupt_id == interrupt_id
            and self._resume_reply is not None
        ):
            self._answered[interrupt_id] = self._resume_reply
            # 清除 pending 状态，允许后续 interrupt 正常触发
            self._pending_interrupt_id = None
            self._resume_reply = None
            return self._answered[interrupt_id]

        # 分支 3：首次到达 → 抛异常终止 run
        raise SkillInterrupt(
            interrupt_id=interrupt_id,
            data=data,
            state=dict(self.state),
            answered=dict(self._answered),
        )


class SkillScript(ABC):
    """技能脚本基类 — 子类实现 run() 方法。

    run() 中可调用 ctx.interrupt() 进行用户交互。
    每次 run 从头执行，已回答的 interrupt 自动跳过。
    """

    name: str = ""
    """skill 名称，必须与 SKILL.md 的 name 字段一致。"""

    @abstractmethod
    async def run(self, ctx: SkillContext) -> str:
        """执行技能脚本逻辑。

        Args:
            ctx: 技能上下文，提供 state 和 interrupt 能力。

        Returns:
            最终结果文本，返回给 LLM 作为工具调用结果。

        Raises:
            SkillInterrupt: 由 ctx.interrupt() 抛出，executor 负责处理。
        """
        ...
