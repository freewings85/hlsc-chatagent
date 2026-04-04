"""测试用 Agent 服务器。

自包含，不依赖 mainagent 的生产代码。
组装：mock tools + real extension tools + skills → Agent → AgentApp → HTTP server
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Annotated, Any

# 确保 extensions 和 sdk 可 import
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "extensions"))

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps


# ── Mock business tool ──

async def mock_get_car_price(
    ctx: RunContext[AgentDeps],
    car_model_id: Annotated[str, Field(description="车型 ID")],
    lat: Annotated[float, Field(description="纬度")],
    lng: Annotated[float, Field(description="经度")],
) -> str:
    """查询指定车型在指定位置附近的养车价格。

    需要 car_model_id 和 lat/lng 参数。
    如果 request_context 中有这些信息且用户没指定新的，直接使用。
    否则参考 confirm-car-info / confirm-location skill 获取。
    """
    from agent_sdk.logging import log_tool_start, log_tool_end
    sid = getattr(ctx.deps, "session_id", "?")
    rid = getattr(ctx.deps, "request_id", "?")
    log_tool_start("get_car_price", sid, rid, {"car_model_id": car_model_id, "lat": lat, "lng": lng})
    result = (
        f"车型 {car_model_id}（lat={lat}, lng={lng}）附近养车价格：\n"
        f"- 普洗：¥35\n- 精洗：¥120\n- 小保养：¥580\n- 大保养：¥1200"
    )
    log_tool_end("get_car_price", sid, rid, {"car_model_id": car_model_id})
    return result


def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8195)
    args = parser.parse_args()
    os.environ["SERVER_PORT"] = str(args.port)

    from agent_sdk._common.nacos import register_service
    register_service()

    from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
    from agent_sdk._agent.tools import create_default_tool_map
    from agent_sdk.prompt_loader import TemplatePromptLoader

    # Extension tools（真实 tool，service 层在无 URL 时会抛异常被 tool 捕获）
    from hlsc.tools.get_representative_car_model import get_representative_car_model
    from hlsc.tools.list_user_cars import list_user_cars
    from hlsc.tools.collect_car_info import collect_car_info

    # Context formatter
    from agent_sdk._common.request_context import ContextFormatter, RequestContext
    from hlsc.models import CarInfo, LocationInfo

    class TestRequestContext(RequestContext):
        current_car: CarInfo | None = None
        current_location: LocationInfo | None = None

    class TestContextFormatter(ContextFormatter):
        def format(self, context: RequestContext) -> str:
            if isinstance(context, dict):
                try:
                    context = TestRequestContext(**context)
                except Exception:
                    return ""
            if not isinstance(context, TestRequestContext):
                return ""
            parts = []
            if context.current_car is not None:
                car = context.current_car
                parts.append(f"current_car(car_model_id={car.car_model_id}, car_model_name={car.car_model_name}, vin_code={car.vin_code})")
            else:
                parts.append("current_car: (未设置)")
            if context.current_location is not None:
                loc = context.current_location
                parts.append(f"current_location(address={loc.address})")
            else:
                parts.append("current_location: (未设置)")
            return "[request_context]: " + ", ".join(parts)

    # Prompt templates（复用 mainagent 的模板）
    prompts_dir = PROJECT_ROOT / "mainagent" / "prompts" / "templates"
    template_parts = [
        prompts_dir / "IDENTITY.md",
        prompts_dir / "TOOLS.md",
        prompts_dir / "context.md",
        prompts_dir / "card.md",
    ]
    # 只用存在的文件
    template_parts = [p for p in template_parts if p.exists()]

    prompt_loader = TemplatePromptLoader(template_parts=template_parts)

    # Diagnose agent tool（通过 A2A 调用，需要 DIAGNOSE_AGENT_URL 环境变量）
    diagnose_url = os.getenv("DIAGNOSE_AGENT_URL", "")
    diagnose_tool = None
    if diagnose_url:
        from agent_sdk.a2a import call_subagent

        async def call_diagnose_agent(
            ctx: RunContext[AgentDeps],
            query: Annotated[str, Field(description="包含车型信息和故障描述的完整查询")],
        ) -> str:
            """调用诊断 Agent 分析汽车故障原因。

            适用场景：用户描述故障症状（如"过减速带咚咚响"、"方向盘抖"）。
            query 应包含车型信息和故障描述。
            """
            return await call_subagent(ctx, url=diagnose_url, message=query)

        diagnose_tool = call_diagnose_agent

    # 组装 tool map
    tool_map = {
        **create_default_tool_map(),
        "get_car_price": mock_get_car_price,
        "get_representative_car_model": get_representative_car_model,
        "list_user_cars": list_user_cars,
        "collect_car_info": collect_car_info,
    }
    if diagnose_tool:
        tool_map["call_diagnose_agent"] = diagnose_tool

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map, exclude=["write", "edit", "bash"]),
        context_formatter=TestContextFormatter(),
    )

    app = AgentApp(
        agent,
        AgentAppConfig(
            description="测试用 Agent — mock business tools + real extension tools",
        ),
    )

    # Copy skills to .chatagent/fstools/skills/（和 mainagent 结构一致）
    import shutil
    skills_dest = Path(".chatagent/fstools/skills")
    skills_src = PROJECT_ROOT / "extensions" / "skills"
    if skills_src.exists():
        if skills_dest.exists():
            shutil.rmtree(skills_dest)
        skills_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skills_src, skills_dest)

    app.run()


if __name__ == "__main__":
    main()
