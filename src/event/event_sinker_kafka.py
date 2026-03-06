"""Kafka Sinker 实现：将事件发布到 Kafka topic（占位）"""

from __future__ import annotations

from typing import Any

from src.event.event_model import EventModel


class KafkaSinker:
    """将事件发布到 Kafka topic。"""

    def __init__(self, producer: Any, topic: str) -> None:
        self._producer: Any = producer
        self._topic: str = topic

    async def send(self, event: EventModel) -> None:
        """发布事件到 Kafka。"""
        await self._producer.send(self._topic, event.to_json().encode())

    async def close(self) -> None:
        """刷新 producer 缓冲。"""
        await self._producer.flush()
