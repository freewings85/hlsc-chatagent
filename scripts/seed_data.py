"""
seed_data.py — 模拟 Kafka 消息 + 商户详情补充 + embedding + 写入 Milvus

用法:
    python scripts/seed_data.py              # 全流程: produce -> consume -> 入库
    python scripts/seed_data.py --produce    # 只发 Kafka
    python scripts/seed_data.py --consume    # 只消费 + 入库
    python scripts/seed_data.py --verify     # 只验证 Milvus 数据
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import httpx
from kafka import KafkaConsumer, KafkaProducer
from pymilvus import Collection, connections

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP: str = "localhost:9092"
KAFKA_TOPIC: str = "coupon-events"
MILVUS_HOST: str = "localhost"
MILVUS_PORT: str = "19530"
MILVUS_COLLECTION: str = "coupon_activities"
EMBEDDING_URL: str = "http://localhost:7683/v1/embeddings"
EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
DATA_MANAGER_URL: str = "http://192.168.100.108:50400"
CONSUMER_GROUP: str = "test-coupon-consumer"
CONSUMER_TIMEOUT_MS: int = 15000

# ---------------------------------------------------------------------------
# 测试数据 (8 条 CommercialActivityDTO)
# ---------------------------------------------------------------------------
TEST_ACTIVITIES: list[dict] = [
    {
        "activityId": 2001, "commercialId": 101, "packageId": 5001,
        "packageName": "换机油", "content": "换机油满500减80",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-06-30 23:59:59",
        "description": "满500元减80元，支持支付宝和微信支付，赠送免费洗车一次",
        "opCode": 0, "activityCategory": "满减", "relativeAmount": 80.0,
    },
    {
        "activityId": 2002, "commercialId": 102, "packageId": 5002,
        "packageName": "换轮胎", "content": "轮胎8折优惠",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-05-31 23:59:59",
        "description": "指定品牌轮胎享8折，含免费安装和动平衡，仅限微信支付",
        "opCode": 0, "activityCategory": "折扣", "relativeAmount": 120.0,
    },
    {
        "activityId": 2003, "commercialId": 103, "packageId": 5001,
        "packageName": "换机油", "content": "保养套餐送机油",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-07-31 23:59:59",
        "description": "做保养送全合成机油一桶，仅限周末使用，需提前预约，支持支付宝付款",
        "opCode": 0, "activityCategory": "赠送", "relativeAmount": 60.0,
    },
    {
        "activityId": 2004, "commercialId": 101, "packageId": 5003,
        "packageName": "空调清洗", "content": "空调清洗满200减50",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-06-30 23:59:59",
        "description": "空调系统深度清洗满200元减50元，含杀菌除味，仅限支付宝支付",
        "opCode": 0, "activityCategory": "满减", "relativeAmount": 50.0,
    },
    {
        "activityId": 2005, "commercialId": 103, "packageId": 5004,
        "packageName": "喷漆补漆", "content": "喷漆补漆送抛光",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-05-15 23:59:59",
        "description": "喷漆或补漆项目赠送全车抛光一次，需提前一天预约",
        "opCode": 0, "activityCategory": "赠送", "relativeAmount": 100.0,
    },
    {
        "activityId": 2006, "commercialId": 102, "packageId": 5005,
        "packageName": "刹车片更换", "content": "刹车片更换7折",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-08-31 23:59:59",
        "description": "原厂刹车片更换享7折优惠，含工时费，支持花呗分期",
        "opCode": 0, "activityCategory": "折扣", "relativeAmount": 150.0,
    },
    {
        "activityId": 2007, "commercialId": 101, "packageId": 5001,
        "packageName": "换机油", "content": "机油滤芯买一送一",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-04-30 23:59:59",
        "description": "购买机油滤芯一个赠送一个，限品牌型号，送免费洗车，活动即将结束",
        "opCode": 0, "activityCategory": "赠送", "relativeAmount": 40.0,
    },
    {
        "activityId": 2008, "commercialId": 103, "packageId": 5002,
        "packageName": "换轮胎", "content": "轮胎满4条减200",
        "startTime": "2026-04-01 00:00:00", "endTime": "2026-12-31 23:59:59",
        "description": "一次更换4条轮胎减200元，含四轮定位，支持支付宝微信银行卡",
        "opCode": 0, "activityCategory": "满减", "relativeAmount": 200.0,
    },
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def embed(text: str) -> list[float]:
    """调用 vLLM embedding 服务获取向量"""
    resp: httpx.Response = httpx.post(
        EMBEDDING_URL,
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def ts_millis(time_str: str) -> int:
    """时间字符串 -> Unix 毫秒"""
    dt: datetime = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    return int(dt.timestamp() * 1000)


def fetch_shop_details(commercial_ids: list[int]) -> dict[int, dict]:
    """批量调 DataManager getShopsById 获取商户详情，返回 {commercialId: shop_info}"""
    url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/shop/getShopsById"
    print(f"[shop] 调用 DataManager 获取 {len(commercial_ids)} 个商户详情...")
    resp: httpx.Response = httpx.post(
        url,
        json={"commercialIds": commercial_ids},
        timeout=15.0,
    )
    resp.raise_for_status()
    data: dict = resp.json()
    if data.get("status") != 0:
        raise RuntimeError(f"getShopsById 失败: {data.get('message')}")

    shop_map: dict[int, dict] = {}
    for shop in data["result"]["commercials"]:
        cid: int = shop["commercialId"]
        shop_map[cid] = {
            "commercial_name": shop.get("commercialName") or "",
            "shop_lat": float(shop.get("latitude") or 0.0),
            "shop_lng": float(shop.get("longitude") or 0.0),
            "province": shop.get("provinceName") or "",
            "city_name": shop.get("cityName") or "",
            "district": shop.get("districtName") or "",
            "address": shop.get("address") or "",
            "phone": shop.get("phone") or "",
            "rating": float(shop.get("rating") or 0.0),
            "service_scope": shop.get("serviceScope") or "",
            "opening_hours": _format_opening_hours(shop.get("openingHour")),
        }
        print(f"  商户 {cid}: {shop_map[cid]['commercial_name']} ({shop_map[cid]['city_name']})")
    return shop_map


def _format_opening_hours(opening_hour: dict | None) -> str:
    """格式化营业时间"""
    if not opening_hour:
        return ""
    start: str = opening_hour.get("starTime") or ""
    end: str = opening_hour.get("endTime") or ""
    if start and end:
        return f"{start}-{end}"
    return ""


# 空商户详情（DataManager 未返回时的兜底）
_EMPTY_SHOP: dict[str, object] = {
    "commercial_name": "", "shop_lat": 0.0, "shop_lng": 0.0,
    "province": "", "city_name": "", "district": "", "address": "",
    "phone": "", "rating": 0.0, "service_scope": "", "opening_hours": "",
}


# ---------------------------------------------------------------------------
# 步骤 1: 发送 Kafka 消息
# ---------------------------------------------------------------------------
def produce(activities: list[dict]) -> None:
    print(f"[produce] 连接 Kafka: {KAFKA_BOOTSTRAP}")
    producer: KafkaProducer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )
    for activity in activities:
        producer.send(KAFKA_TOPIC, value=activity)
        print(f"  发送: {activity['activityId']} - {activity['content']}")
    producer.flush()
    producer.close()
    print(f"[produce] 完成，共发送 {len(activities)} 条消息")


# ---------------------------------------------------------------------------
# 步骤 2: 消费 Kafka + 补充商户详情 + embedding + 写入 Milvus
# ---------------------------------------------------------------------------
def consume_and_ingest() -> int:
    print(f"[consume] 连接 Milvus: {MILVUS_HOST}:{MILVUS_PORT}")
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    collection: Collection = Collection(MILVUS_COLLECTION)

    print(f"[consume] 连接 Kafka consumer: {KAFKA_BOOTSTRAP}, topic={KAFKA_TOPIC}")
    consumer: KafkaConsumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        group_id=CONSUMER_GROUP,
        consumer_timeout_ms=CONSUMER_TIMEOUT_MS,
    )

    # 先收集所有消息，批量查商户
    messages: list[dict] = []
    for msg in consumer:
        messages.append(msg.value)
    consumer.close()
    print(f"[consume] 收到 {len(messages)} 条 Kafka 消息")

    if not messages:
        print("[consume] 无消息，跳过")
        connections.disconnect("default")
        return 0

    # 提取所有 commercialId，批量查商户详情
    commercial_ids: list[int] = list({dto["commercialId"] for dto in messages if dto.get("opCode") != 3})
    shop_map: dict[int, dict] = fetch_shop_details(commercial_ids) if commercial_ids else {}

    # 逐条处理
    ingested: int = 0
    deleted: int = 0
    for dto in messages:
        op_code: int = dto.get("opCode", 0)

        # opCode == 3 表示删除
        if op_code == 3:
            collection.delete(f"activity_id == {dto['activityId']}")
            print(f"  删除: {dto['activityId']}")
            deleted += 1
            continue

        # embedding
        content_text: str = dto["content"]
        desc_text: str = dto["description"]
        print(f"  embedding: {dto['activityId']} - {content_text}")
        content_vec: list[float] = embed(content_text)
        desc_vec: list[float] = embed(desc_text)

        # 时间转毫秒
        start_ts: int = ts_millis(dto["startTime"])
        end_ts: int = ts_millis(dto["endTime"])

        # 商户详情
        shop: dict = shop_map.get(dto["commercialId"], _EMPTY_SHOP)

        # upsert 到 Milvus（23 个字段，顺序与 schema 一致）
        collection.upsert([
            # 活动字段 (10)
            [dto["activityId"]],
            [dto["commercialId"]],
            [dto["packageId"]],
            [dto["packageName"]],
            [dto.get("activityCategory", "")],
            [start_ts],
            [end_ts],
            [dto.get("relativeAmount", 0.0)],
            [content_text],
            [desc_text],
            # 商户字段 (11)
            [shop["commercial_name"]],
            [float(shop["shop_lat"])],
            [float(shop["shop_lng"])],
            [shop["province"]],
            [shop["city_name"]],
            [shop["district"]],
            [shop["address"]],
            [shop["phone"]],
            [float(shop["rating"])],
            [shop["service_scope"]],
            [shop["opening_hours"]],
            # 向量字段 (2)
            [content_vec],
            [desc_vec],
        ])
        ingested += 1
        print(f"  入库: {dto['activityId']} - {content_text} (商户: {shop['commercial_name']}, {shop['city_name']})")

    collection.flush()
    entity_count: int = collection.num_entities
    print(f"[consume] 完成，入库 {ingested} 条，删除 {deleted} 条，Milvus 总数据量: {entity_count}")
    connections.disconnect("default")
    return entity_count


# ---------------------------------------------------------------------------
# 步骤 3: 验证数据
# ---------------------------------------------------------------------------
def verify() -> None:
    print(f"[verify] 连接 Milvus: {MILVUS_HOST}:{MILVUS_PORT}")
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    collection: Collection = Collection(MILVUS_COLLECTION)
    collection.flush()
    count: int = collection.num_entities
    print(f"[verify] Collection '{MILVUS_COLLECTION}' entities: {count}")
    if count >= 8:
        print("[verify] OK - 数据量符合预期 (>= 8)")
    else:
        print(f"[verify] WARNING - 期望 >= 8 条，实际 {count} 条")

    # 查询验证（含商户字段）
    collection.load()
    results = collection.query(
        expr="activity_id > 0",
        output_fields=[
            "activity_id", "content", "activity_category",
            "commercial_name", "city_name", "shop_lat", "shop_lng", "rating",
        ],
        limit=10,
    )
    print(f"[verify] 查询结果 ({len(results)} 条):")
    for row in results:
        print(
            f"  id={row['activity_id']} "
            f"category={row['activity_category']} "
            f"content={row['content']} "
            f"| 商户={row['commercial_name']} "
            f"city={row['city_name']} "
            f"lat={row['shop_lat']:.6f} lng={row['shop_lng']:.6f} "
            f"rating={row['rating']}"
        )
    connections.disconnect("default")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Seed coupon data: Kafka -> DataManager shop enrichment -> embedding -> Milvus"
    )
    parser.add_argument("--produce", action="store_true", help="只发送 Kafka 消息")
    parser.add_argument("--consume", action="store_true", help="只消费 Kafka + 入库 Milvus")
    parser.add_argument("--verify", action="store_true", help="只验证 Milvus 数据")
    args: argparse.Namespace = parser.parse_args()

    # 如果没指定任何 flag，执行全流程
    run_all: bool = not (args.produce or args.consume or args.verify)

    if args.produce or run_all:
        produce(TEST_ACTIVITIES)
        if run_all:
            print("[main] 等待 2 秒让 Kafka 消息就绪...")
            time.sleep(2)

    if args.consume or run_all:
        consume_and_ingest()

    if args.verify or run_all:
        verify()

    print("[main] 全部完成")


if __name__ == "__main__":
    main()
