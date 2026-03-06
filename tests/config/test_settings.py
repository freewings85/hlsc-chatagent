"""配置模块测试"""

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
