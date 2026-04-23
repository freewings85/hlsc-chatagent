from __future__ import annotations

from agent_sdk._agent.agent_message import AssistantMessage, UserMessage

from src.chat_stream2_router import _build_commit_filter


def test_full_commit_filter_keeps_user_message() -> None:
    commit_filter = _build_commit_filter("full", "searchshops_followup")

    original_user = UserMessage(content="我要选第一个", metadata={"message_origin": "user"})
    original_assistant = AssistantMessage(content="当前暂不支持直接操作上一轮结果。")

    result = commit_filter([original_user, original_assistant])

    assert len(result) == 2
    assert isinstance(result[0], UserMessage)
    assert result[0].content == "我要选第一个"
    assert result[0].metadata["message_origin"] == "user"
    assert result[0].metadata["agent"] == "searchshops_followup"
    assert isinstance(result[1], AssistantMessage)
    assert result[1].metadata["agent"] == "searchshops_followup"


def test_text_only_commit_filter_keeps_user_and_final_assistant_text() -> None:
    commit_filter = _build_commit_filter("text_only", "searchshops_executed")

    original_user = UserMessage(content="帮我找附近洗车店", metadata={"message_origin": "user"})
    tool_only_assistant = AssistantMessage(
        content="",
        tool_calls=[],
        metadata={"step": "tool"},
    )
    final_assistant = AssistantMessage(
        content="附近有三家可选门店。",
        tool_calls=[],
        metadata={"step": "final"},
    )

    result = commit_filter([original_user, tool_only_assistant, final_assistant])

    assert len(result) == 2
    assert isinstance(result[0], UserMessage)
    assert result[0].content == "帮我找附近洗车店"
    assert result[0].metadata["message_origin"] == "user"
    assert result[0].metadata["agent"] == "searchshops_executed"
    assert isinstance(result[1], AssistantMessage)
    assert result[1].content == "附近有三家可选门店。"
    assert result[1].tool_calls == []
    assert result[1].metadata["step"] == "final"
    assert result[1].metadata["agent"] == "searchshops_executed"
