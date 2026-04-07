"""SS-001 mock 数据：附近门店搜索"""

from __future__ import annotations

from typing import Any

# 用户位置：上海浦东张江
USER_LAT: float = 31.2035
USER_LNG: float = 121.5914

USER_CONTEXT: dict[str, Any] = {
    "current_location": {
        "address": "上海市浦东新区张江高科",
        "lat": USER_LAT,
        "lng": USER_LNG,
    }
}

# Mock DM 商户数据（3 家浦东 + 1 家北京）
SHOPS: list[dict[str, Any]] = [
    {
        "commercialId": 201,
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
        "commercialId": 202,
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
        "commercialId": 203,
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
    {
        "commercialId": 299,
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
]

# Kafka 消息（operationType=1 新增）
SHOP_EVENTS: list[dict[str, Any]] = [
    {**shop, "operationType": 1, "commercialType": [shop["commercialType"]]}
    for shop in SHOPS
]

# Mock DM 项目数据（SS-001 不需要项目，但保留空列表）
PROJECTS: list[dict[str, Any]] = []

QUOTATIONS: list[dict[str, Any]] = []
