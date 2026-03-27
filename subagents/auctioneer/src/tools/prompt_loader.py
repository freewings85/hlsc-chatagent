"""Tool prompt 加载器：从 prompts/ 目录读取工具描述。"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR: Path = Path(__file__).parent / "prompts"


def load_tool_prompt(tool_name: str) -> str:
    """加载指定工具的 prompt 描述文件。"""
    path: Path = _PROMPTS_DIR / f"{tool_name}.md"
    if not path.exists():
        return f"{tool_name} tool"
    return path.read_text(encoding="utf-8").strip()
