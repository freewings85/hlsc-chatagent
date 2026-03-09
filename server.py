"""uvicorn 入口"""

from dotenv import load_dotenv
load_dotenv()

import uvicorn

from src.config.settings import LogfireConfig, get_server_config


def _setup_logfire() -> None:
    """根据配置初始化 Logfire / OTel tracing。"""
    config = LogfireConfig()
    if not config.enabled:
        return

    import logfire

    if config.endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        from src.config.otel import patch_pydantic_ai_json_dumps

        # 在 logfire.configure 之前 patch，让中文直接输出不转义
        patch_pydantic_ai_json_dumps()

        logfire.configure(
            service_name="chatagent",
            send_to_logfire=False,
            additional_span_processors=[
                SimpleSpanProcessor(OTLPSpanExporter(endpoint=config.endpoint)),
            ],
        )
    else:
        logfire.configure(service_name="chatagent")

    logfire.instrument_pydantic_ai()


_setup_logfire()


def main() -> None:
    """启动服务"""
    from src.server.app import app

    config = get_server_config()
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
