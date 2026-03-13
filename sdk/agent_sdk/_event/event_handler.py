"""事件处理中枢：接收原始事件，转换为 EventModel，派发到 Sinker"""

from __future__ import annotations

import logging

from agent_sdk._common.event_sinker import EventSinker
from agent_sdk._event.event_model import EventModel

logger = logging.getLogger(__name__)


class EventHandler:
    """接收 Agent 原始事件，转换后派发到 sinker。

    支持多个 sinker，单个 sinker 异常不影响其他 sinker。
    """

    def __init__(self, sinker: EventSinker | None = None, sinkers: list[EventSinker] | None = None) -> None:
        self._sinkers: list[EventSinker] = []
        if sinker is not None:
            self._sinkers.append(sinker)
        if sinkers is not None:
            self._sinkers.extend(sinkers)

    async def handle(self, event: EventModel) -> None:
        """接收一个事件，派发到所有 sinker。单个 sinker 异常不影响其他。"""
        for sinker in self._sinkers:
            try:
                await sinker.send(event)
            except Exception:
                logger.warning("sinker %s.send() 异常，已跳过", type(sinker).__name__, exc_info=True)

    async def close(self) -> None:
        """通知所有 sinker 关闭。"""
        for sinker in self._sinkers:
            try:
                await sinker.close()
            except Exception:
                logger.warning("sinker %s.close() 异常，已跳过", type(sinker).__name__, exc_info=True)
