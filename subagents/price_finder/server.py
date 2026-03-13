"""PriceFinder Subagent 启动入口

启动方式：
    uv run python server.py
    uv run python server.py --env .env.local
    uv run python server.py --port 8101
"""

from __future__ import annotations

import argparse
import os
import sys


def _load_env() -> argparse.Namespace:
    """解析 --env 参数并加载配置（必须在任何 agent_sdk import 之前）。"""
    parser = argparse.ArgumentParser(description="PriceFinder Subagent")
    parser.add_argument(
        "--env", type=str,
        default=os.path.join(os.path.dirname(__file__), ".env.local"),
        help="配置文件路径（默认: 同目录 .env.local）",
    )
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    args = parser.parse_args()

    from dotenv import load_dotenv

    if os.path.exists(args.env):
        load_dotenv(args.env, override=True)
        print(f"[config] loaded: {args.env}")
    else:
        print(f"[config] WARNING: {args.env} not found, using defaults")
        load_dotenv()

    if args.port is not None:
        os.environ["SERVER_PORT"] = str(args.port)
    if args.host is not None:
        os.environ["SERVER_HOST"] = args.host

    return args


def main() -> None:
    args = _load_env()

    # Nacos
    from agent_sdk._common.nacos import register_service, deregister_service

    register_service()

    import logging
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    # Logfire
    from agent_sdk._config.settings import LogfireConfig

    config = LogfireConfig()
    if config.enabled:
        import logfire

        if config.endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor

            from agent_sdk._config.otel import patch_pydantic_ai_json_dumps

            patch_pydantic_ai_json_dumps()
            logfire.configure(
                service_name="price-finder",
                send_to_logfire=False,
                additional_span_processors=[
                    SimpleSpanProcessor(OTLPSpanExporter(endpoint=config.endpoint)),
                ],
            )
        else:
            logfire.configure(service_name="price-finder")
        logfire.instrument_pydantic_ai()

    # 创建 Agent + AgentApp
    from a2a.types import AgentSkill

    from agent_sdk import Agent, AgentApp, AgentAppConfig, StaticPromptLoader
    from src.tools import create_price_finder_tool_map

    _PRICE_FINDER_SYSTEM_PROMPT = """\
你是 PriceFinder Agent。你只有一个能力：调用 find_best_price_of_project 工具。

## 绝对规则（违反即失败）

1. 收到任何消息后，你必须**立即**调用 find_best_price_of_project 工具
2. 禁止不调用工具就回复用户
3. 禁止编造任何价格数据
4. 禁止向用户提问或要求澄清
5. 将用户消息中的项目描述直接作为 project_name 参数传给工具

## 流程

用户消息 → 调用 find_best_price_of_project(project_name=用户描述) → 返回工具结果
"""

    agent = Agent(
        prompt_loader=StaticPromptLoader(_PRICE_FINDER_SYSTEM_PROMPT),
        tools=create_price_finder_tool_map(),
        agent_name="price_finder",
    )

    agent_app = AgentApp(
        agent,
        AgentAppConfig(
            name="PriceFinder",
            description="汽车维修项目最低价查询 Agent，支持比价和用户确认",
            a2a_skills=[
                AgentSkill(
                    id="find_best_price",
                    name="Find Best Price",
                    description="Search for the cheapest price for a car repair project and confirm with user",
                    tags=["price", "inquiry", "hitl"],
                ),
            ],
        ),
    )

    try:
        uvicorn.run(
            agent_app.app,
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8101")),
            log_level="info",
        )
    finally:
        deregister_service()


if __name__ == "__main__":
    main()
