"""状态树读写服务：管理 session 级别的业务流程状态树（Markdown 文件）。"""

from __future__ import annotations

import logging
from pathlib import Path

logger: logging.Logger = logging.getLogger(__name__)


class StateTreeService:
    """状态树持久化服务。

    状态树以 Markdown 文件存储在 session 目录下，格式为缩进清单：
    - [完成] / [进行中] / [跳过] / [ ] 状态标记
    - ← 当前 焦点标记
    - → 产出内联记录
    """

    FILENAME: str = "state_tree.md"

    def read(self, session_dir: Path) -> str | None:
        """读取状态树，不存在返回 None。"""
        file_path: Path = session_dir / self.FILENAME
        if not file_path.exists():
            return None
        try:
            content: str = file_path.read_text(encoding="utf-8")
            return content if content.strip() else None
        except Exception:
            logger.warning("读取状态树失败: %s", file_path, exc_info=True)
            return None

    def write(self, session_dir: Path, content: str) -> None:
        """写入/更新状态树。"""
        session_dir.mkdir(parents=True, exist_ok=True)
        file_path: Path = session_dir / self.FILENAME
        try:
            file_path.write_text(content, encoding="utf-8")
            logger.info("状态树已更新: %s", file_path)
        except Exception:
            logger.error("写入状态树失败: %s", file_path, exc_info=True)
            raise


state_tree_service: StateTreeService = StateTreeService()
