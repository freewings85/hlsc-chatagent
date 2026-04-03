"""Tool prompt 加载器：从 prompts/ 目录读取工具描述。"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_tool_prompt(tool_name: str, scene: str | None = None) -> str:
    """加载指定工具的 prompt 描述文件。

    支持场景级别的 prompt：优先找 {tool_name}.{scene}.md，没有则回退到 {tool_name}.md。

    Args:
        tool_name: 工具名（对应 prompts/{tool_name}.md）
        scene: 场景名（可选），如 "searchshops"

    Returns:
        prompt 文本内容
    """
    # 优先场景级别的 prompt
    if scene:
        scene_path: Path = _PROMPTS_DIR / f"{tool_name}.{scene}.md"
        if scene_path.exists():
            return scene_path.read_text(encoding="utf-8").strip()

    # 回退到通用 prompt
    path: Path = _PROMPTS_DIR / f"{tool_name}.md"
    if not path.exists():
        return f"{tool_name} tool"
    return path.read_text(encoding="utf-8").strip()
