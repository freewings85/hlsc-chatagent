"""Agent 启动入口（通用模板）

配置加载由 nacos.py 统一处理：
  ACTIVE=local  → 加载 .env.local（本地开发）
  ACTIVE=test   → 加载 .env.test → Nacos 拉取远程配置
  ACTIVE=uat    → 加载 .env.uat  → Nacos 拉取远程配置

启动方式：
    uv run python server.py
    uv run python server.py --port 8101
    ACTIVE=test uv run python server.py
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


_ENV_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _render_api_docs() -> None:
    """将 fstools/apis 下的占位符替换为当前环境变量。"""
    fs_tools_dir = os.getenv("FS_TOOLS_DIR", ".chatagent/fstools").strip()
    apis_dir = Path(fs_tools_dir) / "apis"
    code_runs_dir = Path(fs_tools_dir) / os.getenv("CODING_AGENT_CODE_BASE_DIR", "code_runs").strip()

    if not apis_dir.exists():
        return

    code_runs_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(apis_dir.rglob("*")):
        if not path.is_file():
            continue

        original = path.read_text(encoding="utf-8")

        def _replace(match: re.Match[str]) -> str:
            env_name = match.group(1)
            value = os.getenv(env_name)
            if value is None:
                raise RuntimeError(f"API 文档占位符缺少环境变量：{env_name}（文件: {path}）")
            return value

        rendered = _ENV_PLACEHOLDER_RE.sub(_replace, original)
        unresolved = _ENV_PLACEHOLDER_RE.findall(rendered)
        if unresolved:
            names = ", ".join(sorted(set(unresolved)))
            raise RuntimeError(f"API 文档仍存在未替换占位符：{names}（文件: {path}）")

        if rendered != original:
            path.write_text(rendered, encoding="utf-8")


def _refresh_sdk_config_state() -> None:
    """清理已缓存的 SDK 配置单例，确保使用 .env / Nacos 最新值。"""
    from agent_sdk._config import settings as sdk_settings

    sdk_settings._fs_config = None
    sdk_settings._server_config = None
    sdk_settings._llm_config = None
    sdk_settings._temporal_config = None
    sdk_settings._kafka_config = None
    sdk_settings._fs_tools_backend = None
    sdk_settings._inner_storage_backend = None
    sdk_settings._agent_fs_backend = None


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

    _refresh_sdk_config_state()
    _render_api_docs()

    register_service()

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
                scrubbing=False,
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
