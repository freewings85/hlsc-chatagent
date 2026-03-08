"""session_logger 单元测试"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from src.utils.request_context import clear_request_context, set_request_context


@pytest.fixture(autouse=True)
def _clean_context() -> None:
    """每个测试后清理上下文"""
    yield  # type: ignore[misc]
    clear_request_context()


@pytest.fixture()
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """使用临时目录作为日志目录，避免污染项目"""
    monkeypatch.setattr("src.utils.session_logger._LOG_DIR", str(tmp_path))
    # 清除 logger 缓存，避免复用旧 handler
    import src.utils.session_logger as sl
    sl._session_loggers.clear()
    # 清除全局 logger（含 handler），使其用新 _LOG_DIR 重建
    if sl._global_logger is not None:
        sl._global_logger.handlers.clear()
    sl._global_logger = None
    return tmp_path


class TestGetSessionLogger:
    def test_creates_log_file(self, log_dir: Path) -> None:
        from src.utils.session_logger import get_session_logger
        logger = get_session_logger("test-sess")
        logger.info("hello")
        log_file = log_dir / "test-sess" / "execution.log"
        assert log_file.exists()
        assert "hello" in log_file.read_text()

    def test_reuses_logger(self, log_dir: Path) -> None:
        from src.utils.session_logger import get_session_logger
        l1 = get_session_logger("same")
        l2 = get_session_logger("same")
        assert l1 is l2


class TestLogToolStartEnd:
    def test_tool_start_end(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_tool_end, log_tool_start
        set_request_context("s1", "r1")
        log_tool_start("read", {"file_path": "/foo.py"})
        log_tool_end("read", output_data="ok")
        log_file = log_dir / "s1" / "execution.log"
        text = log_file.read_text()
        assert "[TOOL_START] read" in text
        assert "[TOOL_INPUT] read" in text
        assert "[TOOL_END] read" in text
        assert "[TOOL_OUTPUT] read" in text

    def test_tool_error(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_tool_end, log_tool_start
        set_request_context("s2", "r2")
        log_tool_start("bash")
        log_tool_end("bash", error="command failed")
        text = (log_dir / "s2" / "execution.log").read_text()
        assert "[TOOL_ERROR] bash: command failed" in text

    def test_tool_with_exception(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_tool_end
        set_request_context("s3", "r3")
        try:
            raise ValueError("test exc")
        except ValueError as e:
            log_tool_end("edit", exc=e)
        text = (log_dir / "s3" / "execution.log").read_text()
        assert "[TOOL_ERROR] edit" in text
        assert "[TOOL_TRACEBACK]" in text
        assert "ValueError" in text

    def test_no_context_silent(self, log_dir: Path) -> None:
        """没有设置上下文时不报错"""
        from src.utils.session_logger import log_tool_start
        log_tool_start("read")  # 不应抛出


class TestLogLlmStartEnd:
    def test_llm_text_response(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_llm_end, log_llm_start
        set_request_context("s4", "r4")
        log_llm_start("ModelRequestNode", messages_count=5)
        log_llm_end("ModelRequestNode", response_preview="你好，有什么可以帮你的？")
        text = (log_dir / "s4" / "execution.log").read_text()
        assert "[LLM_START] ModelRequestNode (messages=5)" in text
        assert "[LLM_END] ModelRequestNode" in text
        assert "你好" in text

    def test_llm_tool_calls(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_llm_end, log_llm_start
        set_request_context("s5", "r5")
        log_llm_start("ModelRequestNode")
        log_llm_end("ModelRequestNode", tool_calls=["read", "bash"])
        text = (log_dir / "s5" / "execution.log").read_text()
        assert "tool_calls: ['read', 'bash']" in text

    def test_llm_error(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_llm_end
        set_request_context("s6", "r6")
        log_llm_end("ModelRequestNode", error="rate limit")
        text = (log_dir / "s6" / "execution.log").read_text()
        assert "[LLM_ERROR] ModelRequestNode: rate limit" in text

    def test_llm_start_with_messages_detail(self, log_dir: Path) -> None:
        """log_llm_start 传入 messages 时打印原始 ModelRequest/ModelResponse 结构"""
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            TextPart,
            ToolCallPart,
            ToolReturnPart,
            UserPromptPart,
        )
        from src.utils.session_logger import log_llm_start

        set_request_context("s6b", "r6b")
        messages = [
            ModelRequest(parts=[UserPromptPart(content="你好")]),
            ModelResponse(parts=[
                TextPart(content="我来帮你"),
                ToolCallPart(tool_name="read", args='{"file_path": "/foo.py"}', tool_call_id="tc1"),
            ]),
            ModelRequest(parts=[
                ToolReturnPart(tool_name="read", content="file content here", tool_call_id="tc1"),
            ]),
        ]
        log_llm_start("ModelRequestNode", messages_count=3, messages=messages)
        text = (log_dir / "s6b" / "execution.log").read_text()
        # 验证原始 ModelRequest/ModelResponse 结构
        assert "ModelRequest" in text
        assert "ModelResponse" in text
        assert "UserPromptPart" in text
        assert "TextPart" in text
        assert "ToolCallPart" in text
        assert "ToolReturnPart" in text
        # 验证完整内容被打印
        assert "<<<你好>>>" in text
        assert "<<<我来帮你>>>" in text
        assert "read" in text
        assert "file_path" in text
        assert "file content here" in text


class TestLogHttpRequestResponse:
    def test_http_success(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_http_request, log_http_response
        set_request_context("s7", "r7")
        log_http_request("https://api.example.com/v1", "POST", {"q": "test"})
        log_http_response(200, {"result": "ok"})
        text = (log_dir / "s7" / "execution.log").read_text()
        assert "[HTTP_REQUEST] POST https://api.example.com/v1" in text
        assert "[HTTP_BODY]" in text
        assert "[HTTP_RESPONSE] status=200" in text

    def test_http_error(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_http_response
        set_request_context("s8", "r8")
        log_http_response(500, error="server error")
        text = (log_dir / "s8" / "execution.log").read_text()
        assert "[HTTP_ERROR] status=500" in text


class TestLogRequestStartEnd:
    def test_request_lifecycle(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_request_end, log_request_start
        log_request_start("sess-a", "你好", user_id="u1", request_id="req-a")
        log_request_end("sess-a", success=True, request_id="req-a")
        text = (log_dir / "sess-a" / "execution.log").read_text()
        assert "[REQUEST_START]" in text
        assert "query=你好" in text
        assert "[REQUEST_END]" in text
        assert "success=True" in text

    def test_request_failure(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_request_end, log_request_start
        log_request_start("sess-b", "crash", request_id="req-b")
        log_request_end("sess-b", success=False, error="boom", request_id="req-b")
        text = (log_dir / "sess-b" / "execution.log").read_text()
        assert "success=False" in text
        assert "error=boom" in text


class TestLogInfoDebugError:
    def test_log_info(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_info
        set_request_context("s9", "r9")
        log_info("some info message")
        text = (log_dir / "s9" / "execution.log").read_text()
        assert "some info message" in text

    def test_log_debug(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_debug
        set_request_context("s10", "r10")
        log_debug("debug detail")
        text = (log_dir / "s10" / "execution.log").read_text()
        assert "debug detail" in text

    def test_log_error_with_exc(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_error
        set_request_context("s11", "r11")
        try:
            raise RuntimeError("oops")
        except RuntimeError as e:
            log_error("something failed", exc=e)
        text = (log_dir / "s11" / "execution.log").read_text()
        assert "something failed" in text
        assert "[TRACEBACK]" in text
        assert "RuntimeError" in text


class TestReqPrefix:
    def test_prefix_with_request_id(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_info
        set_request_context("s12", "my-req")
        log_info("test")
        text = (log_dir / "s12" / "execution.log").read_text()
        assert "[req_my-req]" in text

    def test_prefix_without_request_id(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_info
        set_request_context("s13", "")
        log_info("test")
        text = (log_dir / "s13" / "execution.log").read_text()
        assert "[req_" not in text


class TestGlobalLogger:
    def test_global_log_file_created(self, log_dir: Path) -> None:
        from src.utils.session_logger import log_request_start
        log_request_start("sess-g", "hello", request_id="rg")
        global_log = log_dir / "chatagent.log"
        assert global_log.exists()
        text = global_log.read_text()
        assert "请求开始" in text
