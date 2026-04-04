"""address_resolver 单元测试

4 个测试：
1. test_resolve_from_context_with_location — request_context 有 current_location → 直接返回
2. test_resolve_from_context_without_location_interrupt — 无位置 → interrupt → 返回经纬度
3. test_resolve_from_service_success — 地址文本 → address service → 返回经纬度
4. test_resolve_from_service_failure — address service 返回错误 → 抛 ValueError

运行方式：
    cd mainagent && uv run pytest ../tests/test_address_resolver.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 确保 extensions 和 sdk 可 import
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "extensions"))
sys.path.insert(0, str(PROJECT_ROOT / "sdk"))

from hlsc.services.address_resolver import ResolvedLocation, resolve_location


# ── 辅助：构造 mock RunContext[AgentDeps] ──


def _make_ctx(
    *,
    current_location: dict[str, Any] | None = None,
    session_id: str = "test-session",
    request_id: str = "test-request",
) -> MagicMock:
    """构造最小化的 RunContext[AgentDeps] mock。"""
    deps: MagicMock = MagicMock()
    deps.session_id = session_id
    deps.request_id = request_id

    if current_location is not None:
        # request_context 是 dict，current_location 也是 dict
        deps.request_context = {"current_location": current_location}
    else:
        deps.request_context = {}

    ctx: MagicMock = MagicMock()
    ctx.deps = deps
    return ctx


# ============================================================
# 测试用例
# ============================================================


@pytest.mark.asyncio
async def test_resolve_from_context_with_location() -> None:
    """request_context 有 current_location(lat/lng) → 直接返回，不调 service 也不 interrupt。"""
    location_data: dict[str, Any] = {
        "lat": 31.2035,
        "lng": 121.5914,
        "address": "上海市浦东新区张江高科",
    }
    ctx: MagicMock = _make_ctx(current_location=location_data)

    result: ResolvedLocation = await resolve_location(ctx, address=None, tool_name="test")

    assert result.lat == 31.2035
    assert result.lng == 121.5914
    assert result.address == "上海市浦东新区张江高科"


@pytest.mark.asyncio
@patch("hlsc.services.address_resolver.call_interrupt", new_callable=AsyncMock)
async def test_resolve_from_context_without_location_interrupt(
    mock_interrupt: AsyncMock,
) -> None:
    """request_context 无位置信息 → 触发 call_interrupt → 从用户回复解析经纬度。"""
    # interrupt 返回 JSON 字符串（模拟前端地图选点结果）
    interrupt_reply: dict[str, Any] = {
        "lat": 39.9042,
        "lng": 116.4074,
        "address": "北京市东城区天安门",
    }
    mock_interrupt.return_value = json.dumps(interrupt_reply)

    ctx: MagicMock = _make_ctx(current_location=None)

    result: ResolvedLocation = await resolve_location(ctx, address=None, tool_name="test")

    assert result.lat == 39.9042
    assert result.lng == 116.4074
    assert result.address == "北京市东城区天安门"

    # 确认 interrupt 被调用，且 type 是 select_location
    mock_interrupt.assert_awaited_once()
    call_args: dict[str, Any] = mock_interrupt.call_args[0][1]
    assert call_args["type"] == "select_location"


@pytest.mark.asyncio
@patch("hlsc.services.address_resolver.httpx.AsyncClient")
async def test_resolve_from_service_success(
    mock_client_cls: MagicMock,
) -> None:
    """address="南京西路" → 调 address service 成功 → 返回经纬度。"""
    # 构造 mock httpx 响应
    mock_response: MagicMock = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "status": 0,
        "result": {
            "latitude": 31.2294,
            "longitude": 121.4507,
            "formattedAddress": "上海市静安区南京西路",
            "province": "上海市",
            "city": "上海市",
            "district": "静安区",
        },
    }

    # mock AsyncClient 的 __aenter__ 返回一个带 post 方法的对象
    mock_client: AsyncMock = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    ctx: MagicMock = _make_ctx()

    result: ResolvedLocation = await resolve_location(ctx, address="南京西路", tool_name="test")

    assert result.lat == 31.2294
    assert result.lng == 121.4507
    assert result.address == "上海市静安区南京西路"
    assert result.province == "上海市"
    assert result.city == "上海市"
    assert result.district == "静安区"

    # 确认 HTTP POST 被正确调用
    mock_client.post.assert_awaited_once()
    post_kwargs: dict[str, Any] = mock_client.post.call_args
    assert "南京西路" in str(post_kwargs)


@pytest.mark.asyncio
@patch("hlsc.services.address_resolver.httpx.AsyncClient")
async def test_resolve_from_service_failure(
    mock_client_cls: MagicMock,
) -> None:
    """address service 返回 status != 0 → 抛出 ValueError。"""
    mock_response: MagicMock = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "status": -1,
        "message": "地址未找到",
    }

    mock_client: AsyncMock = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    ctx: MagicMock = _make_ctx()

    with pytest.raises(ValueError, match="地址解析失败"):
        await resolve_location(ctx, address="不存在的地址", tool_name="test")
