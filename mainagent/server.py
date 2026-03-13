"""HLSC MainAgent 启动入口

启动方式：
    uv run python mainagent/server.py
    uv run python mainagent/server.py --env mainagent/.env.local
    uv run python mainagent/server.py --port 8100
"""

from __future__ import annotations

import argparse
import os
import sys


def _load_env() -> argparse.Namespace:
    """解析 --env 参数并加载配置（必须在任何 agent_sdk import 之前）。"""
    parser = argparse.ArgumentParser(description="HLSC Main Agent")
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

    # Nacos 必须最先 import：连接 Nacos → 写入 os.environ
    from agent_sdk._common.nacos import register_service, deregister_service

    register_service()

    # 注册业务上下文格式化器
    from agent_sdk._config.settings import register_context_formatter
    from src.hlsc_context import hlsc_context_formatter
    register_context_formatter(hlsc_context_formatter)

    import logging
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    # Logfire / OTel tracing
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
                service_name="hlsc-mainagent",
                send_to_logfire=False,
                additional_span_processors=[
                    SimpleSpanProcessor(OTLPSpanExporter(endpoint=config.endpoint)),
                ],
            )
        else:
            logfire.configure(service_name="hlsc-mainagent")
        logfire.instrument_pydantic_ai()

    # 创建 Agent + AgentApp
    from src.app import create_main_agent

    from agent_sdk import AgentApp, AgentAppConfig

    agent = create_main_agent()
    agent_app = AgentApp(
        agent,
        AgentAppConfig(
            name="HLSC-MainAgent",
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
        ),
    )

    try:
        uvicorn.run(
            agent_app.app,
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8100")),
            log_level="info",
        )
    finally:
        deregister_service()


if __name__ == "__main__":
    main()
