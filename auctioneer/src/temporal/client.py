"""Temporal 客户端工厂（地址从环境变量 TEMPORAL_HOST 读取）。"""

from __future__ import annotations

from agent_sdk._config.settings import TemporalConfig
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

TASK_QUEUE: str = "auction-queue"


async def get_client() -> Client:
    """创建 Temporal 客户端，地址取自 TEMPORAL_HOST 环境变量。"""
    config: TemporalConfig = TemporalConfig()
    return await Client.connect(config.host, data_converter=pydantic_data_converter)
