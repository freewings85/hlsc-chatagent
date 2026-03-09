"""提交竞价：调用后端 API 提交询价请求。

用法：
    python submit_bidding.py '<task_data_json>'

输入：prepare_bidding.py 输出的 task_data JSON（经用户确认后的版本）。

输出：JSON 格式，包含 inquiry_id 或 error。

环境变量：
    INQUIRY_SUBMIT_URL — 提交询价的 API 地址
"""

import json
import os
import sys
from typing import Any

import httpx


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺少参数，用法: python submit_bidding.py '<task_data_json>'"}))
        sys.exit(1)

    try:
        task_data: dict[str, Any] = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败: {e}"}))
        sys.exit(1)

    url = os.getenv("INQUIRY_SUBMIT_URL", "")
    if not url:
        print(json.dumps({"error": "环境变量 INQUIRY_SUBMIT_URL 未设置"}))
        sys.exit(1)

    try:
        transport = httpx.HTTPTransport(proxy=None)
        with httpx.Client(transport=transport, timeout=30) as client:
            resp = client.post(url, json=task_data)
            resp.raise_for_status()
            result_data = resp.json()

        result: dict[str, Any] = {
            "inquiry_id": result_data.get("inquiry_id", ""),
            "inquiry_task_id": task_data.get("inquiry_task_id", ""),
            "status": "submitted",
        }
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"error": f"提交失败: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
