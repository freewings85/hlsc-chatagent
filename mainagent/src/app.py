"""HLSC 主 Agent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from typing import Any

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.hlsc_context import HlscContextFormatter, HlscRequestContext, SceneInfo
from src.prompt_loader import create_main_prompt_loader

# subagent 调用工具
from src.tools.call_code_agent import call_code_agent
# from src.tools.call_demo_price_finder import call_demo_price_finder
from src.tools.call_diagnose_agent import call_diagnose_agent
from src.tools.call_recommend_project import call_recommend_project

# extensions 业务工具
from hlsc.tools.fuzzy_match_car_info import fuzzy_match_car_info
from hlsc.tools.list_user_cars import list_user_cars
from hlsc.tools.ask_user_car_info import ask_user_car_info
from hlsc.tools.fuzzy_match_location import fuzzy_match_location
from hlsc.tools.ask_user_location import ask_user_location
from hlsc.tools.match_project import match_project


async def _before_agent_run_hook(
    user_id: str,
    session_id: str,
    deps: Any,
    message: str,
) -> None:
    """运行前场景钩子（占位实现）：当前固定判定为 clarify。"""
    request_id = getattr(deps, "request_id", "")
    scene_info = SceneInfo(
        scene_type="clarify",
        confidence=1.0,
        request_id=request_id,
    )

    ctx = getattr(deps, "request_context", None)
    if isinstance(ctx, dict):
        ctx["scene_info"] = scene_info.model_dump()
        return
    if isinstance(ctx, HlscRequestContext):
        ctx.scene_info = scene_info
        return
    if ctx is None:
        deps.request_context = HlscRequestContext(scene_info=scene_info)
        return
    # 兼容其他 RequestContext 对象
    try:
        setattr(ctx, "scene_info", scene_info)
    except Exception:
        deps.request_context = HlscRequestContext(scene_info=scene_info)


def create_agent_app() -> AgentApp:
    """创建 HLSC 主 AgentApp"""
    prompt_loader = create_main_prompt_loader()

    # SDK 内置工具 + subagent 调用 + extensions 业务工具
    tool_map = {
        **create_default_tool_map(),
        # subagent 调用
        "call_code_agent": call_code_agent,
        # "call_demo_price_finder": call_demo_price_finder,
        "call_diagnose_agent": call_diagnose_agent,
        "call_recommend_project": call_recommend_project,
        # 车辆信息
        "fuzzy_match_car_info": fuzzy_match_car_info,
        "list_user_cars": list_user_cars,
        "ask_user_car_info": ask_user_car_info,
        # 位置信息
        "fuzzy_match_location": fuzzy_match_location,
        "ask_user_location": ask_user_location,
        # 项目 & 报价
        "match_project": match_project,
    }

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map, exclude=["write", "edit"]),
        context_formatter=HlscContextFormatter(),
        before_agent_run_hook=_before_agent_run_hook,
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
        ),
    )
