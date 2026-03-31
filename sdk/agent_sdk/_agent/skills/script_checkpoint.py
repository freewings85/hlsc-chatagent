"""SkillCheckpoint：技能脚本的断点持久化。

每个 session 同时只有一个 checkpoint（技能脚本串行执行）。
使用 inner_storage_backend 存储，路径：/{user_id}/sessions/{session_id}/skill_script_checkpoint.json

与 InvokedSkillStore 使用相同的 delete-then-write 模式。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_sdk._common.filesystem_backend import BackendProtocol

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class SkillCheckpoint:
    """技能脚本断点数据。"""

    skill_name: str
    """触发中断的技能名称。"""

    state: dict[str, Any] = field(default_factory=dict)
    """中断时的累积状态快照。"""

    answered: dict[str, str] = field(default_factory=dict)
    """已回答的 interrupt_id → 用户回复。"""

    pending_interrupt_id: str = ""
    """等待用户回复的 interrupt_id。"""

    pending_data: dict[str, Any] = field(default_factory=dict)
    """pending interrupt 的前端数据（用于重发事件）。"""

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    """创建时间 ISO 格式。"""


def _checkpoint_path(user_id: str, session_id: str) -> str:
    """checkpoint 文件路径。"""
    return f"/{user_id}/sessions/{session_id}/skill_script_checkpoint.json"


async def save_checkpoint(
    backend: "BackendProtocol",
    user_id: str,
    session_id: str,
    checkpoint: SkillCheckpoint,
) -> None:
    """保存 checkpoint 到 session 目录。"""
    path: str = _checkpoint_path(user_id, session_id)
    data: dict[str, Any] = {
        "skill_name": checkpoint.skill_name,
        "state": checkpoint.state,
        "answered": checkpoint.answered,
        "pending_interrupt_id": checkpoint.pending_interrupt_id,
        "pending_data": checkpoint.pending_data,
        "created_at": checkpoint.created_at,
    }
    content: str = json.dumps(data, ensure_ascii=False, indent=2)

    # delete-then-write（同 InvokedSkillStore）
    if await backend.aexists(path):
        await backend.adelete(path)

    result = await backend.awrite(path, content)
    if result.error is not None:
        raise OSError(f"保存 skill checkpoint 失败: {path}: {result.error}")

    logger.info("Skill checkpoint 已保存: skill=%s, interrupt=%s",
                checkpoint.skill_name, checkpoint.pending_interrupt_id)


async def load_checkpoint(
    backend: "BackendProtocol",
    user_id: str,
    session_id: str,
) -> SkillCheckpoint | None:
    """加载 checkpoint，不存在或损坏时返回 None。"""
    path: str = _checkpoint_path(user_id, session_id)
    if not await backend.aexists(path):
        return None

    responses = await backend.adownload_files([path])
    resp = responses[0]
    if resp.error is not None or resp.content is None:
        return None

    raw: str = resp.content.decode("utf-8").strip()
    if not raw:
        return None

    try:
        data: dict[str, Any] = json.loads(raw)
        return SkillCheckpoint(
            skill_name=data["skill_name"],
            state=data.get("state", {}),
            answered=data.get("answered", {}),
            pending_interrupt_id=data.get("pending_interrupt_id", ""),
            pending_data=data.get("pending_data", {}),
            created_at=data.get("created_at", ""),
        )
    except (json.JSONDecodeError, KeyError):
        logger.warning("Skill checkpoint 文件损坏，已忽略: %s", path)
        return None


async def clear_checkpoint(
    backend: "BackendProtocol",
    user_id: str,
    session_id: str,
) -> None:
    """清除 checkpoint 文件。"""
    path: str = _checkpoint_path(user_id, session_id)
    if await backend.aexists(path):
        await backend.adelete(path)
        logger.info("Skill checkpoint 已清除: %s", path)
