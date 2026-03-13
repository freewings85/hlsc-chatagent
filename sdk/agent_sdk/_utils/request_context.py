"""请求上下文管理

使用 contextvars 在异步请求中传递 session_id 和 request_id，
避免在每个函数签名中显式传递。
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass
class RequestContext:
    """请求上下文"""
    session_id: str
    request_id: str


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "request_context", default=None,
)


def set_request_context(session_id: str, request_id: str) -> None:
    """设置当前请求的上下文（在请求入口调用）"""
    _request_context.set(RequestContext(session_id=session_id, request_id=request_id))


def clear_request_context() -> None:
    """清除请求上下文（在请求结束时调用）"""
    _request_context.set(None)


def get_session_id() -> Optional[str]:
    """获取当前请求的 session_id"""
    ctx = _request_context.get()
    return ctx.session_id if ctx else None


def get_request_id() -> Optional[str]:
    """获取当前请求的 request_id"""
    ctx = _request_context.get()
    return ctx.request_id if ctx else None
