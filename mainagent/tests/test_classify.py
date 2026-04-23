from __future__ import annotations

import pytest

from src.classify import ScenePhase, classify_scenario


@pytest.mark.asyncio
async def test_classify_scenario_wraps_primary_scene_phase_into_single_scene_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_bma_classify(message: str, recent_turns=None):  # type: ignore[no-untyped-def]
        return [ScenePhase(name="searchshops", phase="followup")]

    monkeypatch.setattr("src.classify._call_bma_classify", fake_call_bma_classify)

    scenes = await classify_scenario(
        user_id="u1",
        session_id="s1",
        message="第二家几点关门",
        memory_service_factory=None,
    )

    assert len(scenes) == 1
    assert scenes[0].name == "searchshops"
    assert scenes[0].phase == "followup"


@pytest.mark.asyncio
async def test_classify_scenario_keeps_legacy_scenes_shape_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_bma_classify(message: str, recent_turns=None):  # type: ignore[no-untyped-def]
        return [ScenePhase(name="guide", phase="intake")]

    monkeypatch.setattr("src.classify._call_bma_classify", fake_call_bma_classify)

    scenes = await classify_scenario(
        user_id="u1",
        session_id="s1",
        message="你好",
        memory_service_factory=None,
    )

    assert len(scenes) == 1
    assert scenes[0].name == "guide"
    assert scenes[0].phase == "intake"
