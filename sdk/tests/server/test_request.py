"""请求模型测试"""

from agent_sdk._server.request import ChatRequest


class TestChatRequest:

    def test_basic(self) -> None:
        req = ChatRequest(session_id="s1", message="hello", user_id="u1")
        assert req.session_id == "s1"
        assert req.message == "hello"
