"""共享 mock 数据：项目、商户、报价三组接口共用。"""

from __future__ import annotations

from typing import Any


CAR_MODEL = {
    "car_model_id": "lavida_2021_15l",
    "car_model_name": "大众 朗逸 2021款 1.5L",
}

SHOP_TYPES: list[dict[str, Any]] = [
    {
        "shop_type_id": 34,
        "shop_type_name": "4S店",
        "advantages": "原厂体系、流程标准、适合质保期车辆。",
        "disadvantages": "整体价格更高，性价比通常不是最优。",
        "suitable_scenes": "新车、质保期内、对原厂体系要求高的项目。",
        "summary": "质保期或重视原厂体系时优先考虑。",
    },
    {
        "shop_type_id": 35,
        "shop_type_name": "快修连锁",
        "advantages": "价格透明、覆盖广、适合标准化项目。",
        "disadvantages": "复杂疑难问题的个性化处理能力一般。",
        "suitable_scenes": "保养、洗车、轮胎、常规更换类项目。",
        "summary": "标准化项目通常优先考虑快修连锁。",
    },
    {
        "shop_type_id": 36,
        "shop_type_name": "周边小店",
        "advantages": "距离近、沟通灵活、熟人关系可能更强。",
        "disadvantages": "服务标准和价格透明度波动较大。",
        "suitable_scenes": "就近需求、轻度服务、熟悉商户复购。",
        "summary": "对方便性和熟悉关系要求高时可优先考虑。",
    },
]

SHOPS: list[dict[str, Any]] = [
    {
        "shop_id": 101,
        "shop_name": "嘉定德保快修",
        "shop_type_id": 35,
        "shop_type_name": "快修连锁",
        "address": "上海市嘉定区众仁路 275 号",
        "province": "上海市",
        "city": "上海城区",
        "district": "嘉定区",
        "latitude": 31.287737,
        "longitude": 121.326912,
        "distance_m": 650,
        "rating": 4.7,
        "trading_count": 186,
        "phone": "17522536027",
        "opening_hours": "09:00-18:00",
        "tags": ["洗车", "保养", "刹车"],
        "images": [],
        "project_ids": [502, 516, 569],
    },
    {
        "shop_id": 102,
        "shop_name": "虹桥车友中心",
        "shop_type_id": 36,
        "shop_type_name": "周边小店",
        "address": "上海市闵行区虹桥机场附近",
        "province": "上海市",
        "city": "上海城区",
        "district": "闵行区",
        "latitude": 31.194206,
        "longitude": 121.316684,
        "distance_m": 1200,
        "rating": 4.5,
        "trading_count": 92,
        "phone": "15988888888",
        "opening_hours": "10:00-19:00",
        "tags": ["洗车", "美容", "玻璃"],
        "images": [],
        "project_ids": [502, 522],
    },
    {
        "shop_id": 103,
        "shop_name": "沪上大众 4S 店",
        "shop_type_id": 34,
        "shop_type_name": "4S店",
        "address": "上海市普陀区真南路 888 号",
        "province": "上海市",
        "city": "上海城区",
        "district": "普陀区",
        "latitude": 31.250101,
        "longitude": 121.401223,
        "distance_m": 3200,
        "rating": 4.8,
        "trading_count": 268,
        "phone": "021-58886666",
        "opening_hours": "08:30-17:30",
        "tags": ["保养", "原厂", "刹车"],
        "images": [],
        "project_ids": [502, 516],
    },
]

