"""hlsc 汽车服务核心概念（从 extensions 重新导出）"""

from hlsc.models import CarInfo, LocationInfo

MESSAGE_ORIGIN_USER: str = "user"

__all__ = ["CarInfo", "LocationInfo", "MESSAGE_ORIGIN_USER"]
