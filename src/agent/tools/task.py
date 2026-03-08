"""Task 工具：启动子 agent 执行复杂任务。

参考 Claude Code 的 Agent/Task tool 设计：
- 主 agent 调用 Task 工具，指定 prompt 和 subagent_type
- Task 工具内部创建新的 Agent 实例（独立上下文）
- 子 agent 完成任务后返回结果文本给主 agent
- 子 agent 不推送 SSE 事件（结果只回给主 agent）

支持的子 agent 类型：
- plan: 只读，探索代码库并设计实现方案
- explore: 只读，快速搜索和分析代码
- general: 全能力，可读写文件（默认）
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets._dynamic import DynamicToolset

from src.agent.deps import AgentDeps
from src.agent.model import create_model

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 子 agent 类型定义
# --------------------------------------------------------------------------- #

# 只读工具列表（plan / explore 使用）
_READ_ONLY_TOOLS: list[str] = ["read", "glob", "grep", "bash"]

# 子 agent 可用工具集（按类型）
_SUBAGENT_TOOLS: dict[str, list[str]] = {
    "plan": _READ_ONLY_TOOLS,
    "explore": _READ_ONLY_TOOLS,
    "general": ["read", "edit", "write", "glob", "grep", "bash"],
}

# --------------------------------------------------------------------------- #
# 子 agent System Prompt
# --------------------------------------------------------------------------- #

_PLAN_SYSTEM_PROMPT = """\
你是一个软件架构师和规划专家。你的角色是探索代码库并设计实现方案。

=== 关键：只读模式 — 禁止修改文件 ===
这是一个只读规划任务。你被严格禁止：
- 创建新文件（不能使用 write、touch 或任何文件创建操作）
- 修改现有文件（不能使用 edit 操作）
- 删除文件
- 使用重定向操作符写入文件

你的角色仅限于探索代码库和设计实现方案。

## 工作流程

1. **理解需求**：聚焦提供的需求
2. **充分探索**：
   - 使用 glob、grep、read 查找现有模式和约定
   - 理解当前架构
   - 找到相似功能作为参考
   - 追踪相关代码路径
   - bash 仅用于只读操作（ls, git status, git log, git diff）
3. **设计方案**：
   - 基于探索结果创建实现方案
   - 考虑权衡和架构决策
   - 遵循现有模式
4. **详述计划**：
   - 提供分步实现策略
   - 标识依赖和执行顺序
   - 预判潜在挑战

## 输出要求

在响应末尾包含：

### 关键文件
列出实现此方案最关键的 3-5 个文件：
- path/to/file1 - [原因]
- path/to/file2 - [原因]

记住：你只能探索和规划。不能写入、编辑或修改任何文件。
"""

_EXPLORE_SYSTEM_PROMPT = """\
你是一个代码搜索专家。你擅长快速导航和探索代码库。

=== 关键：只读模式 — 禁止修改文件 ===
这是一个只读搜索任务。你被严格禁止创建、修改或删除文件。

你的优势：
- 使用 glob 模式快速查找文件
- 使用正则表达式搜索代码内容
- 阅读和分析文件内容

工作准则：
- 用 glob 做广泛文件模式匹配
- 用 grep 搜索文件内容
- 用 read 读取已知路径的文件
- bash 仅用于只读操作（ls, git status, git log, git diff）
- 尽可能并行调用多个工具以提高效率
- 返回文件路径时使用绝对路径

高效完成搜索请求并清晰报告发现。
"""

_GENERAL_SYSTEM_PROMPT = """\
你是一个子 agent，被主 agent 分配了一个具体任务。\
根据分配的任务使用可用工具完成工作。完成后提供详细的结果报告。

你的优势：
- 搜索代码、配置和模式
- 分析多个文件以理解系统架构
- 执行多步研究任务
- 读写文件完成实现任务

