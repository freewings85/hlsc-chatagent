"""After-run hooks：Agent 运行结束后的异步副作用

hook 始终被调用（只要不是子 agent 且未抛异常），
由 hook 自身根据 context.result 决定是否执行实际动作。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from agent_sdk._agent.loop import RunLoopResult

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class AfterRunContext:
    """传递给 hook 的回调上下文。

    包含定位信息 + 本轮运行结果，hook 自行决定基于什么条件执行。
    """

    user_id: str
    session_id: str
    request_id: str
    result: RunLoopResult


class AfterRunHook(Protocol):
    """Agent 运行结束后的钩子签名。

    主 agent 每轮请求结束（未抛异常）时调用。
    hook 应检查 context.result.finish_reason / transcript_persisted 判断是否执行。
    """

    async def __call__(self, context: AfterRunContext) -> None: ...


class ProfileTriggerHook:
    """发布画像提取触发事件到专用 Kafka topic。

    仅在 finish_reason == "completed" 且 transcript 已持久化时发送。
    """

    def __init__(self, topic: str | None = None) -> None:
        self._topic: str | None = topic
        self._producer: Any = None

    async def __call__(self, context: AfterRunContext) -> None:
        if context.result.finish_reason != "completed":
            return
        if not context.result.transcript_persisted:
            return

        from agent_sdk._config.settings import get_kafka_config

        kafka_config = get_kafka_config()
        if not kafka_config.enabled:
            return

        topic: str = self._topic or kafka_config.profile_topic

        if self._producer is None:
            from agent_sdk._event.event_sinker_kafka import get_kafka_producer

            self._producer = await get_kafka_producer()

        payload: dict[str, Any] = {
            "event_type": "profile_trigger_ready",
            "user_id": context.user_id,
            "session_id": context.session_id,
            "request_id": context.request_id,
            "timestamp": int(time.time() * 1000),
        }
        await self._producer.send(
            topic,
            key=context.user_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
        )
        logger.debug(
            "profile trigger sent: user=%s session=%s request=%s",
            context.user_id, context.session_id, context.request_id,
        )
