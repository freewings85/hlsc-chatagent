"""AgentDeps 测试"""

from agent_sdk._agent.deps import AgentDeps


class TestAgentDeps:
    def test_default(self) -> None:
        deps = AgentDeps()
        assert deps.session_id == "default"
        assert deps.tool_call_count == 0

    def test_custom(self) -> None:
        deps = AgentDeps(
            session_id="test-001",
            user_id="user-1",
            available_tools=["get_weather"],
        )
        assert deps.session_id == "test-001"
        assert "get_weather" in deps.available_tools
