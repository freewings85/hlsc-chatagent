"""用户车辆列表服务

调用后端 API 获取用户绑定的车辆列表。
"""

from __future__ import annotations

import logging
import os
from typing import List

import httpx

from hlsc.models import CarInfo

logger = logging.getLogger(__name__)

LIST_USER_CARS_URL = os.getenv("LIST_USER_CARS_URL", "")


class ListUserCarsService:
    """用户车辆列表服务"""

    async def get_user_cars(self, session_id: str) -> List[CarInfo]:
        """获取用户绑定的车辆列表。

        Args:
            session_id: 会话 ID

        Returns:
            车辆列表
        """
        url = LIST_USER_CARS_URL
        if not url:
            logger.warning("LIST_USER_CARS_URL 未配置")
            return []

        payload = {"conversationId": session_id}

        logger.info(f"[list_user_cars] POST {url} payload={payload}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                logger.info(f"[list_user_cars] status={response.status_code} count={len(data.get('result', []))}")

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
                    logger.error(f"[list_user_cars] API error: {error_msg}")
                    return []

        except Exception as e:
            logger.error(f"[list_user_cars] error: {e}")
            return []


# 单例
list_user_cars_service = ListUserCarsService()
