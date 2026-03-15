"""模糊匹配车型服务

根据用户自然语言描述的车型名称，从车型库中匹配对应的 CarInfo。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from hlsc.models import CarInfo

logger = logging.getLogger(__name__)

# 接口地址（环境变量配置）
FUZZY_MATCH_CAR_URL = os.getenv("FUZZY_MATCH_CAR_URL", "")


class FuzzyMatchCarService:
    """模糊匹配车型服务"""

    async def match(self, query: str, session_id: str = "") -> Optional[CarInfo]:
        """根据用户输入的车型关键词匹配车型。

        Args:
            query: 车型关键词，如"宝马X3"、"卡罗拉"
            session_id: 会话 ID

        Returns:
            匹配成功返回 CarInfo，失败返回 None
        """
        if not query:
            return None

        url = FUZZY_MATCH_CAR_URL
        if not url:
            logger.warning("FUZZY_MATCH_CAR_URL 未配置")
            return None

        payload = {
            "queryKey": query,
            "conversationId": session_id,
        }

        logger.info(f"[fuzzy_match_car] POST {url} payload={payload}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            logger.info(f"[fuzzy_match_car] status={response.status_code} data={data}")

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


# 单例
fuzzy_match_car_service = FuzzyMatchCarService()
