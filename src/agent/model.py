"""LLM 模型工厂：根据配置创建 Pydantic AI Model"""

from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncAzureOpenAI, AsyncOpenAI

from src.config.settings import LLMConfig, get_llm_config


def create_model(config: LLMConfig | None = None) -> Model:
    """根据配置创建 Pydantic AI Model 实例"""
    if config is None:
        config = get_llm_config()

    if config.llm_type == "azure":
        client: AsyncOpenAI = AsyncAzureOpenAI(
            azure_endpoint=config.azure_endpoint,
            api_key=config.azure_api_key,
            api_version=config.azure_api_version,
        )
        provider: OpenAIProvider = OpenAIProvider(openai_client=client)
        model: Model = OpenAIChatModel(config.azure_deployment_name, provider=provider)
        return model
    else:
        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        provider = OpenAIProvider(openai_client=client)
        model = OpenAIChatModel(config.model, provider=provider)
        return model
