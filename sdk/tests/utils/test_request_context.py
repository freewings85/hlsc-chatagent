"""request_context 单元测试"""

from agent_sdk._utils.request_context import (
    clear_request_context,
    get_request_id,
    get_session_id,
    set_request_context,
)


def test_set_and_get() -> None:
    set_request_context("sess-1", "req-1")
    assert get_session_id() == "sess-1"
    assert get_request_id() == "req-1"
    clear_request_context()


def test_clear() -> None:
    set_request_context("sess-2", "req-2")
    clear_request_context()
    assert get_session_id() is None
    assert get_request_id() is None


def test_default_none() -> None:
    clear_request_context()
    assert get_session_id() is None
    assert get_request_id() is None


def test_overwrite() -> None:
    set_request_context("a", "b")
    set_request_context("c", "d")
    assert get_session_id() == "c"
    assert get_request_id() == "d"
    clear_request_context()
