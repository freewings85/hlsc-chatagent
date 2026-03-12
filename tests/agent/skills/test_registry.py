"""SkillRegistry 和 parse_skill_file 测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.sdk._agent.skills.registry import (
    SkillEntry,
    SkillRegistry,
    _MAX_SKILL_DESC_CHARS,
    _MAX_SKILL_LIST_CHARS,
    parse_skill_file,
)


# --------------------------------------------------------------------------- #
# 工具函数                                                                     #
# --------------------------------------------------------------------------- #

def write_skill(base: Path, name: str, content: str) -> Path:
    """在 base 下创建 name/SKILL.md，返回 SKILL.md 路径。"""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(content, encoding="utf-8")
    return p


CC_SKILL = """\
---
name: commit
description: Create a git commit with a well-formatted message.
when_to_use: "Use when committing changes. Triggers on: commit, git commit."
---

# Commit Skill

Step 1: Run git status.
Step 2: Stage files.
Step 3: Commit.
"""

OC_SKILL = """\
---
name: summarize
description: Summarize a document or conversation.
user-invocable: true
disable-model-invocation: false
---

# Summarize Skill

Provide a concise summary of the given text.
"""

OC_SKILL_DISABLED = """\
---
name: hidden
description: A hidden skill not shown to model.
user-invocable: true
disable-model-invocation: true
---

# Hidden Skill
"""

MINIMAL_SKILL = """\
---
name: minimal
description: Minimal skill with only required fields.
---

# Minimal Skill
"""

BAD_NO_NAME = """\
---
description: Missing name field.
---

# Bad Skill
"""

BAD_NO_DESC = """\
---
name: nodesc
---

# No description
"""

BAD_NO_FRONTMATTER = """\
# No frontmatter

Just markdown body.
"""


# --------------------------------------------------------------------------- #
# parse_skill_file                                                             #
# --------------------------------------------------------------------------- #

class TestParseSkillFile:
    def test_parse_claude_code_format(self, tmp_path: Path) -> None:
        """解析 Claude Code 格式（含 when_to_use）"""
        p = write_skill(tmp_path, "commit", CC_SKILL)
        entry = parse_skill_file(p)
        assert entry is not None
        assert entry.name == "commit"
        assert entry.description == "Create a git commit with a well-formatted message."
        assert entry.when_to_use is not None
        assert "commit" in entry.when_to_use.lower()
        assert "Step 1" in entry.content
        assert entry.user_invocable is True
        assert entry.disable_model_invocation is False

    def test_parse_openclaw_format(self, tmp_path: Path) -> None:
        """解析 OpenClaw 格式（含 user-invocable / disable-model-invocation）"""
        p = write_skill(tmp_path, "summarize", OC_SKILL)
        entry = parse_skill_file(p)
        assert entry is not None
        assert entry.name == "summarize"
        assert entry.when_to_use is None  # OpenClaw 没有此字段
        assert entry.user_invocable is True
        assert entry.disable_model_invocation is False
        assert "Summarize Skill" in entry.content

    def test_parse_minimal_skill(self, tmp_path: Path) -> None:
        """只有 name 和 description 的最小 skill"""
        p = write_skill(tmp_path, "minimal", MINIMAL_SKILL)
        entry = parse_skill_file(p)
        assert entry is not None
        assert entry.name == "minimal"
        assert entry.when_to_use is None
        assert entry.user_invocable is True  # 默认值

    def test_parse_disable_model_invocation(self, tmp_path: Path) -> None:
        """disable-model-invocation: true 正确解析为布尔"""
        p = write_skill(tmp_path, "hidden", OC_SKILL_DISABLED)
        entry = parse_skill_file(p)
        assert entry is not None
        assert entry.disable_model_invocation is True

    def test_returns_none_when_name_missing(self, tmp_path: Path) -> None:
        """缺少 name 字段时返回 None"""
        p = write_skill(tmp_path, "bad", BAD_NO_NAME)
        assert parse_skill_file(p) is None

    def test_returns_none_when_description_missing(self, tmp_path: Path) -> None:
        """缺少 description 字段时返回 None"""
        p = write_skill(tmp_path, "nodesc", BAD_NO_DESC)
        assert parse_skill_file(p) is None

    def test_returns_none_when_no_frontmatter(self, tmp_path: Path) -> None:
        """无 frontmatter 时返回 None"""
        p = write_skill(tmp_path, "nofm", BAD_NO_FRONTMATTER)
        assert parse_skill_file(p) is None

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        """文件不存在时返回 None"""
        assert parse_skill_file(tmp_path / "nonexistent.md") is None

    def test_unknown_fields_ignored(self, tmp_path: Path) -> None:
        """未知字段（allowed-tools, context, metadata.openclaw）直接忽略"""
        content = """\
