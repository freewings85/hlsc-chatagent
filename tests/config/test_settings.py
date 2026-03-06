"""配置模块测试"""

from src.agent.compact.config import CompactConfig
from src.config.settings import LLMConfig, StorageConfig, ServerConfig


class TestLLMConfig:
    def test_default(self) -> None:
        config = LLMConfig()
        assert config.llm_type in ("azure", "openai", "")


class TestStorageConfig:
    def test_default(self) -> None:
        config = StorageConfig()
        assert "sessions" in config.sessions_dir

    def test_data_dir(self) -> None:
        config = StorageConfig(data_dir="/tmp/test-data")
        assert config.data_dir == "/tmp/test-data"
        assert config.sessions_dir == "/tmp/test-data/sessions"


class TestServerConfig:
    def test_default(self) -> None:
        config = ServerConfig()
        assert config.port == 8100


class TestCompactConfig:
    def test_default(self) -> None:
        config = CompactConfig()
        assert config.context_window == 200_000
        assert config.output_reserve == 20_000
        assert config.keep_recent_tool_results == 3
        assert config.min_savings_threshold == 20_000
        assert config.auto_compact_buffer == 13_000
        assert config.auto_compact_enabled is True
        assert config.microcompact_enabled is True

    def test_derived_properties(self) -> None:
        config = CompactConfig()
        assert config.effective_window == 180_000
        assert config.microcompact_threshold == 160_000
        assert config.full_compact_threshold == 167_000
