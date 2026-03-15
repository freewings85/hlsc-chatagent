"""车辆信息模型"""

from typing import Optional

from pydantic import BaseModel


class CarInfo(BaseModel):
    """车辆信息"""

    car_model_id: str                   # 车型编码，用于 API 精准查询
    car_model_name: str                 # 车型名称，用于展示
    vin_code: Optional[str] = None      # VIN 码
