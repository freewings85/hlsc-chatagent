"""greeting-demo 技能脚本：演示 skill script interrupt 机制。

流程：
1. 用户触发 skill（如说"你好"）
2. script interrupt 询问用户名字 → 终止当前 run，等待回复
3. 用户回复名字 → resume，script 用名字打招呼并说再见
"""

from __future__ import annotations

from agent_sdk._agent.skills.script import SkillContext, SkillScript


class GreetingDemoScript(SkillScript):
    """问候演示脚本。"""

    name: str = "greeting-demo"

    async def run(self, ctx: SkillContext) -> str:
        """执行问候流程。"""
        # 中断点：询问用户名字
        # 首次执行：抛 SkillInterrupt → 终止 run → 前端显示问题
        # resume 后：直接返回用户回复的名字
        user_name: str = await ctx.interrupt("ask_name", {
            "type": "input",
            "question": "你好！请问怎么称呼你？",
        })

        ctx.state["user_name"] = user_name
        return f"很高兴认识你，{user_name}！再见！👋"
