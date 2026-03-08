"""会话日志模块

日志分级：
- execution.log（每个 session 独立）: 请求的完整详细日志
- 控制台 + chatagent.log: 只记录请求开始和结束

参考 cjml-cheap-weixiu 的 thread_logger，session_id 对应 thread_id。
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from threading import Lock
from typing import Any, Optional

from src.utils.request_context import get_request_id, get_session_id

_session_loggers: dict[str, logging.Logger] = {}
_logger_lock = Lock()
_global_logger: logging.Logger | None = None

_LOG_DIR = os.getenv("LOG_DIR", "logs")


def _get_global_logger() -> logging.Logger:
    """获取全局 logger（懒加载）"""
    global _global_logger
    if _global_logger is not None:
        return _global_logger

    logger = logging.getLogger("chatagent")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

        # 全局日志文件
        os.makedirs(_LOG_DIR, exist_ok=True)
        fh = logging.FileHandler(
            os.path.join(_LOG_DIR, "chatagent.log"), encoding="utf-8",
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    _global_logger = logger
    return logger


def get_session_logger(session_id: str) -> logging.Logger:
    """获取或创建指定 session_id 的 logger（只写入 execution.log）"""
    if session_id in _session_loggers:
        return _session_loggers[session_id]

    with _logger_lock:
        if session_id in _session_loggers:
            return _session_loggers[session_id]

        session_log_dir = os.path.join(_LOG_DIR, session_id)
        os.makedirs(session_log_dir, exist_ok=True)

        logger = logging.getLogger(f"session_{session_id}")
        logger.setLevel(logging.DEBUG)

        if logger.handlers:
            _session_loggers[session_id] = logger
            return logger

        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        fh = logging.FileHandler(
            os.path.join(session_log_dir, "execution.log"), encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        logger.propagate = False
        _session_loggers[session_id] = logger
        return logger


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #

def _resolve_context(
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """解析上下文，优先使用显式传参，否则从 contextvars 获取"""
    sid = session_id or get_session_id()
    rid = request_id or get_request_id() or ""
    return sid, rid


def _req_prefix(request_id: str) -> str:
    return f"[req_{request_id}] " if request_id else ""


def _safe_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return str(data)


# --------------------------------------------------------------------------- #
# 详细日志（只写入 session execution.log）
# --------------------------------------------------------------------------- #

def log_info(
    message: str,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    sid, rid = _resolve_context(session_id, request_id)
    if sid:
        get_session_logger(sid).info(f"{_req_prefix(rid)}{message}")


def log_error(
    message: str,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    exc: Exception | None = None,
) -> None:
    sid, rid = _resolve_context(session_id, request_id)
    if sid:
        logger = get_session_logger(sid)
        logger.error(f"{_req_prefix(rid)}{message}")
        if exc:
            tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
            logger.error(f"{_req_prefix(rid)}[TRACEBACK]\n{''.join(tb)}")


def log_debug(
    message: str,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    sid, rid = _resolve_context(session_id, request_id)
    if sid:
        get_session_logger(sid).debug(f"{_req_prefix(rid)}{message}")


# --------------------------------------------------------------------------- #
# 工具调用日志
# --------------------------------------------------------------------------- #

def log_tool_start(tool_name: str, input_data: dict[str, Any] | None = None) -> None:
    """记录工具调用开始"""
    sid, rid = _resolve_context()
    if not sid:
        return
    logger = get_session_logger(sid)
    prefix = _req_prefix(rid)
    logger.info(f"{prefix}[TOOL_START] {tool_name}")
    if input_data:
        logger.info(f"{prefix}[TOOL_INPUT] {tool_name}: {_safe_json(input_data)}")


def log_tool_end(
    tool_name: str,
    output_data: Any = None,
    error: str | None = None,
    exc: Exception | None = None,
) -> None:
    """记录工具调用结束"""
    sid, rid = _resolve_context()
    if not sid:
        return
    logger = get_session_logger(sid)
    prefix = _req_prefix(rid)
    if error or exc:
        error_msg = error or str(exc)
        logger.error(f"{prefix}[TOOL_ERROR] {tool_name}: {error_msg}")
        if exc:
            tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
            logger.error(f"{prefix}[TOOL_TRACEBACK] {tool_name}:\n{''.join(tb)}")
    else:
        logger.info(f"{prefix}[TOOL_END] {tool_name}")
        if output_data is not None:
            logger.info(f"{prefix}[TOOL_OUTPUT] {tool_name}: {_safe_json(output_data)}")


# --------------------------------------------------------------------------- #
# LLM 调用日志
# --------------------------------------------------------------------------- #

def _format_messages_detail(messages: Any, user_prompt: str | None = None) -> str:
    """将消息列表格式化为详细日志字符串。

    接受 Pydantic AI ModelMessage 列表，展示原始 ModelRequest/ModelResponse 结构。
    连续的 ModelRequest 合并 parts 显示（与 Pydantic AI 发送给模型的一致）。
    user_prompt 为当前用户输入，追加在最后显示。
    """
    if not messages:
        return "(empty)"

    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        SystemPromptPart,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    lines: list[str] = []
    # 合并连续 ModelRequest 的 parts
    pending_parts: list[Any] = []
    part_index = 0

    def _flush_request() -> None:
        nonlocal pending_parts, part_index
        if not pending_parts:
            return
        lines.append("--- ModelRequest ---")
        for p in pending_parts:
            _format_part(p, part_index)
            part_index += 1
        pending_parts = []

    def _format_part(part: Any, idx: int) -> None:
        if isinstance(part, SystemPromptPart):
            lines.append(f"  [{idx}] SystemPromptPart: <<<{part.content}>>>")
        elif isinstance(part, UserPromptPart):
            content = part.content if isinstance(part.content, str) else str(part.content)
            lines.append(f"  [{idx}] UserPromptPart: <<<{content}>>>")
        elif isinstance(part, ToolReturnPart):
            content = part.content if isinstance(part.content, str) else str(part.content)
            lines.append(
                f"  [{idx}] ToolReturnPart: {part.tool_name} "
                f"[{part.tool_call_id}]: <<<{content}>>>"
            )
        elif isinstance(part, RetryPromptPart):
            content = part.content if isinstance(part.content, str) else str(part.content)
            lines.append(f"  [{idx}] RetryPromptPart: <<<{content}>>>")
        else:
            lines.append(f"  [{idx}] {type(part).__name__}: <<<{part}>>>")

    try:
        for msg in messages:
            if isinstance(msg, ModelRequest):
                pending_parts.extend(msg.parts)
            elif isinstance(msg, ModelResponse):
                _flush_request()
                lines.append("--- ModelResponse ---")
                for rp in msg.parts:
                    if isinstance(rp, TextPart):
                        lines.append(f"  [{part_index}] TextPart: <<<{rp.content}>>>")
                    elif isinstance(rp, ToolCallPart):
                        lines.append(
                            f"  [{part_index}] ToolCallPart: "
                            f"{rp.tool_name}({rp.args}) [{rp.tool_call_id}]"
                        )
                    else:
                        lines.append(f"  [{part_index}] {type(rp).__name__}")
                    part_index += 1
            else:
                _flush_request()
                lines.append(f"--- {type(msg).__name__} ---")
        _flush_request()
        # 追加当前用户输入（Pydantic AI 会自动追加为 UserPromptPart）
        if user_prompt:
            lines.append(f"  [{part_index}] UserPromptPart (current): <<<{user_prompt}>>>")
    except Exception:
        return f"(format error: {len(messages)} messages)"

    return "\n".join(lines)


def log_llm_start(
    node_name: str,
    messages_count: int = 0,
    messages: Any = None,
    user_prompt: str | None = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """记录 LLM 调用开始（打印完整消息详情）。

    messages: pre_call_service 处理后的 ModelMessage 列表（context + history）
    user_prompt: 当前用户输入（Pydantic AI 会自动追加为 UserPromptPart，此处仅做日志展示）
    """
    sid, rid = _resolve_context(session_id, request_id)
    if not sid:
        return
    logger = get_session_logger(sid)
    prefix = _req_prefix(rid)
    if messages:
        detail = _format_messages_detail(messages, user_prompt=user_prompt)
        total = messages_count + (1 if user_prompt else 0)
        logger.info(f"{prefix}[LLM_START] {node_name} ({total} parts):\n{detail}")
    else:
        logger.info(f"{prefix}[LLM_START] {node_name} (messages={messages_count})")


def log_llm_end(
    node_name: str,
    response_preview: str | None = None,
    tool_calls: list[str] | None = None,
    error: str | None = None,
    exc: Exception | None = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """记录 LLM 调用结束"""
    sid, rid = _resolve_context(session_id, request_id)
    if not sid:
        return
    logger = get_session_logger(sid)
    prefix = _req_prefix(rid)
    if error or exc:
        error_msg = error or str(exc)
        logger.error(f"{prefix}[LLM_ERROR] {node_name}: {error_msg}")
        if exc:
            tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
            logger.error(f"{prefix}[LLM_TRACEBACK] {node_name}:\n{''.join(tb)}")
    else:
        if tool_calls:
            logger.info(f"{prefix}[LLM_END] {node_name} → tool_calls: {tool_calls}")
        elif response_preview:
            logger.info(f"{prefix}[LLM_END] {node_name} → text:\n    <<<{response_preview}>>>")
        else:
            logger.info(f"{prefix}[LLM_END] {node_name}")


# --------------------------------------------------------------------------- #
# HTTP 请求日志（给外部 RESTful 调用用）
# --------------------------------------------------------------------------- #

def log_http_request(
    url: str,
    method: str = "POST",
    request_data: dict[str, Any] | None = None,
) -> None:
    """记录 HTTP 请求"""
    sid, rid = _resolve_context()
    if not sid:
        return
    logger = get_session_logger(sid)
    prefix = _req_prefix(rid)
    logger.info(f"{prefix}[HTTP_REQUEST] {method} {url}")
    if request_data:
        logger.info(f"{prefix}[HTTP_BODY] {_safe_json(request_data)}")


def log_http_response(
    status_code: int,
    response_data: Any = None,
    error: str | None = None,
) -> None:
    """记录 HTTP 响应"""
    sid, rid = _resolve_context()
    if not sid:
        return
    logger = get_session_logger(sid)
    prefix = _req_prefix(rid)
    if error:
        logger.error(f"{prefix}[HTTP_ERROR] status={status_code}, error={error}")
    else:
        logger.info(f"{prefix}[HTTP_RESPONSE] status={status_code}")
        if response_data is not None:
            logger.info(f"{prefix}[HTTP_RESPONSE_BODY] {_safe_json(response_data)}")


# --------------------------------------------------------------------------- #
# 请求级别日志（同时写入 session execution.log + 全局控制台）
# --------------------------------------------------------------------------- #

def log_request_start(
    session_id: str,
    user_query: str,
    user_id: str = "",
    request_id: str = "",
) -> None:
    """记录请求开始"""
    prefix = _req_prefix(request_id)

    if session_id:
        sl = get_session_logger(session_id)
        sl.info("=" * 80)
        sl.info(
            f"{prefix}[REQUEST_START] session_id={session_id}, "
            f"request_id={request_id}, user_id={user_id}, "
            f"query={user_query}"
        )

    gl = _get_global_logger()
    gl.info(
        f"[{session_id}] [{request_id}] 请求开始: "
        f"user_id={user_id}, query={user_query}"
    )


def log_request_end(
    session_id: str,
    success: bool = True,
    error: str | None = None,
    request_id: str = "",
    response: str | None = None,
) -> None:
    """记录请求结束"""
    prefix = _req_prefix(request_id)

    if session_id:
        sl = get_session_logger(session_id)
        if error:
            sl.error(
                f"{prefix}[REQUEST_END] session_id={session_id}, "
                f"success={success}, error={error}"
            )
        else:
            sl.info(
                f"{prefix}[REQUEST_END] session_id={session_id}, "
                f"success={success}"
            )
        sl.info("=" * 80)

    gl = _get_global_logger()
    if error:
        gl.error(f"[{session_id}] [{request_id}] 请求结束: success={success}, error={error}")
    else:
        resp_preview = response[:200] + "..." if response and len(response) > 200 else (response or "")
        gl.info(f"[{session_id}] [{request_id}] 请求结束: success={success}, response={resp_preview}")