PROJECTS: list[dict[str, Any]] = [
    {
        "project_id": 502,
        "project_name": "机油/机滤更换",
        "project_simple_name": "机油机滤",
        "contain_material": True,
        "vehicle_precision_requirement": "need_car_model",
        "description": "常规保养项目。",
        "keywords": ["机油", "机滤", "保养"],
        "unit": "次",
        "source_project_id": 9,
    },
    {
        "project_id": 516,
        "project_name": "前刹车片更换",
        "project_simple_name": "前片",
        "contain_material": True,
        "vehicle_precision_requirement": "need_vin",
        "description": "前刹车片更换服务。",
        "keywords": ["前刹车片", "刹车片", "制动"],
        "unit": "一对",
        "source_project_id": 13,
    },
    {
        "project_id": 522,
        "project_name": "玻璃去油膜",
        "project_simple_name": "去油膜",
        "contain_material": False,
        "vehicle_precision_requirement": "no_need_car",
        "description": "玻璃清洁与去油膜服务。",
        "keywords": ["玻璃", "油膜", "清洁"],
        "unit": "次",
        "source_project_id": 22,
    },
    {
        "project_id": 569,
        "project_name": "轮胎更换",
        "project_simple_name": "轮胎",
        "contain_material": True,
        "vehicle_precision_requirement": "need_car_model",
        "description": "轮胎更换服务。",
        "keywords": ["轮胎", "换胎"],
        "unit": "条",
        "source_project_id": 31,
    },
]

PRIMARY_PARTS: list[dict[str, Any]] = [
    {"primary_part_id": 656, "primary_part_name": "机油滤"},
    {"primary_part_id": 933, "primary_part_name": "前刹车片"},
    {"primary_part_id": 421, "primary_part_name": "轮胎"},
]

PRIMARY_PART_TO_PROJECT_IDS: dict[int, list[int]] = {
    656: [502],
    933: [516],
    421: [569],
}

RELATED_PROJECT_IDS: dict[int, list[int]] = {
    502: [522],
    516: [502],
    522: [502],
    569: [502],
}

PROJECT_HISTORY_BY_USER: dict[str, list[dict[str, Any]]] = {
    "10001": [
        {"project_id": 522, "project_name": "玻璃去油膜", "total": 1},
        {"project_id": 502, "project_name": "机油/机滤更换", "total": 2},
    ]
}

PENDING_PROJECTS_BY_USER: dict[str, list[dict[str, Any]]] = {
    "10001": [
        {"project_id": 516, "project_name": "前刹车片更换", "total": 1}
    ]
}

SHOP_HISTORY_BY_USER: dict[str, dict[str, list[dict[str, Any]]]] = {
    "10001": {
        "latest": [
            {
                "shop_id": 102,
                "last_order_code": "YUN-1234560003",
                "last_order_time": "2026-03-17 15:18:30",
            }
        ],
        "history": [
            {"shop_id": 102},
            {"shop_id": 101},
        ],
    }
}

TRIGGER_CONDITIONS: list[dict[str, Any]] = [
    {
        "trigger_condition_id": 408,
        "title": "过户代办",
        "content": "车辆过户前后常见配套服务场景。",
        "primary_part_ids": [],
        "related_project_ids": [522],
    }
]

FAULTS: list[dict[str, Any]] = [
    {
        "fault_id": 3,
        "title": "刹车异响",
        "content": "低速制动时出现明显异响。",
        "primary_part_ids": [933],
        "related_project_ids": [516],
    }
]

PROJECT_TREE: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "常规养护类",
        "data_type": "category",
        "children": [
            {
                "id": 502,
                "name": "机油/机滤更换",
                "data_type": "project",
                "children": [],
            },
            {
                "id": 522,
                "name": "玻璃去油膜",
                "data_type": "project",
                "children": [],
            },
        ],
    },
    {
        "id": 2,
        "name": "检测/维修类",
        "data_type": "category",
        "children": [
            {
                "id": 516,
                "name": "前刹车片更换",
                "data_type": "project",
                "children": [],
            },
            {
                "id": 569,
                "name": "轮胎更换",
                "data_type": "project",
                "children": [],
            },
        ],
    },
]

