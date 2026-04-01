"""技能脚本发现：从 skill 目录中查找并加载 SkillScript 子类。

约定：skill 目录下如果存在 script.py 文件，则认为该 skill 有 Python 脚本实现。
script.py 中应包含一个 SkillScript 的子类。
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_sdk._agent.skills.script import SkillScript

logger: logging.Logger = logging.getLogger(__name__)


def load_script_class(skill_dir: Path) -> type[SkillScript] | None:
    """从 skill 目录的 script.py 加载 SkillScript 子类。

    Args:
        skill_dir: skill 目录（包含 SKILL.md 和可选的 script.py）。

    Returns:
        找到的 SkillScript 子类，或 None。
    """
    script_file: Path = skill_dir / "script.py"
    if not script_file.exists():
        return None

    # 动态导入
    module_name: str = f"_skill_script_{skill_dir.name.replace('-', '_')}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, script_file)
        if spec is None or spec.loader is None:
            logger.warning("无法为 %s 创建模块 spec", script_file)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 扫描模块中的 SkillScript 子类
        from agent_sdk._agent.skills.script import SkillScript as _Base

        found: type[SkillScript] | None = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, _Base)
                and attr is not _Base
                and hasattr(attr, "name")
                and attr.name
            ):
                found = attr
                break

        if found is not None:
            logger.info("已加载技能脚本: %s → %s", script_file, found.__name__)
        return found

    except Exception:
        logger.warning("加载技能脚本失败: %s", script_file, exc_info=True)
        return None
