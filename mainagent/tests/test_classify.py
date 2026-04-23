from __future__ import annotations

import pytest

from src.classify import classify_scenario


@pytest.mark.asyncio
async def test_classify_scenario_returns_scene_phase_and_scenes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call_bma_classify(message: str, recent_turns=None):  # type: ignore[no-untyped-def]
        return {
            "scene": "searchshops",
            "phase": "followup",
            "scenes": ["searchshops"],
        }

    monkeypatch.setattr("src.classify._call_bma_classify", fake_call_bma_classify)

    scenario, phase, scenes = await classify_scenario(
        user_id="u1",
        session_id="s1",
        message="第二家几点关门",
        memory_service_factory=None,
    )

    assert scenario == "searchshops"
    assert phase == "followup"
    assert scenes == ["searchshops"]


@pytest.mark.asyncio
async def test_classify_scenario_falls_back_from_legacy_scenes_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call_bma_classify(message: str, recent_turns=None):  # type: ignore[no-untyped-def]
        return {
            "scenes": ["guide"],
        }

    monkeypatch.setattr("src.classify._call_bma_classify", fake_call_bma_classify)

    scenario, phase, scenes = await classify_scenario(
        user_id="u1",
        session_id="s1",
        message="你好",
        memory_service_factory=None,
    )

    assert scenario == "guide"
    assert phase == "intake"
    assert scenes == ["guide"]
