"""SS-006 mock 数据：文字地址搜索（无 GPS context）"""

from __future__ import annotations

from typing import Any

# 不传 current_location，测试文字地址解析
USER_CONTEXT: dict[str, Any] = {}

# 商户在南京西路附近
SHOPS: list[dict[str, Any]] = [
    {
        "commercialId": 701,
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
        "commercialId": 702,
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
]

SHOP_EVENTS: list[dict[str, Any]] = [
    {**shop, "operationType": 1, "commercialType": [shop["commercialType"]]}
    for shop in SHOPS
]

PROJECTS: list[dict[str, Any]] = []
QUOTATIONS: list[dict[str, Any]] = []
