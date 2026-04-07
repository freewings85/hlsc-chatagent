"""SS-004 mock 数据：比价查询"""

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
        "commercialId": 501,
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
        "commercialId": 502,
        "commercialName": "小拇指快修（金桥店）",
        "commercialType": 3,
        "address": "上海市浦东新区金桥路200号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.210,
        "longitude": 121.595,
        "rating": 4.5,
        "tradingCount": 1800,
        "phone": "021-50881002",
        "serviceScope": "快修,保养,洗车",
        "openingHours": "09:00-21:00",
        "imageObject": [],
    },
    {
        "commercialId": 503,
        "commercialName": "华胜宝马奔驰专修（浦东店）",
        "commercialType": 4,
        "address": "上海市浦东新区碧波路300号",
        "provinceName": "上海市",
        "cityName": "上海市",
        "districtName": "浦东新区",
        "latitude": 31.198,
        "longitude": 121.600,
        "rating": 4.9,
        "tradingCount": 980,
        "phone": "021-50771003",
        "serviceScope": "保养,维修,BBA专修",
        "openingHours": "08:30-18:30",
        "imageObject": [],
    },
]

SHOP_EVENTS: list[dict[str, Any]] = [
    {**shop, "operationType": 1, "commercialType": [shop["commercialType"]]}
    for shop in SHOPS
]

PROJECTS: list[dict[str, Any]] = [
    {"packageId": 1101, "packageName": "机油/机滤更换", "category": "保养", "chooseCar": "car_and_param"},
    {"packageId": 1102, "packageName": "大保养", "category": "保养", "chooseCar": "car_and_param"},
]

QUOTATIONS: list[dict[str, Any]] = []
