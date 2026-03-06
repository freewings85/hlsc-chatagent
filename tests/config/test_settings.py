"""配置模块测试"""

from src.agent.compact.config import CompactConfig
from src.config import settings
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


class TestSingletons:
    def test_get_llm_config(self) -> None:
        # 重置单例
        settings._llm_config = None
        config = settings.get_llm_config()
        assert isinstance(config, LLMConfig)
        # 二次调用返回同一实例
        assert settings.get_llm_config() is config

    def test_get_server_config(self) -> None:
        settings._server_config = None
        config = settings.get_server_config()
        assert isinstance(config, ServerConfig)
        assert settings.get_server_config() is config


class TestSingletonsEdgeCases:
    """US-007: 配置系统单例安全"""

    def test_get_llm_config_returns_same_instance(self) -> None:
        """get_llm_config() 多次调用返回同一实例"""
        settings._llm_config = None
        c1 = settings.get_llm_config()
        c2 = settings.get_llm_config()
        c3 = settings.get_llm_config()
        assert c1 is c2
        assert c2 is c3

    def test_get_compact_config_singleton(self) -> None:
        """get_compact_config() 多次调用返回同一实例"""
        settings._compact_config = None
        c1 = settings.get_compact_config()
        c2 = settings.get_compact_config()
        assert c1 is c2

    def test_get_storage_config_singleton(self) -> None:
        """get_storage_config() 多次调用返回同一实例"""
        settings._storage_config = None
        c1 = settings.get_storage_config()
        c2 = settings.get_storage_config()
        assert c1 is c2

    def test_get_backend_singleton(self) -> None:
        """get_backend() 多次调用返回同一实例"""
        settings._backend = None
        b1 = settings.get_backend()
        b2 = settings.get_backend()
        assert b1 is b2


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
