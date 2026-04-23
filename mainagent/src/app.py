"""HLSC 主 Agent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from typing import Any

from agent_sdk import Agent, AgentApp, AgentAppConfig, ProfileTriggerHook, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.pre_run_hook import PreRunHook
from src.hlsc_context import HlscContextFormatter
from src.prompt_loader import create_main_prompt_loader

# common 工具
from hlsc.tools.search_shops import search_shops
from hlsc.tools.list_user_cars import list_user_cars
from hlsc.tools.collect_user_car_info import collect_user_car_info
from hlsc.tools.collect_vehicle_info import collect_vehicle_info
from hlsc.tools.collect_insurance_info import collect_insurance_info
from hlsc.tools.collect_user_location import collect_user_location
from hlsc.tools.delegate import delegate
from hlsc.tools.update_workflow_state import update_workflow_state
from hlsc.tools.submit_shop_search_criteria import submit_shop_search_criteria
from hlsc.tools.submit_coupon_search_criteria import submit_coupon_search_criteria

# 分类与匹配
from hlsc.tools.classify_project import classify_project
from hlsc.tools.search_coupon import search_coupon
from hlsc.tools.match_project import match_project

# 下单
from hlsc.tools.confirm_booking import confirm_booking

# 优惠领取
from hlsc.tools.claim_coupon import claim_coupon

# 复杂查询
from hlsc.tools.call_query_codingagent import call_query_codingagent



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
        "collect_user_car_info": collect_user_car_info,
        "collect_vehicle_info": collect_vehicle_info,
        "collect_insurance_info": collect_insurance_info,
        # 位置
        "collect_user_location": collect_user_location,
        # 商户
        "search_shops": search_shops,
        # 优惠查询与申领
        "search_coupon": search_coupon,
        "claim_coupon": claim_coupon,
        # 下单
        "confirm_booking": confirm_booking,
        # 编排模式通用登记工具（旧 scene 兜底，仍没迁到 Validate-Loop 的 insurance 在用）
        "update_workflow_state": update_workflow_state,
        # 搜商户场景专用：登记 shop_search_info，系统自动搜并回结果
        "submit_shop_search_criteria": submit_shop_search_criteria,
        # 搜优惠场景专用：登记 activity_search_info + shop_search_info，联合查询
        "submit_coupon_search_criteria": submit_coupon_search_criteria,
        # 复杂查询
        "call_query_codingagent": call_query_codingagent,
        # 商户联系单
        # orchestrator 委派
        "delegate": delegate,
    }

    formatter: HlscContextFormatter = HlscContextFormatter()

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map, exclude=["write", "edit"]),
        context_formatter=formatter,
        before_agent_run_hook=PreRunHook(),
        after_run_hooks=[ProfileTriggerHook()],
    )

    agent_app: AgentApp = AgentApp(
        agent,
        AgentAppConfig(
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
        ),
    )

    # ── 注册 /classify 端点（mainagent 独有，供 orchestrator 调用）──
    from src.classify_router import router as classify_router, set_memory_factory
    set_memory_factory(agent._build_memory_service)
    agent_app.app.include_router(classify_router)

    # ── 注册 /plan 端点（同 /classify 模式：同步 HTTP，复用 agent 的 memory service 拿历史）──
    from src.plan_router import router as plan_router, set_memory_factory as set_plan_memory_factory
    set_plan_memory_factory(agent._build_memory_service)
    agent_app.app.include_router(plan_router)

    # ── 按 agents.yaml 预构建 per-agent-type Agent 实例，注册 /chat/stream2 ──
    from pathlib import Path
    from src.agent_registry import AGENT_REGISTRY, load_default_registry
    from src.chat_stream2_router import router as chat_stream2_router, set_agent_instances
    from src.spec_prompt_loader import SpecPromptLoader

    load_default_registry()
    templates_root: Path = Path(__file__).resolve().parent.parent / "prompts" / "templates"

    agent_instances: dict[str, Agent] = {}
    for name, spec in AGENT_REGISTRY.items():
        missing: list[str] = [t for t in spec.tools if t not in tool_map]
        if missing:
            raise ValueError(
                f"agents.yaml {name!r} 的 tools 里有未注册的 tool: {missing}"
            )
        spec_tool_map: dict[str, Any] = {t: tool_map[t] for t in spec.tools}

        async def _stream2_before_run(
            user_id: str,
            session_id: str,
            deps: Any,
            message: str,
            *,
            _skills: tuple[str, ...] = spec.skills,
        ) -> None:
            """/chat/stream2 不走 PreRunHook，这里补上 per-agent skills 约束。"""
            deps.allowed_skills = list(_skills) if _skills else []

        # /chat/stream2 path 不走 PreRunHook —— AgentSpec 已承载 prompt/tools/memory
        # 策略，PreRunHook 是给 /chat/stream 旧路径从 stage_config.yaml 加 scene 配的
        # skills_enabled 按 spec.skills 是否非空来定——严格按 agents.yaml 走，
        # 没列 skills 的 agent 不会被 SDK 自动塞 "Skill" 工具
        agent_instances[name] = Agent(
            prompt_loader=SpecPromptLoader(spec, templates_root),
            tools=ToolConfig(manual=spec_tool_map) if spec_tool_map else None,
            context_formatter=formatter,
            after_run_hooks=[ProfileTriggerHook()],
            before_agent_run_hook=_stream2_before_run,
            agent_name=name,
            skills_enabled=bool(spec.skills),
        )

    set_agent_instances(agent_instances)
    agent_app.app.include_router(chat_stream2_router)

    return agent_app
