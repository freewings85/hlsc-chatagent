"""用户状态服务：根据 user_id 返回用户当前阶段和关键状态。

内存数据库实现，进程内持久化。后续接入真实数据源。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class UserStat:
    """用户状态。"""

    stage: str = "S1"               # "S1" | "S2"
    has_ordered: bool = False       # 是否下过单
    has_vin: bool = False           # 是否上传过 VIN 码
    has_driving_license: bool = False  # 是否上传过行驶证
    has_bound_car: bool = False     # 是否绑定过车辆


class UserStatService:
    """用户状态服务（内存数据库实现）。

    进程级持久化：同一进程内跨 session 有效，重启后重置。
    后续接入真实数据源（用户中心 API）。
    """

    def __init__(self) -> None:
        self._store: dict[str, UserStat] = {}

    def _get_or_create(self, user_id: str) -> UserStat:
        """获取用户状态，不存在则创建默认值。"""
        if user_id not in self._store:
            self._store[user_id] = UserStat()
        return self._store[user_id]

    async def get_user_stat(self, user_id: str) -> UserStat:
        """根据 user_id 返回用户状态。"""
        stat: UserStat = self._get_or_create(user_id)
        logger.debug("获取用户状态: user_id=%s, stage=%s", user_id, stat.stage)
        return stat

    def is_s2_by_hard_signal(self, stat: UserStat) -> bool:
        """根据硬信号判断是否已经是 S2。"""
        return (
            stat.stage == "S2"
            or stat.has_ordered
            or stat.has_vin
            or stat.has_bound_car
        )

    async def upgrade_to_s2(self, user_id: str) -> None:
        """将用户阶段从 S1 升级到 S2。S2 不回退。"""
        stat: UserStat = self._get_or_create(user_id)
        if stat.stage != "S2":
            stat.stage = "S2"
            logger.info("用户 %s 升级到 S2", user_id)


# 模块级单例
user_stat_service: UserStatService = UserStatService()
