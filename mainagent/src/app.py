"""HLSC 主 Agent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ProfileTriggerHook, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.business_map_hook import StageHook
from src.hlsc_context import HlscContextFormatter
from src.prompt_loader import create_main_prompt_loader

# common 工具
from hlsc.tools.search_shops import search_shops
from hlsc.tools.list_user_cars import list_user_cars
from hlsc.tools.collect_car_info import collect_car_info
from hlsc.tools.delegate import delegate
from hlsc.tools.update_session_state import update_session_state

# 分类与匹配
from hlsc.tools.classify_project import classify_project
from hlsc.tools.search_coupon import search_coupon
from hlsc.tools.match_project import match_project

# 下单
from hlsc.tools.confirm_booking import confirm_booking

# 优惠申领
from hlsc.tools.book_coupon import book_coupon

# 复杂查询
from hlsc.tools.call_query_codingagent import call_query_codingagent

# 商户联系单
from hlsc.tools.create_contact_order import create_contact_order


def create_agent_app() -> AgentApp:
    """创建 HLSC 主 AgentApp"""
    prompt_loader = create_main_prompt_loader()

    # SDK 内置工具 + 业务工具
    tool_map = {
        **create_default_tool_map(),
        # 项目分类与匹配
        "classify_project": classify_project,
        "match_project": match_project,
        # 车辆信息
        "list_user_cars": list_user_cars,
        "collect_car_info": collect_car_info,
        # 商户
        "search_shops": search_shops,
        # 优惠查询与申领
        "search_coupon": search_coupon,
        "book_coupon": book_coupon,
        # 下单
        "confirm_booking": confirm_booking,
        # 会话状态
        "update_session_state": update_session_state,
        # 复杂查询
        "call_query_codingagent": call_query_codingagent,
        # 商户联系单
        "create_contact_order": create_contact_order,
        # orchestrator 委派
        "delegate": delegate,
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
