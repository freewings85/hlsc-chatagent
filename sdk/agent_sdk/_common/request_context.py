"""RequestContext：请求上下文基类。

业务层继承此类扩展字段（如位置、车辆信息等）。
随请求传递，贯穿 server → task → deps → tool 全链路。
"""

from pydantic import BaseModel


class RequestContext(BaseModel):
    """请求上下文基类。业务继承扩展字段。"""
