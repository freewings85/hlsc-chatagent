"""MainAgent 工具：更新业务流程状态树。

MainAgent 在完成节点、跳过节点、展开子任务或切换焦点时调用此工具，
将最新状态树持久化到 session 目录下的 state_tree.md 文件。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.state_tree_service import state_tree_service


def _get_session_dir(deps: AgentDeps) -> Path:
    """获取当前 session 的存储目录。"""
    inner_dir: str = os.getenv("INNER_STORAGE_DIR", "data/inner")
    return Path(inner_dir) / deps.user_id / "sessions" / deps.session_id


async def update_state_tree(
    ctx: RunContext[AgentDeps],
    content: Annotated[str, Field(
        description="更新后的完整状态树（缩进 Markdown 格式）。"
        "使用 [完成]/[进行中]/[跳过]/[ ] 标记状态，← 当前 标记焦点，→ 记录产出。"
    )],
) -> str:
    """保存业务进度。用户确认、完成步骤、做出选择后必须立即调用，否则进度丢失。

    调用时机（满足任一即调用）：
    - 用户确认了项目或选项 → 标记 [完成] + → 产出
    - 完成或跳过某节点 → 标记 [完成]/[跳过]
    - 开始处理新节点 → 标记 [进行中] + ← 当前

    content 参数：传入更新后的完整状态树（缩进 Markdown 格式）。
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_state_tree", sid, rid, {"content_length": len(content)})

    session_dir: Path = _get_session_dir(ctx.deps)
    state_tree_service.write(session_dir, content)

    log_tool_end("update_state_tree", sid, rid, {"session_dir": str(session_dir)})
    return "状态树已更新"
