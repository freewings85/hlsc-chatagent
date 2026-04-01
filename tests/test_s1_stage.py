"""S1 阶段单元测试：验证 UserStatService / StageHook / confirm_saving_plan 核心行为。

运行方式：
    cd /mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent
    uv run pytest tests/test_s1_stage.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 确保 extensions 和 sdk 可 import
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "extensions"))
sys.path.insert(0, str(PROJECT_ROOT / "sdk"))
sys.path.insert(0, str(PROJECT_ROOT / "mainagent" / "src"))

from agent_sdk._agent.deps import AgentDeps  # noqa: E402
from hlsc.services.user_stat_service import UserStatService  # noqa: E402


# ============================================================
# A. UserStatService 测试
# ============================================================


class TestUserStatService:
    """UserStatService 单元测试。"""

    @pytest.fixture(autouse=True)
    def _fresh_service(self) -> None:
        """每个用例创建独立的 service 实例，避免用例间污染。"""
        self.svc: UserStatService = UserStatService()

    # ---- A1: 新用户默认 S1（mock _check_has_car 返回 False，避免调真实 API）----
    @pytest.mark.asyncio
    async def test_new_user_default_s1(self) -> None:
        """新用户 get_stage 返回默认 "S1"。"""
        with patch.object(self.svc, "_check_has_car", new_callable=AsyncMock, return_value=False):
            stage: str = await self.svc.get_stage("user_new", session_id="test")
        assert stage == "S1"

    # ---- A2: upgrade_to_s2 后变为 S2 ----
    @pytest.mark.asyncio
    async def test_upgrade_to_s2(self) -> None:
        """upgrade_to_s2 后 get_stage 返回 "S2"。"""
        await self.svc.upgrade_to_s2("user_a2")
        stage: str = await self.svc.get_stage("user_a2", session_id="test")
        assert stage == "S2"

    # ---- A3: 已经 S2 的用户再次 upgrade 不出错 ----
    @pytest.mark.asyncio
    async def test_upgrade_s2_idempotent(self) -> None:
        """已经 S2 的用户再次 upgrade_to_s2 不报错，仍然 "S2"。"""
        await self.svc.upgrade_to_s2("user_a3")
        await self.svc.upgrade_to_s2("user_a3")  # 第二次
        stage: str = await self.svc.get_stage("user_a3", session_id="test")
        assert stage == "S2"

    # ---- A4: 不同 user_id 互不影响 ----
    @pytest.mark.asyncio
    async def test_different_users_isolated(self) -> None:
        """不同 user_id 的状态互不影响。"""
        await self.svc.upgrade_to_s2("user_x")
        stage_x: str = await self.svc.get_stage("user_x", session_id="test")
        with patch.object(self.svc, "_check_has_car", new_callable=AsyncMock, return_value=False):
            stage_y: str = await self.svc.get_stage("user_y", session_id="test")
        assert stage_x == "S2"
        assert stage_y == "S1"

    # ---- A5: _check_has_car 返回 True 时，S1 自动升级到 S2 ----
    @pytest.mark.asyncio
    async def test_auto_upgrade_when_has_car(self) -> None:
        """_check_has_car 返回 True 时，S1 用户自动升级到 S2。"""
        with patch.object(self.svc, "_check_has_car", new_callable=AsyncMock, return_value=True):
            stage: str = await self.svc.get_stage("user_a5", session_id="test")
        assert stage == "S2"


# ============================================================
# B. StageHook 测试
# ============================================================


class TestStageHook:
    """StageHook 单元测试：验证阶段判断和 deps 写入。"""

    @pytest.fixture(autouse=True)
    def _setup_config_path(self) -> None:
        """将 STAGE_CONFIG_PATH 指向真实 stage_config.yaml。"""
        config_path: str = str(PROJECT_ROOT / "mainagent" / "stage_config.yaml")
        os.environ["STAGE_CONFIG_PATH"] = config_path

    @pytest.fixture(autouse=True)
    def _reset_state(self) -> None:
        """每个用例重置 StageHook 的配置加载器和 UserStatService 单例。"""
        # 重置配置加载器，避免前一个用例的缓存影响
        from business_map_hook import _config_loader
        _config_loader._loaded = False
        _config_loader._stages = {}

        # 重置 UserStatService 单例
        import hlsc.services.user_stat_service as uss_mod
        uss_mod.user_stat_service = UserStatService()
        self.user_stat_service: UserStatService = uss_mod.user_stat_service

    def _make_deps(self) -> AgentDeps:
        """构建测试用 AgentDeps。"""
        deps: AgentDeps = AgentDeps(
            session_id="test-session",
            request_id="test-req",
            user_id="test-user",
        )
        return deps

    # ---- B1: 新用户 → S1，available_tools 不含 confirm_booking ----
    @pytest.mark.asyncio
    async def test_new_user_gets_s1(self) -> None:
        """新用户经过 StageHook 后 → S1，tools 不含 confirm_booking。"""
        from business_map_hook import StageHook

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        # mock _check_has_car 避免调真实 API
        with patch.object(self.user_stat_service, "_check_has_car", new_callable=AsyncMock, return_value=False):
            await hook(
                user_id="new_user_b1",
                session_id="sess-b1",
                deps=deps,
                message="你好",
            )

        assert deps.current_stage == "S1"
        assert "confirm_booking" not in deps.available_tools

    # ---- B2: 已升级用户 → S2，available_tools 含 confirm_booking ----
    @pytest.mark.asyncio
    async def test_upgraded_user_gets_s2(self) -> None:
        """已升级到 S2 的用户 → S2，tools 含 confirm_booking。"""
        from business_map_hook import StageHook

        # 先升级
        await self.user_stat_service.upgrade_to_s2("upgraded_user_b2")

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        await hook(
            user_id="upgraded_user_b2",
            session_id="sess-b2",
            deps=deps,
            message="我要下单",
        )

        assert deps.current_stage == "S2"
        assert "confirm_booking" in deps.available_tools

    # ---- B3: S1 的 tools 含 confirm_saving_plan ----
    @pytest.mark.asyncio
    async def test_s1_tools_contain_confirm_saving_plan(self) -> None:
        """S1 阶段的 available_tools 包含 confirm_saving_plan。"""
        from business_map_hook import StageHook

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        # mock _check_has_car 避免调真实 API
        with patch.object(self.user_stat_service, "_check_has_car", new_callable=AsyncMock, return_value=False):
            await hook(
                user_id="user_b3",
                session_id="sess-b3",
                deps=deps,
                message="帮我省钱",
            )

        assert deps.current_stage == "S1"
        assert "confirm_saving_plan" in deps.available_tools

    # ---- B4: S2 的 tools 含 confirm_booking ----
    @pytest.mark.asyncio
    async def test_s2_tools_contain_confirm_booking(self) -> None:
        """S2 阶段的 available_tools 包含 confirm_booking。"""
        from business_map_hook import StageHook

        await self.user_stat_service.upgrade_to_s2("user_b4")

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        await hook(
            user_id="user_b4",
            session_id="sess-b4",
            deps=deps,
            message="预订",
        )

        assert deps.current_stage == "S2"
        assert "confirm_booking" in deps.available_tools


# ============================================================
# C. confirm_saving_plan 测试
# ============================================================


class TestConfirmSavingPlan:
    """confirm_saving_plan 工具单元测试。"""

    @pytest.fixture(autouse=True)
    def _reset_user_stat(self) -> None:
        """重置 UserStatService 单例。"""
        import hlsc.services.user_stat_service as uss_mod
        uss_mod.user_stat_service = UserStatService()
        self.user_stat_service: UserStatService = uss_mod.user_stat_service

    def _make_ctx(self, user_id: str = "test-user") -> MagicMock:
        """构建 Mock RunContext，内部 deps 是真实 AgentDeps。"""
        deps: AgentDeps = AgentDeps(
            session_id="test-session",
            request_id="test-req",
            user_id=user_id,
        )
        ctx: MagicMock = MagicMock()
        ctx.deps = deps
        return ctx

    # ---- C1: 调用后 user_stat 变为 S2 ----
    @pytest.mark.asyncio
    async def test_upgrade_to_s2_after_confirm(self) -> None:
        """confirm_saving_plan 调用后 user 阶段变为 S2。"""
        from hlsc.tools.s1.confirm_saving_plan import confirm_saving_plan

        ctx: MagicMock = self._make_ctx(user_id="user_c1")

        await confirm_saving_plan(
            ctx,
            project_id="proj-001",
            project_name="小保养",
            saving_method="platform_offer",
        )

        stage: str = await self.user_stat_service.get_stage("user_c1", session_id="test")
        assert stage == "S2"

    # ---- C2: 返回值包含项目名和省钱方式 ----
    @pytest.mark.asyncio
    async def test_result_contains_project_and_method(self) -> None:
        """返回值包含项目名称和省钱方式中文标签。"""
        from hlsc.tools.s1.confirm_saving_plan import confirm_saving_plan

        ctx: MagicMock = self._make_ctx(user_id="user_c2")

        result: str = await confirm_saving_plan(
            ctx,
            project_id="proj-002",
            project_name="更换机油",
            saving_method="insurance_bidding",
        )

        assert "更换机油" in result
        assert "保险竞价" in result

    @pytest.mark.asyncio
    async def test_result_merchant_promo(self) -> None:
        """saving_method=merchant_promo 时返回值包含商户自有优惠。"""
        from hlsc.tools.s1.confirm_saving_plan import confirm_saving_plan

        ctx: MagicMock = self._make_ctx(user_id="user_c2b")

        result: str = await confirm_saving_plan(
            ctx,
            project_id="proj-003",
            project_name="轮胎更换",
            saving_method="merchant_promo",
        )

        assert "轮胎更换" in result
        assert "商户自有优惠" in result

    @pytest.mark.asyncio
    async def test_result_platform_offer(self) -> None:
        """saving_method=platform_offer 时返回值包含平台优惠方式。"""
        from hlsc.tools.s1.confirm_saving_plan import confirm_saving_plan

        ctx: MagicMock = self._make_ctx(user_id="user_c2c")

        result: str = await confirm_saving_plan(
            ctx,
            project_id="proj-004",
            project_name="喷漆",
            saving_method="platform_offer",
        )

        assert "喷漆" in result
        assert "平台优惠方式" in result

    # ---- C3: saving_method 只接受三种合法值 ----
    def test_saving_method_type_literal(self) -> None:
        """SavingMethod Literal 类型仅包含三种合法值。"""
        from hlsc.tools.s1.confirm_saving_plan import SavingMethod
        from typing import get_args

        allowed: tuple[str, ...] = get_args(SavingMethod)
        assert set(allowed) == {"platform_offer", "insurance_bidding", "merchant_promo"}
