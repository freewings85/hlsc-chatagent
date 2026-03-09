"""uvicorn 入口"""

import os

from dotenv import load_dotenv
load_dotenv()

import uvicorn

from src.config.settings import get_server_config

# Logfire：trace agent 轨迹（LLM 调用、工具调用、HTTP 请求）
# 通过 LOGFIRE_ENABLED=true 开启，默认关闭
if os.getenv("LOGFIRE_ENABLED", "false").lower() == "true":
    import logfire
    logfire.configure(service_name="chatagent")
    logfire.instrument_pydantic_ai()


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
