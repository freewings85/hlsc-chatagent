"""uvicorn 入口"""

import uvicorn

from src.config.settings import get_server_config


def main() -> None:
    """启动服务"""
    config = get_server_config()
    uvicorn.run(
        "src.server.app:app",
        host=config.host,
        port=config.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
