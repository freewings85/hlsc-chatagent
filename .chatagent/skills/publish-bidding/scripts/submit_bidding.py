"""提交竞价：调用后端 API 提交询价请求。

用法：
    python submit_bidding.py '<task_data_json>'

输入：prepare_bidding.py 输出的 task_data JSON（经用户确认后的版本）。

输出：JSON 格式，包含 inquiry_id 或 error。
"""

import asyncio
import json
import sys
from typing import Any


async def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺少参数，用法: python submit_bidding.py '<task_data_json>'"}))
        sys.exit(1)

    try:
        task_data: dict[str, Any] = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败: {e}"}))
        sys.exit(1)

    try:
        from src.services.restful.submit_inquiry_service import submit_inquiry_service

        inquiry_id: str = await submit_inquiry_service.submit(
            inquiry_task_id=task_data.get("inquiry_task_id", ""),
            projects=task_data.get("projects", []),
            filters=task_data.get("filters"),
            car_model_id=task_data.get("car_model_id", ""),
            car_model_name=task_data.get("car_model_name", ""),
            description=task_data.get("description", ""),
            preferred_time=task_data.get("preferred_time", ""),
            conversation_id=task_data.get("conversation_id", ""),
            longitude=task_data.get("longitude"),
            latitude=task_data.get("latitude"),
        )

        result: dict[str, Any] = {
            "inquiry_id": inquiry_id,
            "inquiry_task_id": task_data.get("inquiry_task_id", ""),
            "status": "submitted",
        }
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"error": f"提交失败: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
