"""位置过滤条件模型"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LocationFilter(BaseModel):
    """位置条件 — 支持范围搜索和区域过滤，可组合使用。

    范围搜索：address + radius → 以某地为中心搜周边
    区域过滤：city / district / street → 按行政区/路名过滤
    """

    # 范围搜索（以某地为中心）
    address: Optional[str] = Field(
        None,
        description="中心地址，如'人民广场'、'张江高科'。不传则使用用户当前位置",
    )
    radius: Optional[int] = Field(
        None,
        description="搜索半径（米）。需要有中心点：指定 address 或用户已有位置",
    )

    # 区域过滤
    city: Optional[str] = Field(None, description="城市，如'上海'")
    district: Optional[str] = Field(None, description="区，如'静安区'")
    street: Optional[str] = Field(None, description="路名，如'淮海中路'")
