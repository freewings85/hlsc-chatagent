"""LLM 模型工厂测试"""

from unittest.mock import patch

from src.sdk._agent.model import create_model
from src.sdk._config.settings import LLMConfig


class TestCreateModel:

    def test_azure_model(self) -> None:
        config = LLMConfig(
            llm_type="azure",
            azure_endpoint="https://test.openai.azure.com/",
            azure_api_key="test-key",
            azure_api_version="2024-12-01-preview",
            azure_deployment_name="gpt-4o",
        )
        model = create_model(config)
        assert model is not None

    def test_openai_model(self) -> None:
        config = LLMConfig(
            llm_type="openai",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        )
        model = create_model(config)
        assert model is not None

    def test_openai_model_no_base_url(self) -> None:
        config = LLMConfig(
            llm_type="openai",
            api_key="test-key",
            base_url="",
            model="gpt-4o",
        )
        model = create_model(config)
        assert model is not None

    def test_default_config(self) -> None:
        """不传 config 使用 get_llm_config()"""
        with patch("src.sdk._agent.model.get_llm_config") as mock_get:
            mock_get.return_value = LLMConfig(
                llm_type="openai", api_key="k", model="m",
            )
            model = create_model()
            mock_get.assert_called_once()
            assert model is not None


class TestModelFactoryEdgeCases:
    """US-007: Model Factory 边界条件"""

    def test_azure_empty_api_key_still_creates_model(self) -> None:
        """Azure 缺少 api_key 时仍能创建 model 实例（调用时才失败）"""
        config = LLMConfig(
            llm_type="azure",
            azure_endpoint="https://test.openai.azure.com/",
            azure_api_key="",  # 空 api_key
            azure_deployment_name="gpt-4o",
        )
        model = create_model(config)
        # model 实例可以创建，只是调用时会失败
        assert model is not None

    def test_openai_empty_api_key_still_creates_model(self) -> None:
        """OpenAI 缺少 api_key 时仍能创建 model 实例"""
        config = LLMConfig(
            llm_type="openai",
            api_key="",  # 空 api_key
            model="gpt-4o",
        )
        model = create_model(config)
        assert model is not None

    def test_switch_azure_to_openai(self) -> None:
        """create_model() 支持 Azure 和 OpenAI 两种模式切换"""
        azure_config = LLMConfig(
            llm_type="azure",
            azure_endpoint="https://test.openai.azure.com/",
            azure_api_key="key1",
            azure_deployment_name="gpt-4o",
        )
        openai_config = LLMConfig(
            llm_type="openai",
            api_key="key2",
            model="gpt-4o-mini",
        )

        azure_model = create_model(azure_config)
        openai_model = create_model(openai_config)

        assert azure_model is not None
        assert openai_model is not None
        # 两个模型应该是不同的实例
        assert azure_model is not openai_model
