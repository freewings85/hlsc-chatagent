from __future__ import annotations

import pytest

from src.classify import ClassifyRequest, _do_classify


@pytest.mark.asyncio
async def test_do_classify_accepts_single_scene_phase_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_llm(message: str, recent_turns=None, use_multi_turn=False):  # type: ignore[no-untyped-def]
        return {"scene": "searchcoupons", "phase": "followup"}

    monkeypatch.setattr("src.classify._call_llm", fake_call_llm)

    result = await _do_classify(
        ClassifyRequest(message="第一个活动怎么参加", recent_turns=[]),
        use_multi_turn=False,
    )

    assert result.scene == "searchcoupons"
    assert result.phase == "followup"


@pytest.mark.asyncio
async def test_do_classify_falls_back_to_guide_intake_on_invalid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_llm(message: str, recent_turns=None, use_multi_turn=False):  # type: ignore[no-untyped-def]
        return {"scene": "ghost", "phase": "weird"}

    monkeypatch.setattr("src.classify._call_llm", fake_call_llm)

    result = await _do_classify(
        ClassifyRequest(message="你好", recent_turns=[]),
        use_multi_turn=False,
    )

    assert result.scene == "guide"
    assert result.phase == "intake"
