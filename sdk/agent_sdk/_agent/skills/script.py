"""SkillScript：Python 实现的技能脚本，复用 call_interrupt 实现中断/恢复。

核心思路：
- interrupt() 直接 await call_interrupt()，协程挂起等待用户回复
- 无需 checkpoint / replay，状态由协程天然保持
- Temporal 模式下支持持久化；内存模式下进程重启丢失（与普通 tool interrupt 一致）

使用方式：
    class MyScript(SkillScript):
        name = "my-skill"

        async def run(self, ctx: SkillContext) -> str:
            answer = await ctx.interrupt({
                "type": "input",
                "question": "你叫什么名字？",
            })
            return f"你好，{answer}！"
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai import RunContext
    from agent_sdk._agent.deps import AgentDeps


@dataclass
class SkillContext:
    """技能脚本的执行上下文。

    提供 state 累积 + interrupt 中断/恢复能力（复用 call_interrupt）。
    """

    state: dict[str, Any] = field(default_factory=dict)
    """自由累积状态，脚本内跨 interrupt 共享。"""

    _run_context: RunContext[AgentDeps] | None = field(default=None, repr=False)
    """Pydantic AI RunContext，用于调用 call_interrupt。"""

    async def interrupt(self, data: dict[str, Any]) -> str:
        """暂停脚本执行，等待用户回复后继续。

        底层复用 call_interrupt → Temporal / asyncio.Event 等待。

        Args:
            data: 发给前端的数据（type、question 等，前端自定义渲染）。

        Returns:
            用户的回复文本。
        """
        if self._run_context is None:
            raise RuntimeError("SkillContext 缺少 _run_context，无法调用 interrupt")

        from agent_sdk._agent.tools.call_interrupt import call_interrupt
        return await call_interrupt(self._run_context, data)


class SkillScript(ABC):
    """技能脚本基类 — 子类实现 run() 方法。

    run() 中可调用 ctx.interrupt() 进行用户交互，
    协程挂起等待回复，无需手动管理状态。
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
        """
        ...
