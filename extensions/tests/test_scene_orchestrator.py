"""SceneOrchestrator 测试（business_map_hook.py）。

覆盖：
- SceneOrchestrator.__call__：mock httpx POST /classify
- SceneContext 正确构建
- deps.allowed_skills 设置正确
- SlotState 持久化
- /classify 调用失败时的兜底
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# business_map_hook 在 mainagent/src 目录，需要加入 sys.path
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_MAINAGENT_SRC: Path = _PROJECT_ROOT / "mainagent" / "src"
if str(_MAINAGENT_SRC) not in sys.path:
    sys.path.insert(0, str(_MAINAGENT_SRC))

from business_map_hook import SceneContext, SceneOrchestrator


# ============================================================
# 测试用 Deps 替身
# ============================================================


@dataclass
class FakeDeps:
    """模拟 mainagent 的 deps 对象。"""

    allowed_skills: list[str] | None = None
    session_id: str = "test-session"


# ============================================================
# /classify 响应样本
# ============================================================


def _make_classify_response() -> dict[str, Any]:
    """构造标准的 /classify 响应。"""
    return {
        "scene_id": "DIRECT_PROJECT",
        "scene_name": "直接表达项目",
        "goal": "匹配养车项目",
        "target_slots": {
            "project_id": {
                "label": "养车项目ID",
                "required": "true",
                "method": "match_project",
            }
        },
        "tools": ["match_project", "ask_user_car_info"],
        "skills": ["diagnose-car"],
        "strategy": "直接匹配",
        "eval_path": ["有养车意图", "直接表达"],
    }


# ============================================================
# 测试类
# ============================================================


class TestSceneOrchestrator:
    """SceneOrchestrator 测试。"""

    @pytest.fixture
    def orchestrator(self) -> SceneOrchestrator:
        """创建新的编排器实例。"""
        return SceneOrchestrator()

    @pytest.mark.asyncio
    async def test_call_success(self, orchestrator: SceneOrchestrator, tmp_path: Path) -> None:
        """正常调用：mock httpx → 构建 SceneContext → 设置 deps。"""
        deps: FakeDeps = FakeDeps()
        classify_resp: dict[str, Any] = _make_classify_response()

        # Mock httpx.AsyncClient
        mock_response: MagicMock = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = classify_resp
        mock_response.raise_for_status = MagicMock()

        mock_client: AsyncMock = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("business_map_hook.httpx.AsyncClient", return_value=mock_client), \
             patch("business_map_hook.os.getenv", side_effect=lambda k, d="": tmp_path.as_posix() if k == "INNER_STORAGE_DIR" else d), \
             patch("hlsc.services.slot_state_service.SlotStateService.read", return_value=None), \
             patch("hlsc.services.slot_state_service.SlotStateService.write"):

            await orchestrator(
                user_id="user1",
                session_id="session1",
                deps=deps,
                message="我要做保养",
            )

        # 验证 SceneContext 构建
        ctx: SceneContext | None = orchestrator.get_scene_context("session1")
        assert ctx is not None
        assert ctx.scene_id == "DIRECT_PROJECT"
        assert ctx.scene_name == "直接表达项目"
        assert ctx.goal == "匹配养车项目"
        assert ctx.tools == ["match_project", "ask_user_car_info"]
        assert ctx.allowed_skills == ["diagnose-car"]
        assert ctx.eval_path == ["有养车意图", "直接表达"]

        # 验证 deps.allowed_skills 设置
        assert deps.allowed_skills == ["diagnose-car"]

    @pytest.mark.asyncio
    async def test_call_empty_skills(self, orchestrator: SceneOrchestrator, tmp_path: Path) -> None:
        """skills 为空时 deps.allowed_skills 设为 None。"""
        deps: FakeDeps = FakeDeps()
        classify_resp: dict[str, Any] = _make_classify_response()
        classify_resp["skills"] = []

        mock_response: MagicMock = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = classify_resp
        mock_response.raise_for_status = MagicMock()

        mock_client: AsyncMock = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("business_map_hook.httpx.AsyncClient", return_value=mock_client), \
             patch("business_map_hook.os.getenv", side_effect=lambda k, d="": tmp_path.as_posix() if k == "INNER_STORAGE_DIR" else d), \
             patch("hlsc.services.slot_state_service.SlotStateService.read", return_value=None), \
             patch("hlsc.services.slot_state_service.SlotStateService.write"):

            await orchestrator(
                user_id="user1",
                session_id="session2",
                deps=deps,
                message="随便聊聊",
            )

        assert deps.allowed_skills is None

    @pytest.mark.asyncio
    async def test_call_http_failure(self, orchestrator: SceneOrchestrator, tmp_path: Path) -> None:
        """/classify 调用失败时安静返回，不抛异常。"""
        deps: FakeDeps = FakeDeps()

        mock_client: AsyncMock = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("business_map_hook.httpx.AsyncClient", return_value=mock_client), \
             patch("business_map_hook.os.getenv", side_effect=lambda k, d="": tmp_path.as_posix() if k == "INNER_STORAGE_DIR" else d), \
             patch("hlsc.services.slot_state_service.SlotStateService.read", return_value=None):

            # 不应抛异常
            await orchestrator(
                user_id="user1",
                session_id="session3",
                deps=deps,
                message="test",
            )

        # 失败时不设置 scene context
        assert orchestrator.get_scene_context("session3") is None
        # deps 不变
        assert deps.allowed_skills is None

    @pytest.mark.asyncio
    async def test_slot_state_persistence(self, orchestrator: SceneOrchestrator, tmp_path: Path) -> None:
        """验证 SlotState 写入时 current_scene 正确设置。"""
        deps: FakeDeps = FakeDeps()
        classify_resp: dict[str, Any] = _make_classify_response()

        mock_response: MagicMock = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = classify_resp
        mock_response.raise_for_status = MagicMock()

        mock_client: AsyncMock = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_write: MagicMock = MagicMock()

        with patch("business_map_hook.httpx.AsyncClient", return_value=mock_client), \
             patch("business_map_hook.os.getenv", side_effect=lambda k, d="": tmp_path.as_posix() if k == "INNER_STORAGE_DIR" else d), \
             patch("hlsc.services.slot_state_service.SlotStateService.read", return_value=None), \
             patch("hlsc.services.slot_state_service.SlotStateService.write", mock_write):

            await orchestrator(
                user_id="user1",
                session_id="session4",
                deps=deps,
                message="保养",
            )

        # 验证 write 被调用且 current_scene 正确
        mock_write.assert_called_once()
        written_state: Any = mock_write.call_args[0][1]
        assert written_state.current_scene == "DIRECT_PROJECT"

    def test_current_session_id(self, orchestrator: SceneOrchestrator) -> None:
        """current_session_id 从 contextvars 读取。"""
        # 默认值
        sid: str = orchestrator.current_session_id
        assert isinstance(sid, str)

    def test_get_scene_context_none(self, orchestrator: SceneOrchestrator) -> None:
        """未设置时返回 None。"""
        assert orchestrator.get_scene_context("nonexistent") is None

    @pytest.mark.asyncio
    async def test_classify_response_no_skills_key(self, orchestrator: SceneOrchestrator, tmp_path: Path) -> None:
        """响应中缺少 skills key 时默认为空列表。"""
        deps: FakeDeps = FakeDeps()
        classify_resp: dict[str, Any] = _make_classify_response()
        del classify_resp["skills"]  # 移除 skills key

        mock_response: MagicMock = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = classify_resp
        mock_response.raise_for_status = MagicMock()

        mock_client: AsyncMock = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("business_map_hook.httpx.AsyncClient", return_value=mock_client), \
             patch("business_map_hook.os.getenv", side_effect=lambda k, d="": tmp_path.as_posix() if k == "INNER_STORAGE_DIR" else d), \
             patch("hlsc.services.slot_state_service.SlotStateService.read", return_value=None), \
             patch("hlsc.services.slot_state_service.SlotStateService.write"):

            await orchestrator(
                user_id="user1",
                session_id="session5",
                deps=deps,
                message="test",
            )

        ctx: SceneContext | None = orchestrator.get_scene_context("session5")
        assert ctx is not None
        assert ctx.allowed_skills == []
        assert deps.allowed_skills is None  # 空列表 → None
