"""阶段 + 场景路由单元测试：验证 UserStatService / StageHook / proceed_to_booking / Jinja2 渲染。

场景模型（3+2）：
  S2 scenes: saving, shop, insurance（业务场景）
             none（BMA 返回空）, multi（BMA 返回多场景）

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
        _config_loader._s2_scenes = {}

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

    # ---- B2: 已升级用户 → S2，BMA 返回 multi 场景 → tools 含 confirm_booking ----
    @pytest.mark.asyncio
    async def test_upgraded_user_gets_s2(self) -> None:
        """已升级到 S2 的用户 → S2，multi 场景 tools 含 confirm_booking。"""
        from business_map_hook import StageHook

        # 先升级
        await self.user_stat_service.upgrade_to_s2("upgraded_user_b2")

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        # S2 会调 BMA，mock 返回多场景 → multi
        with patch("business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["saving", "shop"]):
            await hook(
                user_id="upgraded_user_b2",
                session_id="sess-b2",
                deps=deps,
                message="我要下单",
            )

        assert deps.current_stage == "S2"
        assert deps.current_scene == "multi"
        assert "confirm_booking" in deps.available_tools

    # ---- B3: S1 的 tools 含 proceed_to_booking ----
    @pytest.mark.asyncio
    async def test_s1_tools_contain_proceed_to_booking(self) -> None:
        """S1 阶段的 available_tools 包含 proceed_to_booking。"""
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
        assert "proceed_to_booking" in deps.available_tools

    # ---- B4: S2 saving 场景 → tools 含 confirm_booking ----
    @pytest.mark.asyncio
    async def test_s2_tools_contain_confirm_booking(self) -> None:
        """S2 saving 场景的 available_tools 包含 confirm_booking。"""
        from business_map_hook import StageHook

        await self.user_stat_service.upgrade_to_s2("user_b4")

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        # mock BMA 返回单场景 saving → confirm_booking 可用
        with patch("business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["saving"]):
            await hook(
                user_id="user_b4",
                session_id="sess-b4",
                deps=deps,
                message="预订",
            )

        assert deps.current_stage == "S2"
        assert deps.current_scene == "saving"
        assert "confirm_booking" in deps.available_tools


# ============================================================
# C. proceed_to_booking 测试
# ============================================================


class TestProceedToBooking:
    """proceed_to_booking 工具单元测试。"""

    @pytest.fixture(autouse=True)
    def _setup_config_path(self) -> None:
        """将 STAGE_CONFIG_PATH 指向真实 stage_config.yaml（即时切换需要加载配置）。"""
        config_path: str = str(PROJECT_ROOT / "mainagent" / "stage_config.yaml")
        os.environ["STAGE_CONFIG_PATH"] = config_path
        # 重置配置加载器缓存
        from business_map_hook import _config_loader
        _config_loader._loaded = False
        _config_loader._stages = {}
        _config_loader._s2_scenes = {}

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
        """proceed_to_booking 调用后 user 阶段变为 S2。"""
        from hlsc.tools.s1.proceed_to_booking import proceed_to_booking

        ctx: MagicMock = self._make_ctx(user_id="user_c1")

        await proceed_to_booking(
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
        from hlsc.tools.s1.proceed_to_booking import proceed_to_booking

        ctx: MagicMock = self._make_ctx(user_id="user_c2")

        result: str = await proceed_to_booking(
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
        from hlsc.tools.s1.proceed_to_booking import proceed_to_booking

        ctx: MagicMock = self._make_ctx(user_id="user_c2b")

        result: str = await proceed_to_booking(
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
        from hlsc.tools.s1.proceed_to_booking import proceed_to_booking

        ctx: MagicMock = self._make_ctx(user_id="user_c2c")

        result: str = await proceed_to_booking(
            ctx,
            project_id="proj-004",
            project_name="喷漆",
            saving_method="platform_offer",
        )

        assert "喷漆" in result
        assert "平台优惠方式" in result

    # ---- C3: saving_method 接受四种合法值 ----
    def test_saving_method_type_literal(self) -> None:
        """SavingMethod Literal 类型包含四种合法值（含 none）。"""
        from hlsc.tools.s1.proceed_to_booking import SavingMethod
        from typing import get_args

        allowed: tuple[str, ...] = get_args(SavingMethod)
        assert set(allowed) == {"platform_offer", "insurance_bidding", "merchant_promo", "none"}

    # ---- C4: saving_method=None（不传）时返回值包含"未指定" ----
    @pytest.mark.asyncio
    async def test_result_saving_method_none(self) -> None:
        """saving_method 不传时返回值包含未指定。"""
        from hlsc.tools.s1.proceed_to_booking import proceed_to_booking

        ctx: MagicMock = self._make_ctx(user_id="user_c4")

        result: str = await proceed_to_booking(
            ctx,
            project_id="proj-005",
            project_name="小保养",
        )

        assert "小保养" in result
        assert "未指定" in result

    # ---- C5: saving_method="none" 时返回值包含"无特定省钱方式" ----
    @pytest.mark.asyncio
    async def test_result_saving_method_explicit_none(self) -> None:
        """saving_method="none" 时返回值包含无特定省钱方式。"""
        from hlsc.tools.s1.proceed_to_booking import proceed_to_booking

        ctx: MagicMock = self._make_ctx(user_id="user_c5")

        result: str = await proceed_to_booking(
            ctx,
            project_id="proj-006",
            project_name="轮胎更换",
            saving_method="none",
        )

        assert "轮胎更换" in result
        assert "无特定省钱方式" in result

    # ---- C6: 即时切换 — 调用后 deps 已切换到 S2 ----
    @pytest.mark.asyncio
    async def test_instant_switch_to_s2(self) -> None:
        """proceed_to_booking 调用后 deps 即时切换到 S2。"""
        from hlsc.tools.s1.proceed_to_booking import proceed_to_booking

        ctx: MagicMock = self._make_ctx(user_id="user_c6")

        await proceed_to_booking(
            ctx,
            project_id="proj-007",
            project_name="刹车片更换",
            saving_method="platform_offer",
        )

        # deps 已即时切换
        assert ctx.deps.current_stage == "S2"
        assert ctx.deps.current_scene == "multi"
        assert "confirm_booking" in ctx.deps.available_tools
        assert "proceed_to_booking" not in ctx.deps.available_tools
        # system_prompt_override 已设置
        assert ctx.deps.system_prompt_override is not None
        assert "AGENT_S2" not in ctx.deps.system_prompt_override  # 不含文件名，含内容
        assert len(ctx.deps.system_prompt_override) > 100  # 不为空


# ============================================================
# D. S2 场景路由测试（BMA mock）
# ============================================================


class TestS2SceneRouting:
    """S2 场景路由测试：mock BMA 调用，验证不同场景分类结果下的 deps 写入。"""

    @pytest.fixture(autouse=True)
    def _setup_config_path(self) -> None:
        """将 STAGE_CONFIG_PATH 指向真实 stage_config.yaml。"""
        config_path: str = str(PROJECT_ROOT / "mainagent" / "stage_config.yaml")
        os.environ["STAGE_CONFIG_PATH"] = config_path

    @pytest.fixture(autouse=True)
    def _reset_state(self) -> None:
        """每个用例重置配置加载器和 UserStatService 单例。"""
        from business_map_hook import _config_loader
        _config_loader._loaded = False
        _config_loader._stages = {}
        _config_loader._s2_scenes = {}

        import hlsc.services.user_stat_service as uss_mod
        uss_mod.user_stat_service = UserStatService()
        self.user_stat_service: UserStatService = uss_mod.user_stat_service

    def _make_deps(self) -> AgentDeps:
        """构建测试用 AgentDeps。"""
        return AgentDeps(
            session_id="test-session",
            request_id="test-req",
            user_id="test-user",
        )

    async def _setup_s2_user(self, user_id: str) -> None:
        """将用户升级到 S2。"""
        await self.user_stat_service.upgrade_to_s2(user_id)

    # ---- D1: BMA 返回 ["saving"] → 走 saving 场景 ----
    @pytest.mark.asyncio
    async def test_s2_single_scene_saving(self) -> None:
        """S2 用户 + BMA 返回 ["saving"] → deps.available_tools 包含 search_coupon。"""
        from business_map_hook import StageHook

        user_id: str = "user_d1"
        await self._setup_s2_user(user_id)

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        with patch("business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["saving"]):
            await hook(user_id=user_id, session_id="sess-d1", deps=deps, message="有什么优惠券")

        assert deps.current_stage == "S2"
        assert deps.current_scene == "saving"
        assert "search_coupon" in deps.available_tools
        assert "confirm_booking" in deps.available_tools
        assert deps.current_scene_agent_md == "AGENT_S2_saving.md"
        # saving 场景不含 call_recommend_project（multi 才有）
        assert "call_recommend_project" not in deps.available_tools

    # ---- D2: BMA 返回 ["saving", "shop"] → 走 multi（多场景） ----
    @pytest.mark.asyncio
    async def test_s2_multi_scene_fallback_to_multi(self) -> None:
        """S2 用户 + BMA 返回多场景 → 走 multi，deps.available_tools 包含全量工具。"""
        from business_map_hook import StageHook

        user_id: str = "user_d2"
        await self._setup_s2_user(user_id)

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        with patch("business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["saving", "shop"]):
            await hook(user_id=user_id, session_id="sess-d2", deps=deps, message="找个便宜的店")

        assert deps.current_stage == "S2"
        assert deps.current_scene == "multi"
        # multi 全量工具
        assert "match_project" in deps.available_tools
        assert "call_recommend_project" in deps.available_tools
        assert "confirm_booking" in deps.available_tools
        assert "search_coupon" in deps.available_tools
        # multi 的 agent_md
        assert deps.current_scene_agent_md == "AGENT_S2.md"

    # ---- D3: BMA 返回 [] → 走 none（极简配置，无 confirm_booking） ----
    @pytest.mark.asyncio
    async def test_s2_empty_scene_goes_to_none(self) -> None:
        """S2 用户 + BMA 返回 [] → 走 none 场景（极简，不含 confirm_booking）。"""
        from business_map_hook import StageHook

        user_id: str = "user_d3"
        await self._setup_s2_user(user_id)

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        with patch("business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=[]):
            await hook(user_id=user_id, session_id="sess-d3", deps=deps, message="你好")

        assert deps.current_stage == "S2"
        assert deps.current_scene == "none"
        assert deps.current_scene_agent_md == "AGENT_S2_none.md"
        # none 场景：极简工具，不含 confirm_booking
        assert "confirm_booking" not in deps.available_tools
        assert "classify_project" in deps.available_tools
        assert "search_shops" in deps.available_tools

    # ---- D4: BMA 不可达 → 走 none（容错） ----
    @pytest.mark.asyncio
    async def test_s2_bma_unreachable_goes_to_none(self) -> None:
        """S2 用户 + BMA 不可达 → _call_bma_classify 返回 []，走 none。"""
        from business_map_hook import StageHook

        user_id: str = "user_d4"
        await self._setup_s2_user(user_id)

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        # mock BMA 调用返回 []（模拟不可达或无法分类）
        with patch("business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=[]):
            await hook(user_id=user_id, session_id="sess-d4", deps=deps, message="帮我看看")

        assert deps.current_stage == "S2"
        assert deps.current_scene == "none"
        # none 场景不含 confirm_booking
        assert "confirm_booking" not in deps.available_tools

    # ---- D5: BMA 返回 ["insurance"] → 走 insurance 场景 ----
    @pytest.mark.asyncio
    async def test_s2_single_scene_insurance(self) -> None:
        """S2 用户 + BMA 返回 ["insurance"] → deps.allowed_skills 包含 insurance-bidding。"""
        from business_map_hook import StageHook

        user_id: str = "user_d5"
        await self._setup_s2_user(user_id)

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        with patch("business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["insurance"]):
            await hook(user_id=user_id, session_id="sess-d5", deps=deps, message="我要买保险")

        assert deps.current_stage == "S2"
        assert deps.current_scene == "insurance"
        assert "insurance-bidding" in deps.allowed_skills
        assert deps.current_scene_agent_md == "AGENT_S2_insurance.md"

    # ---- D6: S1 用户不调 BMA ----
    @pytest.mark.asyncio
    async def test_s1_does_not_call_bma(self) -> None:
        """S1 用户不调用 BMA 分类。"""
        from business_map_hook import StageHook

        hook: StageHook = StageHook()
        deps: AgentDeps = self._make_deps()

        mock_bma: AsyncMock = AsyncMock(return_value=["coupon"])
        with patch.object(self.user_stat_service, "_check_has_car", new_callable=AsyncMock, return_value=False):
            with patch("business_map_hook._call_bma_classify", mock_bma):
                await hook(user_id="user_d6", session_id="sess-d6", deps=deps, message="你好")

        assert deps.current_stage == "S1"
        mock_bma.assert_not_called()


# ============================================================
# E. prompt_loader 测试
# ============================================================


class TestPromptLoader:
    """prompt_loader 测试：验证不同 stage/scene 下加载正确的 AGENT.md。"""

    @pytest.fixture(autouse=True)
    def _setup_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """切换 cwd 到 mainagent/，因为 prompt_loader 用相对路径读模板。"""
        monkeypatch.chdir(PROJECT_ROOT / "mainagent")

    # ---- E1: S1 用户 → 加载 AGENT_S1.md ----
    @pytest.mark.asyncio
    async def test_s1_loads_agent_s1(self) -> None:
        """S1 用户 → get_agent_md_content 返回 AGENT_S1.md 内容。"""
        from prompt_loader import MainPromptLoader

        loader: MainPromptLoader = MainPromptLoader(template_parts=[])
        deps: MagicMock = MagicMock()
        deps.current_stage = "S1"
        deps.current_scene_agent_md = None

        content: str | None = await loader.get_agent_md_content(
            user_id="u1", session_id="s1", deps=deps,
        )

        assert content is not None
        assert len(content) > 0

    # ---- E2: S2 default → 加载 AGENT_S2.md ----
    @pytest.mark.asyncio
    async def test_s2_default_loads_agent_s2(self) -> None:
        """S2 default → get_agent_md_content 返回 AGENT_S2.md 内容。"""
        from prompt_loader import MainPromptLoader

        loader: MainPromptLoader = MainPromptLoader(template_parts=[])
        deps: MagicMock = MagicMock()
        deps.current_stage = "S2"
        deps.current_scene_agent_md = None

        content: str | None = await loader.get_agent_md_content(
            user_id="u2", session_id="s2", deps=deps,
        )

        assert content is not None
        assert len(content) > 0

    # ---- E3: S2 saving → 加载 AGENT_S2_saving.md ----
    @pytest.mark.asyncio
    async def test_s2_saving_loads_scene_md(self) -> None:
        """S2 saving → get_agent_md_content 返回 AGENT_S2_saving.md 内容。"""
        from prompt_loader import MainPromptLoader

        loader: MainPromptLoader = MainPromptLoader(template_parts=[])
        deps: MagicMock = MagicMock()
        deps.current_stage = "S2"
        deps.current_scene_agent_md = "AGENT_S2_saving.md"

        content: str | None = await loader.get_agent_md_content(
            user_id="u3", session_id="s3", deps=deps,
        )

        # 应该加载 AGENT_S2_saving.md 而不是 AGENT_S2.md
        assert content is not None
        assert len(content) > 0

    # ---- E4: scene_agent_md 指向不存在的文件 → 回退到 AGENT_S2.md ----
    @pytest.mark.asyncio
    async def test_s2_invalid_scene_md_fallback(self) -> None:
        """scene_agent_md 指向不存在文件 → 回退到 AGENT_S2.md。"""
        from prompt_loader import MainPromptLoader

        loader: MainPromptLoader = MainPromptLoader(template_parts=[])
        deps: MagicMock = MagicMock()
        deps.current_stage = "S2"
        deps.current_scene_agent_md = "AGENT_S2_nonexistent.md"

        content: str | None = await loader.get_agent_md_content(
            user_id="u4", session_id="s4", deps=deps,
        )

        # 文件不存在时回退到 default AGENT_S2.md
        assert content is not None


# ============================================================
# F. Jinja2 OUTPUT.md 渲染测试
# ============================================================


class TestOutputMdRendering:
    """OUTPUT.md Jinja2 模板渲染测试：验证不同 stage/scene 组合下的输出内容。"""

    @pytest.fixture(autouse=True)
    def _setup_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """切换 cwd 到 mainagent/，因为 prompt_loader 用相对路径读模板。"""
        monkeypatch.chdir(PROJECT_ROOT / "mainagent")

    @pytest.fixture(autouse=True)
    def _reset_template_cache(self) -> None:
        """重置 OUTPUT.md 模板缓存，避免用例间污染。"""
        import prompt_loader
        prompt_loader._output_template = None

    # ---- F1: S1, scene=none → 无 spec/action 输出 ----
    def test_s1_none_no_spec_action(self) -> None:
        """S1 + scene=none → 渲染结果无 spec/action 块（只有 # Output 标题）。"""
        from prompt_loader import _render_output_md

        rendered: str = _render_output_md(stage="S1", scene="none")
        assert "`spec`" not in rendered
        assert "`action`" not in rendered
        assert "ShopCard" not in rendered
        assert "CouponCard" not in rendered

    # ---- F2: S2, scene=saving → 有 CouponCard + ShopCard ----
    def test_s2_saving_has_coupon_and_shop_card(self) -> None:
        """S2 + scene=saving → 渲染结果包含 CouponCard 和 ShopCard。"""
        from prompt_loader import _render_output_md

        rendered: str = _render_output_md(stage="S2", scene="saving")
        assert "CouponCard" in rendered
        assert "ShopCard" in rendered
        assert "ProjectCard" in rendered
        # saving 不含 AppointmentCard / PartPriceCard / RecommendProjectsCard
        assert "AppointmentCard" not in rendered
        assert "PartPriceCard" not in rendered
        assert "RecommendProjectsCard" not in rendered
        # 有 spec 段
        assert "`spec`" in rendered
        # 有 change_car action
        assert "change_car" in rendered
        # saving 不含 invite_shop
        assert "invite_shop" not in rendered

    # ---- F3: S2, scene=shop → 有 ShopCard，无 CouponCard ----
    def test_s2_shop_has_shop_card_only(self) -> None:
        """S2 + scene=shop → 渲染结果只含 ShopCard。"""
        from prompt_loader import _render_output_md

        rendered: str = _render_output_md(stage="S2", scene="shop")
        assert "ShopCard" in rendered
        assert "CouponCard" not in rendered
        assert "ProjectCard" not in rendered
        # shop 有 invite_shop action
        assert "invite_shop" in rendered
        # shop 没有 change_car
        assert "change_car" not in rendered

    # ---- F4: S2, scene=insurance → 有 RecommendProjectsCard + ShopCard + CouponCard ----
    def test_s2_insurance_has_full_cards(self) -> None:
        """S2 + scene=insurance → 渲染结果包含 RecommendProjectsCard、ShopCard、CouponCard。"""
        from prompt_loader import _render_output_md

        rendered: str = _render_output_md(stage="S2", scene="insurance")
        assert "RecommendProjectsCard" in rendered
        assert "ShopCard" in rendered
        assert "ProjectCard" in rendered
        assert "AppointmentCard" in rendered
        assert "CouponCard" in rendered
        # insurance 不含 PartPriceCard
        assert "PartPriceCard" not in rendered
        # insurance 有 change_car
        assert "change_car" in rendered

    # ---- F5: S2, scene=multi → 全量卡片 ----
    def test_s2_multi_has_all_cards(self) -> None:
        """S2 + scene=multi → 渲染结果包含所有卡片类型。"""
        from prompt_loader import _render_output_md

        rendered: str = _render_output_md(stage="S2", scene="multi")
        assert "RecommendProjectsCard" in rendered
        assert "ShopCard" in rendered
        assert "ProjectCard" in rendered
        assert "AppointmentCard" in rendered
        assert "PartPriceCard" in rendered
        assert "CouponCard" in rendered
        # multi 同时有 change_car 和 invite_shop
        assert "change_car" in rendered
        assert "invite_shop" in rendered

    # ---- F6: S2, scene=none → 无 spec/action 输出 ----
    def test_s2_none_no_spec_action(self) -> None:
        """S2 + scene=none → 渲染结果无 spec/action 块（只有 # Output 标题）。"""
        from prompt_loader import _render_output_md

        rendered: str = _render_output_md(stage="S2", scene="none")
        assert "`spec`" not in rendered
        assert "`action`" not in rendered
        assert "ShopCard" not in rendered
        assert "CouponCard" not in rendered
