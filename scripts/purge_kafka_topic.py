"""清理 Kafka topic 数据 — 删除后重建。

用法：
  python purge_kafka_topic.py <bootstrap_servers> <topic> [partitions]
  python purge_kafka_topic.py 192.168.100.108:9092 shop-sync
  python purge_kafka_topic.py 192.168.100.108:9092 shop-sync 12
"""

import sys
import time
from kafka import KafkaConsumer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic


def purge_topic(bootstrap_servers: str, topic: str, num_partitions: int = 12) -> None:
    print(f"连接 Kafka: {bootstrap_servers}")
    print(f"清理 topic: {topic}")

    # 先查看当前数据量
    consumer = KafkaConsumer(bootstrap_servers=bootstrap_servers, consumer_timeout_ms=5000)
    partitions = consumer.partitions_for_topic(topic)
    if not partitions:
        print(f"Topic '{topic}' 不存在")
        consumer.close()
        return

    current_partitions: int = len(partitions)
    tps = [TopicPartition(topic, p) for p in sorted(partitions)]
    begin = consumer.beginning_offsets(tps)
    end = consumer.end_offsets(tps)
    total: int = sum(end[tp] - begin[tp] for tp in tps)
    print(f"  当前 partitions={current_partitions}, 总消息数={total}")
    consumer.close()

    # 删除 topic
    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
    print(f"删除 topic '{topic}'...")
    try:
        admin.delete_topics([topic])
    except Exception as e:
        print(f"删除失败: {e}")
        admin.close()
        return

    # 等待删除完成
    print("等待 10 秒...")
    time.sleep(10)

    # 重建 topic
    use_partitions: int = num_partitions if num_partitions > 0 else current_partitions
    print(f"重建 topic '{topic}' (partitions={use_partitions})...")
    new_topic = NewTopic(name=topic, num_partitions=use_partitions, replication_factor=1)
    try:
        admin.create_topics([new_topic])
        print(f"Topic '{topic}' 重建完成!")
    except Exception as e:
        print(f"重建失败: {e}")

    admin.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python purge_kafka_topic.py <bootstrap_servers> <topic> [partitions]")
        sys.exit(1)

    partitions: int = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    purge_topic(sys.argv[1], sys.argv[2], partitions)
