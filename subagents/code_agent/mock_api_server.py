"""业务 API Mock Server — 供 code_agent 开发测试用。

启动：uv run python mock_api_server.py
默认端口：9100
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Mock Business API")

# ── 工单数据 ──

ORDERS = [
    {
        "id": "ORD-20260201-001",
        "customer_name": "张三", "customer_id": "CUS-001",
        "vehicle": "沪A12345 大众帕萨特 2020款",
        "status": "completed",
        "total_amount": 680.00,
        "shop_name": "张江汽修中心", "shop_id": "SHOP-001",
        "created_at": "2026-02-01T10:00:00Z",
        "completed_at": "2026-02-01T16:00:00Z",
        "description": "更换刹车片+四轮定位",
    },
    {
        "id": "ORD-20260205-002",
        "customer_name": "李四", "customer_id": "CUS-002",
        "vehicle": "沪B67890 丰田卡罗拉 2021款",
        "status": "completed",
        "total_amount": 1200.00,
        "shop_name": "浦东汽修店", "shop_id": "SHOP-002",
        "created_at": "2026-02-05T09:00:00Z",
        "completed_at": "2026-02-05T18:00:00Z",
        "description": "空调维修",
    },
    {
        "id": "ORD-20260210-003",
        "customer_name": "张三", "customer_id": "CUS-001",
        "vehicle": "沪A12345 大众帕萨特 2020款",
        "status": "in_progress",
        "total_amount": 3500.00,
        "shop_name": "张江汽修中心", "shop_id": "SHOP-001",
        "created_at": "2026-02-10T08:30:00Z",
        "completed_at": None,
        "description": "发动机保养+更换机油滤芯",
    },
    {
        "id": "ORD-20260212-004",
        "customer_name": "王五", "customer_id": "CUS-003",
        "vehicle": "沪C11111 本田思域 2022款",
        "status": "completed",
        "total_amount": 450.00,
        "shop_name": "浦东汽修店", "shop_id": "SHOP-002",
        "created_at": "2026-02-12T14:00:00Z",
        "completed_at": "2026-02-12T16:00:00Z",
        "description": "轮胎更换",
    },
    {
        "id": "ORD-20260215-005",
        "customer_name": "张三", "customer_id": "CUS-001",
        "vehicle": "沪A12345 大众帕萨特 2020款",
        "status": "pending",
        "total_amount": 5000.00,
        "shop_name": "张江汽修中心", "shop_id": "SHOP-001",
        "created_at": "2026-02-15T11:00:00Z",
        "completed_at": None,
        "description": "变速箱维修",
    },
]


@app.get("/api/orders/search")
async def orders_search(
    status: str | None = None,
    customer_id: str | None = None,
    shop_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    results = list(ORDERS)
    if status:
        results = [o for o in results if o["status"] == status]
    if customer_id:
        results = [o for o in results if o["customer_id"] == customer_id]
    if shop_id:
        results = [o for o in results if o["shop_id"] == shop_id]
    if keyword:
        results = [o for o in results if keyword in o["description"] or keyword in o["vehicle"]]
    if date_from:
        results = [o for o in results if o["created_at"] >= date_from]
    if date_to:
        results = [o for o in results if o["created_at"] <= date_to + "T23:59:59Z"]

    total = len(results)
    start = (page - 1) * page_size
    items = results[start:start + page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/api/orders/{order_id}")
async def orders_detail(order_id: str):
    for o in ORDERS:
        if o["id"] == order_id:
            return {
                **o,
                "customer": {"id": o["customer_id"], "name": o["customer_name"], "phone": "138****1234"},
                "items": [
                    {"project_name": p.strip(), "labor_fee": 200.0, "parts": []}
                    for p in o["description"].split("+")
                ],
                "total_parts": o["total_amount"] * 0.6,
                "total_labor": o["total_amount"] * 0.4,
            }
    return JSONResponse(status_code=404, content={"error": "工单不存在"})


@app.get("/api/orders/stats")
async def orders_stats(
    date_from: str = "2026-01-01",
    date_to: str = "2026-12-31",
    group_by: str = "month",
    shop_id: str | None = None,
):
    results = [o for o in ORDERS if o["created_at"] >= date_from and o["created_at"] <= date_to + "T23:59:59Z"]
    if shop_id:
        results = [o for o in results if o["shop_id"] == shop_id]

    completed = [o for o in results if o["status"] == "completed"]
    total_rev = sum(o["total_amount"] for o in completed)
    return {
        "summary": {
            "total_orders": len(results),
            "completed_orders": len(completed),
            "total_revenue": total_rev,
            "avg_order_amount": round(total_rev / len(completed), 2) if completed else 0,
        },
        "groups": [{"period": "2026-02", "order_count": len(results), "revenue": total_rev}],
    }


# ── 库存数据 ──

PARTS = [
    {"part_no": "BP-BOSCH-001", "name": "前刹车片（博世）", "category": "brake", "price": 380.0, "stock": 15, "supplier": "博世中国", "compatible_vehicles": ["大众帕萨特", "大众迈腾"]},
    {"part_no": "BP-ATE-001", "name": "前刹车片（ATE）", "category": "brake", "price": 320.0, "stock": 8, "supplier": "ATE", "compatible_vehicles": ["丰田卡罗拉", "本田思域"]},
    {"part_no": "OF-MANN-001", "name": "机油滤芯（曼牌）", "category": "engine", "price": 45.0, "stock": 30, "supplier": "曼牌滤清器", "compatible_vehicles": ["大众帕萨特", "大众迈腾", "斯柯达速派"]},
    {"part_no": "TI-MICH-001", "name": "轮胎 205/55R16（米其林）", "category": "suspension", "price": 650.0, "stock": 4, "supplier": "米其林中国", "compatible_vehicles": ["本田思域", "丰田卡罗拉"]},
]


@app.get("/api/inventory/parts")
async def inventory_parts(
    keyword: str | None = None,
    category: str | None = None,
    in_stock: bool = False,
    page: int = 1,
    page_size: int = 20,
):
    results = list(PARTS)
    if keyword:
        results = [p for p in results if keyword in p["name"]]
    if category:
        results = [p for p in results if p["category"] == category]
    if in_stock:
        results = [p for p in results if p["stock"] > 0]
    return {"items": results, "total": len(results), "page": page, "page_size": page_size}


@app.get("/api/inventory/suppliers")
async def inventory_suppliers(keyword: str | None = None):
    suppliers = [
        {"id": "SUP-001", "name": "博世中国", "rating": 4.8, "categories": ["brake", "electrical"], "contact": "021-5555-0001"},
        {"id": "SUP-002", "name": "ATE", "rating": 4.5, "categories": ["brake"], "contact": "021-5555-0002"},
        {"id": "SUP-003", "name": "曼牌滤清器", "rating": 4.7, "categories": ["engine"], "contact": "021-5555-0003"},
        {"id": "SUP-004", "name": "米其林中国", "rating": 4.9, "categories": ["suspension"], "contact": "021-5555-0004"},
    ]
    if keyword:
        suppliers = [s for s in suppliers if keyword in s["name"]]
    return {"items": suppliers, "total": len(suppliers)}


# ── 客户数据 ──

CUSTOMERS = [
    {"id": "CUS-001", "name": "张三", "phone": "138****1234", "vehicle_count": 1, "total_orders": 3, "last_visit": "2026-02-15"},
    {"id": "CUS-002", "name": "李四", "phone": "139****5678", "vehicle_count": 1, "total_orders": 1, "last_visit": "2026-02-05"},
    {"id": "CUS-003", "name": "王五", "phone": "137****9012", "vehicle_count": 1, "total_orders": 1, "last_visit": "2026-02-12"},
]


@app.get("/api/customers/search")
async def customers_search(keyword: str | None = None, page: int = 1, page_size: int = 20):
    results = list(CUSTOMERS)
    if keyword:
        results = [c for c in results if keyword in c["name"] or keyword in c["phone"]]
    return {"items": results, "total": len(results), "page": page, "page_size": page_size}


@app.get("/api/customers/{customer_id}/vehicles")
async def customer_vehicles(customer_id: str):
    vehicles_map = {
        "CUS-001": [{"plate": "沪A12345", "brand": "大众", "model": "帕萨特 2020款", "vin": "LSVNV4189N2******", "mileage": 45000}],
        "CUS-002": [{"plate": "沪B67890", "brand": "丰田", "model": "卡罗拉 2021款", "vin": "JTDKN3DU5M1******", "mileage": 32000}],
        "CUS-003": [{"plate": "沪C11111", "brand": "本田", "model": "思域 2022款", "vin": "2HGFC2F59NH******", "mileage": 18000}],
    }
    return {"customer_id": customer_id, "vehicles": vehicles_map.get(customer_id, [])}


@app.get("/api/customers/{customer_id}/repair_history")
async def customer_repair_history(customer_id: str, date_from: str | None = None, date_to: str | None = None):
    records = [
        {
            "order_id": o["id"],
            "date": o["created_at"][:10],
            "shop_name": o["shop_name"],
            "projects": [p.strip() for p in o["description"].split("+")],
            "total_amount": o["total_amount"],
            "vehicle_plate": o["vehicle"].split(" ")[0],
        }
        for o in ORDERS if o["customer_id"] == customer_id
    ]
    return {"customer_id": customer_id, "records": records, "total": len(records)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-business-api"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
