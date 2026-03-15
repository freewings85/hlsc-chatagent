"""结构化链路日志工具。

SDK 统一日志接口，所有 agent 和 extensions 共用。
每条日志带 session_id + request_id，串联完整调用链路。

用法：
    from agent_sdk.logging import log_tool_start, log_tool_end, log_http_request, log_http_response

    # tool 层（从 ctx.deps 取 ID）
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("fuzzy_match_car_info", sid, rid, {"query": "卡罗拉"})
    ...
    log_tool_end("fuzzy_match_car_info", sid, rid, {"matched": True})

    # service 层（ID 从 tool 层传入）
    log_http_request(url, "POST", sid, rid, payload)
    ...
    log_http_response(status_code, sid, rid, data)
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("chatagent")

_timers: dict[str, float] = {}


def _prefix(session_id: str, request_id: str) -> str:
    """日志前缀：[session_id] [request_id]"""
    sid = session_id[:16] if len(session_id) > 16 else session_id
    rid = request_id[:8] if request_id else "?"
    return f"[{sid}] [{rid}]"


# ── Tool 层日志 ──

def log_tool_start(
    tool_name: str,
    session_id: str,
    request_id: str,
    params: dict[str, Any] | None = None,
) -> None:
    """tool 调用开始"""
    key = f"{request_id}:{tool_name}"
    _timers[key] = time.time()
    p = _prefix(session_id, request_id)
    params_str = f" params={params}" if params else ""
    logger.info(f"{p} [TOOL_START] {tool_name}{params_str}")


def log_tool_end(
    tool_name: str,
    session_id: str,
    request_id: str,
    result: dict[str, Any] | None = None,
    exc: Exception | None = None,
) -> None:
    """tool 调用结束"""
    key = f"{request_id}:{tool_name}"
    elapsed = time.time() - _timers.pop(key, time.time())
    elapsed_ms = int(elapsed * 1000)
    p = _prefix(session_id, request_id)

    if exc is not None:
        logger.error(f"{p} [TOOL_END] {tool_name} FAILED ({elapsed_ms}ms): {exc}")
    else:
        result_str = f" result={result}" if result else ""
        logger.info(f"{p} [TOOL_END] {tool_name} OK ({elapsed_ms}ms){result_str}")


# ── HTTP / Service 层日志 ──

def log_http_request(
    url: str,
    method: str,
    session_id: str,
    request_id: str,
    payload: Any = None,
) -> None:
    """HTTP 请求发出"""
    p = _prefix(session_id, request_id)
    payload_str = f" payload={payload}" if payload else ""
    logger.info(f"{p} [HTTP_REQ] {method} {url}{payload_str}")


def log_http_response(
    status_code: int,
    session_id: str,
    request_id: str,
    data: Any = None,
    error: str | None = None,
) -> None:
    """HTTP 响应收到"""
    p = _prefix(session_id, request_id)
    if error:
        logger.error(f"{p} [HTTP_RES] status={status_code} error={error}")
    else:
        data_str = str(data)
        if len(data_str) > 500:
            data_str = data_str[:500] + "..."
        logger.info(f"{p} [HTTP_RES] status={status_code} data={data_str}")
