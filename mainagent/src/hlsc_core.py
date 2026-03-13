"""
hlsc汽车服务核心概念
"""
from typing import Optional
from pydantic import BaseModel

#车辆信息
class CarInfo(BaseModel):
    """车辆信息"""
    car_model_id: str                   # 车型编码，用于 API 精准查询
    car_model_name: str                 # 车型名称，用于展示
    vin_code: Optional[str] = None      # VIN 码


#位置信息数据类
class LocationInfo(BaseModel):
    """位置信息"""
    address: str                    # 地址文本，如"浦东新区张江"
    lat: Optional[float] = None     # 纬度
    lng: Optional[float] = None     # 经度