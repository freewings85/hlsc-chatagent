#!/usr/bin/env python3
"""搜索零部件 — 根据关键词从零部件库中检索匹配结果。

用法：python search_parts.py --keyword 刹车片 --car_model_id CAR-001
"""

import argparse
import asyncio
import json
import os
import sys

import httpx

CAR_PART_RETRIEVAL_URL = os.getenv("CAR_PART_RETRIEVAL_URL", "")


async def search(keyword: str, car_model_id: str) -> dict:
    if not CAR_PART_RETRIEVAL_URL:
        return {"error": "CAR_PART_RETRIEVAL_URL 未配置"}

    payload = {
        "part_names": [keyword],
        "carKey": car_model_id,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(CAR_PART_RETRIEVAL_URL, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 0:
            return {"error": data.get("message", "未知错误")}

        result = data.get("result", {})

        # 解析精确匹配
        exact = [
            {"part_id": item.get("primary_part_id", 0), "name": item.get("part_name", "")}
            for item in (result.get("exact_matched") or [])
        ]

        # 解析模糊匹配 + RAG 匹配
        fuzzy = [
            {"part_id": item.get("primary_part_id", 0), "name": item.get("part_name", "")}
            for item in (result.get("fuzzy_matched") or [])
        ]
        for group in (result.get("rag_matched") or []):
            for c in (group.get("candidates") or []):
                fuzzy.append({"part_id": c.get("primary_part_id", 0), "name": c.get("part_name", "")})

        # 去重
        seen = set()
        deduped_fuzzy = []
        for p in fuzzy:
            if p["part_id"] and p["part_id"] not in seen:
                seen.add(p["part_id"])
                deduped_fuzzy.append(p)

        return {"keyword": keyword, "parts": {"exact": exact, "fuzzy": deduped_fuzzy}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--car_model_id", required=True)
    args = parser.parse_args()

    result = asyncio.run(search(args.keyword, args.car_model_id))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
