"""槽位状态服务：SlotState 模型 + 持久化读写。

以 ``slot_state.json`` 文件存储在 session 目录下，
提供槽位初始化、读写和便捷操作方法。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from hlsc.services.scene_service import SceneServiceConfig

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================


class SceneHistoryEntry(BaseModel):
    """场景历史记录条目。"""

    scene: str
    turns: int = 0


class SlotState(BaseModel):
    """槽位状态：记录当前会话的所有槽位值和场景历史。"""

    slots: dict[str, str | None] = {}
    scene_history: list[SceneHistoryEntry] = []
    current_scene: str | None = None

    def has_slot(self, name: str) -> bool:
        """判断槽位是否有值（非 None 且已存在）。"""
        return name in self.slots and self.slots[name] is not None

    def set_slot(self, name: str, value: str | None) -> None:
        """设置槽位值。"""
        self.slots[name] = value

    def reset_slots(self, names: list[str]) -> None:
        """重置指定槽位为 None。"""
        name: str
        for name in names:
            if name in self.slots:
                self.slots[name] = None

    def get_filled_slots(self) -> dict[str, str]:
        """只返回有值的槽位。"""
        result: dict[str, str] = {}
        key: str
        value: str | None
        for key, value in self.slots.items():
            if value is not None:
                result[key] = value
        return result


# ============================================================
# 服务类
# ============================================================


class SlotStateService:
    """槽位状态持久化服务。

    文件名固定为 ``slot_state.json``，存储在 session 目录下。
    """

    FILENAME: str = "slot_state.json"

    def read(self, session_dir: Path) -> SlotState | None:
        """读取槽位状态，文件不存在返回 None。"""
        file_path: Path = session_dir / self.FILENAME
        if not file_path.exists():
            return None
        try:
            content: str = file_path.read_text(encoding="utf-8")
            if not content.strip():
                return None
            state: SlotState = SlotState.model_validate_json(content)
            return state
        except Exception:
            logger.warning("读取槽位状态失败: %s", file_path, exc_info=True)
            return None

    def write(self, session_dir: Path, state: SlotState) -> None:
        """写入/更新槽位状态。"""
        session_dir.mkdir(parents=True, exist_ok=True)
        file_path: Path = session_dir / self.FILENAME
        try:
            json_str: str = state.model_dump_json(indent=2)
            file_path.write_text(json_str, encoding="utf-8")
            logger.info("槽位状态已更新: %s", file_path)
        except Exception:
            logger.error("写入槽位状态失败: %s", file_path, exc_info=True)
            raise

    def get_or_create(
        self, session_dir: Path, config: SceneServiceConfig
    ) -> SlotState:
        """读取已有状态，或根据配置创建新状态。

        从 config.stages 的所有 slots 中提取 key 作为初始化槽位，值均为 None。
        """
        existing: SlotState | None = self.read(session_dir)
        if existing is not None:
            return existing

        # 从所有阶段的 slots 中收集槽位名
        all_slot_names: set[str] = set()
        stage_id: str
        stage: Any  # StageConfig，但避免循环 import 只用于迭代
        for stage_id, stage in config.stages.items():
            slot_name: str
            for slot_name in stage.slots:
                all_slot_names.add(slot_name)

        # 初始化所有槽位为 None
        initial_slots: dict[str, str | None] = {
            name: None for name in sorted(all_slot_names)
        }

        state: SlotState = SlotState(slots=initial_slots)
        logger.info(
            "创建新槽位状态: %d 个槽位 (%s)",
            len(initial_slots),
            ", ".join(sorted(all_slot_names)),
        )

        # 持久化到磁盘
        self.write(session_dir, state)
        return state


# 模块级单例
slot_state_service: SlotStateService = SlotStateService()
