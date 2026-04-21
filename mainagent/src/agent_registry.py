"""AGENT_REGISTRY 加载器（agent-graph 简化版）。

启动时从 mainagent/agents.yaml 构建 `agent_name → AgentSpec` 的映射（flat）。
/chat/stream2 按 agent_name 查表后动态组 per-request Agent 实例跑。

agent_name 惯例：`<scene>_<phase>` 或独立 scene 名
（如 `searchshops_collect` / `searchshops_executing` / `guide` / `insurance`）。
具体名字由业务约定，本模块不做语义检查。

每个 AgentSpec 字段对应 agents.yaml 里同名键；prompt_parts 在加载时直接按序读进
内存并拼成一段 system prompt，避免每次请求时 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

CommitPolicy = Literal["full", "text_only", "nothing"]


@dataclass(frozen=True)
class AgentSpec:
    """单个 agent 的静态配置。

    tools / skills / agent_md_files 用 tuple 保持 frozen dataclass 的 hash 能力。
    """

    name: str
    prompt: str
    """prompt_parts 按序读文件 + '\\n\\n' 拼接好的 system prompt。"""
    agent_md_files: tuple[str, ...]
    """agent_md 文件路径（相对 templates/）。路由层可按需渲染成 dynamic context。"""
    tools: tuple[str, ...]
    """tool 名字列表。"""
    skills: tuple[str, ...]
    """skill 名字列表。"""
    load_history: bool
    """是否装载本 session 历史（跨所有 scene / agent 共享）。"""
    commit_policy: CommitPolicy


# agent_name → AgentSpec
AGENT_REGISTRY: dict[str, AgentSpec] = {}


def _load_prompt(templates_root: Path, rel_paths: list[str], agent_name: str) -> str:
    """把 prompt_parts 按序读文件内容拼一段 system prompt。"""
    parts: list[str] = []
    for rel in rel_paths:
        path: Path = (templates_root / rel).resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"agents.yaml agent {agent_name!r} 的 prompt_parts 找不到：{path}"
            )
        parts.append(path.read_text(encoding="utf-8").rstrip())
    return "\n\n".join(parts)


def _to_tuple(raw: object, key: str, agent_name: str) -> tuple[str, ...]:
    """把 yaml 里的 list[str] 字段安全转成 tuple[str, ...]，None 视作空。"""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"agents.yaml {agent_name!r}.{key} 必须是 list，收到：{type(raw).__name__}")
    return tuple(str(item) for item in raw)


def load_registry(yaml_path: Path, mainagent_root: Path) -> dict[str, AgentSpec]:
    """加载 agents.yaml，返回 agent_name → AgentSpec。

    副作用：同时覆盖写入全局 AGENT_REGISTRY（方便路由层直接 import 使用）。

    Args:
        yaml_path: agents.yaml 绝对路径
        mainagent_root: mainagent 目录根，用于解析 prompt_parts 相对路径
    """
    if not yaml_path.is_file():
        raise FileNotFoundError(f"agents.yaml 不存在：{yaml_path}")

    data: dict[str, object] = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    raw_agents: object = data.get("agents", {})
    if not isinstance(raw_agents, dict):
        raise ValueError("agents.yaml 顶层必须有 agents: 字典")

    templates_root: Path = mainagent_root / "prompts" / "templates"

    registry: dict[str, AgentSpec] = {}
    for key, entry in raw_agents.items():
        agent_name: str = str(key)
        if not isinstance(entry, dict):
            raise ValueError(f"agents.yaml 条目 {agent_name!r} 不是字典")

        prompt_parts_raw: object = entry.get("prompt_parts")
        if not isinstance(prompt_parts_raw, list) or not prompt_parts_raw:
            raise ValueError(
                f"agents.yaml {agent_name!r} 的 prompt_parts 必须是非空 list"
            )
        prompt_rel: list[str] = [str(p) for p in prompt_parts_raw]
        prompt_text: str = _load_prompt(templates_root, prompt_rel, agent_name)

        load_history_raw: object = entry.get("load_history", False)
        if not isinstance(load_history_raw, bool):
            raise ValueError(
                f"agents.yaml {agent_name!r}.load_history 必须是 bool，收到：{load_history_raw!r}"
            )

        commit_policy_raw: str = str(entry.get("commit_policy", "text_only"))
        if commit_policy_raw not in ("full", "text_only", "nothing"):
            raise ValueError(
                f"agents.yaml {agent_name!r}.commit_policy 非法：{commit_policy_raw!r}"
            )

        spec: AgentSpec = AgentSpec(
            name=agent_name,
            prompt=prompt_text,
            agent_md_files=_to_tuple(entry.get("agent_md"), "agent_md", agent_name),
            tools=_to_tuple(entry.get("tools"), "tools", agent_name),
            skills=_to_tuple(entry.get("skills"), "skills", agent_name),
            load_history=load_history_raw,
            commit_policy=commit_policy_raw,  # type: ignore[arg-type]
        )
        registry[agent_name] = spec

    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(registry)
    return registry


def default_yaml_path() -> Path:
    return (Path(__file__).resolve().parent.parent / "agents.yaml").resolve()


def default_mainagent_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_default_registry() -> dict[str, AgentSpec]:
    return load_registry(default_yaml_path(), default_mainagent_root())
