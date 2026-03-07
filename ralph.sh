#!/bin/bash
# Ralph Wiggum - Long-running AI agent loop
# Usage: ./ralph.sh [--tool amp|claude] [max_iterations]
# Source: https://github.com/snarktank/ralph

# 不使用 set -e：脚本内已有 || true 保护，set -e 会在管道命令里误杀进程

# Ctrl+C 信号处理：确保用户可以随时终止
# 管道放后台 + wait，这样 trap 能在 wait 期间立即触发
trap 'echo ""; echo "  [Ralph] Interrupted by user."; kill $(jobs -p) 2>/dev/null; exit 130' INT TERM

# Parse arguments
TOOL="amp"  # Default to amp for backwards compatibility
MAX_ITERATIONS=10

while [[ $# -gt 0 ]]; do
  case $1 in
    --tool)
      TOOL="$2"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    *)
      # Assume it's max_iterations if it's a number
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
      fi
      shift
      ;;
  esac
done

# Validate tool choice
if [[ "$TOOL" != "amp" && "$TOOL" != "claude" ]]; then
  echo "Error: Invalid tool '$TOOL'. Must be 'amp' or 'claude'."
  exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
ARCHIVE_DIR="$SCRIPT_DIR/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"

# Archive previous run if branch changed
if [ -f "$PRD_FILE" ] && [ -f "$LAST_BRANCH_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  LAST_BRANCH=$(cat "$LAST_BRANCH_FILE" 2>/dev/null || echo "")

  if [ -n "$CURRENT_BRANCH" ] && [ -n "$LAST_BRANCH" ] && [ "$CURRENT_BRANCH" != "$LAST_BRANCH" ]; then
    # Archive the previous run
    DATE=$(date +%Y-%m-%d)
    # Strip "ralph/" prefix from branch name for folder
    FOLDER_NAME=$(echo "$LAST_BRANCH" | sed 's|^ralph/||')
    ARCHIVE_FOLDER="$ARCHIVE_DIR/$DATE-$FOLDER_NAME"

    echo "Archiving previous run: $LAST_BRANCH"
    mkdir -p "$ARCHIVE_FOLDER"
    [ -f "$PRD_FILE" ] && cp "$PRD_FILE" "$ARCHIVE_FOLDER/"
    [ -f "$PROGRESS_FILE" ] && cp "$PROGRESS_FILE" "$ARCHIVE_FOLDER/"
    echo "   Archived to: $ARCHIVE_FOLDER"

    # Reset progress file for new run
    echo "# Ralph Progress Log" > "$PROGRESS_FILE"
    echo "Started: $(date)" >> "$PROGRESS_FILE"
    echo "---" >> "$PROGRESS_FILE"
  fi
fi

# Track current branch
if [ -f "$PRD_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  if [ -n "$CURRENT_BRANCH" ]; then
    echo "$CURRENT_BRANCH" > "$LAST_BRANCH_FILE"
  fi
fi

# Initialize progress file if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
  echo "# Ralph Progress Log" > "$PROGRESS_FILE"
  echo "Started: $(date)" >> "$PROGRESS_FILE"
  echo "---" >> "$PROGRESS_FILE"
fi

echo "Starting Ralph - Tool: $TOOL - Max iterations: $MAX_ITERATIONS"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "==============================================================="
  echo "  Ralph Iteration $i of $MAX_ITERATIONS ($TOOL)"
  echo "==============================================================="

  # 记录迭代开始前的任务 ID
  CURRENT_TASK=$(jq -r '[.userStories[] | select(.passes == false)][0].id // "unknown"' "$PRD_FILE" 2>/dev/null || echo "unknown")

  # Run the selected tool
  # CLAUDE.md 在项目根目录，Claude Code 自动读取
  if [[ "$TOOL" == "amp" ]]; then
    cat "$SCRIPT_DIR/prompt.md" | amp --dangerously-allow-all || true
  else
    # 防止嵌套 Claude Code 报错（如果从另一个 Claude 会话中启动）
    unset CLAUDECODE 2>/dev/null || true
    # 禁止 Claude 把命令放后台执行
    export CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1
    # --print 模式确保 Claude 完成后自动退出
    # stream-json + 过滤器让用户实时看到 Claude 的完整对话流
    CLAUDE_PROMPT="读取 prd.json 和 CLAUDE.md，找到所有 passes: false 的任务，按照 CLAUDE.md 的指令在本次会话中全部完成。不要只做一个就停下来。"
    echo -e "\033[36m❯ $CLAUDE_PROMPT\033[0m"
    echo ""
    claude --dangerously-skip-permissions --print --verbose --output-format stream-json \
      "$CLAUDE_PROMPT" \
      2>&1 | "$SCRIPT_DIR/claude-progress-filter.sh" &
    wait $! || true
  fi

  # ── Training Record ──
  echo ""
  echo "---------------------------------------------------------------"
  echo "  [Ralph] Claude session ended. Recording training data..."
  echo "---------------------------------------------------------------"
  ITER_DIR="$SCRIPT_DIR/iterations/iter_$(printf '%03d' $i)"
  PARAMS_DIR="$ITER_DIR/params"
  mkdir -p "$PARAMS_DIR"

  # 参数快照（Checkpoint）
  [ -f "$SCRIPT_DIR/learnings.md" ] && cp "$SCRIPT_DIR/learnings.md" "$PARAMS_DIR/"
  [ -f "$SCRIPT_DIR/progress.txt" ] && cp "$SCRIPT_DIR/progress.txt" "$PARAMS_DIR/"
  [ -f "$SCRIPT_DIR/prd.json" ] && cp "$SCRIPT_DIR/prd.json" "$PARAMS_DIR/"
  [ -f "$SCRIPT_DIR/AGENTS.md" ] && cp "$SCRIPT_DIR/AGENTS.md" "$PARAMS_DIR/"
  [ -f "$SCRIPT_DIR/decisions.log" ] && cp "$SCRIPT_DIR/decisions.log" "$PARAMS_DIR/"

  # 产出快照（Output Snapshot）
  # 如果 output/ 已被 setup-workspace.sh 创建为工作空间，则跳过
  if [ ! -d "$ITER_DIR/output" ] && [ -d "$SCRIPT_DIR/src" ] && [ -n "$(ls -A "$SCRIPT_DIR/src" 2>/dev/null)" ]; then
    cp -r "$SCRIPT_DIR/src" "$ITER_DIR/output"
  fi

  # 代码变更 diff
  (cd "$SCRIPT_DIR" && git diff HEAD~1 --no-color 2>/dev/null > "$ITER_DIR/diff.patch" || true)

  # 评估结果（Training Log）— 只测试当前任务对应的测试文件
  TESTS_PASSED=0
  TESTS_TOTAL=0
  OVERALL_PASS=false

  # 从 prd.json 的 acceptanceCriteria 中提取当前任务的测试文件
  CURRENT_TEST_FILE=""
  if [ "$CURRENT_TASK" != "unknown" ]; then
    CURRENT_TEST_FILE=$(jq -r --arg id "$CURRENT_TASK" \
      '.userStories[] | select(.id == $id) | .acceptanceCriteria[]' \
      "$PRD_FILE" 2>/dev/null | grep -oP 'tests/\S+\.py' | head -1 || true)
  fi

  if [ -n "$CURRENT_TEST_FILE" ] && [ -f "$SCRIPT_DIR/$CURRENT_TEST_FILE" ]; then
    TEST_OUTPUT=$(cd "$SCRIPT_DIR" && uv run pytest "$CURRENT_TEST_FILE" -v 2>&1 || true)
  elif [ -d "$SCRIPT_DIR/tests" ] && [ -n "$(find "$SCRIPT_DIR/tests" -name '*.py' -not -name '__init__.py' 2>/dev/null)" ]; then
    TEST_OUTPUT=$(cd "$SCRIPT_DIR" && uv run pytest tests/ -v 2>&1 || true)
  else
    TEST_OUTPUT=""
  fi

  if [ -n "$TEST_OUTPUT" ]; then
    if echo "$TEST_OUTPUT" | grep -qE "[0-9]+ passed"; then
      TESTS_PASSED=$(echo "$TEST_OUTPUT" | grep -oE "[0-9]+ passed" | tail -1 | grep -oE "[0-9]+" || echo "0")
      TESTS_TOTAL=$TESTS_PASSED
    fi
    if echo "$TEST_OUTPUT" | grep -qE "[0-9]+ failed"; then
      TESTS_FAILED=$(echo "$TEST_OUTPUT" | grep -oE "[0-9]+ failed" | tail -1 | grep -oE "[0-9]+" || echo "0")
      TESTS_TOTAL=$((TESTS_TOTAL + TESTS_FAILED))
    fi
    if echo "$TEST_OUTPUT" | grep -qE "[0-9]+ error"; then
      TESTS_ERRORS=$(echo "$TEST_OUTPUT" | grep -oE "[0-9]+ error" | tail -1 | grep -oE "[0-9]+" || echo "0")
      TESTS_TOTAL=$((TESTS_TOTAL + TESTS_ERRORS))
    fi
    if [ "$TESTS_PASSED" -eq "$TESTS_TOTAL" ] && [ "$TESTS_TOTAL" -gt 0 ]; then
      OVERALL_PASS=true
    fi
  fi

  # 检查 prd.json 中所有任务是否都通过
  ALL_PASS=$(jq '[.userStories[].passes] | all' "$PRD_FILE" 2>/dev/null || echo "false")
  if [ "$ALL_PASS" = "true" ]; then
    OVERALL_PASS=true
  fi

  cat > "$ITER_DIR/loss.json" <<LOSSJSON
{
  "iteration": $i,
  "timestamp": "$(date -Iseconds)",
  "task_id": "$CURRENT_TASK",
  "layer1": {
    "tests_total": $TESTS_TOTAL,
    "tests_passed": $TESTS_PASSED,
    "pass": $([ "$TESTS_PASSED" -eq "$TESTS_TOTAL" ] && [ "$TESTS_TOTAL" -gt 0 ] && echo true || echo false)
  },
  "overall_pass": $OVERALL_PASS
}
LOSSJSON

  # 更新 learning_curve.json（追加本轮数据）
  LC_FILE="$SCRIPT_DIR/iterations/learning_curve.json"
  if [ ! -f "$LC_FILE" ]; then
    echo '{"iterations":[]}' > "$LC_FILE"
  fi
  if jq --argjson iter "$i" \
     --arg task "$CURRENT_TASK" \
     --argjson tp "${TESTS_PASSED:-0}" \
     --argjson tt "${TESTS_TOTAL:-0}" \
     --argjson op "${OVERALL_PASS:-false}" \
     '.iterations += [{"iter":$iter,"task":$task,"tests_passed":$tp,"tests_total":$tt,"overall_pass":$op}]' \
     "$LC_FILE" > "$LC_FILE.tmp" 2>/dev/null; then
    mv "$LC_FILE.tmp" "$LC_FILE"
  else
    echo "  [Warning] Failed to update learning_curve.json" >&2
    rm -f "$LC_FILE.tmp"
  fi

  echo "  [Training Record] Saved to $ITER_DIR (passed=$TESTS_PASSED/$TESTS_TOTAL)"
  # ── End Training Record ──

  # 完成检测：检查 prd.json 而非 grep 输出
  if [ "$ALL_PASS" = "true" ]; then
    echo ""
    echo "==============================================================="
    echo "  Ralph completed all tasks!"
    echo "  Completed at iteration $i of $MAX_ITERATIONS"
    echo "==============================================================="
    exit 0
  fi

  echo ""
  echo "  [Ralph] $CURRENT_TASK done. Starting next iteration in 3s..."
  echo ""
  sleep 3
done

echo ""
echo "Ralph reached max iterations ($MAX_ITERATIONS) without completing all tasks."
echo "Check $PROGRESS_FILE for status."
exit 1
