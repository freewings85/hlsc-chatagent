"""用户车辆列表服务

调用后端 API 获取用户绑定的车辆列表。
"""

from __future__ import annotations

import os
from typing import List

import httpx

from agent_sdk.logging import log_http_request, log_http_response
from hlsc.models import CarInfo

LIST_USER_CARS_URL = os.getenv("LIST_USER_CARS_URL", "")


class ListUserCarsService:
    """用户车辆列表服务"""

    async def get_user_cars(
        self, session_id: str, request_id: str = "",
    ) -> List[CarInfo]:
        """获取用户绑定的车辆列表。

        Raises:
            RuntimeError: URL 未配置或 API 返回错误状态
        """
        url = LIST_USER_CARS_URL
        if not url:
            raise RuntimeError("LIST_USER_CARS_URL 未配置")

        payload = {"conversationId": session_id}
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return [
                    CarInfo(
                        car_model_id=c.get("car_key", ""),
                        car_model_name=c.get("car_name", ""),
                        vin_code=c.get("vin_code") or None,
                    )
                    for c in data.get("result", [])
                ]
            else:
                error_msg = data.get("message", "未知错误")
                raise RuntimeError(f"获取用户车辆失败: {error_msg}")


list_user_cars_service = ListUserCarsService()
