"""SkillRegistry：SKILL.md 解析 + 多目录加载。

兼容 Claude Code 和 OpenClaw 两种 SKILL.md 格式（Decision 4）：
- Claude Code：name, description, when_to_use, allowed-tools(忽略), context(忽略)
- OpenClaw：name, description, user-invocable, disable-model-invocation, metadata.openclaw(忽略)

加载优先级（后覆盖前，同名 skill 取最高优先级）：
  1. bundled（内置，src/agent/skills/bundled/）
  2. project（SKILLS_DIR 环境变量配置，默认 .chatagent/skills/）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# SkillEntry 数据结构                                                          #
# --------------------------------------------------------------------------- #

@dataclass
class SkillEntry:
    """一条已加载的 skill 记录。"""

    name: str
    """skill 名称，用于 Skill 工具调用（Skill(skill="commit")）。"""

    description: str
    """一行描述，注入到 skill_listing attachment 供 LLM 匹配。"""

    content: str
    """SKILL.md 完整 Markdown 正文（不含 frontmatter），invoke 时返回给 LLM。"""

    # Claude Code 字段
    when_to_use: str | None = None
    """触发描述（CC 格式），更精确地描述触发时机。"""

    # OpenClaw 字段
    user_invocable: bool = True
    """是否出现在 skill_listing 中（供用户/模型调用）。"""

    disable_model_invocation: bool = False
    """禁止模型自动触发（仅用户手动调用）。"""

    source_path: Path | None = None
    """来源文件路径（调试用）。"""

    def trigger_description(self) -> str:
        """用于注入 skill_listing 的触发描述。

        有 when_to_use 用它（CC 风格，更精确）；没有退化到 description（OpenClaw 风格）。
        """
        return self.when_to_use or self.description

    def should_include_in_listing(self) -> bool:
        """是否应出现在 skill_listing attachment 中。"""
        return self.user_invocable and not self.disable_model_invocation


# --------------------------------------------------------------------------- #
# SKILL.md 解析                                                                #
# --------------------------------------------------------------------------- #

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def _parse_frontmatter_line(line: str) -> tuple[str, str | bool] | None:
    """解析 'key: value' 行，返回 (key, value) 或 None（忽略行）。

    支持：
    - key: value
    - key: "quoted value"
    - key: 'quoted value'
    - key: true / false（布尔）
    - 忽略缩进行（嵌套块如 metadata.openclaw）
    - 忽略注释行
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    # 忽略缩进行（嵌套块）
    if line.startswith(" ") or line.startswith("\t"):
        return None
    if ":" not in stripped:
        return None

    key, _, raw_val = stripped.partition(":")
    key = key.strip()
    value = raw_val.strip()

    # 去除引号
    if len(value) >= 2 and (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        value = value[1:-1]

    # 布尔
    if value.lower() == "true":
        return key, True
    if value.lower() == "false":
        return key, False

    return key, value


def parse_skill_content(text: str, source_path: Path | None = None) -> SkillEntry | None:
    """解析 SKILL.md 文本内容，返回 SkillEntry 或 None（格式错误时）。

    兼容 Claude Code 和 OpenClaw 两种格式，未知字段直接忽略。
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None

    fm_text, body = m.group(1), m.group(2).strip()

    raw: dict[str, str | bool] = {}
    for line in fm_text.splitlines():
        parsed = _parse_frontmatter_line(line)
        if parsed is not None:
            key, val = parsed
            raw[key] = val

    name = raw.get("name")
    description = raw.get("description")

    # name 和 description 是必填字段
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(description, str) or not description.strip():
        return None

    when_to_use = raw.get("when_to_use")
    user_invocable_raw = raw.get("user-invocable", True)
    disable_model_raw = raw.get("disable-model-invocation", False)

    return SkillEntry(
        name=name.strip(),
        description=description.strip(),
        content=body,
        when_to_use=when_to_use.strip() if isinstance(when_to_use, str) else None,
        user_invocable=bool(user_invocable_raw),
        disable_model_invocation=bool(disable_model_raw),
        source_path=source_path,
    )


def parse_skill_file(path: Path) -> SkillEntry | None:
    """解析 SKILL.md 文件，返回 SkillEntry 或 None（格式错误时）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_skill_content(text, source_path=path)


# --------------------------------------------------------------------------- #
# SkillRegistry                                                                #
# --------------------------------------------------------------------------- #

# 字符限制（参照 Claude Code LT8 / Xs9，简化版）
_MAX_SKILL_LIST_CHARS = 4000
_MAX_SKILL_DESC_CHARS = 200


@dataclass
class SkillRegistry:
    """已加载的 skill 集合，按名称索引。

    通过 load() 类方法从目录列表构建。
    优先级：dirs 列表靠后的目录优先级更高（后覆盖前）。
    """

    _entries: dict[str, SkillEntry] = field(default_factory=dict)

    def get(self, name: str) -> SkillEntry | None:
        """按名称获取 skill。"""
        return self._entries.get(name)

    def list_invocable(self) -> list[SkillEntry]:
        """返回应出现在 skill_listing 中的 skill 列表（按名称排序）。"""
        return sorted(
            (e for e in self._entries.values() if e.should_include_in_listing()),
            key=lambda e: e.name,
        )

    def has_skills(self) -> bool:
        """是否有任何已加载的 skill。"""
        return bool(self._entries)

    @classmethod
    def load(cls, dirs: list[Path]) -> "SkillRegistry":
        """从多个目录加载 skill，后覆盖前（优先级更高的目录放后面）。

        每个目录中：每个子目录对应一个 skill，子目录下的 SKILL.md 为定义文件。
        """
        registry = cls()
        for d in dirs:
            base_dir = Path(d) if isinstance(d, str) else d
            if not base_dir.is_dir():
                continue
            for skill_dir in sorted(base_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue
                entry = parse_skill_file(skill_file)
                if entry is not None:
                    registry._entries[entry.name] = entry
        return registry

    def format_listing(self) -> str:
        """格式化 skill_listing 文本（带字符预算控制）。

        格式（兼容 Claude Code ET8 风格）：
          - skill_name: description - when_to_use
        """
        skills = self.list_invocable()
        if not skills:
            return ""

        lines: list[str] = []
        total_chars = 0

        for skill in skills:
            desc = skill.description
            if skill.when_to_use:
                desc = f"{desc} - {skill.when_to_use}"
            if len(desc) > _MAX_SKILL_DESC_CHARS:
                desc = desc[:_MAX_SKILL_DESC_CHARS - 1] + "…"
            line = f"- {skill.name}: {desc}"

            if total_chars + len(line) + 1 > _MAX_SKILL_LIST_CHARS:
                break
            lines.append(line)
            total_chars += len(line) + 1

        return "\n".join(lines)


def get_default_skill_dirs() -> list[Path]:
    """返回默认的 skill 目录列表（优先级从低到高）。

    两层：bundled（内置）→ project（AGENT_FS_DIR/fstools/skills）。
    """
    from agent_sdk.config import SKILL_DIRS

    return [
        Path(__file__).parent / "bundled",                          # 内置（最低优先级）
        *[Path(d) for d in SKILL_DIRS],                             # 项目级（最高优先级）
    ]
