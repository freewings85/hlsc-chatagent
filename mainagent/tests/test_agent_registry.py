"""agent_registry 的单测（agent-graph 简化版）。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src import agent_registry


def _write_yaml(tmp_path: Path, content: dict) -> Path:
    p: Path = tmp_path / "agents.yaml"
    p.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")
    return p


def _mainagent_root_fixture(tmp_path: Path) -> Path:
    (tmp_path / "prompts" / "templates" / "_shared").mkdir(parents=True)
    (tmp_path / "prompts" / "templates" / "_shared" / "A.md").write_text("A body", encoding="utf-8")
    (tmp_path / "prompts" / "templates" / "_shared" / "B.md").write_text("B body", encoding="utf-8")
    return tmp_path


# ──────────── 默认 registry 端到端 ────────────


def test_load_default_registry_has_expected_agents() -> None:
    reg: dict[str, agent_registry.AgentSpec] = agent_registry.load_default_registry()
    for name in (
        "searchshops_collect",
        "searchshops_executing",
        "searchshops_executed",
        "searchcoupons_collect",
        "searchcoupons_executing",
        "searchcoupons_executed",
        "debug_collect",
        "debug_executing",
        "debug_executed",
        "guide",
        "platform",
        "insurance",
    ):
        assert name in reg, f"agents.yaml 缺 {name}"


def test_insurance_has_tools() -> None:
    reg: dict[str, agent_registry.AgentSpec] = agent_registry.load_default_registry()
    assert len(reg["insurance"].tools) > 0


def test_load_history_is_bool() -> None:
    reg: dict[str, agent_registry.AgentSpec] = agent_registry.load_default_registry()
    assert reg["searchshops_collect"].load_history is True
    assert reg["searchshops_executing"].load_history is False


def test_commit_policy_variants() -> None:
    reg: dict[str, agent_registry.AgentSpec] = agent_registry.load_default_registry()
    assert reg["searchshops_collect"].commit_policy == "full"
    assert reg["searchshops_executed"].commit_policy == "text_only"


# ──────────── 合成 yaml 错误路径 ────────────


def test_empty_prompt_parts_rejected(tmp_path: Path) -> None:
    root: Path = _mainagent_root_fixture(tmp_path)
    yaml_path: Path = _write_yaml(tmp_path, {
        "agents": {
            "x": {
                "prompt_parts": [],
                "load_history": False,
                "commit_policy": "text_only",
            }
        }
    })
    with pytest.raises(ValueError, match="prompt_parts"):
        agent_registry.load_registry(yaml_path, root)


def test_missing_prompt_file_rejected(tmp_path: Path) -> None:
    root: Path = _mainagent_root_fixture(tmp_path)
    yaml_path: Path = _write_yaml(tmp_path, {
        "agents": {
            "x": {
                "prompt_parts": ["_shared/NOPE.md"],
                "load_history": False,
                "commit_policy": "text_only",
            }
        }
    })
    with pytest.raises(FileNotFoundError):
        agent_registry.load_registry(yaml_path, root)


def test_invalid_load_history_rejected(tmp_path: Path) -> None:
    root: Path = _mainagent_root_fixture(tmp_path)
    yaml_path: Path = _write_yaml(tmp_path, {
        "agents": {
            "x": {
                "prompt_parts": ["_shared/A.md"],
                "load_history": "all",
                "commit_policy": "text_only",
            }
        }
    })
    with pytest.raises(ValueError, match="load_history"):
        agent_registry.load_registry(yaml_path, root)


def test_invalid_commit_policy_rejected(tmp_path: Path) -> None:
    root: Path = _mainagent_root_fixture(tmp_path)
    yaml_path: Path = _write_yaml(tmp_path, {
        "agents": {
            "x": {
                "prompt_parts": ["_shared/A.md"],
                "load_history": False,
                "commit_policy": "bogus",
            }
        }
    })
    with pytest.raises(ValueError, match="commit_policy"):
        agent_registry.load_registry(yaml_path, root)


def test_yaml_file_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        agent_registry.load_registry(tmp_path / "no.yaml", tmp_path)


def test_agents_top_level_wrong_type(tmp_path: Path) -> None:
    p: Path = tmp_path / "agents.yaml"
    p.write_text("agents: [1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="agents"):
        agent_registry.load_registry(p, _mainagent_root_fixture(tmp_path))


def test_prompt_parts_assembled(tmp_path: Path) -> None:
    root: Path = _mainagent_root_fixture(tmp_path)
    yaml_path: Path = _write_yaml(tmp_path, {
        "agents": {
            "x": {
                "prompt_parts": ["_shared/A.md", "_shared/B.md"],
                "load_history": False,
                "commit_policy": "text_only",
            }
        }
    })
    reg: dict[str, agent_registry.AgentSpec] = agent_registry.load_registry(yaml_path, root)
    assert reg["x"].prompt == "A body\n\nB body"
