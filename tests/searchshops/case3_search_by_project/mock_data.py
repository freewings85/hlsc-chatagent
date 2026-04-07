"""SS-003 mock 数据：按项目搜索门店"""

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

SHOPS: list[dict[str, Any]] = [
    {
        "commercialId": 401,
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
    {
        "commercialId": 402,
        "commercialName": "精典汽车（浦东店）",
        "commercialType": 3,
        "address": "上海市浦东新区碧波路300号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.198,
        "longitude": 121.600,
        "rating": 4.7,
        "tradingCount": 1500,
        "phone": "021-50771003",
        "serviceScope": "保养,维修,钣喷,洗车",
        "openingHours": "08:00-21:00",
        "imageObject": [],
    },
]

SHOP_EVENTS: list[dict[str, Any]] = [
    {**shop, "operationType": 1, "commercialType": [shop["commercialType"]]}
    for shop in SHOPS
]

# match_project 需要的项目数据
PROJECTS: list[dict[str, Any]] = [
    {"packageId": 1201, "packageName": "轮胎更换", "category": "轮胎", "chooseCar": "brand_series"},
    {"packageId": 1202, "packageName": "轮胎修补", "category": "轮胎", "chooseCar": "no_need_car"},
    {"packageId": 1101, "packageName": "机油/机滤更换", "category": "保养", "chooseCar": "car_and_param"},
]

QUOTATIONS: list[dict[str, Any]] = []
