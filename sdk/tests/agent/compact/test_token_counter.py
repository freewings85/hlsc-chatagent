"""Token counter 测试"""

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from agent_sdk._agent.compact.token_counter import (
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
)


class TestEstimateTokens:

    def test_basic(self) -> None:
        assert estimate_tokens("hello world") == 2  # 11 chars / 4

    def test_empty(self) -> None:
        assert estimate_tokens("") == 1  # min 1

    def test_chinese(self) -> None:
        # 中文字符每个 3 bytes UTF-8，但我们按字符数算
        result = estimate_tokens("你好世界测试")  # 6 chars / 4 = 1
        assert result >= 1


class TestEstimateMessageTokens:

    def test_user_message(self) -> None:
        msg = ModelRequest(parts=[UserPromptPart(content="a" * 400)])
        assert estimate_message_tokens(msg) == 100  # 400 / 4

    def test_response_message(self) -> None:
        msg = ModelResponse(parts=[TextPart(content="b" * 800)])
        assert estimate_message_tokens(msg) == 200

    def test_tool_return(self) -> None:
        msg = ModelRequest(parts=[ToolReturnPart(
            tool_name="test",
            content="c" * 1200,
            tool_call_id="call_1",
        )])
        assert estimate_message_tokens(msg) == 300


class TestEstimateMessagesTokens:

    def test_multiple(self) -> None:
        messages = [
            ModelRequest(parts=[UserPromptPart(content="a" * 400)]),
            ModelResponse(parts=[TextPart(content="b" * 800)]),
        ]
        assert estimate_messages_tokens(messages) == 300
