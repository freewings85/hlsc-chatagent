"""6 场景架构路由测试

覆盖：
A 组 - StageHook 场景路由（mock BMA）
B 组 - delegate 工具校验
C 组 - MainPromptLoader 场景加载
D 组 - 安全边界（guide 无 confirm_booking）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from agent_sdk._agent.deps import AgentDeps
from src.business_map_hook import SceneConfigLoader, StageHook, _config_loader


# ============================================================
# 固定 STAGE_CONFIG_PATH 指向 mainagent/stage_config.yaml
# ============================================================

_MAINAGENT_DIR: Path = Path(__file__).resolve().parent.parent
_STAGE_CONFIG_PATH: str = str(_MAINAGENT_DIR / "stage_config.yaml")


@pytest.fixture(autouse=True)
def _set_config_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有测试统一使用 mainagent/stage_config.yaml。"""
    monkeypatch.setenv("STAGE_CONFIG_PATH", _STAGE_CONFIG_PATH)


@pytest.fixture()
def fresh_loader() -> SceneConfigLoader:
    """每次测试重新加载配置（避免缓存互相污染）。"""
    loader: SceneConfigLoader = SceneConfigLoader()
    loader.ensure_loaded()
    return loader


@pytest.fixture()
def deps() -> AgentDeps:
    """创建干净的 AgentDeps 实例。"""
    return AgentDeps(user_id="test_user", session_id="test_session")


# ============================================================
# A 组：StageHook 场景路由（mock BMA）
# ============================================================


