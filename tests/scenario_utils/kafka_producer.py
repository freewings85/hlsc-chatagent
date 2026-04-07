"""Kafka 数据造入工具 — 向 shop/coupon consumer 发送测试事件"""

from __future__ import annotations

import json
import time
from typing import Any

from kafka import KafkaProducer
from pymilvus import Collection, connections

# Kafka 默认配置（与 consumer 的 bootstrap-local.properties 一致）
KAFKA_BOOTSTRAP: str = "localhost:9092"
SHOP_TOPIC: str = "commercial-shop-rag"
COUPON_TOPIC: str = "commercial-activity-rag"


def _get_producer(bootstrap_servers: str = KAFKA_BOOTSTRAP) -> KafkaProducer:
    """创建 Kafka producer。"""
    return KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda k: str(k).encode("utf-8") if k is not None else None,
    )


def send_shop_events(
    shops: list[dict[str, Any]],
    bootstrap_servers: str = KAFKA_BOOTSTRAP,
) -> int:
    """发送商户数据到 commercial-shop-rag topic。

    每条 shop dict 需包含 ShopEventDTO 字段：
    commercialId, commercialName, provinceName, cityName, districtName,
    address, serviceScope, phone, openingHours, longitude, latitude,
    rating, commercialType (list[int]), operationType (1=新增)
    """
    producer: KafkaProducer = _get_producer(bootstrap_servers)
    count: int = 0
    for shop in shops:
        key: str = str(shop.get("commercialId", ""))
        producer.send(SHOP_TOPIC, value=shop, key=key)
        count += 1
    producer.flush()
    producer.close()
    print(f"[kafka] 发送 {count} 条商户事件到 {SHOP_TOPIC}")
    return count


def send_coupon_events(
    coupons: list[dict[str, Any]],
    bootstrap_servers: str = KAFKA_BOOTSTRAP,
) -> int:
    """发送优惠活动数据到 commercial-activity-rag topic。

    每条 coupon dict 需包含 CouponEventDTO 字段：
    activityId, commercialId, packageId, packageName, content,
    startTime, endTime, description, activityCategory,
    promoValue, relativeAmount, operationType (1=添加)
    """
    producer: KafkaProducer = _get_producer(bootstrap_servers)
    count: int = 0
    for coupon in coupons:
        key: str = str(coupon.get("activityId", ""))
        producer.send(COUPON_TOPIC, value=coupon, key=key)
        count += 1
    producer.flush()
    producer.close()
    print(f"[kafka] 发送 {count} 条优惠事件到 {COUPON_TOPIC}")
    return count


def wait_for_consumer(
    collection_name: str,
    expected_count: int,
    timeout: int = 30,
    host: str = "localhost",
    port: str = "19530",
) -> bool:
    """等待 consumer 将数据入库到 Milvus，达到 expected_count 条。

    返回 True 表示在 timeout 内达成，False 表示超时。
    """
    connections.connect(host=host, port=port)
    coll: Collection = Collection(collection_name)

    deadline: float = time.monotonic() + timeout
    while time.monotonic() < deadline:
        coll.flush()
        current: int = coll.num_entities
        if current >= expected_count:
            print(f"[kafka] {collection_name} 已入库 {current} 条（期望 {expected_count}）")
            return True
        time.sleep(1)

    coll.flush()
    final: int = coll.num_entities
    print(f"[kafka] 超时！{collection_name} 当前 {final} 条，期望 {expected_count}")
    return False