PROJECT_DETAILS: dict[int, dict[str, Any]] = {
    502: {
        "first_maintenance_mileage": 5000,
        "first_maintenance_time_month": 6,
        "maintenance_mileage": 10000,
        "maintenance_time_month": 12,
        "related_parts": [
            {"primary_part_id": 656, "primary_part_name": "机油滤"}
        ],
        "shop_type_scope": [34, 35, 36],
    },
    516: {
        "first_maintenance_mileage": 0,
        "first_maintenance_time_month": 0,
        "maintenance_mileage": 0,
        "maintenance_time_month": 0,
        "related_parts": [
            {"primary_part_id": 933, "primary_part_name": "前刹车片"}
        ],
        "shop_type_scope": [34, 35],
    },
    522: {
        "first_maintenance_mileage": 0,
        "first_maintenance_time_month": 0,
        "maintenance_mileage": 0,
        "maintenance_time_month": 0,
        "related_parts": [],
        "shop_type_scope": [35, 36],
    },
    569: {
        "first_maintenance_mileage": 0,
        "first_maintenance_time_month": 0,
        "maintenance_mileage": 40000,
        "maintenance_time_month": 48,
        "related_parts": [
            {"primary_part_id": 421, "primary_part_name": "轮胎"}
        ],
        "shop_type_scope": [34, 35],
    },
}

NEARBY_QUOTES: dict[tuple[int, int], dict[str, Any]] = {
    (101, 502): {
        "plan_name": "默认方案",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 299.0,
        "price_text": "¥299",
    },
    (102, 502): {
        "plan_name": "默认方案",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 329.0,
        "price_text": "¥329",
    },
    (103, 502): {
        "plan_name": "原厂方案",
        "plan_type": "OEM",
        "total_price": 468.0,
        "price_text": "¥468",
    },
    (101, 516): {
        "plan_name": "国货精品",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 499.0,
        "price_text": "¥499",
    },
    (103, 516): {
        "plan_name": "原厂方案",
        "plan_type": "OEM",
        "total_price": 699.0,
        "price_text": "¥699",
    },
    (101, 569): {
        "plan_name": "默认方案",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 360.0,
        "price_text": "¥360",
    },
}

MARKET_QUOTES: dict[int, dict[str, Any]] = {
    502: {
        "plan_name": "默认方案",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 320.0,
        "price_text": "¥280-¥360",
    },
    516: {
        "plan_name": "默认方案",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 580.0,
        "price_text": "¥520-¥680",
    },
}

TIRE_QUOTES: dict[str, dict[str, Any]] = {
    "20565R15": {
        "project_id": 569,
        "project_name": "轮胎更换",
        "plan_name": "默认方案",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 360.0,
        "price_text": "¥360",
    }
}


def public_shop(shop: dict[str, Any]) -> dict[str, Any]:
    return {
        "shop_id": shop["shop_id"],
        "shop_name": shop["shop_name"],
        "shop_type_id": shop["shop_type_id"],
        "shop_type_name": shop["shop_type_name"],
        "address": shop["address"],
        "province": shop["province"],
        "city": shop["city"],
        "district": shop["district"],
        "latitude": shop["latitude"],
        "longitude": shop["longitude"],
        "distance_m": shop["distance_m"],
        "rating": shop["rating"],
        "trading_count": shop["trading_count"],
        "phone": shop["phone"],
        "opening_hours": shop["opening_hours"],
        "tags": shop["tags"],
        "images": shop["images"],
    }


def public_project(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": project["project_id"],
        "project_name": project["project_name"],
        "project_simple_name": project["project_simple_name"],
        "contain_material": project["contain_material"],
        "vehicle_precision_requirement": project["vehicle_precision_requirement"],
        "description": project["description"],
        "keywords": project["keywords"],
        "unit": project["unit"],
    }


def get_project(project_id: int) -> dict[str, Any] | None:
    return next((item for item in PROJECTS if item["project_id"] == project_id), None)


def get_shop(shop_id: int) -> dict[str, Any] | None:
    return next((item for item in SHOPS if item["shop_id"] == shop_id), None)

