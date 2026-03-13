"""真实 SKILL.md 兼容性测试

使用本地克隆的 OpenClaw 和 ralph-marketplace 中的真实 SKILL.md 文件，
验证 parse_skill_file() 的解析兼容性。

若 SKILL.md 路径不存在（CI 环境），自动跳过对应测试组。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_sdk._agent.skills.registry import SkillEntry, parse_skill_file

# --------------------------------------------------------------------------- #
# 真实 skills 路径
# --------------------------------------------------------------------------- #

# OpenClaw: /mnt/e/Documents/github/openclaw/skills/<skill_name>/SKILL.md
_OPENCLAW_SKILLS_DIR = Path("/mnt/e/Documents/github/openclaw/skills")

# ralph-marketplace: ~/.claude/plugins/cache/ralph-marketplace/ralph-skills/1.0.0/skills/
_RALPH_SKILLS_DIR = (
    Path.home()
    / ".claude/plugins/cache/ralph-marketplace/ralph-skills/1.0.0/skills"
)

# 无 frontmatter 的已知文件（解析返回 None 是预期行为）
_EXPECTED_NO_FRONTMATTER = {"canvas"}


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #

def _collect_skill_files(base_dir: Path) -> list[Path]:
    """收集 base_dir 下所有 <skill_name>/SKILL.md 文件。"""
    if not base_dir.is_dir():
        return []
    return sorted(
        p
        for skill_dir in base_dir.iterdir()
        if skill_dir.is_dir()
        for p in [skill_dir / "SKILL.md"]
        if p.exists()
    )


# --------------------------------------------------------------------------- #
# OpenClaw 兼容性测试
# --------------------------------------------------------------------------- #

class TestOpenClawCompatibility:
    """OpenClaw 格式 SKILL.md 解析兼容性。"""

    @pytest.fixture(autouse=True)
    def require_openclaw(self) -> None:
        if not _OPENCLAW_SKILLS_DIR.is_dir():
            pytest.skip(f"OpenClaw skills dir not found: {_OPENCLAW_SKILLS_DIR}")

    def test_majority_skills_parse_successfully(self) -> None:
        """超过 90% 的 OpenClaw skills 能成功解析。"""
        files = _collect_skill_files(_OPENCLAW_SKILLS_DIR)
        assert len(files) >= 10, "测试需要至少 10 个 skill 文件"

        parsed = [parse_skill_file(f) for f in files]
        success = [e for e in parsed if e is not None]
        fail = [f for f, e in zip(files, parsed) if e is None]

        # 排除已知无 frontmatter 文件
        unexpected_fail = [
            f for f in fail if f.parent.name not in _EXPECTED_NO_FRONTMATTER
        ]

        assert not unexpected_fail, (
            f"以下 skills 解析失败（非预期）：\n"
            + "\n".join(f"  {f.parent.name}" for f in unexpected_fail)
        )
        success_rate = len(success) / len(files)
        assert success_rate >= 0.9, f"解析成功率 {success_rate:.0%} 低于 90%"

    def test_parsed_entries_have_required_fields(self) -> None:
        """每个成功解析的 SkillEntry 都有非空 name 和 description。"""
        files = _collect_skill_files(_OPENCLAW_SKILLS_DIR)
        for f in files:
            if f.parent.name in _EXPECTED_NO_FRONTMATTER:
                continue
            entry = parse_skill_file(f)
            if entry is None:
                continue
            assert entry.name, f"{f.parent.name}: name 为空"
            assert entry.description, f"{f.parent.name}: description 为空"

    def test_specific_skills_parse_correctly(self) -> None:
        """几个具体 skill 的字段值与文件内容一致。"""
        cases = [
            (
                "1password",
                "Set up and use 1Password CLI (op)",
            ),
            (
                "github",
                "GitHub operations via",
            ),
            (
                "gemini",
                "Gemini CLI",
            ),
        ]
        for skill_name, expected_desc_prefix in cases:
            skill_file = _OPENCLAW_SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_file.exists():
                continue
            entry = parse_skill_file(skill_file)
            assert entry is not None, f"{skill_name} 应成功解析"
            assert entry.name == skill_name, f"{skill_name}: name 不匹配"
            assert expected_desc_prefix in entry.description, (
                f"{skill_name}: description 中不含 '{expected_desc_prefix}'，"
                f"实际：{entry.description[:80]}"
            )

    def test_metadata_block_ignored_correctly(self) -> None:
        """包含 JSON metadata 块的 skill 能正确解析（缩进行被忽略）。"""
        # clawhub 包含复杂的 metadata JSON 块
        clawhub_file = _OPENCLAW_SKILLS_DIR / "clawhub" / "SKILL.md"
        if not clawhub_file.exists():
            pytest.skip("clawhub SKILL.md 不存在")
        entry = parse_skill_file(clawhub_file)
        assert entry is not None
        assert entry.name == "clawhub"
        # content 应包含 body（ClawHub CLI 操作命令），而不是 JSON
        assert "clawhub" in entry.content.lower()

    def test_user_invocable_defaults_to_true(self) -> None:
        """OpenClaw skills 未设置 user-invocable 时默认 True。"""
        # 大多数 OpenClaw skills 没有 user-invocable 字段，应默认 True
        files = _collect_skill_files(_OPENCLAW_SKILLS_DIR)
        for f in files:
            if f.parent.name in _EXPECTED_NO_FRONTMATTER:
                continue
            entry = parse_skill_file(f)
            if entry is None:
                continue
            # 默认应为 True（除非文件中显式设置了 false）
            raw = f.read_text()
            has_explicit_false = "user-invocable: false" in raw.lower()
            if not has_explicit_false:
                assert entry.user_invocable is True, (
                    f"{f.parent.name}: user_invocable 应默认 True"
                )

    def test_no_when_to_use_falls_back_to_description(self) -> None:
        """OpenClaw skills 无 when_to_use，trigger_description() 应退化到 description。"""
        files = _collect_skill_files(_OPENCLAW_SKILLS_DIR)
        for f in files:
            if f.parent.name in _EXPECTED_NO_FRONTMATTER:
                continue
            entry = parse_skill_file(f)
            if entry is None:
                continue
            if entry.when_to_use is None:
                assert entry.trigger_description() == entry.description


    def test_content_not_empty(self) -> None:
        """body（非 frontmatter 部分）不为空。"""
        files = _collect_skill_files(_OPENCLAW_SKILLS_DIR)
        for f in files:
            if f.parent.name in _EXPECTED_NO_FRONTMATTER:
                continue
            entry = parse_skill_file(f)
            if entry is None:
                continue
            assert entry.content.strip(), f"{f.parent.name}: content 为空"

    def test_source_path_is_set(self) -> None:
        """source_path 字段正确指向文件路径。"""
        files = _collect_skill_files(_OPENCLAW_SKILLS_DIR)
        for f in files[:5]:  # 检查前 5 个
            if f.parent.name in _EXPECTED_NO_FRONTMATTER:
                continue
            entry = parse_skill_file(f)
            if entry is None:
                continue
            assert entry.source_path == f


# --------------------------------------------------------------------------- #
# ralph-marketplace 兼容性测试（Claude Code 格式）
# --------------------------------------------------------------------------- #

class TestRalphSkillsCompatibility:
    """ralph-marketplace 格式 SKILL.md（含 user-invocable 字段）解析兼容性。"""

    @pytest.fixture(autouse=True)
    def require_ralph(self) -> None:
        if not _RALPH_SKILLS_DIR.is_dir():
            pytest.skip(f"ralph-skills dir not found: {_RALPH_SKILLS_DIR}")

    def test_prd_skill_parses_correctly(self) -> None:
        """prd skill 正确解析（name、description、user-invocable）。"""
        prd_file = _RALPH_SKILLS_DIR / "prd" / "SKILL.md"
        if not prd_file.exists():
            pytest.skip("prd SKILL.md 不存在")
        entry = parse_skill_file(prd_file)
        assert entry is not None
        assert entry.name == "prd"
        assert "PRD" in entry.description or "Product Requirements" in entry.description
        assert entry.user_invocable is True
        assert entry.should_include_in_listing() is True

    def test_ralph_skill_parses_correctly(self) -> None:
        """ralph skill 正确解析。"""
        ralph_file = _RALPH_SKILLS_DIR / "ralph" / "SKILL.md"
        if not ralph_file.exists():
            pytest.skip("ralph SKILL.md 不存在")
        entry = parse_skill_file(ralph_file)
        assert entry is not None
        assert entry.name == "ralph"
        assert entry.user_invocable is True

    def test_ralph_skills_all_parse(self) -> None:
        """ralph-skills 目录下所有 skills 均能成功解析。"""
        files = _collect_skill_files(_RALPH_SKILLS_DIR)
        if not files:
            pytest.skip("无 ralph-skills 文件")
        for f in files:
            entry = parse_skill_file(f)
            assert entry is not None, f"ralph skill {f.parent.name} 解析失败"
            assert entry.name
            assert entry.description

    def test_ralph_skill_content_is_rich(self) -> None:
        """ralph skill 的 body content 包含真实指令内容。"""
        prd_file = _RALPH_SKILLS_DIR / "prd" / "SKILL.md"
        if not prd_file.exists():
            pytest.skip("prd SKILL.md 不存在")
        entry = parse_skill_file(prd_file)
        assert entry is not None
        # PRD skill 应包含结构性内容
        assert len(entry.content) > 100
        assert "##" in entry.content or "#" in entry.content  # 有标题

    def test_user_invocable_field_respected(self) -> None:
        """user-invocable: true 字段被正确解析为 user_invocable=True。"""
        ralph_file = _RALPH_SKILLS_DIR / "ralph" / "SKILL.md"
        if not ralph_file.exists():
            pytest.skip("ralph SKILL.md 不存在")
        entry = parse_skill_file(ralph_file)
        assert entry is not None
        assert entry.user_invocable is True
        assert entry.disable_model_invocation is False


# --------------------------------------------------------------------------- #
# 跨格式对比测试
# --------------------------------------------------------------------------- #

class TestCrossFormatCompatibility:
    """对比 OpenClaw 和 ralph-marketplace 格式，验证统一解析接口。"""

    @pytest.fixture(autouse=True)
    def require_both(self) -> None:
        if not _OPENCLAW_SKILLS_DIR.is_dir() or not _RALPH_SKILLS_DIR.is_dir():
            pytest.skip("需要 OpenClaw 和 ralph-skills 两个目录")

    def test_both_formats_produce_valid_entries(self) -> None:
        """两种格式均能产生有效的 SkillEntry，接口一致。"""
        # OpenClaw sample
        github_file = _OPENCLAW_SKILLS_DIR / "github" / "SKILL.md"
        # ralph sample
        prd_file = _RALPH_SKILLS_DIR / "prd" / "SKILL.md"

        entries: list[SkillEntry] = []
        for f in [github_file, prd_file]:
            if f.exists():
                e = parse_skill_file(f)
                if e:
                    entries.append(e)

        assert len(entries) >= 1, "至少应有一个格式解析成功"
        for entry in entries:
            # 共同接口验证
            assert isinstance(entry.name, str) and entry.name
            assert isinstance(entry.description, str) and entry.description
            assert isinstance(entry.content, str) and entry.content
            assert isinstance(entry.user_invocable, bool)
            assert isinstance(entry.disable_model_invocation, bool)
            # trigger_description 应总是返回非空字符串
            assert entry.trigger_description()
            # should_include_in_listing 应总是返回 bool
            result = entry.should_include_in_listing()
            assert isinstance(result, bool)

    def test_load_from_real_directories_with_registry(self) -> None:
        """用 SkillRegistry.load() 加载真实目录，验证批量加载。"""
        from agent_sdk._agent.skills.registry import SkillRegistry
        dirs = []
        if _OPENCLAW_SKILLS_DIR.is_dir():
            dirs.append(_OPENCLAW_SKILLS_DIR)
        if _RALPH_SKILLS_DIR.is_dir():
            dirs.append(_RALPH_SKILLS_DIR)

        registry = SkillRegistry.load(dirs)
        assert registry.has_skills()
        assert len(registry.list_invocable()) >= 5

        # format_listing 不应崩溃，结果在字符预算内
        listing = registry.format_listing()
        assert isinstance(listing, str)
        assert len(listing) <= 4100  # 允许轻微超出（最后一行完整性）
