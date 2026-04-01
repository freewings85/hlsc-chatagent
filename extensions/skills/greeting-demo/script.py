"""greeting-demo 技能脚本：演示 skill script interrupt 机制。

流程：
1. 用户触发 skill（如说"你好"）
2. ctx.interrupt() 挂起协程，等待用户回复名字
3. 用户回复名字 → 协程恢复，用名字打招呼并说再见
"""

from __future__ import annotations

from agent_sdk._agent.skills.script import SkillContext, SkillScript


class GreetingDemoScript(SkillScript):
    """问候演示脚本。"""

    name: str = "greeting-demo"

    async def run(self, ctx: SkillContext) -> str:
        """执行问候流程。"""
        # 挂起等待用户回复名字（底层复用 call_interrupt）
        user_name: str = await ctx.interrupt({
            "type": "input",
            "question": "你好！请问怎么称呼你？",
        })

        ctx.state["user_name"] = user_name
        return f"很高兴认识你，{user_name}！再见！"
