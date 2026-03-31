"""技能脚本执行器：运行 SkillScript，interrupt 由 call_interrupt 处理。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_sdk._agent.skills.script import SkillContext, SkillScript

if TYPE_CHECKING:
    from pydantic_ai import RunContext
    from agent_sdk._agent.deps import AgentDeps

logger: logging.Logger = logging.getLogger(__name__)


async def execute_skill_script(
    script: SkillScript,
    run_context: RunContext[AgentDeps],
) -> str:
    """执行技能脚本，返回结果文本。

    interrupt 由 SkillContext.interrupt() → call_interrupt 处理，
    协程会挂起等待用户回复，无需 checkpoint。

    Args:
        script: 要执行的技能脚本实例。
        run_context: Pydantic AI RunContext（传给 SkillContext 用于 call_interrupt）。

    Returns:
        脚本返回的结果文本。
    """
    ctx: SkillContext = SkillContext(
        _run_context=run_context,
    )

    logger.info("执行技能脚本: skill=%s", script.name)
    output: str = await script.run(ctx)
    logger.info("技能脚本完成: skill=%s", script.name)
    return output
