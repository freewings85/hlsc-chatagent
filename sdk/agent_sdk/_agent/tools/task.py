"""Task 工具：启动子 agent 执行复杂任务。

参考 Claude Code 的 Agent/Task tool 设计：
- 主 agent 调用 Task 工具，指定 prompt 和 subagent_type
- Task 工具内部创建新的 Agent 实例（独立上下文）
- 子 agent 通过 run_agent_loop 引擎运行（与主 agent 共享同一套核心循环）
- 子 agent 的事件通过父 agent 的 emitter 推送（agent_name 区分）

工具继承策略（参考 Claude Code）：
- subagent 继承父 agent 的所有工具，**排除** task（防递归）和 Skill（高层意图）
- MCP 工具等动态注册的工具也会被继承
- Skills 只在主 agent 层面触发和执行

支持的子 agent 类型：
- plan: 只读，探索代码库并设计实现方案
- general: 全能力，可读写文件（默认）
"""

from __future__ import annotations

import logging
import uuid as _uuid

from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets._dynamic import DynamicToolset

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.model import create_model

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 子 agent 工具排除列表
# --------------------------------------------------------------------------- #

# 子 agent 不能使用的工具（防递归 + 高层意图隔离）
_EXCLUDED_TOOLS: set[str] = {"task", "Skill"}

# plan 模式额外排除的写操作工具
_PLAN_EXCLUDED_TOOLS: set[str] = {"edit", "write"}

# --------------------------------------------------------------------------- #
# 子 agent System Prompt
# --------------------------------------------------------------------------- #

_PLAN_SYSTEM_PROMPT = """\
你是一个只读分析规划 agent。根据分配的任务进行信息收集和分析，不多做也不少做。

=== 只读模式 — 禁止修改文件 ===
你只能使用 read、glob、grep、bash（仅只读命令）。禁止创建、修改或删除任何文件。

## 工作流程

1. **理解需求**：聚焦分配的任务目标
2. **信息收集**：
   - 使用 glob、grep、read 查找相关信息和数据
   - bash 仅用于只读操作（ls, curl 等）
3. **分析整理**：
   - 基于收集的信息进行分析
   - 识别关键点和潜在风险
   - 提出可行方案
4. **输出报告**：
   - 提供结构化的分析结果
   - 标明信息来源和依据

注意事项：
- bash 每次调用是独立进程，工作目录会重置，请始终使用绝对路径。
- 返回结果中引用文件时必须使用绝对路径。
"""

_GENERAL_SYSTEM_PROMPT = """\
你是一个子 agent，被主 agent 分配了一个具体任务。\
使用可用工具完成分配的任务，不多做也不少做。完成后提供详细的结果报告。

注意事项：
- bash 每次调用是独立进程，工作目录会重置，请始终使用绝对路径。
- 返回结果中引用文件时必须使用绝对路径。
- 优先编辑现有文件而非创建新文件。
"""

_SUBAGENT_PROMPTS: dict[str, str] = {
    "plan": _PLAN_SYSTEM_PROMPT,
    "general": _GENERAL_SYSTEM_PROMPT,
}

_SUBAGENT_MAX_TURNS: dict[str, int] = {
    "plan": 20,
    "general": 25,
}


# --------------------------------------------------------------------------- #
# 子 agent 工具集构建
# --------------------------------------------------------------------------- #

def _resolve_subagent_tools(
    parent_deps: AgentDeps,
    subagent_type: str,
) -> list[str]:
    """从父 agent 的 tool_map 动态解析子 agent 可用工具列表。

    策略：继承父 agent 所有工具，排除 task/Skill；plan 额外排除写操作工具。
    """
    excluded = _EXCLUDED_TOOLS.copy()
    if subagent_type == "plan":
        excluded |= _PLAN_EXCLUDED_TOOLS

    return [name for name in parent_deps.tool_map if name not in excluded]


def _build_subagent_get_tools(tool_names: list[str], parent_deps: AgentDeps):
    """构建子 agent 的 get_tools 函数，从父 deps 的 tool_map 中筛选工具。"""
    from pydantic_ai import Tool
    from pydantic_ai.toolsets.function import FunctionToolset

    from agent_sdk._agent.toolset import wrap_tool_safe

    def get_tools(ctx: RunContext[AgentDeps]) -> FunctionToolset:
        toolset = FunctionToolset()
        for name in tool_names:
            func = parent_deps.tool_map.get(name)
            if func is not None:
                toolset.add_tool(Tool(wrap_tool_safe(func), name=name))
        return toolset

    return get_tools