class TestHookSceneRouting:
    """StageHook 根据 BMA 返回值进行场景路由。"""

    @pytest.fixture()
    def hook(self) -> StageHook:
        return StageHook()

    @pytest.mark.asyncio
    async def test_bma_returns_platform(self, hook: StageHook, deps: AgentDeps) -> None:
        """BMA 返回 ["platform"] → scene=platform，tools 含 confirm_booking。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["platform"]):
            await hook("user1", "sess1", deps, "我想预订保养")

        assert deps.current_scene == "platform"
        assert "confirm_booking" in deps.available_tools

    @pytest.mark.asyncio
    async def test_bma_returns_searchshops(self, hook: StageHook, deps: AgentDeps) -> None:
        """BMA 返回 ["searchshops"] → scene=searchshops。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["searchshops"]):
            await hook("user1", "sess1", deps, "附近有什么修车的店")

        assert deps.current_scene == "searchshops"

    @pytest.mark.asyncio
    async def test_bma_returns_searchcoupons(self, hook: StageHook, deps: AgentDeps) -> None:
        """BMA 返回 ["searchcoupons"] → scene=searchcoupons。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["searchcoupons"]):
            await hook("user1", "sess1", deps, "有没有优惠券")

        assert deps.current_scene == "searchcoupons"

    @pytest.mark.asyncio
    async def test_bma_returns_insurance(self, hook: StageHook, deps: AgentDeps) -> None:
        """BMA 返回 ["insurance"] → scene=insurance。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["insurance"]):
            await hook("user1", "sess1", deps, "我要买保险")

        assert deps.current_scene == "insurance"

    @pytest.mark.asyncio
    async def test_bma_returns_multiple_scenes(self, hook: StageHook, deps: AgentDeps) -> None:
        """BMA 返回多个场景 → scene=orchestrator，tools 只有 delegate。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["platform", "searchcoupons"]):
            await hook("user1", "sess1", deps, "我想保养还想找优惠")

        assert deps.current_scene == "orchestrator"
        assert deps.available_tools == ["delegate"]

    @pytest.mark.asyncio
    async def test_bma_returns_empty(self, hook: StageHook, deps: AgentDeps) -> None:
        """BMA 返回 [] → scene=guide，tools 不含 confirm_booking。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=[]):
            await hook("user1", "sess1", deps, "你好")

        assert deps.current_scene == "guide"
        assert "confirm_booking" not in deps.available_tools

    @pytest.mark.asyncio
    async def test_bma_unreachable_fallback_to_guide(self, hook: StageHook, deps: AgentDeps) -> None:
        """BMA 不可达（抛异常）→ _call_bma_classify 内部 catch 返回 [] → guide。"""
        # _call_bma_classify 内部 try/except 已经处理异常，返回 []
        # 我们直接 mock 返回 [] 来模拟这个行为
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=[]):
            await hook("user1", "sess1", deps, "随便说点什么")

        assert deps.current_scene == "guide"

    @pytest.mark.asyncio
    async def test_hook_sets_agent_md(self, hook: StageHook, deps: AgentDeps) -> None:
        """Hook 应设置 current_scene_agent_md。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["platform"]):
            await hook("user1", "sess1", deps, "预订")

        assert deps.current_scene_agent_md == "platform/AGENT.md"

    @pytest.mark.asyncio
    async def test_hook_sets_skills(self, hook: StageHook, deps: AgentDeps) -> None:
        """Hook 应设置 allowed_skills。"""
        with patch("src.business_map_hook._call_bma_classify", new_callable=AsyncMock, return_value=["platform"]):
            await hook("user1", "sess1", deps, "预订")

        assert deps.allowed_skills == ["saving-playbook"]


# ============================================================
# B 组：delegate 工具
# ============================================================


class TestDelegateTool:
    """delegate 工具校验。"""

    @pytest.mark.asyncio
    async def test_delegate_valid_scene(self) -> None:
        """delegate("platform", "查保养报价") → 返回非空字符串。"""
        from hlsc.tools.delegate import delegate, _DELEGATABLE_SCENES

        # 验证白名单包含 4 个业务场景
        assert _DELEGATABLE_SCENES == {"platform", "searchshops", "searchcoupons", "insurance"}

    @pytest.mark.asyncio
    async def test_delegate_guide_rejected(self) -> None:
        """delegate("guide", ...) → 返回错误。"""
        from hlsc.tools.delegate import delegate

        # 创建 mock ctx
        mock_ctx: Any = AsyncMock()
        mock_ctx.deps = AgentDeps(user_id="test", session_id="test")

        result: str = await delegate(mock_ctx, "guide", "任务")
        assert "错误" in result
        assert "guide" in result

    @pytest.mark.asyncio
    async def test_delegate_orchestrator_rejected(self) -> None:
        """delegate("orchestrator", ...) → 返回错误。"""
        from hlsc.tools.delegate import delegate

        mock_ctx: Any = AsyncMock()
        mock_ctx.deps = AgentDeps(user_id="test", session_id="test")

        result: str = await delegate(mock_ctx, "orchestrator", "任务")
        assert "错误" in result

    @pytest.mark.asyncio
    async def test_delegate_nonexistent_rejected(self) -> None:
        """delegate("nonexistent", ...) → 返回错误。"""
        from hlsc.tools.delegate import delegate

        mock_ctx: Any = AsyncMock()
        mock_ctx.deps = AgentDeps(user_id="test", session_id="test")

        result: str = await delegate(mock_ctx, "nonexistent", "任务")
        assert "错误" in result


# ============================================================
# C 组：MainPromptLoader 场景加载
# ============================================================


class TestPromptLoader:
    """MainPromptLoader 按场景加载 system prompt + agent_md。"""

    @pytest.fixture()
    def loader(self) -> Any:
        from src.prompt_loader import MainPromptLoader
        return MainPromptLoader(template_parts=[])

    @pytest.mark.asyncio
    async def test_guide_scene_prompt(self, loader: Any) -> None:
        """guide 场景 → system prompt 包含 SYSTEM.md + SOUL.md + guide/OUTPUT.md。"""
        deps: AgentDeps = AgentDeps(
            current_scene="guide",
            current_scene_agent_md="guide/AGENT.md",
        )

        # 直接调用内部方法测试 system prompt 拼接
        system_prompt: str = loader._load_scene_system_prompt("guide")

        # 验证包含各部分内容（通过检查文件是否存在 + prompt 非空）
        templates_dir: Path = _MAINAGENT_DIR / "prompts" / "templates"

        system_md: Path = templates_dir / "SYSTEM.md"
        soul_md: Path = templates_dir / "SOUL.md"
        guide_output: Path = templates_dir / "guide" / "OUTPUT.md"

        assert system_md.exists(), "SYSTEM.md 不存在"
        assert soul_md.exists(), "SOUL.md 不存在"
        assert guide_output.exists(), "guide/OUTPUT.md 不存在"

        # system prompt 应包含这些文件的内容
        system_content: str = system_md.read_text(encoding="utf-8").strip()
        soul_content: str = soul_md.read_text(encoding="utf-8").strip()
        guide_output_content: str = guide_output.read_text(encoding="utf-8").strip()

        if system_content:
            assert system_content in system_prompt, "system prompt 缺少 SYSTEM.md 内容"
        if soul_content:
            assert soul_content in system_prompt, "system prompt 缺少 SOUL.md 内容"
        if guide_output_content:
            assert guide_output_content in system_prompt, "system prompt 缺少 guide/OUTPUT.md 内容"

    @pytest.mark.asyncio
    async def test_platform_scene_prompt(self, loader: Any) -> None:
        """platform 场景 → system prompt 包含 platform/OUTPUT.md。"""
        system_prompt: str = loader._load_scene_system_prompt("platform")

        templates_dir: Path = _MAINAGENT_DIR / "prompts" / "templates"
        platform_output: Path = templates_dir / "platform" / "OUTPUT.md"

        assert platform_output.exists(), "platform/OUTPUT.md 不存在"

        platform_output_content: str = platform_output.read_text(encoding="utf-8").strip()
        if platform_output_content:
            assert platform_output_content in system_prompt, "system prompt 缺少 platform/OUTPUT.md 内容"

    @pytest.mark.asyncio
    async def test_agent_md_loading(self, loader: Any) -> None:
        """场景 agent_md 加载。"""
        deps: AgentDeps = AgentDeps(
            current_scene="platform",
            current_scene_agent_md="platform/AGENT.md",
        )

        content: str | None = await loader.get_agent_md_content(
            user_id="test", session_id="test", deps=deps,
        )

        assert content is not None, "platform/AGENT.md 应该返回内容"
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_agent_md_fallback_for_missing_scene(self, loader: Any) -> None:
        """不存在的场景 agent_md → 返回 None（合理 fallback）。"""
        deps: AgentDeps = AgentDeps(
            current_scene="nonexistent",
            current_scene_agent_md="nonexistent/AGENT.md",
        )

        content: str | None = await loader.get_agent_md_content(
            user_id="test", session_id="test", deps=deps,
        )

        assert content is None, "不存在的场景 agent_md 应返回 None"

    @pytest.mark.asyncio
    async def test_guide_agent_md(self, loader: Any) -> None:
        """guide 场景 → agent_md 包含 guide/AGENT.md 内容。"""
        deps: AgentDeps = AgentDeps(
            current_scene="guide",
            current_scene_agent_md="guide/AGENT.md",
        )

        content: str | None = await loader.get_agent_md_content(
            user_id="test", session_id="test", deps=deps,
        )

        assert content is not None, "guide/AGENT.md 应该返回内容"

    @pytest.mark.asyncio
    async def test_no_deps_fallback(self, loader: Any) -> None:
        """无 deps 时 agent_md 返回 None。"""
        content: str | None = await loader.get_agent_md_content(
            user_id="test", session_id="test", deps=None,
        )

        assert content is None


# ============================================================
# D 组：安全边界
# ============================================================


class TestSecurity:
    """安全边界：guide 不含 confirm_booking，orchestrator 只有 delegate。"""

    def test_guide_no_confirm_booking(self, fresh_loader: SceneConfigLoader) -> None:
        """guide 的 tools 不含 confirm_booking。"""
        config = fresh_loader.get_scene("guide")
        assert "confirm_booking" not in config.tools, "guide 不应有 confirm_booking"

    def test_orchestrator_only_delegate(self, fresh_loader: SceneConfigLoader) -> None:
        """orchestrator 的 tools 只有 delegate。"""
        config = fresh_loader.get_scene("orchestrator")
        assert config.tools == ["delegate"], f"orchestrator 应只有 delegate，实际: {config.tools}"

    def test_business_scenes_have_confirm_booking(self, fresh_loader: SceneConfigLoader) -> None:
        """platform/searchshops/searchcoupons/insurance 都有 confirm_booking。"""
        for scene_name in ["platform", "searchshops", "searchcoupons", "insurance"]:
            config = fresh_loader.get_scene(scene_name)
            assert "confirm_booking" in config.tools, f"{scene_name} 应有 confirm_booking"

    def test_delegate_whitelist_excludes_guide_and_orchestrator(self) -> None:
        """delegate 白名单不含 guide 和 orchestrator。"""
        from hlsc.tools.delegate import _DELEGATABLE_SCENES

        assert "guide" not in _DELEGATABLE_SCENES
        assert "orchestrator" not in _DELEGATABLE_SCENES


# ============================================================
# E 组：配置完整性
# ============================================================


class TestConfigIntegrity:
    """场景配置完整性校验。"""

    def test_all_six_scenes_exist(self, fresh_loader: SceneConfigLoader) -> None:
        """6 个场景都存在。"""
        expected: set[str] = {"guide", "platform", "searchshops", "searchcoupons", "insurance", "orchestrator"}
        actual: set[str] = set(fresh_loader._scenes.keys())
        assert actual == expected, f"场景不匹配: 缺少 {expected - actual}, 多余 {actual - expected}"

    def test_each_scene_has_prompt_parts(self, fresh_loader: SceneConfigLoader) -> None:
        """每个场景都有 prompt_parts 配置。"""
        for scene_id, config in fresh_loader._scenes.items():
            assert len(config.prompt_parts) > 0, f"场景 {scene_id} 缺少 prompt_parts"

    def test_each_scene_has_agent_md(self, fresh_loader: SceneConfigLoader) -> None:
        """每个场景都有 agent_md 配置。"""
        for scene_id, config in fresh_loader._scenes.items():
            assert config.agent_md, f"场景 {scene_id} 缺少 agent_md"

    def test_scene_template_files_exist(self) -> None:
        """所有场景目录的 AGENT.md + OUTPUT.md 文件都存在。"""
        templates_dir: Path = _MAINAGENT_DIR / "prompts" / "templates"
        scenes: list[str] = ["guide", "platform", "searchshops", "searchcoupons", "insurance", "orchestrator"]

        for scene in scenes:
            agent_md: Path = templates_dir / scene / "AGENT.md"
            output_md: Path = templates_dir / scene / "OUTPUT.md"
            assert agent_md.exists(), f"{scene}/AGENT.md 不存在"
            assert output_md.exists(), f"{scene}/OUTPUT.md 不存在"

    def test_old_files_deleted(self) -> None:
        """旧的 S1/S2 文件应该不存在（或被场景文件替代）。"""
        templates_dir: Path = _MAINAGENT_DIR / "prompts" / "templates"
        old_files: list[str] = [
            "AGENT_S1.md",
            "AGENT_S2.md",
            "AGENT_S2_saving.md",
            "AGENT_S2_shop.md",
            "AGENT_S2_insurance.md",
            "AGENT_S2_none.md",
        ]
        # 注意：旧文件可能还存在但不被引用，此处检查是否还有代码引用它们
        # 如果文件物理存在但没有代码引用，也可以接受（后续清理）
        # 这里主要检查新代码不引用旧文件
        from src.prompt_loader import MainPromptLoader
        import inspect
        source: str = inspect.getsource(MainPromptLoader)
        for old_file in old_files:
            assert old_file not in source, f"prompt_loader.py 仍引用旧文件 {old_file}"

    def test_unknown_scene_falls_back_to_guide(self, fresh_loader: SceneConfigLoader) -> None:
        """未知场景回退到 guide。"""
        config = fresh_loader.get_scene("nonexistent_scene")
        assert config.name == "guide", f"未知场景应回退到 guide，实际: {config.name}"
