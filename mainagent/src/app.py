"""HLSC 主 Agent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ProfileTriggerHook, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.business_map_hook import StageHook
from src.hlsc_context import HlscContextFormatter
from src.prompt_loader import create_main_prompt_loader

# common 工具（S1+S2 共用）
from hlsc.tools.common.search_shops import search_shops
from hlsc.tools.s2.call_recommend_project import call_recommend_project
from hlsc.tools.common.list_user_cars import list_user_cars
from hlsc.tools.common.collect_car_info import collect_car_info
from hlsc.tools.common.collect_location import collect_location
from hlsc.tools.common.geocode_location import geocode_location

# S1 专属工具
from hlsc.tools.s1.classify_project import classify_project
from hlsc.tools.s1.proceed_to_booking import proceed_to_booking
from hlsc.tools.s1.search_coupon import search_coupon

# S2 专属工具
from hlsc.tools.s2.match_project import match_project
from hlsc.tools.s2.confirm_booking import confirm_booking
from hlsc.tools.s2.call_query_codingagent import call_query_codingagent
from hlsc.tools.s2.get_representative_car_model import get_representative_car_model


def create_agent_app() -> AgentApp:
    """创建 HLSC 主 AgentApp"""
    prompt_loader = create_main_prompt_loader()

    # SDK 内置工具 + subagent 调用 + extensions 业务工具
    tool_map = {
        **create_default_tool_map(),
        # 项目分类与匹配
        "classify_project": classify_project,
        "match_project": match_project,
        "call_recommend_project": call_recommend_project,
        # 车辆信息
        "get_representative_car_model": get_representative_car_model,
        "list_user_cars": list_user_cars,
        "collect_car_info": collect_car_info,
        # 位置
        "geocode_location": geocode_location,
        "collect_location": collect_location,
        # 商户
        "search_shops": search_shops,
        # 优惠查询
        "search_coupon": search_coupon,
        # 进入下单流程（S1 → S2 即时升级）
        "proceed_to_booking": proceed_to_booking,
        # 下单
        "confirm_booking": confirm_booking,
        # 复杂查询
        "call_query_codingagent": call_query_codingagent,
    }

    formatter: HlscContextFormatter = HlscContextFormatter()

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map, exclude=["write", "edit"]),
        context_formatter=formatter,
        before_agent_run_hook=StageHook(),
        after_run_hooks=[ProfileTriggerHook()],
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
        ),
    )
