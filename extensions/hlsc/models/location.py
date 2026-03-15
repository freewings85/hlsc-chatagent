"""位置信息模型"""

from typing import Optional

from pydantic import BaseModel


class LocationInfo(BaseModel):
    """位置信息"""

    address: str                    # 地址文本，如"浦东新区张江"
    lat: Optional[float] = None     # 纬度
    lng: Optional[float] = None     # 经度
