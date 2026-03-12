"""MemoryContextService 测试"""

from __future__ import annotations

import pytest

from src.agent.memory.inmemory_context_service import InMemoryContextService
from src.common.request_context import RequestContext


class SampleContext(RequestContext):
    """测试用上下文子类"""
    city: str | None = None
    vehicle: str | None = None


@pytest.fixture
def service() -> InMemoryContextService:
    return InMemoryContextService()


class TestInMemoryContextService:

    async def test_get_empty(self, service: InMemoryContextService) -> None:
        """未设置时返回 None"""
        result = await service.get("u1", "s1")
        assert result is None

    async def test_set_and_get(self, service: InMemoryContextService) -> None:
        """set 后 get 能拿到"""
        ctx = SampleContext(city="上海")
        await service.set("u1", "s1", ctx)
        result = await service.get("u1", "s1")
        assert result is not None
        assert result.model_dump()["city"] == "上海"

    async def test_get_returns_copy(self, service: InMemoryContextService) -> None:
        """get 返回的是副本"""
        ctx = SampleContext(city="上海")
        await service.set("u1", "s1", ctx)
        result = await service.get("u1", "s1")
        assert result is not ctx

    async def test_session_isolation(self, service: InMemoryContextService) -> None:
        """不同 session 隔离"""
        await service.set("u1", "s1", SampleContext(city="上海"))
        await service.set("u1", "s2", SampleContext(city="北京"))
        r1 = await service.get("u1", "s1")
        r2 = await service.get("u1", "s2")
        assert r1 is not None and r1.model_dump()["city"] == "上海"
        assert r2 is not None and r2.model_dump()["city"] == "北京"

    async def test_user_isolation(self, service: InMemoryContextService) -> None:
        """不同用户隔离"""
        await service.set("u1", "s1", SampleContext(city="上海"))
        await service.set("u2", "s1", SampleContext(city="广州"))
        r1 = await service.get("u1", "s1")
        r2 = await service.get("u2", "s1")
        assert r1 is not None and r1.model_dump()["city"] == "上海"
        assert r2 is not None and r2.model_dump()["city"] == "广州"

    async def test_diff_first_time(self, service: InMemoryContextService) -> None:
        """首次 diff，所有非 None 字段都是变化"""
        ctx = SampleContext(city="上海", vehicle="宝马")
        result = await service.diff("u1", "s1", ctx)
        assert result == {"city": "上海", "vehicle": "宝马"}

    async def test_diff_no_change(self, service: InMemoryContextService) -> None:
        """context 没变，返回 None"""
        ctx = SampleContext(city="上海")
        await service.set("u1", "s1", ctx)
        result = await service.diff("u1", "s1", SampleContext(city="上海"))
        assert result is None

    async def test_diff_partial_change(self, service: InMemoryContextService) -> None:
        """只返回变化的字段"""
        await service.set("u1", "s1", SampleContext(city="上海", vehicle="宝马"))
        result = await service.diff("u1", "s1", SampleContext(city="上海", vehicle="奔驰"))
        assert result == {"vehicle": "奔驰"}

    async def test_diff_new_field(self, service: InMemoryContextService) -> None:
        """新增字段也算变化"""
        await service.set("u1", "s1", SampleContext(city="上海"))
        result = await service.diff("u1", "s1", SampleContext(city="上海", vehicle="宝马"))
        assert result == {"vehicle": "宝马"}

    async def test_diff_empty_context(self, service: InMemoryContextService) -> None:
        """空 context（所有字段为 None）返回 None"""
        result = await service.diff("u1", "s1", SampleContext())
        assert result is None

    async def test_overwrite(self, service: InMemoryContextService) -> None:
        """set 覆盖旧值"""
        await service.set("u1", "s1", SampleContext(city="上海"))
        await service.set("u1", "s1", SampleContext(city="北京"))
        result = await service.get("u1", "s1")
        assert result is not None and result.model_dump()["city"] == "北京"

    async def test_format_changed_default(self, service: InMemoryContextService) -> None:
        """默认 formatter 输出 JSON"""
        result = service.format_changed({"city": "上海"})
        assert "上海" in result
        assert "已更新的字段" in result

    async def test_format_changed_custom(self) -> None:
        """自定义 formatter"""
        custom = InMemoryContextService(formatter=lambda c: f"ctx: {list(c.keys())}")
        result = custom.format_changed({"city": "上海", "vehicle": "宝马"})
        assert result == "ctx: ['city', 'vehicle']"
