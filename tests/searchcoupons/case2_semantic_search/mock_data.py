"""SC-002 mock 数据：语义搜索优惠"""

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
        "commercialId": 901,
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
        "activityId": 6001,
        "commercialId": 901,
        "packageId": 1101,
        "packageName": "机油/机滤更换",
        "content": "途虎机油保养支付宝立减",
        "startTime": "2026-01-01 00:00:00",
        "endTime": "2026-12-31 23:59:59",
        "description": "使用支付宝支付机油保养套餐立减30元",
        "activityCategory": "满减",
        "promoValue": 30.0,
        "relativeAmount": 0.3,
        "operationType": 1,
    },
    {
        "activityId": 6002,
        "commercialId": 901,
        "packageId": 1101,
        "packageName": "机油/机滤更换",
        "content": "途虎机油保养微信折扣",
        "startTime": "2026-01-01 00:00:00",
        "endTime": "2026-12-31 23:59:59",
        "description": "微信支付机油保养九折优惠",
        "activityCategory": "折扣",
        "promoValue": 90.0,
        "relativeAmount": 0.9,
        "operationType": 1,
    },
]

QUOTATIONS: list[dict[str, Any]] = []
