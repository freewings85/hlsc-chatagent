"""LLM 模型工厂测试"""

from unittest.mock import patch

from src.agent.model import create_model
from src.config.settings import LLMConfig


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
        with patch("src.agent.model.get_llm_config") as mock_get:
            mock_get.return_value = LLMConfig(
                llm_type="openai", api_key="k", model="m",
            )
            model = create_model()
            mock_get.assert_called_once()
            assert model is not None
