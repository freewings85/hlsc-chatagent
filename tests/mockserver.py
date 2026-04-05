"""Mock DataManager 服务器：模拟 DataManager 接口，配合真实服务联动测试。

启动方式：uv run python tests/mockserver.py
端口 50400: DataManager（getNearbyShops / Discount/recommend / classify_project 等）

其他服务使用真实部署：
- Address Service: localhost:8092 (Docker)
- Coupon Consumer: localhost:8091 (Docker)
- BMA: localhost:8103 (真实)
- MainAgent: localhost:8100
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

import uvicorn
from fastapi import FastAPI

app: FastAPI = FastAPI(title="Mock DataManager")

# ============================================================
# Mock 商户数据
# ============================================================

MOCK_SHOPS: list[dict[str, Any]] = [
    {
        "commercialId": 101,
        "commercialName": "途虎养车（南京西路店）",
        "commercialType": 2,
        "address": "上海市静安区南京西路1266号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "静安区",
        "latitude": 31.232,
        "longitude": 121.465,
        "rating": 4.8,
        "tradingCount": 3250,
        "phone": "021-62881234",
        "serviceScope": "保养,轮胎,钣喷",
        "openingHours": "08:00-22:00",
        "imageObject": [],
    },
    {
        "commercialId": 102,
        "commercialName": "小拇指快修（曹家渡店）",
        "commercialType": 3,
        "address": "上海市静安区万航渡路888号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "静安区",
        "latitude": 31.235,
        "longitude": 121.443,
        "rating": 4.5,
        "tradingCount": 1820,
        "phone": "021-62135678",
        "serviceScope": "快修,保养,洗车",
        "openingHours": "09:00-21:00",
        "imageObject": [],
    },
    {
        "commercialId": 103,
        "commercialName": "华胜宝马奔驰专修（徐汇店）",
        "commercialType": 4,
        "address": "上海市徐汇区宜山路900号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "徐汇区",
        "latitude": 31.185,
        "longitude": 121.430,
        "rating": 4.9,
        "tradingCount": 980,
        "phone": "021-54321678",
        "serviceScope": "保养,维修,BBA专修",
        "openingHours": "08:30-18:30",
        "imageObject": [],
    },
    {
        "commercialId": 104,
        "commercialName": "驰加汽车服务（望京店）",
        "commercialType": 2,
        "address": "北京市朝阳区望京SOHO",
        "provinceName": "北京市",
        "cityName": "北京市",
        "districtName": "朝阳区",
        "latitude": 39.996,
        "longitude": 116.481,
        "rating": 4.6,
        "tradingCount": 2100,
        "phone": "010-84567890",
        "serviceScope": "轮胎,保养,四轮定位",
        "openingHours": "08:00-20:00",
        "imageObject": [],
    },
    {
        "commercialId": 105,
        "commercialName": "精典汽车（浦东店）",
        "commercialType": 3,
        "address": "上海市浦东新区张江高科技园区",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.205,
        "longitude": 121.590,
        "rating": 4.7,
        "tradingCount": 1560,
        "phone": "021-50991234",
        "serviceScope": "保养,维修,钣喷,洗车",
        "openingHours": "08:00-21:00",
        "imageObject": [],
    },
    {
        "commercialId": 106,
        "commercialName": "途虎养车（朝阳大悦城店）",
        "commercialType": 2,
        "address": "北京市朝阳区朝阳北路101号",
        "provinceName": "北京市",
        "cityName": "北京市",
        "districtName": "朝阳区",
        "latitude": 39.922,
        "longitude": 116.445,
        "rating": 4.7,
        "tradingCount": 2780,
        "phone": "010-65432100",
        "serviceScope": "保养,轮胎,洗车,钣喷",
        "openingHours": "08:00-21:00",
        "imageObject": [],
    },
    {
        "commercialId": 107,
        "commercialName": "京东养车（CBD店）",
        "commercialType": 3,
        "address": "北京市朝阳区建国路93号",
        "provinceName": "北京市",
        "cityName": "北京市",
        "districtName": "朝阳区",
        "latitude": 39.920,
        "longitude": 116.460,
        "rating": 4.5,
        "tradingCount": 1450,
        "phone": "010-65987654",
        "serviceScope": "保养,维修,轮胎",
        "openingHours": "09:00-20:00",
        "imageObject": [],
    },
    {
        "commercialId": 108,
        "commercialName": "精典汽车（浦东金桥店）",
        "commercialType": 3,
        "address": "上海市浦东新区金桥路1100号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.210,
        "longitude": 121.595,
        "rating": 4.6,
        "tradingCount": 1230,
        "phone": "021-50887766",
        "serviceScope": "保养,维修,洗车",
        "openingHours": "08:30-20:30",
        "imageObject": [],
    },
]

# Mock 项目数据
MOCK_PROJECTS: list[dict[str, Any]] = [
    {"id": 1001, "name": "基础洗车", "category": "洗车", "chooseCar": False},
    {"id": 1002, "name": "精致洗车", "category": "洗车", "chooseCar": False},
    {"id": 1101, "name": "机油/机滤更换", "category": "保养", "chooseCar": True},
    {"id": 1102, "name": "大保养", "category": "保养", "chooseCar": True},
    {"id": 1201, "name": "轮胎更换", "category": "轮胎", "chooseCar": True},
    {"id": 1202, "name": "前刹车片更换", "category": "制动", "chooseCar": True},
    {"id": 1301, "name": "钣金喷漆", "category": "钣喷", "chooseCar": False},
    {"id": 1461, "name": "车险", "category": "保险", "chooseCar": False},
]


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间距离（米）"""
    R: float = 6371000
    d_lat: float = math.radians(lat2 - lat1)
    d_lng: float = math.radians(lng2 - lng1)
    a: float = (math.sin(d_lat / 2) ** 2 +
                math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ============================================================
# 商户接口
# ============================================================

@app.post("/service_ai_datamanager/shop/getNearbyShops")
async def get_nearby_shops(body: dict[str, Any]) -> dict[str, Any]:
    """模拟附近商户搜索"""
    lat: float = body.get("latitude", 0)
    lng: float = body.get("longitude", 0)
    radius: int = body.get("radius", 10000)
    top: int = body.get("top", 5)
    keyword: str = body.get("keyword", "")

    results: list[dict[str, Any]] = []
    for shop in MOCK_SHOPS:
        dist: float = _haversine(lat, lng, shop["latitude"], shop["longitude"])
        if dist <= radius:
            if keyword and keyword.lower() not in shop["commercialName"].lower():
                continue
            item: dict[str, Any] = {**shop, "distance": int(dist)}
            results.append(item)

    results.sort(key=lambda x: x["distance"])
    results = results[:top]

    print(f"[MockDM] getNearbyShops lat={lat:.4f}, lng={lng:.4f}, radius={radius} → {len(results)} shops: {[s['commercialName'] for s in results]}")
    return {"status": 0, "result": {"commercials": results}}


@app.post("/service_ai_datamanager/shop/getLatestVisitedShops")
async def get_latest_visited_shops(body: dict[str, Any]) -> dict[str, Any]:
    """模拟上次去过的商户"""
    print(f"[MockDM] getLatestVisitedShops ownerId={body.get('ownerId')}")
    return {"status": 0, "result": {"commercials": [MOCK_SHOPS[0]]}}


@app.post("/service_ai_datamanager/shop/getAllShopType")
async def get_all_shop_types(body: dict[str, Any]) -> dict[str, Any]:
    """模拟商户类型列表"""
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
    """按 commercialId 批量查询商户详情（coupon consumer 入库时调用）"""
    commercial_ids: list[int] = body.get("commercialIds", [])
    # 建索引方便查找
    shop_index: dict[int, dict[str, Any]] = {s["commercialId"]: s for s in MOCK_SHOPS}
    results: list[dict[str, Any]] = []
    for cid in commercial_ids:
        shop: dict[str, Any] | None = shop_index.get(cid)
        if shop is not None:
            # 返回与 getNearbyShops 一致的字段（不含 distance）
            results.append({
                "commercialId": shop["commercialId"],
                "commercialName": shop["commercialName"],
                "latitude": shop["latitude"],
                "longitude": shop["longitude"],
                "cityName": shop["cityName"],
                "provinceName": shop["provinceName"],
                "districtName": shop["districtName"],
                "address": shop["address"],
                "phone": shop["phone"],
                "rating": shop["rating"],
                "serviceScope": shop["serviceScope"],
                "openingHours": shop["openingHours"],
            })

    print(f"[MockDM] getShopsById ids={commercial_ids} → {len(results)} shops: {[s['commercialName'] for s in results]}")
    return {"status": 0, "result": {"commercials": results}}


# ============================================================
# 优惠接口（DataManager 回退路径）
# ============================================================

@app.post("/service_ai_datamanager/Discount/recommend")
async def discount_recommend(body: dict[str, Any]) -> dict[str, Any]:
    """模拟优惠推荐"""
    print(f"[MockDM] Discount/recommend lat={body.get('latitude')}, lng={body.get('longitude')}")
    return {
        "status": 0,
        "result": {
            "platformActivities": [
                {
                    "coupon_id": "P001",
                    "coupon_name": "平台九折保养券",
                    "shop_id": 101,
                    "shop_name": "途虎养车（南京西路店）",
                    "coupon_description": "保养项目全场九折",
                    "address": "上海市静安区南京西路1266号",
                    "phone": "021-62881234",
                    "rating": 4.8,
                }
            ],
            "shopActivities": [],
        },
    }


# ============================================================
# 项目分类接口
# ============================================================

# classifyProject 的同义词映射：用户关键词 → 项目名称关键词
_CLASSIFY_SYNONYMS: dict[str, list[str]] = {
    "换机油": ["机油"],
    "机油": ["机油"],
    "保养": ["保养", "机油"],
    "洗车": ["洗车"],
    "刹车片": ["刹车片"],
    "刹车": ["刹车片"],
    "车险续保": ["车险"],
    "续保": ["车险"],
    "车险": ["车险"],
    "轮胎": ["轮胎"],
    "钣金": ["钣金"],
    "喷漆": ["钣金"],
}


@app.post("/service_ai_datamanager/package/classifyProject")
async def classify_project(body: dict[str, Any]) -> dict[str, Any]:
    """模拟项目分类：支持同义词扩展匹配"""
    keyword: str = body.get("keyword", "")
    matched: list[dict[str, Any]] = []

    # 先通过同义词映射扩展搜索词
    search_terms: list[str] = _CLASSIFY_SYNONYMS.get(keyword, [keyword])

    for p in MOCK_PROJECTS:
        for term in search_terms:
            if term in p["name"] or term in p["category"]:
                matched.append(p)
                break  # 一个项目只匹配一次

    print(f"[MockDM] classifyProject keyword='{keyword}' → {len(matched)} matches: {[m['name'] for m in matched]}")
    return {"status": 0, "result": matched}


@app.post("/service_ai_datamanager/package/matchProject")
async def match_project(body: dict[str, Any]) -> dict[str, Any]:
    """模拟项目匹配：返回项目名称和 chooseCar 精度要求"""
    project_id: int = body.get("projectId", 0)
    for p in MOCK_PROJECTS:
        if p["id"] == project_id:
            print(f"[MockDM] matchProject id={project_id} → {p['name']} (chooseCar={p.get('chooseCar', False)})")
            return {"status": 0, "result": p}
    return {"status": -1, "message": f"项目 {project_id} 不存在"}


# ============================================================
# 车辆接口
# ============================================================

@app.post("/service_ai_datamanager/Auto/getCarModelByQueryKey")
async def fuzzy_match_car(body: dict[str, Any]) -> dict[str, Any]:
    """模拟车型模糊匹配"""
    keyword: str = body.get("queryKey", "")
    print(f"[MockDM] fuzzyMatchCar keyword='{keyword}'")
    return {
        "status": 0,
        "result": [
            {"carModelId": "CM_001", "carModelName": f"2021款大众朗逸 1.5L（匹配: {keyword}）"},
            {"carModelId": "CM_002", "carModelName": f"2022款丰田卡罗拉 1.8L（匹配: {keyword}）"},
        ],
    }


# ============================================================
# 下单/联系单接口
# ============================================================

@app.post("/web_owner/task/submit")
async def task_submit(body: dict[str, Any]) -> dict[str, Any]:
    """模拟下单/联系单提交：支持 confirm_booking 和 create_contact_order"""
    func_name: str = body.get("funcName", "")
    params: dict[str, Any] = body.get("funcParams", body)
    shop_name: str = params.get("shopName", "")
    visit_time: str = params.get("visitTime", "")

    if func_name == "confirm_booking":
        order_id: str = "ORD_BK_20260404_001"
        print(f"[MockDM] task/submit confirm_booking shop={shop_name}, time={visit_time}")
        return {
            "status": 0,
            "result": {
                "orderId": order_id,
                "shopName": shop_name,
                "visitTime": visit_time,
                "orderType": "booking",
            },
        }
    elif func_name == "create_contact_order":
        order_id = "ORD_CT_20260404_001"
        print(f"[MockDM] task/submit create_contact_order shop={shop_name}")
        return {
            "status": 0,
            "result": {
                "orderId": order_id,
                "shopName": shop_name,
                "visitTime": visit_time,
                "orderType": "contact",
            },
        }
    else:
        # 兼容旧格式
        order_id = "ORD_20260404_001"
        print(f"[MockDM] task/submit funcName={func_name}, body={body}")
        return {
            "status": 0,
            "result": {
                "orderId": order_id,
                "shopName": shop_name,
                "visitTime": visit_time,
            },
        }


# ============================================================
# 通配：未匹配的路径返回空成功
# ============================================================

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def catch_all(path: str) -> dict[str, Any]:
    """未匹配的路径"""
    print(f"[MockDM] UNHANDLED: /{path}")
    return {"status": 0, "result": {}}


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Mock DataManager 启动: http://localhost:50400")
    print("=" * 60)
    print()
    print("模拟数据:")
    print(f"  商户: {len(MOCK_SHOPS)} 家（上海静安/徐汇/浦东 + 北京朝阳）")
    print(f"  项目: {len(MOCK_PROJECTS)} 个（洗车/保养/轮胎/钣喷/车险）")
    print()
    uvicorn.run(app, host="0.0.0.0", port=50400, log_level="warning")
