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
        "commercialId": 201,
        "commercialName": "途虎养车（张江店）",
        "commercialType": 2,
        "address": "上海市浦东新区张江路100号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.2050,
        "longitude": 121.5900,
        "rating": 4.8,
        "tradingCount": 3250,
        "phone": "021-50991001",
        "serviceScope": "保养,轮胎,钣喷,洗车",
        "openingHours": "08:00-22:00",
        "imageObject": [],
    },
    {
        "commercialId": 202,
        "commercialName": "小拇指快修（金科路店）",
        "commercialType": 3,
        "address": "上海市浦东新区金科路888号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.2080,
        "longitude": 121.5950,
        "rating": 4.5,
        "tradingCount": 1820,
        "phone": "021-50991002",
        "serviceScope": "快修,保养,洗车",
        "openingHours": "09:00-21:00",
        "imageObject": [],
    },
    {
        "commercialId": 203,
        "commercialName": "上汽大众4S店（浦东店）",
        "commercialType": 1,
        "address": "上海市浦东新区龙东大道3000号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.2000,
        "longitude": 121.5500,
        "rating": 4.9,
        "tradingCount": 980,
        "phone": "021-50991003",
        "serviceScope": "新车销售,保养,维修,钣喷",
        "openingHours": "08:30-18:30",
        "imageObject": [],
    },
    {
        "commercialId": 204,
        "commercialName": "途虎养车（南京西路店）",
        "commercialType": 2,
        "address": "上海市静安区南京西路1266号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "静安区",
        "latitude": 31.2320,
        "longitude": 121.4650,
        "rating": 4.6,
        "tradingCount": 2100,
        "phone": "021-62881234",
        "serviceScope": "保养,轮胎,钣喷",
        "openingHours": "08:00-20:00",
        "imageObject": [],
    },
    {
        "commercialId": 205,
        "commercialName": "驰加汽车服务（望京店）",
        "commercialType": 2,
        "address": "北京市朝阳区望京SOHO",
        "provinceName": "北京市",
        "cityName": "北京市",
        "districtName": "朝阳区",
        "latitude": 39.9960,
        "longitude": 116.4810,
        "rating": 4.7,
        "tradingCount": 2780,
        "phone": "010-84567890",
        "serviceScope": "轮胎,保养,四轮定位",
        "openingHours": "08:00-20:00",
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

# Mock 报价数据：shopId → 项目报价列表（与 MOCK_SHOPS ID 201-205 一致）
MOCK_QUOTATIONS: list[dict[str, Any]] = [
    {
        "shopId": 201, "shopName": "途虎养车（张江店）", "shopType": [2],
        "projects": [
            {"projectId": 1001, "projectName": "基础洗车", "priceType": 1, "priceStringObject": {"price": 35, "conditionPrices": None, "minPrice": None, "maxPrice": None}},
            {"projectId": 1101, "projectName": "机油/机滤更换", "priceType": 1, "priceStringObject": {"price": 380, "conditionPrices": None, "minPrice": None, "maxPrice": None}},
        ],
    },
    {
        "shopId": 202, "shopName": "小拇指快修（金科路店）", "shopType": [3],
        "projects": [
            {"projectId": 1001, "projectName": "基础洗车", "priceType": 1, "priceStringObject": {"price": 28, "conditionPrices": None, "minPrice": None, "maxPrice": None}},
            {"projectId": 1101, "projectName": "机油/机滤更换", "priceType": 1, "priceStringObject": {"price": 299, "conditionPrices": None, "minPrice": None, "maxPrice": None}},
        ],
    },
    {
        "shopId": 203, "shopName": "上汽大众4S店（浦东店）", "shopType": [1],
        "projects": [
            {"projectId": 1001, "projectName": "基础洗车", "priceType": 1, "priceStringObject": {"price": 60, "conditionPrices": None, "minPrice": None, "maxPrice": None}},
        ],
    },
    {
        "shopId": 204, "shopName": "途虎养车（南京西路店）", "shopType": [2],
        "projects": [
            {"projectId": 1001, "projectName": "基础洗车", "priceType": 1, "priceStringObject": {"price": 35, "conditionPrices": None, "minPrice": None, "maxPrice": None}},
        ],
    },
    {
        "shopId": 205, "shopName": "驰加汽车服务（望京店）", "shopType": [2],
        "projects": [
            {"projectId": 1001, "projectName": "基础洗车", "priceType": 1, "priceStringObject": {"price": 40, "conditionPrices": None, "minPrice": None, "maxPrice": None}},
        ],
    },
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
# 商户报价接口
# ============================================================

@app.post("/service_ai_datamanager/shop/getCommercialPackages")
async def get_commercial_packages(body: dict[str, Any]) -> dict[str, Any]:
    """查询商户项目报价"""
    shop_ids: list[int] = body.get("shopIds", [])
    project_ids: list[int] = body.get("projectIds", [])
    results: list[dict[str, Any]] = []
    for q in MOCK_QUOTATIONS:
        if q["shopId"] in shop_ids:
            if project_ids:
                filtered_projects: list[dict[str, Any]] = [
                    p for p in q["projects"] if p["projectId"] in project_ids
                ]
                if filtered_projects:
                    results.append({**q, "projects": filtered_projects})
            else:
                results.append(q)
    print(f"[MockDM] getCommercialPackages shopIds={shop_ids}, projectIds={project_ids} → {len(results)} shops")
    return {"status": 0, "result": results}


# ============================================================
# 项目分类接口（classify_project 调用）
# ============================================================

_CLASSIFY_SYNONYMS: dict[str, list[str]] = {
    "换机油": ["机油"], "机油": ["机油"], "保养": ["保养", "机油"],
    "洗车": ["洗车"], "刹车片": ["刹车片"], "刹车": ["刹车片"],
    "车险续保": ["车险"], "续保": ["车险"], "车险": ["车险"],
    "轮胎": ["轮胎"], "钣金": ["钣金"], "喷漆": ["钣金"],
}


@app.post("/service_ai_datamanager/package/searchPackageByKeyword")
async def search_package_by_keyword(body: dict[str, Any]) -> dict[str, Any]:
    """模拟项目分类（classify_project 用）"""
    keyword: str = body.get("keyword", "")
    search_terms: list[str] = _CLASSIFY_SYNONYMS.get(keyword, [keyword])
    matched: list[dict[str, Any]] = []
    for p in MOCK_PROJECTS:
        for term in search_terms:
            if term in p["name"] or term in p["category"]:
                matched.append({"packageId": p["id"], "packageName": p["name"]})
                break
    print(f"[MockDM] searchPackageByKeyword keyword='{keyword}' → {len(matched)} matches")
    return {"status": 0, "result": matched}


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
                    "shop_id": 201,
                    "shop_name": "途虎养车（张江店）",
                    "coupon_description": "保养项目全场九折",
                    "address": "上海市浦东新区张江路100号",
                    "phone": "021-50991001",
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
    print(f"  商户: {len(MOCK_SHOPS)} 家（上海浦东/静安 + 北京朝阳，ID 201-205）")
    print(f"  项目: {len(MOCK_PROJECTS)} 个（洗车/保养/轮胎/钣喷/车险）")
    print()
    uvicorn.run(app, host="0.0.0.0", port=50400, log_level="warning")