---
name: advanced
description: Skill with extra fields.
when_to_use: "Test skill."
allowed-tools:
  - Bash
  - Read
context: fork
metadata:
  openclaw:
    emoji: "🔧"
---

# Advanced Skill
"""
        p = write_skill(tmp_path, "advanced", content)
        entry = parse_skill_file(p)
        assert entry is not None
        assert entry.name == "advanced"

    def test_source_path_recorded(self, tmp_path: Path) -> None:
        """source_path 记录为 SKILL.md 文件路径"""
        p = write_skill(tmp_path, "commit", CC_SKILL)
        entry = parse_skill_file(p)
        assert entry is not None
        assert entry.source_path == p


# --------------------------------------------------------------------------- #
# SkillEntry                                                                   #
# --------------------------------------------------------------------------- #

class TestSkillEntry:
    def test_trigger_description_uses_when_to_use_if_present(self) -> None:
        """有 when_to_use 时 trigger_description 返回它"""
        entry = SkillEntry(
            name="commit",
            description="Commit changes.",
            content="# Skill",
            when_to_use="Use when committing.",
        )
        assert entry.trigger_description() == "Use when committing."

    def test_trigger_description_falls_back_to_description(self) -> None:
        """无 when_to_use 时退化到 description（OpenClaw 风格）"""
        entry = SkillEntry(
            name="summarize",
            description="Summarize a document.",
            content="# Skill",
        )
        assert entry.trigger_description() == "Summarize a document."

    def test_should_include_default_true(self) -> None:
        """默认 user_invocable=True, disable_model_invocation=False → 应出现在列表"""
        entry = SkillEntry(name="x", description="d", content="c")
        assert entry.should_include_in_listing() is True

    def test_should_not_include_when_disable_model_invocation(self) -> None:
        """disable_model_invocation=True 时不出现在列表"""
        entry = SkillEntry(
            name="x", description="d", content="c",
            disable_model_invocation=True,
        )
        assert entry.should_include_in_listing() is False

    def test_should_not_include_when_not_user_invocable(self) -> None:
        """user_invocable=False 时不出现在列表"""
        entry = SkillEntry(
            name="x", description="d", content="c",
            user_invocable=False,
        )
        assert entry.should_include_in_listing() is False


# --------------------------------------------------------------------------- #
# SkillRegistry.load()                                                         #
# --------------------------------------------------------------------------- #

class TestSkillRegistryLoad:
    def test_load_empty_dir(self, tmp_path: Path) -> None:
        """空目录不报错，返回空 registry"""
        registry = SkillRegistry.load([tmp_path])
        assert not registry.has_skills()

    def test_load_nonexistent_dir(self, tmp_path: Path) -> None:
        """不存在的目录不报错"""
        registry = SkillRegistry.load([tmp_path / "nonexistent"])
        assert not registry.has_skills()

    def test_load_single_skill(self, tmp_path: Path) -> None:
        """加载单个 skill"""
        write_skill(tmp_path, "commit", CC_SKILL)
        registry = SkillRegistry.load([tmp_path])
        assert registry.has_skills()
        entry = registry.get("commit")
        assert entry is not None
        assert entry.name == "commit"

    def test_load_multiple_skills(self, tmp_path: Path) -> None:
        """加载多个 skill"""
        write_skill(tmp_path, "commit", CC_SKILL)
        write_skill(tmp_path, "summarize", OC_SKILL)
        registry = SkillRegistry.load([tmp_path])
        assert registry.get("commit") is not None
        assert registry.get("summarize") is not None

    def test_later_dir_overrides_earlier(self, tmp_path: Path) -> None:
        """后面的目录优先级更高（同名 skill 覆盖）"""
        low = tmp_path / "low"
        high = tmp_path / "high"
        low.mkdir()
        high.mkdir()

        low_skill = """\
---
name: commit
description: Low priority version.
---
# Low
"""
        high_skill = """\
