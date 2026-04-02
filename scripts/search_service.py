"""优惠活动搜索服务 — FastAPI + Milvus hybrid search + LLM 意图提取 + 位置过滤"""

import math

from fastapi import FastAPI
import httpx
import json
from pymilvus import Collection, connections, AnnSearchRequest, RRFRanker

app: FastAPI = FastAPI(title="Coupon Search Service")

# Milvus 连接
connections.connect(host="localhost", port="19530")
collection: Collection = Collection("coupon_activities")
collection.load()

# LLM 配置
LLM_ENDPOINT: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_API_KEY: str = "sk-8cf834ae11f94a9d91f7a98960e116cb"
LLM_MODEL: str = "qwen3-30b-a3b"

# 输出字段（含新增商户字段）
OUTPUT_FIELDS: list[str] = [
    "activity_id", "commercial_id", "package_id", "package_name",
    "activity_category", "relative_amount", "content", "description", "end_time",
    "commercial_name", "address", "phone", "rating", "opening_hours",
    "shop_lat", "shop_lng", "city_name",
]


def embed(text: str) -> list[float]:
    """调用 vLLM embedding 服务获取向量"""
    resp: httpx.Response = httpx.post(
        "http://localhost:7683/v1/embeddings",
        json={"model": "BAAI/bge-large-zh-v1.5", "input": text},
    )
    return resp.json()["data"][0]["embedding"]


def lat_lng_range(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """根据中心点和半径计算经纬度矩形范围（近似）"""
    # 1 纬度 ≈ 111km
    lat_delta: float = radius_km / 111.0
    # 1 经度 ≈ 111km * cos(lat)
    lng_delta: float = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)


async def extract_intent(semantic_query: str, type_list: str) -> dict:
    """调小模型提取意图"""
    prompt: str = f"""你是优惠活动查询意图提取器。从用户查询中提取结构化条件。

## 活动分类（只能选其中一个或 null）
{type_list}

## 输出格式
严格输出 JSON，不要包含任何其他内容：
{{"activity_category": "分类名或null", "keywords": ["关键词列表"], "sort_preference": "discount_amount或validity_end或null"}}

用户查询："{semantic_query}"
输出："""

    async with httpx.AsyncClient(timeout=30) as client:
        resp: httpx.Response = await client.post(
            f"{LLM_ENDPOINT}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "enable_thinking": False,
            },
        )
        content: str = resp.json()["choices"][0]["message"]["content"]
        # 提取 JSON（可能被包在 markdown code block 里）
        if "```" in content:
            content = content.split("```")[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        return json.loads(content)


@app.post("/api/coupon/search")
async def search(body: dict) -> dict:
    project_ids: list[int] | None = body.get("projectIds")
    shop_ids: list[int] | None = body.get("shopIds")
    semantic_query: str = body.get("semanticQuery", "")
    city: str | None = body.get("city")
    latitude: float | None = body.get("latitude")
    longitude: float | None = body.get("longitude")
    radius_km: float = body.get("radius", 5.0)
    top_k: int = body.get("topK", 10)

    # 构建 filter
    filters: list[str] = []
    if project_ids:
        ids_str: str = ",".join(str(i) for i in project_ids)
        filters.append(f"package_id in [{ids_str}]")
    if shop_ids:
        ids_str = ",".join(str(i) for i in shop_ids)
        filters.append(f"commercial_id in [{ids_str}]")
    if city:
        filters.append(f'city_name == "{city}"')
    if latitude is not None and longitude is not None:
        lat_min, lat_max, lng_min, lng_max = lat_lng_range(latitude, longitude, radius_km)
        filters.append(f"shop_lat >= {lat_min} and shop_lat <= {lat_max}")
        filters.append(f"shop_lng >= {lng_min} and shop_lng <= {lng_max}")

    # 小模型意图提取
    if semantic_query:
        # TODO: 从 DiscountTypeCache 获取分类列表（这里先硬编码测试）
        type_list: str = "1. 满减\n2. 折扣\n3. 赠送"
        try:
            intent: dict = await extract_intent(semantic_query, type_list)
            if intent.get("activity_category"):
                filters.append(f'activity_category == "{intent["activity_category"]}"')
        except Exception as e:
            print(f"意图提取失败: {e}")

    filter_expr: str = " and ".join(filters) if filters else ""

    # Hybrid search vs 纯结构化搜索
    if semantic_query:
        query_vec: list[float] = embed(semantic_query)

        req1: AnnSearchRequest = AnnSearchRequest(
            data=[query_vec],
            anns_field="content_vector",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            expr=filter_expr if filter_expr else None,
        )
        req2: AnnSearchRequest = AnnSearchRequest(
            data=[query_vec],
            anns_field="description_vector",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            expr=filter_expr if filter_expr else None,
        )

        results = collection.hybrid_search(
            [req1, req2],
            rerank=RRFRanker(),
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
        )
    else:
        # 无语义查询，纯结构化搜索
        results = collection.query(
            expr=filter_expr if filter_expr else "activity_id > 0",
            output_fields=OUTPUT_FIELDS,
            limit=top_k,
        )

    # 格式化返回
    activities: list[dict] = []

    def _to_activity(entity: dict) -> dict:
        result: dict = {
            "activity_id": entity.get("activity_id"),
            "activity_name": entity.get("content"),
            "shop_id": entity.get("commercial_id"),
            "activity_description": entity.get("description"),
            "discount_amount": entity.get("relative_amount"),
            "activity_category": entity.get("activity_category"),
            "commercial_name": entity.get("commercial_name"),
            "address": entity.get("address"),
            "phone": entity.get("phone"),
            "rating": entity.get("rating"),
            "opening_hours": entity.get("opening_hours"),
        }
        # 如果有用户坐标，计算距离
        if latitude is not None and longitude is not None:
            s_lat: float | None = entity.get("shop_lat")
            s_lng: float | None = entity.get("shop_lng")
            if s_lat is not None and s_lng is not None:
                result["distance_km"] = _haversine(latitude, longitude, s_lat, s_lng)
        return result

    if semantic_query:
        # hybrid_search 返回 list[list[Hit]]
        for hits in results:
            for hit in hits:
                entity = hit.entity if hasattr(hit, "entity") else hit
                activities.append(_to_activity(entity))
    else:
        # query 返回 list[dict]
        for row in results:
            activities.append(_to_activity(row))

    # 按距离排序（如果有）
    if latitude is not None and longitude is not None:
        activities.sort(key=lambda a: a.get("distance_km", float("inf")))

    return {"status": 0, "result": {"shopActivities": activities}}


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine 公式计算两点距离（km）"""
    r: float = 6371.0
    d_lat: float = math.radians(lat2 - lat1)
    d_lng: float = math.radians(lng2 - lng1)
    a: float = (math.sin(d_lat / 2) ** 2
                + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
                * math.sin(d_lng / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "coupon-search"}
