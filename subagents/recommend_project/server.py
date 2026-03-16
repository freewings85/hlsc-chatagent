"""Agent 启动入口（通用模板）

配置加载由 nacos.py 统一处理：
  ACTIVE=local  → 加载 .env.local（本地开发）
  ACTIVE=test   → 加载 .env.test → Nacos 拉取远程配置
  ACTIVE=uat    → 加载 .env.uat  → Nacos 拉取远程配置

启动方式：
    uv run python server.py
    uv run python server.py --port 8105
    ACTIVE=test uv run python server.py
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    import logging

    logging.basicConfig(level=logging.INFO)

    # 解析命令行参数（仅 --port/--host，配置加载交给 nacos.py）
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    args = parser.parse_args()

    # nacos.py 在 import 时自动根据 ACTIVE 加载 .env.{ACTIVE} + Nacos 远程配置
    from agent_sdk._common.nacos import register_service, deregister_service

    # 命令行参数覆盖（优先级最高）
    if args.port is not None:
        os.environ["SERVER_PORT"] = str(args.port)
    if args.host is not None:
        os.environ["SERVER_HOST"] = args.host

    register_service()

    # Logfire / OTel tracing
    from agent_sdk._config.settings import LogfireConfig
    from agent_sdk.config import get_agent_name

    logfire_config = LogfireConfig()
    if logfire_config.enabled:
        import logfire

        if logfire_config.endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            from agent_sdk._config.otel import patch_pydantic_ai_json_dumps

            patch_pydantic_ai_json_dumps()
            logfire.configure(
                service_name=get_agent_name(),
                send_to_logfire=False,
                additional_span_processors=[
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=logfire_config.endpoint)),
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
