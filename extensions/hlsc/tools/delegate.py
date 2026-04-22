"""delegate 工具：orchestrator 通过此工具将任务委派给专业 agent 执行。

内部创建临时 Agent 实例，加载目标场景的 system prompt + tools，
以 context + task 作为输入静默运行，返回文本结果。
"""

from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext, Tool
from pydantic_ai.toolsets.function import FunctionToolset

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.model import create_model
from agent_sdk._agent.toolset import wrap_tool_safe
from hlsc.tools.prompt_loader import load_tool_prompt
from src.scene_config import registry

logger: logging.Logger = logging.getLogger(__name__)

# 可委派的场景白名单（不能 delegate 给 guide / orchestrator）
_DELEGATABLE_SCENES: set[str] = {"searchshops", "searchcoupons"}
_REMOVED_SCENES: set[str] = {"platform", "insurance"}


def _build_scene_system_prompt(scene_config: dict[str, Any]) -> str:
    """根据场景配置的 prompt_parts + agent_md 拼接完整 system prompt。"""
    # prompt_parts 和 agent_md 的文件路径相对于 templates/ 目录
    templates_dir: Path = Path(__file__).resolve().parents[3] / "mainagent" / "prompts" / "templates"

    parts: list[str] = []

    # 拼接 prompt_parts
    prompt_part_files: list[str] = scene_config.get("prompt_parts", [])
    for filename in prompt_part_files:
        filepath: Path = templates_dir / filename
        if filepath.exists():
            content: str = filepath.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)

    # 拼接 agent_md（支持 list 或 str，兼容老格式）
    raw_agent_md: Any = scene_config.get("agent_md", [])
    agent_md_files: list[str] = (
        raw_agent_md if isinstance(raw_agent_md, list)
        else ([raw_agent_md] if raw_agent_md else [])
    )
    for agent_md_file in agent_md_files:
        agent_md_path: Path = templates_dir / agent_md_file
        if agent_md_path.exists():
            agent_md_content: str = agent_md_path.read_text(encoding="utf-8").strip()
            if agent_md_content:
                parts.append(agent_md_content)

    return "\n\n".join(parts)


def _build_scene_toolset(
    scene_config: dict[str, Any],
    parent_deps: AgentDeps,
) -> dict[str, Any]:
    """从父 agent 的 tool_map 中筛选目标场景的工具。"""
    tool_names: list[str] = scene_config.get("tools", [])
    sub_tool_map: dict[str, Any] = {}
    for name in tool_names:
        func: Any = parent_deps.tool_map.get(name)
        if func is not None:
            sub_tool_map[name] = func
    return sub_tool_map


async def delegate(
    ctx: RunContext[AgentDeps],
    agent_name: Annotated[str, Field(description="委派给哪个 agent：searchshops/searchcoupons")],
    task: Annotated[str, Field(description="具体任务描述")],
    context: Annotated[str, Field(description="当前已知的上下文信息摘要")] = "",
) -> str:
    """委派任务给专业 agent 执行。你是协调者，不直接执行业务，而是判断用户意图后分配给最合适的 agent。

    可委派的 agent：
    - searchshops：找商户、对比商户
    - searchcoupons：找优惠、省钱方案

    委派时必须提供：
    - agent_name：分配给谁
    - task：具体要做什么
    - context：当前已知信息的摘要（项目、车型、位置等已确认的信息）

    委派后会返回该 agent 的执行结果，你可以直接使用这个结果回复用户，或者继续委派给其他 agent。
    """
    # 校验 agent_name
    if agent_name in _REMOVED_SCENES:
        raise ValueError(f"场景 '{agent_name}' 已下线，禁止再委派")
    if agent_name not in _DELEGATABLE_SCENES:
        return f"错误：不能委派给 '{agent_name}'，可委派的 agent：{sorted(_DELEGATABLE_SCENES)}"

    # 加载场景配置
    all_raw: dict[str, dict[str, Any]] = registry.get_all_raw()
    scene_config: dict[str, Any] | None = all_raw.get(agent_name)
    if scene_config is None:
        return f"错误：场景 '{agent_name}' 的配置不存在"

    logger.info("delegate: agent_name=%s, task=%s", agent_name, task[:80])

    try:
        result: str = await _run_delegate_agent(ctx, agent_name, scene_config, task, context)
        logger.info("delegate 完成: agent_name=%s, output_length=%d", agent_name, len(result))
        return result
    except Exception as exc:
        error_msg: str = f"delegate 执行失败 (agent={agent_name}): {exc}"
        logger.error(error_msg, exc_info=True)
        return error_msg


async def _run_delegate_agent(
    ctx: RunContext[AgentDeps],
    agent_name: str,
    scene_config: dict[str, Any],
    task: str,
    context: str,
) -> str:
    """创建临时 Agent 实例运行委派任务。"""
    from agent_sdk import Agent as SdkAgent, ToolConfig
    from agent_sdk.prompt_loader import StaticPromptLoader

    parent_deps: AgentDeps = ctx.deps

    # 1. 构建 system prompt
    system_prompt: str = _build_scene_system_prompt(scene_config)

    # 2. 构建工具集
    sub_tool_map: dict[str, Any] = _build_scene_toolset(scene_config, parent_deps)

    # 3. 创建临时 Agent
    model = create_model()
    sub_agent: SdkAgent = SdkAgent(
        prompt_loader=StaticPromptLoader(system_prompt),
        tools=ToolConfig(manual=sub_tool_map),
        model=model,
        agent_name=agent_name,
        max_iterations=20,
    )

    # 3.5 设置 skills 过滤（子 agent 自动加载 skill_registry，这里限制可用范围）
    scene_skills: list[str] = scene_config.get("skills", [])

    async def _set_allowed_skills(
        user_id: str, session_id: str, deps: Any = None, message: str | None = None
    ) -> None:
        """子 agent 的 before_run hook：设置 allowed_skills。"""
        if deps is not None:
            deps.allowed_skills = scene_skills

    sub_agent._before_agent_run_hook = _set_allowed_skills

    # 4. 构建用户消息（context + task）
    user_message: str = task
    if context:
        user_message = f"上下文：{context}\n\n任务：{task}"

    # 5. 共享父 emitter
    if parent_deps.emitter is not None:
        emitter = parent_deps.emitter
    else:
        from agent_sdk._event.event_emitter import EventEmitter
        dummy_queue: asyncio.Queue[Any] = asyncio.Queue()
        emitter = EventEmitter(dummy_queue)

    # 6. 运行子 agent（静默模式，不流式、不 interrupt）
    agent_id: str = f"delegate-{agent_name}-{_uuid.uuid4().hex[:8]}"

    # 获取当前 delegate tool call 的 ID，子 agent 的事件将携带此 ID 供前端分区渲染
    delegate_tool_call_id: str = getattr(ctx, "tool_call_id", None) or ""

    result: str | None = await sub_agent.run(
        message=user_message,
        user_id=parent_deps.user_id,
        session_id=parent_deps.session_id,
        emitter=emitter,
        temporal_client=parent_deps.temporal_client,
        request_context=parent_deps.request_context,
        fs_tools_backend=parent_deps.fs_tools_backend,
        is_sub_agent=True,
        message_history=[],
        transcript_session_id=f"{parent_deps.session_id}/delegates/{agent_id}",
        session_state=parent_deps.session_state,
        parent_tool_call_id=delegate_tool_call_id,
        request_id=parent_deps.request_id,
        parent_request_id=parent_deps.request_id,
    )
    return result or ""
