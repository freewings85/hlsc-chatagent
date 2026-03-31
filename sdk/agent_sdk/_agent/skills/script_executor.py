"""技能脚本执行器：运行 SkillScript，捕获 SkillInterrupt，管理 checkpoint。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.skills.script import SkillContext, SkillInterrupt, SkillScript
from agent_sdk._agent.skills.script_checkpoint import SkillCheckpoint
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class ExecuteResult:
    """技能脚本执行结果。"""

    output: str | None = None
    """脚本正常完成时的返回值。中断时为 None。"""

    interrupted: bool = False
    """是否因 SkillInterrupt 中断。"""

    checkpoint: SkillCheckpoint | None = None
    """中断时生成的 checkpoint（需要调用方持久化）。"""


async def execute_skill_script(
    script: SkillScript,
    deps: AgentDeps,
    checkpoint: SkillCheckpoint | None = None,
    resume_reply: str | None = None,
) -> ExecuteResult:
    """执行技能脚本，处理中断和恢复。

    Args:
        script: 要执行的技能脚本实例。
        deps: Agent 依赖。
        checkpoint: 从持久化加载的断点（resume 时提供）。
        resume_reply: 用户对上次中断的回复（resume 时提供）。

    Returns:
        ExecuteResult，包含执行结果或中断信息。
    """
    # 构建 SkillContext
    ctx: SkillContext = SkillContext(
        state=dict(checkpoint.state) if checkpoint else {},
        deps=deps,
        _answered=dict(checkpoint.answered) if checkpoint else {},
        _pending_interrupt_id=checkpoint.pending_interrupt_id if checkpoint else None,
        _resume_reply=resume_reply,
    )

    is_resume: bool = checkpoint is not None and resume_reply is not None
    logger.info(
        "执行技能脚本: skill=%s, resume=%s, pending=%s",
        script.name, is_resume,
        checkpoint.pending_interrupt_id if checkpoint else "none",
    )

    try:
        output: str = await script.run(ctx)
        logger.info("技能脚本正常完成: skill=%s", script.name)
        return ExecuteResult(output=output, interrupted=False)

    except SkillInterrupt as e:
        logger.info(
            "技能脚本中断: skill=%s, interrupt_id=%s",
            script.name, e.interrupt_id,
        )

        # 构建 checkpoint
        new_checkpoint: SkillCheckpoint = SkillCheckpoint(
            skill_name=script.name,
            state=e.state,
            answered=e.answered,
            pending_interrupt_id=e.interrupt_id,
            pending_data=e.data,
        )

        # 发 INTERRUPT 事件给前端
        if deps.emitter is not None:
            await deps.emitter.emit(EventModel(
                session_id=deps.session_id,
                request_id=deps.request_id,
                type=EventType.INTERRUPT,
                data={
                    "type": e.data.get("type", "skill_script"),
                    "question": e.data.get("question", ""),
                    "skill_name": script.name,
                    "interrupt_id": e.interrupt_id,
                    **{k: v for k, v in e.data.items() if k not in ("type", "question")},
                },
            ))

        return ExecuteResult(
            output=None,
            interrupted=True,
            checkpoint=new_checkpoint,
        )
