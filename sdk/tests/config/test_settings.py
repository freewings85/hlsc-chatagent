"""配置模块测试"""

from agent_sdk._agent.compact.config import CompactConfig
from agent_sdk._config import settings
from agent_sdk._config.settings import LLMConfig, DataDirConfig, AgentFsConfig, ServerConfig


class TestLLMConfig:
    def test_default(self) -> None:
        config = LLMConfig()
        assert config.llm_type in ("azure", "openai", "")


class TestUserFsConfig:
    def test_default(self) -> None:
        config = DataDirConfig()
        assert "inner" in config.inner_dir
        assert "fstools" in config.fstools_dir

    def test_data_dir(self) -> None:
        config = DataDirConfig(data_dir="/tmp/test-data")
        assert config.data_dir == "/tmp/test-data"
        assert config.inner_dir == "/tmp/test-data/inner"
        assert config.fstools_dir == "/tmp/test-data/fstools"


class TestAgentFsConfig:
    def test_default(self) -> None:
        config = AgentFsConfig()
        assert config.agent_fs_dir == ".chatagent"


class TestServerConfig:
    def test_default(self) -> None:
        config = ServerConfig()
        assert config.port == 8100


class TestSingletons:
    def test_get_llm_config(self) -> None:
        settings._llm_config = None
        config = settings.get_llm_config()
        assert isinstance(config, LLMConfig)
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

    def test_get_user_fs_config_singleton(self) -> None:
        """get_user_fs_config() 多次调用返回同一实例"""
        settings._user_fs_config = None
        c1 = settings.get_user_fs_config()
        c2 = settings.get_user_fs_config()
        assert c1 is c2

    def test_get_user_fs_backend_singleton(self) -> None:
        """get_user_fs_backend() 多次调用返回同一实例"""
        settings._user_fs_backend = None
        b1 = settings.get_user_fs_backend()
        b2 = settings.get_user_fs_backend()
        assert b1 is b2

    def test_get_agent_fs_config_singleton(self) -> None:
        """get_agent_fs_config() 多次调用返回同一实例"""
        settings._agent_fs_config = None
        c1 = settings.get_agent_fs_config()
        c2 = settings.get_agent_fs_config()
        assert c1 is c2

    def test_get_agent_fs_backend_singleton(self) -> None:
        """get_agent_fs_backend() 多次调用返回同一实例"""
        settings._agent_fs_backend = None
        b1 = settings.get_agent_fs_backend()
        b2 = settings.get_agent_fs_backend()
        assert b1 is b2

    def test_backward_compat_aliases(self) -> None:
        """get_backend / get_storage_config 是向后兼容别名"""
        assert settings.get_backend is settings.get_fs_tools_backend
        assert settings.get_storage_config is settings.get_user_fs_config


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
