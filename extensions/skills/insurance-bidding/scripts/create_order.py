"""创建竞价订单 + 启动竞价 — 独立 CLI 脚本，通过 bash 工具执行。

用法：
    python create_order.py --project_id 1461 --shop_ids 87,88 --car_model_id 56
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

import httpx

_logger: logging.Logger = logging.getLogger(__name__)

SERVICE_OWNER_URL: str = os.getenv("SERVICE_OWNER_URL", "")


# ── 参数工具 ─────────────────────────────────────────────────────────────


def _as_int_list(value: str) -> list[int]:
    """逗号分隔字符串 → int list。如 "87,88" → [87, 88]"""
    if not value or not value.strip():
        return []
    return [int(v.strip()) for v in value.split(",") if v.strip()]


# ── 核心逻辑 ─────────────────────────────────────────────────────────────


def create_order(
    owner_id: str,
    conversation_id: str,
    package_list: list[int],
    commercial_list: list[int],
    car_model_id: str = "",
    remark: str = "",
) -> dict:
    """调用 POST /serviceorder/create 创建报价单。"""
    url: str = f"{SERVICE_OWNER_URL}/serviceorder/create"
    payload: dict[str, object] = {
        "ownerId": int(owner_id),
        "conversationId": conversation_id,
        "orderType": 2,
        "packageList": package_list,
        "commercialList": commercial_list,
        "carModelId": car_model_id,
        "demand": remark,
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
    card: dict[str, str] = {
        "order_id": order_id,
        "status": "created",
    }
    card_json: str = json.dumps(card, ensure_ascii=False)
    return (
        f"<!--card:order_created-->\n{card_json}\n<!--/card-->\n"
        f"订单已创建，订单号：{order_id}"
    )


async def start_auction(order_id: str, conversation_id: str) -> None:
    """启动竞价（fire-and-forget）。"""
    from hlsc.services.restful.auctioneer_service import auctioneer_service
    await auctioneer_service.start_auction(order_id, conversation_id)


# ── 入口 ─────────────────────────────────────────────────────────────────


async def main(
    *,
    project_id: int,
    shop_ids: list[int],
    car_model_id: str,
    remark: str = "",
) -> str:
    """创建订单 + 启动竞价，返回 order card。

    owner_id / conversation_id 从环境变量 OWNER_ID / CONVERSATION_ID 读取
    （由 bash 工具自动注入）。
    """
    if not project_id or not shop_ids:
        return "缺少必要参数：project_id 和 shop_ids 不能为空"

    if not SERVICE_OWNER_URL:
        return "缺少 SERVICE_OWNER_URL 环境变量，无法创建订单"

    owner_id: str = os.getenv("OWNER_ID", "")
    if not owner_id:
        return "缺少 OWNER_ID 环境变量，无法创建订单"

    conversation_id: str = os.getenv("CONVERSATION_ID", "")

    try:
        result: dict = create_order(
            owner_id=owner_id,
            conversation_id=conversation_id,
            package_list=[project_id],
            commercial_list=shop_ids,
            car_model_id=car_model_id,
            remark=remark,
        )
    except Exception as e:
        return f"创建订单失败：{e}"

    order_id: str = str(result.get("orderId", ""))

    try:
        await start_auction(order_id, conversation_id)
        _logger.info("竞价启动成功: order_id=%s", order_id)
    except Exception as e:
        _logger.error("竞价启动失败: %s", e, exc_info=True)

    return build_order_card(result)


# ── CLI ──────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建竞价订单")
    parser.add_argument("--project_id", required=True, type=int, help="项目 ID")
    parser.add_argument("--shop_ids", required=True, help="商户 ID，逗号分隔")
    parser.add_argument("--car_model_id", required=True, help="车型 ID")
    parser.add_argument("--remark", default="", help="备注信息")
    args = parser.parse_args()

    output: str = asyncio.run(main(
        project_id=args.project_id,
        shop_ids=_as_int_list(args.shop_ids),
        car_model_id=args.car_model_id,
        remark=args.remark,
    ))
    print(output)
    sys.exit(0)
