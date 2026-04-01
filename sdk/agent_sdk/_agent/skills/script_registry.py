"""技能脚本发现：从 skill 目录中查找并加载 SkillScript 子类。

扫描顺序：
1. skill_dir/scripts/*.py — 推荐，一个 skill 可包含多个脚本
2. skill_dir/script.py   — 向后兼容

每个 .py 文件中如果包含 SkillScript 子类且 name 非空，则注册。
同名 skill 后扫描到的会覆盖先扫描到的（scripts/ 优先于 script.py）。
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


def _load_script_from_file(
    script_file: Path,
    module_name: str,
) -> type[SkillScript] | None:
    """从单个 .py 文件中加载 SkillScript 子类。"""
    try:
        # 将脚本所在目录加入 sys.path，使同目录脚本可互相 import
        script_dir: str = str(script_file.resolve().parent)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

        spec = importlib.util.spec_from_file_location(module_name, script_file)
        if spec is None or spec.loader is None:
            logger.warning("无法为 %s 创建模块 spec", script_file)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        from agent_sdk._agent.skills.script import SkillScript as _Base

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, _Base)
                and attr is not _Base
                and hasattr(attr, "name")
                and attr.name
            ):
                logger.info("已加载技能脚本: %s → %s", script_file, attr.__name__)
                return attr

        return None

    except Exception:
        logger.warning("加载技能脚本失败: %s", script_file, exc_info=True)
        return None


def load_script_class(skill_dir: Path) -> type[SkillScript] | None:
    """从 skill 目录加载 SkillScript 子类。

    扫描 scripts/*.py（推荐）和 script.py（兼容），返回第一个找到的。

    Args:
        skill_dir: skill 目录（包含 SKILL.md）。

    Returns:
        找到的 SkillScript 子类，或 None。
    """
    safe_name: str = skill_dir.name.replace("-", "_")

    # 1. 优先扫描 scripts/ 目录
    scripts_dir: Path = skill_dir / "scripts"
    if scripts_dir.is_dir():
        for py_file in sorted(scripts_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name: str = f"_skill_script_{safe_name}_{py_file.stem}"
            found: type[SkillScript] | None = _load_script_from_file(py_file, module_name)
            if found is not None:
                return found

    # 2. 向后兼容：skill_dir/script.py
    legacy_file: Path = skill_dir / "script.py"
    if legacy_file.exists():
        module_name = f"_skill_script_{safe_name}"
        return _load_script_from_file(legacy_file, module_name)

    return None


def load_script_class_by_name(
    skill_dir: Path,
    script_name: str,
) -> type[SkillScript] | None:
    """按名称加载 skill 下的指定脚本。

    查找顺序：
    1. scripts/{script_name}.py
    2. script.py（仅当 script_name 匹配 skill 名称时）

    Args:
        skill_dir: skill 目录。
        script_name: 脚本名称（不含 .py 后缀）。

    Returns:
        找到的 SkillScript 子类，或 None。
    """
    safe_name: str = skill_dir.name.replace("-", "_")

    # 1. scripts/{script_name}.py
    target: Path = skill_dir / "scripts" / f"{script_name}.py"
    if target.exists():
        module_name: str = f"_skill_script_{safe_name}_{script_name}"
        return _load_script_from_file(target, module_name)

    # 2. 向后兼容 script.py
    legacy: Path = skill_dir / "script.py"
    if legacy.exists():
        module_name = f"_skill_script_{safe_name}"
        return _load_script_from_file(legacy, module_name)

    return None
