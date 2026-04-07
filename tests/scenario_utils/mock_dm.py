"""Mock DataManager 管理 — 启动/停止可自定义数据的 mock DM 服务"""

from __future__ import annotations

import math
import multiprocessing
import time
from typing import Any

import uvicorn
from fastapi import FastAPI

# 全局进程引用
_dm_process: multiprocessing.Process | None = None


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间距离（米）。"""
    R: float = 6371000
    d_lat: float = math.radians(lat2 - lat1)
    d_lng: float = math.radians(lng2 - lng1)
    a: float = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_app(
    shops: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    quotations: list[dict[str, Any]],
) -> FastAPI:
    """构建 FastAPI app，数据由参数注入。"""
    app: FastAPI = FastAPI(title="Mock DataManager (scenario test)")

    shop_index: dict[int, dict[str, Any]] = {s["commercialId"]: s for s in shops}

    # ── 商户接口 ──

    @app.post("/service_ai_datamanager/shop/getNearbyShops")
    async def get_nearby_shops(body: dict[str, Any]) -> dict[str, Any]:
        lat: float = body.get("latitude", 0)
        lng: float = body.get("longitude", 0)
        radius: int = body.get("radius", 10000)
        top: int = body.get("top", 5)
        keyword: str = body.get("keyword", "")

        results: list[dict[str, Any]] = []
        for shop in shops:
            dist: float = _haversine(lat, lng, shop["latitude"], shop["longitude"])
            if dist <= radius:
                if keyword and keyword.lower() not in shop.get("commercialName", "").lower():
                    continue
                results.append({**shop, "distance": int(dist)})

        results.sort(key=lambda x: x["distance"])
        return {"status": 0, "result": {"commercials": results[:top]}}

    @app.post("/service_ai_datamanager/shop/getLatestVisitedShops")
    async def get_latest_visited_shops(body: dict[str, Any]) -> dict[str, Any]:
        return {"status": 0, "result": {"commercials": shops[:1] if shops else []}}

    @app.post("/service_ai_datamanager/shop/getAllShopType")
    async def get_all_shop_types(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": 0,
            "result": [
                {"typeId": 1, "typeName": "4S店"},
                {"typeId": 2, "typeName": "连锁门店"},
                {"typeId": 3, "typeName": "综合修理厂"},
                {"typeId": 4, "typeName": "专修店"},
            ],
        }

    @app.post("/service_ai_datamanager/shop/getShopsById")
    async def get_shops_by_id(body: dict[str, Any]) -> dict[str, Any]:
        commercial_ids: list[int] = body.get("commercialIds", [])
        results: list[dict[str, Any]] = []
        for cid in commercial_ids:
            shop: dict[str, Any] | None = shop_index.get(cid)
            if shop is not None:
                results.append({
                    "commercialId": shop["commercialId"],
                    "commercialName": shop.get("commercialName", ""),
                    "latitude": shop.get("latitude", 0),
                    "longitude": shop.get("longitude", 0),
                    "cityName": shop.get("cityName", ""),
                    "provinceName": shop.get("provinceName", ""),
                    "districtName": shop.get("districtName", ""),
                    "address": shop.get("address", ""),
                    "phone": shop.get("phone", ""),
                    "rating": shop.get("rating", 0),
                    "serviceScope": shop.get("serviceScope", ""),
                    "openingHours": shop.get("openingHours", ""),
                })
        return {"status": 0, "result": {"commercials": results}}

    # ── 优惠接口 ──

    @app.post("/service_ai_datamanager/Discount/recommend")
    async def discount_recommend(body: dict[str, Any]) -> dict[str, Any]:
        return {"status": 0, "result": {"platformActivities": [], "shopActivities": []}}

    # ── 项目分类/匹配接口 ──
    # classify_project 实际调用路径
    @app.post("/service_ai_datamanager/package/searchPackageByKeyword")
    async def search_package_by_keyword(body: dict[str, Any]) -> dict[str, Any]:
        keyword: str = body.get("keyword", "")
        matched: list[dict[str, Any]] = []
        for p in projects:
            p_name: str = p.get("packageName", p.get("name", ""))
            p_cat: str = p.get("category", "")
            if keyword in p_name or keyword in p_cat:
                matched.append(p)
        return {"status": 0, "result": matched}

    # match_project 实际调用路径
    @app.post("/service_ai_datamanager/project/searchProjectPackageByKeyword")
    async def search_project_package_by_keyword(body: dict[str, Any]) -> dict[str, Any]:
        search_key: str = body.get("searchKey", "")
        matched: list[dict[str, Any]] = []
        for p in projects:
            p_name: str = p.get("packageName", p.get("name", ""))
            p_cat: str = p.get("category", "")
            if search_key in p_name or search_key in p_cat:
                matched.append(p)
        return {"status": 0, "result": matched}

    # ── 车辆接口 ──

    @app.post("/service_ai_datamanager/Auto/getCarModelByQueryKey")
    async def fuzzy_match_car(body: dict[str, Any]) -> dict[str, Any]:
        keyword: str = body.get("queryKey", "")
        return {
            "status": 0,
            "result": [
                {"carModelId": "CM_001", "carModelName": f"2021款大众朗逸 1.5L（匹配: {keyword}）"},
            ],
        }

    # ── 下单接口 ──

    @app.post("/web_owner/task/submit")
    async def task_submit(body: dict[str, Any]) -> dict[str, Any]:
        func_name: str = body.get("funcName", "")
        params: dict[str, Any] = body.get("funcParams", body)
        shop_name: str = params.get("shopName", "")
        visit_time: str = params.get("visitTime", "")
        return {
            "status": 0,
            "result": {
                "orderId": f"ORD_TEST_{func_name}",
                "shopName": shop_name,
                "visitTime": visit_time,
                "orderType": func_name,
            },
        }

    # ── 通配 ──

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def catch_all(path: str) -> dict[str, Any]:
        return {"status": 0, "result": {}}

    return app


def _run_server(
    shops: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    quotations: list[dict[str, Any]],
    port: int,
) -> None:
    """在子进程中运行 uvicorn。"""
    app: FastAPI = _build_app(shops, projects, quotations)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def _kill_port(port: int) -> None:
    """杀掉占用指定端口的进程。"""
    import subprocess
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids: list[str] = result.stdout.strip().split()
        for pid in pids:
            if pid:
                subprocess.run(["kill", "-9", pid], timeout=5)
                print(f"[mock_dm] 已杀掉端口 {port} 上的进程 {pid}")
    except Exception:
        pass


def start_mock_dm(
    shops: list[dict[str, Any]] | None = None,
    projects: list[dict[str, Any]] | None = None,
    quotations: list[dict[str, Any]] | None = None,
    port: int = 50400,
) -> None:
    """启动 mock DataManager（子进程），如果已运行则先停止。"""
    global _dm_process

    if _dm_process is not None and _dm_process.is_alive():
        stop_mock_dm()

    # 杀掉可能占用端口的外部进程
    _kill_port(port)

    _shops: list[dict[str, Any]] = shops or []
    _projects: list[dict[str, Any]] = projects or []
    _quotations: list[dict[str, Any]] = quotations or []

    _dm_process = multiprocessing.Process(
        target=_run_server,
        args=(_shops, _projects, _quotations, port),
        daemon=True,
    )
    _dm_process.start()

    # 等待服务就绪
    import httpx

    deadline: float = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            resp: httpx.Response = httpx.get(f"http://localhost:{port}/health", timeout=1)
            if resp.status_code == 200:
                print(f"[mock_dm] 已启动，端口 {port}")
                return
        except Exception:
            time.sleep(0.3)

    print(f"[mock_dm] 启动超时（10s），端口 {port}")


def stop_mock_dm() -> None:
    """停止 mock DataManager。"""
    global _dm_process

    if _dm_process is not None and _dm_process.is_alive():
        _dm_process.terminate()
        _dm_process.join(timeout=5)
        if _dm_process.is_alive():
            _dm_process.kill()
        print("[mock_dm] 已停止")

    _dm_process = None
