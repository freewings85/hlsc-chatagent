# PRD: chatagent 代码覆盖率 100%

## Introduction

chatagent 项目当前单元测试 160 个，覆盖率 95%，E2E 测试 11 个 session case 全部通过。但存在明确的覆盖盲点（error fallback 路径、timeout/truncation、边界条件）以及 E2E 测试数据污染问题。本 PRD 定义将覆盖率提升至 ≥99% 所需的所有工作，并修复过程中发现的 bug。

**重要说明**：本任务使用自动化开发框架（uv + pytest + coverage），所有命令必须用 `uv run` 执行。测试文件 **可以** 修改（添加测试是本任务的核心工作）。

## Goals

- 为所有未覆盖代码路径添加单元测试
- 修复 fs.py fallback 路径绕过 virtual_mode 沙箱的潜在 bug
- 修复 E2E 测试数据污染（tests 间 TEST_DATA_DIR 不清理）
- 最终：`uv run pytest tests/ --cov=src --cov-report=term-missing -v` 全部通过，TOTAL ≥ 99%

## User Stories

### US-001: 修复并测试 fs.py error fallback 路径
**Description:** As a developer, I want the fs.py error fallback paths to be both correct and tested so that the tools don't bypass virtual_mode when an exception occurs.

**Acceptance Criteria:**
- [ ] 读取 `src/agent/tools/fs.py` 第 56-60、101-108、140-144 行的 fallback 逻辑
- [ ] 确认 fallback 路径是否正确处理 virtual_mode（不绕过沙箱）；如有 bug 则修复
- [ ] 在 `tests/agent/tools/test_fs_tools.py` 中添加测试覆盖 `AttributeError`/`OSError` 触发路径
- [ ] 在 `tests/agent/tools/test_fs_tools.py` 中添加测试覆盖 grep 返回 str 错误的路径（第 193 行）
- [ ] `uv run pytest tests/agent/tools/test_fs_tools.py -v` 全部通过
- [ ] fs.py 覆盖率达到 100%

### US-002: 测试 bash.py timeout 和 truncation 路径
**Description:** As a developer, I want bash tool's timeout and output truncation logic to be tested so that edge cases don't silently fail.

**Acceptance Criteria:**
- [ ] 在 `tests/agent/tools/test_bash.py` 中添加：超时场景测试（mock asyncio.wait_for 抛 TimeoutError）
- [ ] 在 `tests/agent/tools/test_bash.py` 中添加：输出超过 MAX_OUTPUT_BYTES 截断测试（已有但需验证覆盖到第 52 行）
- [ ] `uv run pytest tests/agent/tools/test_bash.py -v` 全部通过
- [ ] bash.py 覆盖率达到 100%

### US-003: 测试 file_state.py 外部文件修改检测路径
**Description:** As a developer, I want the get_changed_files() method to be tested for the mtime-change branch so that the AttachmentCollector can rely on it.

**Acceptance Criteria:**
- [ ] 在相关测试文件中添加：on_read 后外部修改文件，get_changed_files() 返回该文件的测试
- [ ] `uv run pytest tests/ -k "file_state" -v` 全部通过
- [ ] file_state.py 覆盖率达到 100%

### US-004: 补充 history_message_loader.py 和 task_queue.py 边界路径测试
**Description:** As a developer, I want all uncovered lines in history_message_loader.py and task_queue.py to be tested.

**Acceptance Criteria:**
- [ ] 查看 `tests/agent/message/test_history_message_loader.py` 当前测试，补充第 130、169 行的场景
- [ ] 查看 `tests/engine/test_task_queue.py` 当前测试，补充第 111-112、115、118-123 行的场景
- [ ] `uv run pytest tests/agent/message/ tests/engine/ -v` 全部通过
- [ ] history_message_loader.py 和 task_queue.py 覆盖率达到 100%

### US-005: 修复 E2E 测试数据隔离问题
**Description:** As a developer, I want E2E session case tests to clean up TEST_DATA_DIR between runs so that tests don't interfere with each other.

**Acceptance Criteria:**
- [ ] 在 `tests/e2e/test_session_cases.py` 的 `test_session_case` 函数中，SETUP 执行前先清理 TEST_DATA_DIR
- [ ] 或在 `tests/e2e/conftest.py` 中添加 function-scoped fixture 在每个 E2E 测试前清理 TEST_DATA_DIR
- [ ] 验证：单独运行 `uv run pytest tests/e2e/test_session_cases.py::test_session_case[chromium-tools/glob_tool] -v` 在任意顺序下均通过
- [ ] 所有 11 个 session case 仍然通过

### US-006: 最终验证覆盖率 ≥ 99%
**Description:** As a developer, I want to verify that all tests pass and coverage meets the target.

**Acceptance Criteria:**
- [ ] `uv run pytest tests/ --ignore=tests/e2e --cov=src --cov-report=term-missing -v` 全部通过
- [ ] 输出中 TOTAL 覆盖率 ≥ 99%
- [ ] 没有任何 FAILED 的测试
- [ ] `uv run mypy src/agent/tools/ src/agent/file_state.py --ignore-missing-imports` 无错误

## Functional Requirements

- FR-1: fs.py 的所有 error fallback 分支必须有对应单元测试触发
- FR-2: bash.py 的 TimeoutError 路径和 truncation 路径必须有单元测试
- FR-3: file_state.py 的 get_changed_files 必须测试 mtime 变化场景
- FR-4: E2E 测试在每个 test function 开始时清空 TEST_DATA_DIR（只删内容，不删目录）
- FR-5: 所有新增测试必须使用 `uv run pytest` 执行，不直接调用 python

## Non-Goals

- 不实现 AttachmentCollector（loop.py TODO #5）——这是独立功能
- 不增加 memory/、mcp/、skills/ 的实现——这些是存根，留待后续
- 不修改 E2E 测试的核心逻辑，只修复数据隔离
- 不追求绝对 100%（pg_backend.py、s3_backend.py 等基础设施代码可排除在外）

## Technical Considerations

- 项目使用 `uv`，所有命令格式：`uv run pytest ...`、`uv run mypy ...`
- 异步测试：`pytest-anyio` 已配置 `asyncio_mode=AUTO`，直接用 `async def test_xxx` 即可
- Mock 模式：用 `unittest.mock.patch` / `AsyncMock` mock 异步函数
- E2E 测试依赖真实 LLM（.env 中配置），session case runner 不需要改变核心逻辑
- 覆盖率命令：`uv run pytest tests/ --ignore=tests/e2e --cov=src --cov-report=term-missing`
- mypy 检查：`uv run mypy src/ --ignore-missing-imports`

## Success Metrics

- 单元测试全部通过（目标：≥160 个，新增后更多）
- TOTAL 覆盖率 ≥ 99%（排除 e2e 测试本身）
- E2E session cases 11/11 通过（任意顺序）
- 无 mypy 类型错误（在修改的文件范围内）
