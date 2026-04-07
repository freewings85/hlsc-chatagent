"""SC-003 mock 数据：预订优惠"""

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
        "commercialId": 1001,
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

PROJECTS: list[dict[str, Any]] = [
    {"packageId": 1101, "packageName": "机油/机滤更换", "category": "保养", "chooseCar": "car_and_param"},
]

COUPON_EVENTS: list[dict[str, Any]] = [
    {
        "activityId": 7001,
        "commercialId": 1001,
        "packageId": 1101,
        "packageName": "机油/机滤更换",
        "content": "途虎机油保养八折",
        "startTime": "2026-01-01 00:00:00",
        "endTime": "2026-12-31 23:59:59",
        "description": "全合成机油保养套餐八折优惠，含机油+机滤更换",
        "activityCategory": "折扣",
        "promoValue": 80.0,
        "relativeAmount": 0.8,
        "operationType": 1,
    },
]

QUOTATIONS: list[dict[str, Any]] = []
