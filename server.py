"""uvicorn 入口"""

# Nacos 必须最先 import：加载 .env → 连接 Nacos → 写入 os.environ
# 后续所有 os.getenv() 调用才能读到 Nacos 远程配置
from src.sdk._common.nacos import register_service, deregister_service  # noqa: F401, E402

register_service()

import uvicorn

from src.sdk._config.settings import LogfireConfig, get_server_config


def _setup_logfire() -> None:
    """根据配置初始化 Logfire / OTel tracing。"""
    config = LogfireConfig()
    if not config.enabled:
        return

    import logfire

    if config.endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        from src.sdk._config.otel import patch_pydantic_ai_json_dumps

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
    from src.sdk._server.app import app

    config = get_server_config()
    try:
        uvicorn.run(
            app,
            host=config.host,
            port=config.port,
            log_level="info",
        )
    finally:
        deregister_service()


if __name__ == "__main__":
    main()