# --------------------------------------------------------------------------- #
# Task 工具实现
# --------------------------------------------------------------------------- #

async def task(
    ctx: RunContext[AgentDeps],
    description: str,
    prompt: str,
    subagent_type: str = "general",
) -> str:
    """Launch a sub-agent to handle complex, multi-step tasks autonomously.

    The sub-agent runs in an independent context window with its own tool set,
    using the same core engine as the main agent (streaming, compact, transcript).
    It inherits all parent tools except task (no recursion) and Skill (main
    agent only). Plan mode additionally excludes write/edit tools.

    Args:
        description: A short (3-5 word) summary of the task for logging.
        prompt: Detailed task description for the sub-agent. Must contain ALL
            necessary context since the sub-agent cannot see the main session.
        subagent_type: Type of sub-agent to launch.
            "plan" — read-only; analyze requirements and design a step-by-step plan.
            "general" — full capability; can read, write, and execute commands.

    Returns:
        The sub-agent's result text. The result is NOT visible to the user —
        you must relay it back.
    """
    from agent_sdk._utils.session_logger import log_info

    # 校验子 agent 类型
    if subagent_type not in _SUBAGENT_PROMPTS:
        return f"错误：不支持的 subagent_type '{subagent_type}'，可选值：{list(_SUBAGENT_PROMPTS.keys())}"

    log_info(f"[TASK_START] type={subagent_type}, description={description}")

    try:
        result = await _run_sub_agent(ctx, description, prompt, subagent_type)
        log_info(
            f"[TASK_END] type={subagent_type}, description={description}, "
            f"output_length={len(result)}"
        )
        return result

    except Exception as exc:
        error_msg = f"子 agent 执行失败 (type={subagent_type}): {exc}"
        logger.error(error_msg, exc_info=True)
        log_info(f"[TASK_ERROR] type={subagent_type}, description={description}, error={exc}")
        return error_msg


async def _run_sub_agent(
    ctx: RunContext[AgentDeps],
    description: str,
    prompt: str,
    subagent_type: str,
) -> str:
    """创建子 Agent 实例并通过 Agent.run() 运行。"""
    from agent_sdk import Agent as SdkAgent, ToolConfig
    from agent_sdk.prompt_loader import StaticPromptLoader

    parent_deps = ctx.deps

    # 1. 构建子 agent 的工具集（从父 agent 继承，按 subagent_type 过滤）
    tool_names = _resolve_subagent_tools(parent_deps, subagent_type)
    sub_tool_map = {name: parent_deps.tool_map[name] for name in tool_names if name in parent_deps.tool_map}

    # 2. 创建 SDK Agent 实例（使用 create_model 以支持测试 mock）
    system_prompt = _SUBAGENT_PROMPTS[subagent_type]
    model = create_model()
    sub_agent = SdkAgent(
        prompt_loader=StaticPromptLoader(system_prompt),
        tools=ToolConfig(manual=sub_tool_map),
        model=model,
        agent_name=subagent_type,
        max_iterations=_SUBAGENT_MAX_TURNS.get(subagent_type, 25),
    )

    # 3. 共享父 emitter（子 agent 事件通过同一个 emitter 推送）
    import asyncio
    if parent_deps.emitter is not None:
        emitter = parent_deps.emitter
    else:
        from agent_sdk._event.event_emitter import EventEmitter
        dummy_queue: asyncio.Queue = asyncio.Queue()
        emitter = EventEmitter(dummy_queue)

    # 4. 运行子 agent
    # session_id 用父级（事件路由用），transcript 路径隔离到 subagents/ 子目录
    agent_id = f"{subagent_type}-{_uuid.uuid4().hex[:8]}"

    # 获取父工具调用 ID，子 agent 事件携带此字段，前端据此嵌套渲染
    parent_tool_call_id: str = getattr(ctx, "tool_call_id", None) or ""

    result = await sub_agent.run(
        message=prompt,
        user_id=parent_deps.user_id,
        session_id=parent_deps.session_id,
        emitter=emitter,
        temporal_client=parent_deps.temporal_client,
        fs_tools_backend=parent_deps.fs_tools_backend,
        is_sub_agent=True,
        message_history=[],  # fresh context，不加载历史
        transcript_session_id=f"{parent_deps.session_id}/subagents/{agent_id}",
        parent_tool_call_id=parent_tool_call_id,
    )
    return result or ""
