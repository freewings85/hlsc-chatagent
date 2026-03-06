"""EventHandler + SseSinker + EventModel 测试"""

import asyncio

import pytest

from src.event.event_handler import EventHandler
from src.event.event_model import EventModel
from src.event.event_sinker_sse import SseSinker
from src.event.event_type import EventType
from tests.conftest import MockSinker


class TestEventHandler:

    @pytest.mark.asyncio
    async def test_handle_dispatches_to_sinker(self) -> None:
        sinker = MockSinker()
        handler = EventHandler(sinker)
        event = EventModel(
            conversation_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "hi"},
        )
        await handler.handle(event)
        assert len(sinker.events) == 1
        assert sinker.events[0] is event

    @pytest.mark.asyncio
    async def test_close_delegates_to_sinker(self) -> None:
        sinker = MockSinker()
        handler = EventHandler(sinker)
        await handler.close()
        assert sinker.closed is True


class TestSseSinker:

    @pytest.mark.asyncio
    async def test_send_puts_event_in_queue(self) -> None:
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        sinker = SseSinker(queue)
        event = EventModel(
            conversation_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "hello"},
        )
        await sinker.send(event)
        assert await queue.get() is event

    @pytest.mark.asyncio
    async def test_close_sends_sentinel(self) -> None:
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        sinker = SseSinker(queue)
        await sinker.close()
        assert await queue.get() is None


class TestEventModel:

    def test_to_dict(self) -> None:
        event = EventModel(
            conversation_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "hi"},
            timestamp=1000, finish_reason="stop",
        )
        d = event.to_dict()
        assert d["conversation_id"] == "c1"
        assert d["type"] == "text"
        assert d["finish_reason"] == "stop"
        assert d["agent_name"] == "main"

    def test_to_json(self) -> None:
        event = EventModel(
            conversation_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "hi"},
            timestamp=1000,
        )
        json_str = event.to_json()
        assert '"conversation_id": "c1"' in json_str
        assert '"type": "text"' in json_str
