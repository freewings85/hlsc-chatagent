"""BusinessMapAgent 启动入口

纯 FastAPI 服务，暴露 /classify 端点进行场景分类。
不使用 AgentApp / A2A 协议。

启动方式：
    uv run python server.py
    uv run python server.py --port 8103
"""

from __future__ import annotations

import argparse
import logging
import os


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    args: argparse.Namespace = parser.parse_args()

    # Nacos 服务注册（如果启用）
    from agent_sdk._common.nacos import register_service, deregister_service

    if args.port is not None:
        os.environ["SERVER_PORT"] = str(args.port)
    if args.host is not None:
        os.environ["SERVER_HOST"] = args.host

    register_service()

    # Logfire / OpenTelemetry（可选）
    from agent_sdk._config.settings import LogfireConfig

    logfire_config: LogfireConfig = LogfireConfig()
    if logfire_config.enabled:
        import logfire

        if logfire_config.endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            logfire.configure(
                service_name="business_map_agent",
                send_to_logfire=False,
                scrubbing=False,
                additional_span_processors=[
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=logfire_config.endpoint)),
                ],
            )
        else:
            logfire.configure(service_name="business_map_agent")

    # 构建 FastAPI app
    from src.classify import create_app

    app = create_app()

    # 启动 uvicorn
    import uvicorn

    host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    port: int = int(os.getenv("SERVER_PORT", "8103"))

    try:
        uvicorn.run(app, host=host, port=port)
    finally:
        deregister_service()


if __name__ == "__main__":
    main()
