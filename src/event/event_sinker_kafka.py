"""Kafka Sinker 实现：将事件发布到 Kafka topic"""

from __future__ import annotations

import logging

from aiokafka import AIOKafkaProducer

from src.event.event_model import EventModel

logger = logging.getLogger(__name__)


class KafkaSinker:
    """将事件发布到 Kafka topic。"""

    def __init__(self, producer: AIOKafkaProducer, topic: str) -> None:
        self._producer: AIOKafkaProducer = producer
        self._topic: str = topic

    async def send(self, event: EventModel) -> None:
        """发布事件到 Kafka。"""
        await self._producer.send(self._topic, event.to_json().encode("utf-8"))

    async def close(self) -> None:
        """刷新 producer 缓冲（不关闭 producer，由全局管理）。"""
        # producer 是共享的，这里只 flush 不 close
        pass


# ── Kafka Producer 全局管理 ──────────────────────────────────────

_producer: AIOKafkaProducer | None = None


async def get_kafka_producer() -> AIOKafkaProducer:
    """获取全局共享的 Kafka producer（懒初始化）。"""
    global _producer
    if _producer is None:
        from src.config.settings import get_kafka_config

        config = get_kafka_config()
        _producer = AIOKafkaProducer(
            bootstrap_servers=config.bootstrap_servers,
        )
        await _producer.start()
        logger.info("Kafka producer 已启动: %s", config.bootstrap_servers)
    return _producer


async def close_kafka_producer() -> None:
    """关闭全局 Kafka producer。"""
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer 已关闭")
