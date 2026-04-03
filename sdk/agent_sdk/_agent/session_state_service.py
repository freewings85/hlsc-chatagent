"""SessionStateService：会话状态持久化。

当前实现：JSON 文件存储。
路径：{base_dir}/{user_id}/session_state/{session_id}.json
后续可替换为 SQLite 实现。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)


class SessionStateService:
    """会话状态持久化服务（文件实现）。"""

    def __init__(self, base_dir: str) -> None:
        self._base_dir: str = base_dir

    def _get_path(self, user_id: str, session_id: str) -> Path:
        """获取 session_state 文件路径。"""
        return Path(self._base_dir) / user_id / "session_state" / f"{session_id}.json"

    def load(self, user_id: str, session_id: str) -> dict[str, Any]:
        """加载 session_state，不存在返回空 dict。"""
        path: Path = self._get_path(user_id, session_id)
        if not path.exists():
            return {}
        try:
            raw: str = path.read_text(encoding="utf-8")
            state: dict[str, Any] = json.loads(raw)
            logger.debug("加载 session_state: %s, keys=%s", path, list(state.keys()))
            return state
        except Exception:
            logger.warning("加载 session_state 失败: %s", path, exc_info=True)
            return {}

    def save(self, user_id: str, session_id: str, state: dict[str, Any]) -> None:
        """保存 session_state。"""
        path: Path = self._get_path(user_id, session_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug("保存 session_state: %s, keys=%s", path, list(state.keys()))
        except Exception:
            logger.warning("保存 session_state 失败: %s", path, exc_info=True)

    def delete(self, user_id: str, session_id: str) -> None:
        """删除 session_state。"""
        path: Path = self._get_path(user_id, session_id)
        try:
            if path.exists():
                path.unlink()
                logger.debug("删除 session_state: %s", path)
        except Exception:
            logger.warning("删除 session_state 失败: %s", path, exc_info=True)
