"""HLSC 主 Agent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ProfileTriggerHook, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.hlsc_context import HlscContextFormatter
from src.prompt_loader import create_main_prompt_loader


# subagent 调用工具
from src.tools.call_code_agent import call_code_agent
from src.tools.call_demo_price_finder import call_demo_price_finder
from hlsc.tools.call_recommend_project import call_recommend_project

# extensions 业务工具
from hlsc.tools.get_representative_car_model import get_representative_car_model
from hlsc.tools.list_user_cars import list_user_cars
from hlsc.tools.ask_user_car_info import ask_user_car_info
from hlsc.tools.geocode_location import geocode_location
from hlsc.tools.ask_user_location import ask_user_location
from hlsc.tools.match_project import match_project
from hlsc.tools.get_project_price import get_project_price
from hlsc.tools.get_visited_shops import get_visited_shops

# 新版业务工具（stub，待实现）
from hlsc.tools.knowledge_base_search import knowledge_base_search
from hlsc.tools.search_nearby_shops import search_nearby_shops
from hlsc.tools.invite_merchant import invite_merchant
from hlsc.tools.check_coupon_eligibility import check_coupon_eligibility
from hlsc.tools.purchase_coupon import purchase_coupon
from hlsc.tools.create_booking_order import create_booking_order
from hlsc.tools.push_order_to_merchant import push_order_to_merchant
from hlsc.tools.create_bidding_order import create_bidding_order
from hlsc.tools.handle_bidding_timeout import handle_bidding_timeout
from hlsc.tools.submit_execution_request import submit_execution_request
from hlsc.tools.query_execution_status import query_execution_status
from hlsc.tools.tire_image_recognize import tire_image_recognize




def create_agent_app() -> AgentApp:
    """创建 HLSC 主 AgentApp"""
    prompt_loader = create_main_prompt_loader()

    # SDK 内置工具 + subagent 调用 + extensions 业务工具
    tool_map = {
        **create_default_tool_map(),
        # subagent 调用
        "call_code_agent": call_code_agent,
        # "call_demo_price_finder": call_demo_price_finder,
        "call_recommend_project": call_recommend_project,
        # 车辆信息
        "get_representative_car_model": get_representative_car_model,
        "list_user_cars": list_user_cars,
        "ask_user_car_info": ask_user_car_info,
        # 位置信息
        "geocode_location": geocode_location,
        "ask_user_location": ask_user_location,
        # 项目 & 报价
        "match_project": match_project,
        "get_project_price": get_project_price,
        # 商户查询
        "get_visited_shops": get_visited_shops,
        # 新版业务工具（stub，待实现真实逻辑）
        "knowledge_base_search": knowledge_base_search,
        "search_nearby_shops": search_nearby_shops,
        "invite_merchant": invite_merchant,
        "check_coupon_eligibility": check_coupon_eligibility,
        "purchase_coupon": purchase_coupon,
        "create_booking_order": create_booking_order,
        "push_order_to_merchant": push_order_to_merchant,
        "create_bidding_order": create_bidding_order,
        "handle_bidding_timeout": handle_bidding_timeout,
        "submit_execution_request": submit_execution_request,
        "query_execution_status": query_execution_status,
        "tire_image_recognize": tire_image_recognize,
    }

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map, exclude=["write", "edit"]),
        context_formatter=HlscContextFormatter(),
        after_run_hooks=[ProfileTriggerHook()],
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
        ),
    )
