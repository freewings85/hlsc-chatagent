"""用户状态服务：判断用户当前阶段（S1/S2）。

判断逻辑：
1. 已经标记为 S2 → 直接返回 S2
2. 还是 S1 → 调 ListUserCarsService 检查用户是否有车
   - 有车 → 升级到 S2
   - 无车 / 查询失败 → 保持 S1
"""

from __future__ import annotations

import logging

logger: logging.Logger = logging.getLogger(__name__)


class UserStatService:
    """用户状态服务（内存 stage + ListUserCarsService 检查车型）。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}  # user_id → stage

    async def get_stage(self, user_id: str, session_id: str = "") -> str:
        """返回用户当前阶段："S1" 或 "S2"。"""
        stage: str = self._store.get(user_id, "S1")

        if stage == "S2":
            return "S2"

        # S1：检查用户是否有车
        has_car: bool = await self._check_has_car(user_id, session_id)
        if has_car:
            self._store[user_id] = "S2"
            logger.info("用户 %s 有车型记录，自动升级到 S2", user_id)
            return "S2"

        return "S1"

    async def upgrade_to_s2(self, user_id: str) -> None:
        """将用户阶段从 S1 升级到 S2。S2 不回退。"""
        if self._store.get(user_id) != "S2":
            self._store[user_id] = "S2"
            logger.info("用户 %s 升级到 S2", user_id)

    async def _check_has_car(self, user_id: str, session_id: str) -> bool:
        """检查用户是否有车型记录。"""
        try:
            from hlsc.services.restful.list_user_cars_service import list_user_cars_service

            cars = await list_user_cars_service.get_user_cars(
                session_id=session_id or user_id,
            )
            return len(cars) > 0
        except Exception:
            logger.debug("检查用户 %s 车型失败，默认无车", user_id, exc_info=True)
            return False


# 模块级单例
user_stat_service: UserStatService = UserStatService()
