"""创建竞价服务订单 — 纯函数模块，由 confirm_information.py 调用。"""

from __future__ import annotations

import json
import os

import httpx

SERVICEORDER_URL: str = os.getenv(
    "SERVICEORDER_URL", "http://192.168.100.108:50201/service_owner",
)


def create_order(
    owner_id: str,
    conversation_id: str,
    package_list: list[int],
    commercial_list: list[int],
    demand: str,
) -> dict:
    """调用 POST /serviceorder/create 创建报价单。"""
    url: str = f"{SERVICEORDER_URL}/serviceorder/create"
    payload: dict[str, object] = {
        "ownerId": int(owner_id) if owner_id.isdigit() else 307,
        "conversationId": conversation_id,
        "orderType": 2,
        "packageList": package_list,
        "commercialList": commercial_list,
        "demand": demand,
    }
    resp: httpx.Response = httpx.post(url, json=payload, timeout=15.0)
    resp.raise_for_status()
    data: dict = resp.json()
    if data.get("status") == 0:
        return data.get("result", {})
    raise RuntimeError(f"创建订单失败: {data.get('message', '未知错误')}")


def build_order_card(result: dict) -> str:
    """构建 order_created 卡片文本。"""
    order_id: str = str(result.get("orderId", ""))
    card: dict[str, str] = {"order_id": order_id, "status": "created"}
    card_json: str = json.dumps(card, ensure_ascii=False)
    return (
        f"<!--card:order_created-->\n{card_json}\n<!--/card-->\n"
        f"订单已创建，订单号：{order_id}"
    )