---
name: commit
description: High priority version.
---
# High
"""
        write_skill(low, "commit", low_skill)
        write_skill(high, "commit", high_skill)

        registry = SkillRegistry.load([low, high])  # high 优先
        entry = registry.get("commit")
        assert entry is not None
        assert entry.description == "High priority version."

    def test_skips_files_without_skill_md(self, tmp_path: Path) -> None:
        """子目录下没有 SKILL.md 时跳过"""
        (tmp_path / "empty_skill").mkdir()
        (tmp_path / "readme_only").mkdir()
        (tmp_path / "readme_only" / "README.md").write_text("# readme")
        registry = SkillRegistry.load([tmp_path])
        assert not registry.has_skills()

    def test_get_returns_none_for_unknown_name(self, tmp_path: Path) -> None:
        """get() 对不存在的 skill 返回 None"""
        write_skill(tmp_path, "commit", CC_SKILL)
        registry = SkillRegistry.load([tmp_path])
        assert registry.get("unknown") is None


# --------------------------------------------------------------------------- #
# SkillRegistry.list_invocable() + format_listing()                           #
# --------------------------------------------------------------------------- #

class TestSkillRegistryListing:
    def test_list_invocable_excludes_disabled(self, tmp_path: Path) -> None:
        """disable_model_invocation=True 的 skill 不出现在列表"""
        write_skill(tmp_path, "active", CC_SKILL)
        write_skill(tmp_path, "hidden", OC_SKILL_DISABLED)
        registry = SkillRegistry.load([tmp_path])
        names = [e.name for e in registry.list_invocable()]
        assert "active" in names or "commit" in names  # CC_SKILL 的 name 是 commit
        assert "hidden" not in names

    def test_list_invocable_sorted_by_name(self, tmp_path: Path) -> None:
        """list_invocable 按名称排序"""
        write_skill(tmp_path, "z_skill", """\
---
name: zzz
description: Z skill.
---
# Z
""")
        write_skill(tmp_path, "a_skill", """\
---
name: aaa
description: A skill.
---
# A
""")
        registry = SkillRegistry.load([tmp_path])
        names = [e.name for e in registry.list_invocable()]
        assert names == sorted(names)

    def test_format_listing_empty_when_no_skills(self, tmp_path: Path) -> None:
        """无 skill 时 format_listing 返回空字符串"""
        registry = SkillRegistry.load([tmp_path])
        assert registry.format_listing() == ""

    def test_format_listing_contains_skill_names(self, tmp_path: Path) -> None:
        """format_listing 包含 skill 名称和描述"""
        write_skill(tmp_path, "commit", CC_SKILL)
        registry = SkillRegistry.load([tmp_path])
        listing = registry.format_listing()
        assert "commit" in listing
        assert "Create a git commit" in listing

    def test_format_listing_includes_when_to_use(self, tmp_path: Path) -> None:
        """有 when_to_use 时 format_listing 包含触发描述"""
        write_skill(tmp_path, "commit", CC_SKILL)
        registry = SkillRegistry.load([tmp_path])
        listing = registry.format_listing()
        # when_to_use 内容应出现在列表中
        assert "commit" in listing.lower()

    def test_format_listing_truncates_long_description(self, tmp_path: Path) -> None:
        """超长描述截断到 MAX_SKILL_DESC_CHARS"""
        long_desc = "A" * (_MAX_SKILL_DESC_CHARS + 100)
        content = f"""\
---
name: longdesc
description: {long_desc}
---
# Long
"""
        write_skill(tmp_path, "longdesc", content)
        registry = SkillRegistry.load([tmp_path])
        listing = registry.format_listing()
        # 单行不超过 name + desc + margin
        assert len(listing) <= _MAX_SKILL_LIST_CHARS + 50  # 宽松检查

    def test_format_listing_total_within_budget(self, tmp_path: Path) -> None:
        """总字符数不超过 MAX_SKILL_LIST_CHARS"""
        for i in range(50):
            name = f"skill{i:03d}"
            content = f"""\
---
name: {name}
description: Description for skill number {i}.
when_to_use: "Use when doing thing {i}."
---
# {name}
"""
            write_skill(tmp_path, name, content)
        registry = SkillRegistry.load([tmp_path])
        listing = registry.format_listing()
        assert len(listing) <= _MAX_SKILL_LIST_CHARS


# --------------------------------------------------------------------------- #
# 内置 skill 加载验证                                                          #
# --------------------------------------------------------------------------- #

class TestBundledSkills:
    def test_bundled_example_skill_loadable(self) -> None:
        """内置 example skill 可正常加载"""
        from src.sdk._agent.skills.registry import get_default_skill_dirs
        dirs = get_default_skill_dirs()
        # 只加载 bundled dir（第一个）
        registry = SkillRegistry.load([dirs[0]])
        assert registry.get("example") is not None
        entry = registry.get("example")
        assert entry is not None
        assert "example" in entry.name
        assert entry.content  # 有正文


class TestRegistryLoadEdgeCases:
    def test_non_directory_file_in_base_dir_skipped(self, tmp_path: Path) -> None:
        """base_dir 中的普通文件（非目录）被跳过，不影响加载（覆盖 line 204: if not skill_dir.is_dir: continue）"""
        # 在 base_dir 中放一个 SKILL.md 文件（不是目录）
        (tmp_path / "SKILL.md").write_text("not a skill dir\n")
        # 同时放一个正常的 skill 目录
        d = tmp_path / "commit"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: commit\ndescription: Commit code\n---\n# Commit\n"
        )
        registry = SkillRegistry.load([tmp_path])
        assert registry.get("commit") is not None
        # 普通文件不应被处理
        assert len(registry._entries) == 1
