"""SC-001 mock 数据：按项目查优惠"""

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

# mock DM 返回的商户（coupon-consumer 入库时查 getShopsById 用）
SHOPS: list[dict[str, Any]] = [
    {
        "commercialId": 801,
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
        "commercialId": 802,
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
]

# classify_project 返回的项目
PROJECTS: list[dict[str, Any]] = [
    {"packageId": 1101, "packageName": "机油/机滤更换", "category": "保养", "chooseCar": "car_and_param"},
    {"packageId": 1102, "packageName": "大保养", "category": "保养", "chooseCar": "car_and_param"},
]

# Kafka 优惠活动事件
COUPON_EVENTS: list[dict[str, Any]] = [
    {
        "activityId": 5001,
        "commercialId": 801,
        "packageId": 1101,
        "packageName": "机油/机滤更换",
        "content": "机油保养八折优惠",
        "startTime": "2026-01-01 00:00:00",
        "endTime": "2026-12-31 23:59:59",
        "description": "全合成机油保养套餐八折，含机油+机滤更换，支持所有品牌车型",
        "activityCategory": "折扣",
        "promoValue": 80.0,
        "relativeAmount": 0.8,
        "operationType": 1,
    },
    {
        "activityId": 5002,
        "commercialId": 802,
        "packageId": 1101,
        "packageName": "机油/机滤更换",
        "content": "小拇指保养满减",
        "startTime": "2026-01-01 00:00:00",
        "endTime": "2026-12-31 23:59:59",
        "description": "保养项目满300减50，机油机滤更换适用",
        "activityCategory": "满减",
        "promoValue": 50.0,
        "relativeAmount": 0.5,
        "operationType": 1,
    },
]

# Kafka 商户事件（入 shop_merchants）
SHOP_EVENTS: list[dict[str, Any]] = [
    {**shop, "operationType": 1, "commercialType": [shop["commercialType"]]}
    for shop in SHOPS
]

QUOTATIONS: list[dict[str, Any]] = []
