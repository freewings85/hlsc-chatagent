"""Agent 启动入口（通用模板）

启动方式：
    uv run python server.py
    uv run python server.py --env .env.local
    uv run python server.py --port 8101
"""

from __future__ import annotations

import argparse
import os


def _load_env() -> argparse.Namespace:
    """解析 --env 参数并加载配置（必须在任何 agent_sdk import 之前）。"""
    parser = argparse.ArgumentParser()
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
    _load_env()

    from agent_sdk._common.nacos import register_service, deregister_service

    register_service()

    import logging
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    # Logfire / OTel tracing
    from agent_sdk._config.settings import LogfireConfig
    from agent_sdk.config import get_agent_name

    logfire_config = LogfireConfig()
    if logfire_config.enabled:
        import logfire

        if logfire_config.endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor

            from agent_sdk._config.otel import patch_pydantic_ai_json_dumps

            patch_pydantic_ai_json_dumps()
            logfire.configure(
                service_name=get_agent_name(),
                send_to_logfire=False,
                additional_span_processors=[
                    SimpleSpanProcessor(OTLPSpanExporter(endpoint=logfire_config.endpoint)),
                ],
            )
        else:
            logfire.configure(service_name=get_agent_name())
        logfire.instrument_pydantic_ai()

    # 创建 AgentApp（业务逻辑全在 src/app.py）
    from src.app import create_agent_app

    agent_app = create_agent_app()

    try:
        agent_app.run()
    finally:
        deregister_service()


if __name__ == "__main__":
    main()
