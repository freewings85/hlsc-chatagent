"""模糊匹配车型服务

根据用户自然语言描述的车型名称，从车型库中匹配对应的 CarInfo。
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from agent_sdk.logging import log_http_request, log_http_response
from hlsc.models import CarInfo

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_FUZZY_MATCH_CAR_PATH: str = "/service_ai_datamanager/Auto/getCarModelByQueryKey"


class FuzzyMatchCarService:
    """模糊匹配车型服务"""

    async def match(
        self, query: str, session_id: str = "", request_id: str = "",
    ) -> Optional[CarInfo]:
        """根据用户输入的车型关键词匹配车型。

        Raises:
            RuntimeError: URL 未配置或 API 返回错误状态
        """
        if not query:
            return None

        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")
        url: str = f"{DATA_MANAGER_URL}{_FUZZY_MATCH_CAR_PATH}"

        payload = {"queryKey": query, "conversationId": session_id}
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                result = data.get("result")
                if result and result.get("car_key"):
                    return CarInfo(
                        car_model_id=result["car_key"],
                        car_model_name=result.get("car_name", ""),
                        vin_code=result.get("vin_code") or None,
                    )
                return None
            else:
                error_msg = data.get("message", "未知错误")
                raise RuntimeError(f"模糊匹配车型失败: {error_msg}")


fuzzy_match_car_service = FuzzyMatchCarService()
