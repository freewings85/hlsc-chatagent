"""Skill 解析器红蓝对抗测试

红队：设计边缘情况 SKILL.md 输入（格式异常、边界值、恶意输入）
蓝队：验证解析器能正确处理（成功解析或安全失败）

每个测试用例包含：
  - 红队攻击：异常 SKILL.md 内容
  - 预期结果：成功解析（并验证字段值）或 None（解析失败）
  - 防御理由：为什么这个行为是正确的

覆盖的攻击类别：
  1. 格式异常：CRLF 行尾、空值、缺少必填字段
  2. 注入攻击：description 中含 frontmatter 标记、多余 `---`
  3. 编码边界：Unicode、emoji、超长字符串
  4. 引号边界：嵌套引号、不匹配引号
  5. 值类型边界：布尔大小写、整数值、空白值
  6. 结构异常：重复 key、只有 frontmatter 无 body、frontmatter 在末尾
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.sdk._agent.skills.registry import SkillEntry, _parse_frontmatter_line, parse_skill_file


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

def write_skill(tmp_path: Path, content: str, filename: str = "SKILL.md") -> Path:
    """写 SKILL.md 到临时目录（直接文件，不建子目录），返回路径。"""
    p = tmp_path / filename
    p.write_bytes(content.encode("utf-8"))
    return p


@dataclass
class RedBlueCase:
    """一个红蓝对抗测试用例。"""
    name: str
    content: str
    expect_parse_success: bool
    expected_name: str | None = None
    expected_description_contains: str | None = None
    expected_content_contains: str | None = None
    expected_user_invocable: bool | None = None
    defense_rationale: str = ""


# --------------------------------------------------------------------------- #
# 红队攻击用例定义
# --------------------------------------------------------------------------- #

RED_BLUE_CASES: list[RedBlueCase] = [
    # ── 1. 格式异常 ────────────────────────────────────────────────────────
    RedBlueCase(
        name="crlf_line_endings",
        content="---\r\nname: commit\r\ndescription: Commit code\r\n---\r\n# Body\r\n",
        expect_parse_success=True,
        expected_name="commit",
        expected_description_contains="Commit code",
        defense_rationale="CRLF 行尾常见于 Windows 编辑的 SKILL.md，应正常解析",
    ),
    RedBlueCase(
        name="missing_name_field",
        content="---\ndescription: A skill without name\n---\n# Body\n",
        expect_parse_success=False,
        defense_rationale="name 是必填字段，缺少时应返回 None",
    ),
    RedBlueCase(
        name="missing_description_field",
        content="---\nname: commit\n---\n# Body\n",
        expect_parse_success=False,
        defense_rationale="description 是必填字段，缺少时应返回 None",
    ),
    RedBlueCase(
        name="empty_name_value",
        content="---\nname: \ndescription: A skill\n---\n# Body\n",
        expect_parse_success=False,
        defense_rationale="name 为空字符串时应返回 None（等效于缺少）",
    ),
    RedBlueCase(
        name="empty_description_value",
        content="---\nname: commit\ndescription: \n---\n# Body\n",
        expect_parse_success=False,
        defense_rationale="description 为空字符串时应返回 None",
    ),
    RedBlueCase(
        name="no_frontmatter",
        content="# Just Markdown\n\nNo frontmatter here.\n",
        expect_parse_success=False,
        defense_rationale="无 frontmatter 时应返回 None",
    ),
    RedBlueCase(
        name="unclosed_frontmatter",
        content="---\nname: commit\ndescription: A skill\n",  # 没有结束 ---
        expect_parse_success=False,
        defense_rationale="frontmatter 未关闭时应返回 None",
    ),
    RedBlueCase(
        name="only_frontmatter_no_body",
        content="---\nname: commit\ndescription: A skill\n---\n",
        expect_parse_success=True,
        expected_name="commit",
        expected_content_contains="",  # body 为空，但解析应成功
        defense_rationale="只有 frontmatter 无 body 也是有效的 SKILL.md",
    ),
    # ── 2. 注入攻击 ─────────────────────────────────────────────────────────
    RedBlueCase(
        name="frontmatter_marker_in_description",
        content="---\nname: attack\ndescription: '---\\nname: injected\\n---'\n---\n# Body\n",
        expect_parse_success=True,
        expected_name="attack",
        defense_rationale="description 中的 '---' 不应被当作 frontmatter 标记",
    ),
    RedBlueCase(
        name="extra_frontmatter_in_body",
        content=(
            "---\n"
            "name: commit\n"
            "description: Commit code\n"
            "---\n"
            "# Body\n\n"
            "---\n"
            "name: injected\n"
            "---\n"
            "Injected body.\n"
        ),
        expect_parse_success=True,
        expected_name="commit",
        expected_description_contains="Commit code",
        defense_rationale="body 中的 --- 分隔符不应影响已解析的 frontmatter",
    ),
    # ── 3. 编码边界 ─────────────────────────────────────────────────────────
    RedBlueCase(
        name="unicode_description",
        content="---\nname: 提交\ndescription: 使用 git 提交代码，支持中文工作流\n---\n# 提交指南\n",
        expect_parse_success=True,
        expected_name="提交",
        expected_description_contains="中文",
        defense_rationale="Unicode name 和 description 应正确解析",
    ),
    RedBlueCase(
        name="emoji_in_description",
        content="---\nname: deploy\ndescription: 🚀 Deploy to production\n---\n# Deploy\n",
        expect_parse_success=True,
        expected_name="deploy",
        expected_description_contains="🚀",
        defense_rationale="description 中的 emoji 应保留",
    ),
    RedBlueCase(
        name="very_long_description",
        content=(
            "---\nname: commit\ndescription: " + "A" * 500 + "\n---\n# Body\n"
        ),
        expect_parse_success=True,
        expected_name="commit",
        defense_rationale="超长 description 应原样保存（截断由 format_listing 负责，不由 parser 负责）",
    ),
    # ── 4. 引号边界 ─────────────────────────────────────────────────────────
    RedBlueCase(
        name="double_quoted_description_with_colon",
        content=(
            '---\nname: github\n'
            'description: "GitHub ops via `gh` CLI: issues, PRs, CI runs"\n'
            "---\n# GitHub\n"
        ),
        expect_parse_success=True,
        expected_name="github",
        expected_description_contains="issues",
        defense_rationale="双引号中含冒号时，partition(':') 后正确去引号",
    ),
    RedBlueCase(
        name="single_quoted_description",
        content=(
            "---\nname: commit\n"
            "description: 'Commit changes with optional args'\n"
            "---\n# Commit\n"
        ),
        expect_parse_success=True,
        expected_name="commit",
        expected_description_contains="Commit changes",
        defense_rationale="单引号 description 应正确去引号",
    ),
    RedBlueCase(
        name="nested_single_quotes_in_double",
        content=(
            '---\nname: commit\n'
            "description: \"Use 'git commit' to commit\"\n"
            "---\n# Commit\n"
        ),
        expect_parse_success=True,
        expected_name="commit",
        expected_description_contains="git commit",
        defense_rationale="双引号内的单引号应保留",
    ),
    RedBlueCase(
        name="unmatched_quote_in_description",
        content=(
            '---\nname: commit\n'
            "description: \"Start but no end\n"
            "---\n# Commit\n"
        ),
        expect_parse_success=True,
        expected_name="commit",
        expected_description_contains="Start but no end",
        defense_rationale="不匹配引号时，原始字符串（含引号）被用作 description",
    ),
    # ── 5. 值类型边界 ────────────────────────────────────────────────────────
    RedBlueCase(
        name="boolean_true_lowercase",
        content="---\nname: commit\ndescription: A skill\nuser-invocable: true\n---\n# Body\n",
        expect_parse_success=True,
        expected_user_invocable=True,
        defense_rationale="'true'（小写）应解析为布尔 True",
    ),
    RedBlueCase(
        name="boolean_true_uppercase",
        content="---\nname: commit\ndescription: A skill\nuser-invocable: True\n---\n# Body\n",
        expect_parse_success=True,
        expected_user_invocable=True,
        defense_rationale="'True'（首字母大写）也应解析为布尔 True（case-insensitive）",
    ),
    RedBlueCase(
        name="boolean_false",
        content=(
            "---\nname: internal\ndescription: Internal skill\n"
            "user-invocable: false\ndisable-model-invocation: true\n---\n# Internal\n"
        ),
        expect_parse_success=True,
        expected_user_invocable=False,
        defense_rationale="'false' 应解析为布尔 False，skill 不出现在 listing 中",
    ),
    RedBlueCase(
        name="name_with_trailing_whitespace",
        content="---\nname: commit   \ndescription: A skill\n---\n# Body\n",
        expect_parse_success=True,
        expected_name="commit",
        defense_rationale="name 的尾部空白应被 strip()",
    ),
    RedBlueCase(
        name="description_with_trailing_whitespace",
        content="---\nname: commit\ndescription: A skill   \n---\n# Body\n",
        expect_parse_success=True,
        expected_description_contains="A skill",
        defense_rationale="description 尾部空白应被 strip()",
    ),
    # ── 6. 结构异常 ──────────────────────────────────────────────────────────
    RedBlueCase(
        name="duplicate_name_key",
        content=(
            "---\nname: first\nname: second\ndescription: A skill\n---\n# Body\n"
        ),
        expect_parse_success=True,
        expected_name="second",
        defense_rationale="重复 key 时，后出现的覆盖前出现的（dict 行为）",
    ),
    RedBlueCase(
        name="indented_key_ignored",
        content=(
            "---\nname: commit\ndescription: A skill\n"
            "  nested_key: should_be_ignored\n"
            "---\n# Body\n"
        ),
        expect_parse_success=True,
        expected_name="commit",
        defense_rationale="缩进的 key（嵌套块）应被忽略，不影响解析",
    ),
    RedBlueCase(
        name="comment_in_frontmatter",
        content=(
            "---\n# This is a comment\nname: commit\ndescription: A skill\n---\n# Body\n"
        ),
        expect_parse_success=True,
        expected_name="commit",
        defense_rationale="frontmatter 中以 # 开头的注释行应被忽略",
    ),
    RedBlueCase(
        name="frontmatter_at_end_not_beginning",
        content="# No frontmatter here\n---\nname: commit\ndescription: A skill\n---\n",
        expect_parse_success=False,
        defense_rationale="frontmatter 不在文件开头时应返回 None（regex 需要 ^ 匹配）",
    ),
    RedBlueCase(
        name="openclaw_complex_metadata_json",
        content=(
            "---\n"
            "name: 1password\n"
            'description: Use 1Password CLI for secrets management\n'
            "metadata:\n"
            '  {\n'
            '    "openclaw": {\n'
            '      "emoji": "🔐",\n'
            '      "requires": { "bins": ["op"] }\n'
            '    }\n'
            "  }\n"
            "---\n"
            "# 1Password CLI\n"
            "Run `op signin` to authenticate.\n"
        ),
        expect_parse_success=True,
        expected_name="1password",
        expected_description_contains="secrets",
        expected_content_contains="1Password",
        defense_rationale="OpenClaw 的多行 JSON metadata 块（缩进行）应被忽略，不影响解析",
    ),
    RedBlueCase(
        name="key_without_colon",
        content=(
            "---\nname commit\ndescription: A skill\n---\n# Body\n"
        ),
        expect_parse_success=False,
        defense_rationale="无冒号的 name 行被忽略，name 字段缺失，返回 None",
    ),
    RedBlueCase(
        name="empty_file",
        content="",
        expect_parse_success=False,
        defense_rationale="空文件应返回 None",
    ),
    RedBlueCase(
        name="only_whitespace",
        content="   \n  \n  ",
        expect_parse_success=False,
        defense_rationale="只有空白的文件应返回 None",
    ),
]


# --------------------------------------------------------------------------- #
# 参数化测试
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "case",
    RED_BLUE_CASES,
    ids=[c.name for c in RED_BLUE_CASES],
)
def test_red_team_skill_parse(case: RedBlueCase, tmp_path: Path) -> None:
    """红蓝对抗：每个边缘情况的解析结果符合预期。"""
    skill_file = write_skill(tmp_path, case.content)
    entry = parse_skill_file(skill_file)

    if case.expect_parse_success:
        assert entry is not None, (
            f"[{case.name}] 应成功解析，但返回 None。\n"
            f"防御理由：{case.defense_rationale}\n"
            f"内容：{case.content[:200]}"
        )
        if case.expected_name is not None:
            assert entry.name == case.expected_name, (
                f"[{case.name}] name 期望 {case.expected_name!r}，实际 {entry.name!r}"
            )
        if case.expected_description_contains is not None:
            assert case.expected_description_contains in entry.description, (
                f"[{case.name}] description 应含 {case.expected_description_contains!r}，"
                f"实际：{entry.description!r}"
            )
        if case.expected_content_contains is not None and case.expected_content_contains:
            assert case.expected_content_contains in entry.content, (
                f"[{case.name}] content 应含 {case.expected_content_contains!r}"
            )
        if case.expected_user_invocable is not None:
            assert entry.user_invocable == case.expected_user_invocable, (
                f"[{case.name}] user_invocable 期望 {case.expected_user_invocable}，"
                f"实际 {entry.user_invocable}"
            )
    else:
        assert entry is None, (
            f"[{case.name}] 应返回 None，但返回了 {entry}。\n"
            f"防御理由：{case.defense_rationale}"
        )


# --------------------------------------------------------------------------- #
# _parse_frontmatter_line 单元红队
# --------------------------------------------------------------------------- #

class TestParseFrontmatterLineRedTeam:
    """直接对 _parse_frontmatter_line 进行红队测试（内部函数）。"""

    def test_empty_line_returns_none(self) -> None:
        assert _parse_frontmatter_line("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _parse_frontmatter_line("   ") is None

    def test_comment_returns_none(self) -> None:
        assert _parse_frontmatter_line("# comment") is None

    def test_indented_line_returns_none(self) -> None:
        assert _parse_frontmatter_line("  nested: value") is None

    def test_tab_indented_line_returns_none(self) -> None:
        assert _parse_frontmatter_line("\tnested: value") is None

    def test_no_colon_returns_none(self) -> None:
        assert _parse_frontmatter_line("just text") is None

    def test_simple_key_value(self) -> None:
        result = _parse_frontmatter_line("name: commit")
        assert result == ("name", "commit")

    def test_double_quoted_value(self) -> None:
        result = _parse_frontmatter_line('description: "GitHub ops: issues"')
        assert result is not None
        key, val = result
        assert key == "description"
        assert val == "GitHub ops: issues"

    def test_single_quoted_value(self) -> None:
        result = _parse_frontmatter_line("description: 'single quoted'")
        assert result is not None
        _, val = result
        assert val == "single quoted"

    def test_boolean_true_lowercase(self) -> None:
        result = _parse_frontmatter_line("user-invocable: true")
        assert result == ("user-invocable", True)

    def test_boolean_true_uppercase(self) -> None:
        result = _parse_frontmatter_line("user-invocable: True")
        assert result == ("user-invocable", True)

    def test_boolean_false(self) -> None:
        result = _parse_frontmatter_line("disable-model-invocation: false")
        assert result == ("disable-model-invocation", False)

    def test_value_with_multiple_colons(self) -> None:
        """多个冒号时，partition 只分割第一个，余下作为 value。"""
        result = _parse_frontmatter_line("description: a: b: c")
        assert result is not None
        _, val = result
        assert val == "a: b: c"

    def test_unicode_value(self) -> None:
        result = _parse_frontmatter_line("name: 提交")
        assert result == ("name", "提交")

    def test_value_with_trailing_spaces(self) -> None:
        result = _parse_frontmatter_line("name: commit   ")
        assert result is not None
        _, val = result
        assert val == "commit"

    def test_key_only_no_value(self) -> None:
        """'key:' 无值时，value 为空字符串。"""
        result = _parse_frontmatter_line("metadata:")
        assert result is not None
        key, val = result
        assert key == "metadata"
        assert val == ""


# --------------------------------------------------------------------------- #
# 安全边界：解析不应崩溃（fuzz-style）
# --------------------------------------------------------------------------- #

class TestParseSafety:
    """确保任何输入都不会导致解析器崩溃（异常必须 → None，而非 exception）。"""

    @pytest.mark.parametrize("content", [
        "\x00\x01\x02\x03",          # 控制字符
        "---\n\x00name: \x01\n---\n",  # frontmatter 中的控制字符
        "---\n" + "x" * 100_000 + "\n---\n",  # 超大 frontmatter
        "---\n---\n---\n---\n",       # 多余的 --- 分隔符
        b"\xff\xfe".decode("utf-8", errors="replace"),  # 替换后的无效字节
    ])
    def test_parse_does_not_crash(self, content: str, tmp_path: Path) -> None:
        """任何内容都不应导致 parse_skill_file 抛出异常。"""
        skill_file = tmp_path / "SKILL.md"
        try:
            skill_file.write_bytes(content.encode("utf-8", errors="replace"))
        except Exception:
            pytest.skip("内容无法写入文件（预期）")
        # 不应抛异常，只应返回 None 或 SkillEntry
        try:
            result = parse_skill_file(skill_file)
            assert result is None or isinstance(result, SkillEntry)
        except Exception as e:
            pytest.fail(f"parse_skill_file 不应抛出异常，但抛出了: {type(e).__name__}: {e}")
