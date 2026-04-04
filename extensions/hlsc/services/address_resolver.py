"""地址解析服务：统一处理地址 → 经纬度的转换。

所有需要经纬度的 tool 通过此模块获取坐标，LLM 层面无需感知经纬度。

解析策略：
- address=None → 从 request_context 取用户当前位置（含经纬度）
  - 如果 request_context 也没有 → interrupt 让前端弹地图选点
- address="南京西路" → 调 address service 转经纬度
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import httpx
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end

ADDRESS_SERVICE_URL: str = os.getenv("ADDRESS_SERVICE_URL", "http://localhost:8092")


@dataclass
class ResolvedLocation:
    """解析后的位置信息"""
    lat: float
    lng: float
    address: str
    province: str = ""
    city: str = ""
    district: str = ""


async def resolve_location(
    ctx: RunContext[AgentDeps],
    address: Optional[str],
    tool_name: str = "",
) -> ResolvedLocation:
    """解析地址为经纬度。

    Args:
        ctx: RunContext，用于读取 request_context 和发起 interrupt
        address: 地址文本；None 表示使用用户当前位置
        tool_name: 调用方工具名，用于日志

    Returns:
        ResolvedLocation 包含 lat/lng/address 等

    Raises:
        ValueError: 地址解析失败
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id

    if address is None:
        # 从 request_context 取用户位置
        return await _resolve_from_context(ctx, tool_name)
    else:
        # 调 address service 解析
        return await _resolve_from_service(address, sid, rid, tool_name)


async def _resolve_from_context(
    ctx: RunContext[AgentDeps],
    tool_name: str,
) -> ResolvedLocation:
    """从 request_context 获取用户位置，没有则 interrupt。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id

    # 尝试从 request_context 取
    req_ctx = ctx.deps.request_context
    if req_ctx is not None:
        loc = None
        if isinstance(req_ctx, dict):
            loc = req_ctx.get("current_location")
        else:
            loc = getattr(req_ctx, "current_location", None)

        if loc is not None:
            lat: Optional[float] = None
            lng: Optional[float] = None
            addr: str = ""
            if isinstance(loc, dict):
                lat = loc.get("lat")
                lng = loc.get("lng")
                addr = loc.get("address", "")
            else:
                lat = getattr(loc, "lat", None)
                lng = getattr(loc, "lng", None)
                addr = getattr(loc, "address", "")

            if lat is not None and lng is not None:
                log_tool_end(f"address_resolver({tool_name})", sid, rid,
                             {"source": "request_context", "address": addr})
                return ResolvedLocation(lat=lat, lng=lng, address=addr)

    # request_context 没有位置 → interrupt 让前端弹地图选点
    log_tool_start(f"address_resolver({tool_name})", sid, rid,
                   {"action": "interrupt_select_location"})

    reply: str = await call_interrupt(ctx, {
        "type": "select_location",
        "question": "需要您的位置信息，请选择或确认您的位置",
    })

    try:
        data: dict = json.loads(reply)
        lat_val: Optional[float] = data.get("lat")
        lng_val: Optional[float] = data.get("lng")
        addr_val: str = data.get("address", "")
        if lat_val is not None and lng_val is not None:
            log_tool_end(f"address_resolver({tool_name})", sid, rid,
                         {"source": "interrupt", "address": addr_val})
            return ResolvedLocation(lat=lat_val, lng=lng_val, address=addr_val)
    except (json.JSONDecodeError, AttributeError):
        pass

    raise ValueError("无法获取用户位置信息")


async def _resolve_from_service(
    address: str,
    session_id: str,
    request_id: str,
    tool_name: str,
) -> ResolvedLocation:
    """调用 address service 将地址文本转为经纬度。"""
    url: str = f"{ADDRESS_SERVICE_URL.rstrip('/')}/api/address/geocode"
    payload: dict[str, str] = {"address": address}

    log_tool_start(f"address_resolver({tool_name})", session_id, request_id,
                   {"action": "call_address_service", "address": address})

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()

            if data.get("status") != 0:
                msg: str = data.get("message", "地址解析失败")
                raise ValueError(f"地址解析失败: {msg}")

            result: dict = data.get("result", {})
            lat: float = result.get("latitude", 0.0)
            lng: float = result.get("longitude", 0.0)
            if lat == 0.0 and lng == 0.0:
                raise ValueError(f"地址解析结果无效: {address}")

            resolved: ResolvedLocation = ResolvedLocation(
                lat=lat,
                lng=lng,
                address=result.get("formattedAddress", address),
                province=result.get("province", ""),
                city=result.get("city", ""),
                district=result.get("district", ""),
            )

            log_tool_end(f"address_resolver({tool_name})", session_id, request_id,
                         {"source": "address_service", "lat": lat, "lng": lng})
            return resolved

    except httpx.HTTPError as e:
        raise ValueError(f"地址服务请求异常: {e}")
