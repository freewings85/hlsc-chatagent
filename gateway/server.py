"""DataManager API 网关启动入口。

转发请求到 DATA_MANAGER_URL，统一改写参数和返回值字段名。

启动方式：
    uv run python server.py
    uv run python server.py --port 9000
"""

from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv

# 根据 ACTIVE 环境变量加载对应 .env 文件（默认 .env）
_active: str = os.getenv("ACTIVE", "")
_env_file: str = f".env.{_active}" if _active else ".env"
load_dotenv(_env_file)

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args: argparse.Namespace = parser.parse_args()

    import uvicorn
    from app import create_app

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
