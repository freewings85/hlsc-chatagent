"""用户车辆详情服务

调用 datamanager API 获取用户车库中的车辆详细信息。
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
from pydantic import BaseModel

from agent_sdk.logging import log_http_request, log_http_response

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_GET_MY_CAR_PATH: str = "/service_ai_datamanager/Auto/getMyCarModel"


class MyCarModel(BaseModel):
    """用户车库中的车辆详细信息"""

    car_key: str                               # 车辆唯一标识（如 my_3483）
    car_name: str                              # 车型名称
    vin_code: Optional[str] = None             # VIN 码
    auto_info: Optional[str] = None            # 车型补充信息
    car_param_list: Optional[list] = None      # 车辆参数列表
    mmu_ids: Optional[list[int]] = None        # mmu ID 列表
    month: int = 0                             # 月份
    out_of_warranty: Optional[str] = None      # 是否过保
    car_number: Optional[str] = None           # 车牌号
    engine_number: Optional[str] = None        # 发动机号
    registration_time: Optional[str] = None    # 注册日期


class GetMyCarService:
    """获取用户车库车辆详情"""

    async def get_my_cars(
        self,
        session_id: str,
        user_id: int,
        request_id: str = "",
    ) -> list[MyCarModel]:
        """获取用户车库中的车辆列表（含车牌号、VIN、注册日期等详细信息）。

        Raises:
            RuntimeError: URL 未配置或 API 返回错误状态
        """
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

        url: str = f"{DATA_MANAGER_URL}{_GET_MY_CAR_PATH}"
        payload: dict[str, object] = {
            "conversationId": session_id,
            "userId": user_id,
        }
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                car_list: list[dict] = data.get("result", [])
                return [
                    MyCarModel(
                        car_key=c.get("car_key", ""),
                        car_name=c.get("car_name", ""),
                        vin_code=c.get("vin_code") or None,
                        auto_info=c.get("autoInfo") or None,
                        car_param_list=c.get("carParamList") or None,
                        mmu_ids=c.get("mmuIds") or None,
                        month=c.get("month", 0),
                        out_of_warranty=c.get("outOfWarranty") or None,
                        car_number=c.get("carNumber") or None,
                        engine_number=c.get("engineNumber") or None,
                        registration_time=c.get("registrationTime") or None,
                    )
                    for c in car_list
                ]
            else:
                error_msg: str = data.get("message", "未知错误")
                raise RuntimeError(f"获取用户车辆详情失败: {error_msg}")


get_my_car_service: GetMyCarService = GetMyCarService()
