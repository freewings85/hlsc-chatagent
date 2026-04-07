"""SC-004 mock 数据：无结果降级"""

from __future__ import annotations

from typing import Any

USER_LAT: float = 31.2035
USER_LNG: float = 121.5914

USER_CONTEXT: dict[str, Any] = {
    "current_location": {
        "address": "上海市浦东新区张江高科",
        "lat": USER_LAT,
        "lng": USER_LNG,
    }
}

# 商户存在，但没有相关优惠
SHOPS: list[dict[str, Any]] = [
    {
        "commercialId": 1101,
        "commercialName": "途虎养车（张江店）",
        "commercialType": 2,
        "address": "上海市浦东新区张江路100号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.206,
        "longitude": 121.588,
        "rating": 4.8,
        "tradingCount": 3200,
        "phone": "021-50991001",
        "serviceScope": "保养,轮胎,钣喷",
        "openingHours": "08:00-22:00",
        "imageObject": [],
    },
]

SHOP_EVENTS: list[dict[str, Any]] = [
    {**shop, "operationType": 1, "commercialType": [shop["commercialType"]]}
    for shop in SHOPS
]

# 项目有但对应不到优惠
PROJECTS: list[dict[str, Any]] = [
    {"packageId": 9901, "packageName": "四轮定位", "category": "底盘", "chooseCar": "no_need_car"},
]

# 不造优惠数据 — 让 coupon_vectors 为空
COUPON_EVENTS: list[dict[str, Any]] = []

QUOTATIONS: list[dict[str, Any]] = []
