"""CodingRequestContext 与格式化逻辑。"""

from __future__ import annotations

import os

from agent_sdk._common.request_context import ContextFormatter, RequestContext


def normalize_code_base_dir(code_base_dir: str | None = None) -> str:
    """标准化代码工作目录基路径。"""
    value = (code_base_dir or os.getenv("CODING_AGENT_CODE_BASE_DIR", "code_runs")).strip()
    value = value.replace("\\", "/")
    if not value.startswith("/"):
        value = "/" + value
    normalized = value.rstrip("/")
    return normalized or "/code_runs"


class CodingRequestContext(RequestContext):
    """QueryCodingAgent 的请求上下文。"""

    code_task_id: str


def resolve_code_dir(request_context: RequestContext | dict | None, code_base_dir: str | None = None) -> str | None:
    """根据 request_context 和配置推导当前代码目录。"""
    if request_context is None:
        return None

    if isinstance(request_context, RequestContext):
        try:
            request_context = request_context.model_dump()
        except Exception:
            return None

    if isinstance(request_context, dict):
        try:
            request_context = CodingRequestContext(**request_context)
        except Exception:
            return None

    base_dir = normalize_code_base_dir(code_base_dir)
    return f"{base_dir}/{request_context.code_task_id}"


class CodingContextFormatter(ContextFormatter):
    """将 CodingRequestContext 注入给 LLM。"""

    def __init__(self, code_base_dir: str | None = None) -> None:
        self._code_base_dir = normalize_code_base_dir(code_base_dir)

    def format(self, context: RequestContext) -> str:
        if isinstance(context, RequestContext):
            try:
                context = context.model_dump()
            except Exception:
                return ""
        if isinstance(context, dict):
            try:
                context = CodingRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, CodingRequestContext):
            return ""

        code_dir = resolve_code_dir(context, self._code_base_dir)
        if not code_dir:
            return ""

        return f"[request_context]: code_task_id={context.code_task_id}, code_dir={code_dir}"
