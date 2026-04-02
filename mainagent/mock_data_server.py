#!/usr/bin/env python3
"""Mock DataManager 服务：在本地运行，模拟数据管理服务的优惠查询接口。

启动方式：
    uv run python mock_data_server.py
    uv run python mock_data_server.py --port 50400
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from uvicorn import run

from data.mock_coupons import (
    COUPONS_BY_DISCOUNT_AMOUNT,
    COUPONS_EMPTY,
    COUPONS_EXPIRING_SOON,
    COUPONS_PLATFORM_ONLY,
    COUPONS_WITH_BOTH,
)

app: FastAPI = FastAPI(title="Mock DataManager Service", version="1.0.0")


@app.post("/service_ai_datamanager/Discount/recommend")
async def recommend_discounts(request: Request) -> dict[str, Any]:
    """
    模拟 Discount/recommend 接口。

    根据查询参数返回不同的 mock 数据：
    - semantic_query 包含 "error" → 返回错误
    - semantic_query 包含 "empty" → 返回空结果
    - semantic_query 包含 "expiring" → 返回即将过期优惠
    - semantic_query 包含 "discount_amount" → 按金额排序
    - 其他 → 返回有商户 + 平台优惠的完整结果
    """
    body: dict[str, Any] = await request.json()
    semantic_query: str = body.get("semanticQuery", "").lower()

    print(f"[MOCK] POST /Discount/recommend")
    print(f"  Params: {json.dumps(body, ensure_ascii=False, indent=2)}")

    # 根据 semantic_query 返回不同场景
    if "error" in semantic_query:
        response: dict[str, Any] = COUPONS_EMPTY  # 实际应返回错误
        print(f"  → Scenario: error (empty result)")
    elif "empty" in semantic_query:
        response = COUPONS_EMPTY
        print(f"  → Scenario: empty (no coupons)")
    elif "expiring" in semantic_query:
        response = COUPONS_EXPIRING_SOON
        print(f"  → Scenario: expiring soon (priority)")
    elif "discount_amount" in semantic_query or body.get("sortBy") == "discount_amount":
        response = COUPONS_BY_DISCOUNT_AMOUNT
        print(f"  → Scenario: sort by discount amount")
    elif not semantic_query and not body.get("projectIds"):
        # 参数为空 → 返回平台优惠
        response = COUPONS_PLATFORM_ONLY
        print(f"  → Scenario: platform only (no semantic query)")
    else:
        # 默认返回完整结果
        response = COUPONS_WITH_BOTH
        print(f"  → Scenario: full (shop + platform coupons)")

    print(f"  ✓ Returning {len(response['result']['platformActivities'])} platform + "
          f"{len(response['result']['shopActivities'])} shop activities\n")
    return response


@app.post("/service_ai_datamanager/Discount/apply")
async def apply_coupon(request: Request) -> dict[str, Any]:
    """模拟 Discount/apply 接口（生成联系单）。"""
    body: dict[str, Any] = await request.json()
    activity_id: str = str(body.get("activityId", ""))
    shop_id: str = str(body.get("shopId", ""))
    visit_time: str = body.get("visitTime", "")

    print(f"[MOCK] POST /Discount/apply")
    print(f"  Activity: {activity_id}, Shop: {shop_id}, Time: {visit_time}")

    response: dict[str, Any] = {
        "status": 0,
        "message": "success",
        "result": {
            "orderId": f"MOCK-ORDER-{activity_id}-{shop_id}",
            "activityName": f"优惠活动 {activity_id}",
            "shopName": f"商户 {shop_id}",
            "visitTime": visit_time,
        },
    }

    print(f"  ✓ Generated contact order: {response['result']['orderId']}\n")
    return response


@app.get("/health")
async def health_check() -> dict[str, str]:
    """健康检查。"""
    return {"status": "healthy", "service": "Mock DataManager"}


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Mock DataManager Service"
    )
    parser.add_argument("--port", type=int, default=50400, help="Server port (default: 50400)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    args: argparse.Namespace = parser.parse_args()

    print(f"🚀 Starting Mock DataManager on {args.host}:{args.port}")
    print(f"   Endpoint: http://{args.host}:{args.port}/service_ai_datamanager/Discount/recommend")
    print(f"   Health: http://{args.host}:{args.port}/health\n")

    run(app, host=args.host, port=args.port, log_level="info")
