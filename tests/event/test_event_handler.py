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
            session_id="c1", request_id="r1",
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
            session_id="c1", request_id="r1",
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


class TestEventEmitterEdgeCases:
    """US-004: EventEmitter close 后 emit 不抛异常"""

    @pytest.mark.asyncio
    async def test_emit_after_close_silent(self) -> None:
        """close() 后再 emit() 静默丢弃，不抛异常"""
        from src.event.event_emitter import EventEmitter
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)

        await emitter.close()
        # close 后 emit 不应抛异常
        event = EventModel(
            session_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "after close"},
        )
        await emitter.emit(event)  # 应该静默丢弃

        # queue 中只有 sentinel
        item = await queue.get()
        assert item is None
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_double_close_safe(self) -> None:
        """多次 close() 只放一个 sentinel"""
        from src.event.event_emitter import EventEmitter
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)

        await emitter.close()
        await emitter.close()

        assert await queue.get() is None
        assert queue.empty()


class TestEventHandlerMultipleSinkers:
    """US-004: sinker 异常不影响其他 sinker"""

    @pytest.mark.asyncio
    async def test_bad_sinker_does_not_block_others(self) -> None:
        """一个 sinker 抛异常不影响其他 sinker"""

        class BadSinker:
            async def send(self, event: EventModel) -> None:
                raise RuntimeError("sinker exploded")
            async def close(self) -> None:
                raise RuntimeError("close exploded")

        good_sinker = MockSinker()
        bad_sinker = BadSinker()

        handler = EventHandler(sinkers=[bad_sinker, good_sinker])
        event = EventModel(
            session_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "hi"},
        )

        # 不应抛异常
        await handler.handle(event)
        assert len(good_sinker.events) == 1

        # close 也不应抛异常
        await handler.close()
        assert good_sinker.closed is True


class TestEventModel:

    def test_to_dict(self) -> None:
        event = EventModel(
            session_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "hi"},
            timestamp=1000, finish_reason="stop",
        )
        d = event.to_dict()
        assert d["session_id"] == "c1"
        assert d["type"] == "text"
        assert d["finish_reason"] == "stop"
        assert d["agent_name"] == "main"

    def test_to_json(self) -> None:
        event = EventModel(
            session_id="c1", request_id="r1",
            type=EventType.TEXT, data={"content": "hi"},
            timestamp=1000,
        )
        json_str = event.to_json()
        assert '"session_id": "c1"' in json_str
        assert '"type": "text"' in json_str

    def test_all_event_types_serializable(self) -> None:
        """所有 EventType 都能正确序列化 to_dict() 和 to_json()"""
        import json
        for event_type in EventType:
            event = EventModel(
                session_id="c1", request_id="r1",
                type=event_type, data={"key": "value"},
                timestamp=1000,
            )
            d = event.to_dict()
            assert d["type"] == event_type.value
            assert isinstance(d["data"], dict)

            json_str = event.to_json()
            parsed = json.loads(json_str)
            assert parsed["type"] == event_type.value
