"""Playwright Session Case Runner：解析 tests/session_cases/ 下的 .txt 用例文件并驱动浏览器执行。

用例格式（.txt）：
  CASE: <name>
  SETUP:
    CREATE: /path | content
    DELETE_IF_EXISTS: /path
  --- TURN N ---
  INPUT:
  <用户输入文字>
  EXPECT_TOOL: <tool_name>      (可多行)
  EXPECT_RESULT_CONTAINS: <str>  (可多行)
  EXPECT_RESPONSE_CONTAINS: <str>(可多行)
  VERIFY_FILE_EXISTS: /path
  VERIFY_FILE_CONTAINS: <str>
  VERIFY_FILE_NOT_CONTAINS: <str>
  --- END TURN N ---
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import (
    RESPONSE_TIMEOUT_MS,
    TEST_DATA_DIR,
    TOOL_TIMEOUT_MS,
    send_and_wait,
    wait_for_tool,
)

# session_cases 根目录
SESSION_CASES_DIR: Path = Path(__file__).parent.parent / "session_cases"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class TurnSpec:
    index: int
    input_text: str = ""
    expect_tools: list[str] = field(default_factory=list)
    expect_result_contains: list[str] = field(default_factory=list)
    expect_response_contains: list[str] = field(default_factory=list)
    verify_file_exists: list[str] = field(default_factory=list)
    verify_file_contains: list[tuple[str, str]] = field(default_factory=list)  # (path, text)
    verify_file_not_contains: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class SetupAction:
    action: str      # "CREATE" | "DELETE_IF_EXISTS"
    path: str
    content: str = ""


@dataclass
class CaseSpec:
    name: str
    file_path: Path
    setup_actions: list[SetupAction] = field(default_factory=list)
    turns: list[TurnSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------

def _parse_case_file(txt_path: Path) -> CaseSpec:
    """解析 .txt 用例文件，返回 CaseSpec。"""
    lines = txt_path.read_text(encoding="utf-8").splitlines()
    case_name = txt_path.stem

    # 提取 CASE: 名称
    for line in lines:
        m = re.match(r"^CASE:\s*(.+)$", line)
        if m:
            case_name = m.group(1).strip()
            break

    spec = CaseSpec(name=case_name, file_path=txt_path)

    # 解析 SETUP 块
    in_setup = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "SETUP:":
            in_setup = True
            i += 1
            continue
        if in_setup:
            if line.startswith("---") or line.startswith("MANUAL_TEST_STEPS"):
                in_setup = False
            elif line.strip().startswith("CREATE:"):
                rest = line.strip()[len("CREATE:"):].strip()
                if "|" in rest:
                    path_part, content_part = rest.split("|", 1)
                    spec.setup_actions.append(
                        SetupAction("CREATE", path_part.strip(), content_part.strip())
                    )
                else:
                    spec.setup_actions.append(SetupAction("CREATE", rest.strip()))
            elif line.strip().startswith("DELETE_IF_EXISTS:"):
                path_part = line.strip()[len("DELETE_IF_EXISTS:"):].strip()
                spec.setup_actions.append(SetupAction("DELETE_IF_EXISTS", path_part))
        i += 1

    # 解析 TURN 块
    turn_start_re = re.compile(r"^---\s*TURN\s+(\d+)\s*---")
    turn_end_re = re.compile(r"^---\s*END TURN\s+\d+\s*---")

    i = 0
    while i < len(lines):
        m = turn_start_re.match(lines[i])
        if m:
            turn_idx = int(m.group(1))
            i += 1
            turn = TurnSpec(index=turn_idx)

            # 读取 INPUT
            if i < len(lines) and lines[i].strip() == "INPUT:":
                i += 1
                input_lines: list[str] = []
                while i < len(lines) and not lines[i].startswith("EXPECT_") \
                        and not lines[i].startswith("VERIFY_") \
                        and not turn_end_re.match(lines[i]):
                    input_lines.append(lines[i])
                    i += 1
                turn.input_text = "\n".join(input_lines).strip()

            # 读取 EXPECT/VERIFY 指令
            while i < len(lines) and not turn_end_re.match(lines[i]):
                directive = lines[i].strip()
                if directive.startswith("EXPECT_TOOL:"):
                    val = directive[len("EXPECT_TOOL:"):].strip()
                    if val and val != "(none)":
                        turn.expect_tools.append(val)
                elif directive.startswith("EXPECT_RESULT_CONTAINS:"):
                    val = directive[len("EXPECT_RESULT_CONTAINS:"):].strip()
                    if val:
                        turn.expect_result_contains.append(val)
                elif directive.startswith("EXPECT_RESPONSE_CONTAINS:"):
                    val = directive[len("EXPECT_RESPONSE_CONTAINS:"):].strip()
                    if val:
                        turn.expect_response_contains.append(val)
                elif directive.startswith("VERIFY_FILE_EXISTS:"):
                    val = directive[len("VERIFY_FILE_EXISTS:"):].strip()
                    if val:
                        turn.verify_file_exists.append(val)
                elif directive.startswith("VERIFY_FILE_CONTAINS:"):
                    val = directive[len("VERIFY_FILE_CONTAINS:"):].strip()
                    if val:
                        # 需要和上一个 VERIFY_FILE_EXISTS 配对，简化为从 expect_tools 里查
                        # 或者解析"path → contains"的形式，这里简化：单独记录文本
                        turn.verify_file_contains.append(("", val))  # path 后处理填充
                elif directive.startswith("VERIFY_FILE_NOT_CONTAINS:"):
                    val = directive[len("VERIFY_FILE_NOT_CONTAINS:"):].strip()
                    if val:
                        turn.verify_file_not_contains.append(("", val))
                i += 1

            spec.turns.append(turn)
            if i < len(lines) and turn_end_re.match(lines[i]):
                i += 1  # skip END TURN line
            continue
        i += 1

    # 后处理：为 VERIFY_FILE_CONTAINS / VERIFY_FILE_NOT_CONTAINS 填充路径
    # 从 SETUP CREATE 中找唯一的文件路径
    created_paths = [a.path for a in spec.setup_actions if a.action == "CREATE"]
    for turn in spec.turns:
        for j, (path, text) in enumerate(turn.verify_file_contains):
            if not path and len(created_paths) == 1:
                turn.verify_file_contains[j] = (created_paths[0], text)
        for j, (path, text) in enumerate(turn.verify_file_not_contains):
            if not path and len(created_paths) == 1:
                turn.verify_file_not_contains[j] = (created_paths[0], text)

    return spec


def _collect_cases() -> list[CaseSpec]:
    """发现 session_cases/ 下所有 .txt 文件并解析。"""
    cases: list[CaseSpec] = []
    for txt_path in sorted(SESSION_CASES_DIR.rglob("*.txt")):
        cases.append(_parse_case_file(txt_path))
    return cases


# ---------------------------------------------------------------------------
# Setup 执行
# ---------------------------------------------------------------------------

def _run_setup(setup_actions: list[SetupAction]) -> None:
    """在 TEST_DATA_DIR 下执行 SETUP 动作（CREATE / DELETE_IF_EXISTS）。"""
    for action in setup_actions:
        # 去掉开头的 / 以便拼接到 TEST_DATA_DIR
        rel_path = action.path.lstrip("/")
        full_path = TEST_DATA_DIR / rel_path
        if action.action == "CREATE":
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(action.content + "\n", encoding="utf-8")
        elif action.action == "DELETE_IF_EXISTS":
            full_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Turn 执行与断言
# ---------------------------------------------------------------------------

def _run_turn(page: Page, turn: TurnSpec) -> None:
    """执行一个 TURN：发送消息，等待响应，执行所有断言。"""
    # 记录本轮开始前已有的工具块数量，用于定位本轮新增的块
    existing_count = len(page.locator(".tool-block").all())

    send_and_wait(page, turn.input_text)

    # 等待工具块出现
    for tool_name in turn.expect_tools:
        wait_for_tool(page, tool_name)

    # 验证工具结果内容：收集本轮新增的所有工具块结果，检查 expected 出现在其中之一
    if turn.expect_result_contains:
        all_blocks = page.locator(".tool-block").all()
        new_blocks = all_blocks[existing_count:]  # 本轮新增的工具块
        combined_results: list[str] = []
        for block in new_blocks:
            # 展开工具块
            header = block.locator(".tool-header")
            header.click()
            result_el = block.locator(".tool-result-section .tool-code")
            try:
                result_el.wait_for(state="visible", timeout=15_000)
                combined_results.append(result_el.inner_text())
            except Exception:
                pass  # 个别工具块可能无结果文字，跳过

        combined_text = "\n".join(combined_results)
        for expected in turn.expect_result_contains:
            assert expected in combined_text, (
                f"工具结果中未找到: {expected!r}\n"
                f"本轮所有工具结果：{combined_text[:800]}"
            )

    # 验证文字回复内容
    if turn.expect_response_contains:
        # 等待文字内容稳定后检查
        time.sleep(0.5)  # 流式内容可能仍在写入
        all_text = " ".join(
            el.inner_text() for el in page.locator(".text-segment").all()
        )
        for expected in turn.expect_response_contains:
            assert expected in all_text, (
                f"响应文字中未找到: {expected!r}\n实际内容: {all_text[:500]}"
            )

    # 验证文件存在
    for file_path in turn.verify_file_exists:
        rel = file_path.lstrip("/")
        full = TEST_DATA_DIR / rel
        assert full.exists(), f"期望文件存在但不存在: {full}"

    # 验证文件内容包含
    for file_path, expected_text in turn.verify_file_contains:
        if not file_path:
            continue
        rel = file_path.lstrip("/")
        full = TEST_DATA_DIR / rel
        assert full.exists(), f"验证内容时文件不存在: {full}"
        content = full.read_text(encoding="utf-8")
        assert expected_text in content, (
            f"文件 {full} 中未找到: {expected_text!r}\n实际内容: {content[:500]}"
        )

    # 验证文件内容不包含
    for file_path, excluded_text in turn.verify_file_not_contains:
        if not file_path:
            continue
        rel = file_path.lstrip("/")
        full = TEST_DATA_DIR / rel
        if full.exists():
            content = full.read_text(encoding="utf-8")
            assert excluded_text not in content, (
                f"文件 {full} 中不应包含: {excluded_text!r}\n实际内容: {content[:500]}"
            )


# ---------------------------------------------------------------------------
# pytest 参数化
# ---------------------------------------------------------------------------

def _case_id(case: CaseSpec) -> str:
    """生成用例的 pytest ID（子目录 + 用例名）。"""
    rel = case.file_path.relative_to(SESSION_CASES_DIR)
    parts = list(rel.parts)
    parts[-1] = parts[-1].replace(".txt", "")
    return "/".join(parts)


_ALL_CASES = _collect_cases()


@pytest.mark.parametrize(
    "case_spec",
    _ALL_CASES,
    ids=[_case_id(c) for c in _ALL_CASES],
)
def test_session_case(chat_page: Page, case_spec: CaseSpec) -> None:
    """执行单个 session case：SETUP → 逐 TURN 驱动浏览器 → 断言。"""
    # SETUP
    _run_setup(case_spec.setup_actions)

    # 逐轮执行
    for turn in case_spec.turns:
        _run_turn(chat_page, turn)