工作准则：
- 优先编辑现有文件而非创建新文件
- 不主动创建文档文件
- 结果中包含相关文件路径（使用绝对路径）
- 完成任务后提供详细的完成报告
"""

_SUBAGENT_PROMPTS: dict[str, str] = {
    "plan": _PLAN_SYSTEM_PROMPT,
    "explore": _EXPLORE_SYSTEM_PROMPT,
    "general": _GENERAL_SYSTEM_PROMPT,
}


# --------------------------------------------------------------------------- #
# 子 agent 工具集构建
# --------------------------------------------------------------------------- #

def _build_subagent_get_tools(tool_names: list[str], parent_deps: AgentDeps):
    """构建子 agent 的 get_tools 函数，从父 deps 的 tool_map 中筛选工具。"""
    from pydantic_ai import Tool
    from pydantic_ai.toolsets.function import FunctionToolset

    def get_tools(ctx: RunContext[AgentDeps]) -> FunctionToolset:
        toolset = FunctionToolset()
        for name in tool_names:
            func = parent_deps.tool_map.get(name)
            if func is not None:
                toolset.add_tool(Tool(func, name=name))
        return toolset

    return get_tools


# --------------------------------------------------------------------------- #
# 子 agent 日志
# --------------------------------------------------------------------------- #

def _log_subagent_trace(
    messages: list,
    subagent_type: str,
    description: str,
) -> None:
    """记录子 agent 的完整对话轨迹到 session execution.log。"""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )
    from src.utils.session_logger import log_info

    lines: list[str] = [f"[SUBAGENT_TRACE] type={subagent_type}, desc={description}"]

    for i, msg in enumerate(messages):
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, SystemPromptPart):
                    lines.append(f"  [{i}] system ({len(part.content)} chars)")
                elif isinstance(part, UserPromptPart):
                    content = part.content if isinstance(part.content, str) else str(part.content)
                    lines.append(f"  [{i}] user: {content[:200]}")
                elif isinstance(part, ToolReturnPart):
                    content = part.content if isinstance(part.content, str) else str(part.content)
                    lines.append(f"  [{i}] tool_return({part.tool_name}): {content[:200]}")
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    lines.append(f"  [{i}] assistant: {part.content[:200]}")
                elif isinstance(part, ToolCallPart):
                    args = part.args if isinstance(part.args, str) else str(part.args)
                    lines.append(f"  [{i}] tool_call: {part.tool_name}({args[:150]})")

    log_info("\n".join(lines))


# --------------------------------------------------------------------------- #
# Task 工具实现
# --------------------------------------------------------------------------- #

async def task(
    ctx: RunContext[AgentDeps],
    description: str,
    prompt: str,
    subagent_type: str = "plan",
) -> str:
    """Launch a read-only sub-agent for research or planning.

    The sub-agent runs in an independent context window. It can search and
    analyze files but CANNOT create or modify files. All file writes must
    be done by you directly (using write, edit, bash), not delegated here.

    Args:
        description: A short (3-5 word) summary of the task for logging.
        prompt: Detailed task description for the sub-agent. Must contain ALL
            necessary context since the sub-agent cannot see the main conversation.
        subagent_type: Type of sub-agent to launch.
            "plan" — analyze requirements and design a step-by-step plan.
            "explore" — search and analyze existing files.

    Returns:
        The sub-agent's result text. The result is NOT visible to the user —
        you must relay it back.
    """
    from src.utils.session_logger import log_info

    # 校验子 agent 类型
    if subagent_type not in _SUBAGENT_PROMPTS:
        return f"错误：不支持的 subagent_type '{subagent_type}'，可选值：{list(_SUBAGENT_PROMPTS.keys())}"

    log_info(f"[TASK_START] type={subagent_type}, description={description}")

    try:
        # 构建子 agent（独立实例，独立上下文）
        system_prompt = _SUBAGENT_PROMPTS[subagent_type]
        tool_names = _SUBAGENT_TOOLS[subagent_type]
        sub_get_tools = _build_subagent_get_tools(tool_names, ctx.deps)

        model = create_model()
        sub_agent: Agent[AgentDeps, str] = Agent(
            model,
            deps_type=AgentDeps,
            system_prompt=system_prompt,
            toolsets=[DynamicToolset(sub_get_tools, per_run_step=True)],
        )

        # 子 agent 使用独立的 deps（共享 backend 和 file_state_tracker）
        sub_deps = AgentDeps(
            session_id=ctx.deps.session_id,
            user_id=ctx.deps.user_id,
            available_tools=tool_names,
            tool_map=ctx.deps.tool_map,
            backend=ctx.deps.backend,
            file_state_tracker=ctx.deps.file_state_tracker,
        )

        # 运行子 agent（Pydantic AI 自动处理工具调用循环）
        result = await sub_agent.run(prompt, deps=sub_deps)

        # 记录子 agent 的完整对话轨迹（用于调试）
        _log_subagent_trace(result.all_messages(), subagent_type, description)

        log_info(
            f"[TASK_END] type={subagent_type}, description={description}, "
            f"output_length={len(result.output)}"
        )
        return result.output

    except Exception as exc:
        error_msg = f"子 agent 执行失败 (type={subagent_type}): {exc}"
        logger.error(error_msg, exc_info=True)
        log_info(f"[TASK_ERROR] type={subagent_type}, description={description}, error={exc}")
        return error_msg
