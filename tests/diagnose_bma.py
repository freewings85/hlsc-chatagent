"""
诊断 BMA 场景分类功能

检查：
1. BMA 服务是否在线
2. BMA 对 searchcoupons 相关输入的分类结果
3. MainAgent 的 fallback 行为
"""

import asyncio
import json
import os
from uuid import uuid4

import httpx


async def test_bma_classification() -> None:
    """测试 BMA 对 searchcoupons 相关输入的分类"""

    # 从环境变量读取 BMA URL，或使用默认值
    bma_url: str = os.getenv("BMA_CLASSIFY_URL", "")
    if not bma_url:
        # 回退到旧配置
        from src.config import BUSINESS_MAP_AGENT_URL
        bma_url = f"{BUSINESS_MAP_AGENT_URL.rstrip('/')}/classify"

    print(f"\n{'='*80}")
    print(f"BMA 分类诊断")
    print(f"{'='*80}\n")

    print(f"BMA 地址: {bma_url}\n")

    # 测试用例
    test_messages: list[str] = [
        "换机油有优惠吗？",
        "帮我查查轮胎的优惠。",
        "有什么优惠活动吗？",
        "帮我预订换机油。",
        "我要保养一下车。",
    ]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for message in test_messages:
                try:
                    payload: dict = {"message": message}
                    print(f"输入: '{message}'")
                    print(f"请求: POST {bma_url}")

                    resp: httpx.Response = await client.post(bma_url, json=payload)
                    resp.raise_for_status()
                    data: dict = resp.json()
                    scenes: list[str] = data.get("scenes", [])

                    print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    print(f"分类结果: {scenes if scenes else '[]（回退到 guide 场景）'}\n")

                except Exception as e:
                    print(f"❌ 分类失败: {e}\n")

    except Exception as e:
        print(f"❌ BMA 连接失败: {e}")
        print(f"\n请检查：")
        print(f"  1. BMA 服务是否在线？")
        print(f"  2. BMA 地址是否正确？({bma_url})")
        print(f"  3. 网络连接是否正常？")


if __name__ == "__main__":
    asyncio.run(test_bma_classification())
