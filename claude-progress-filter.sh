#!/usr/bin/env bash
# claude-progress-filter.sh — 将 Claude stream-json 输出转为 Claude Code 风格的可读进度
# 用法: claude --print --verbose --output-format stream-json "prompt" | ./claude-progress-filter.sh
#
# 显示效果 (模仿 Claude Code 终端输出):
#   ● Read(prd.json)
#     ⎿  {"userStories":[{"id":"US-001",...}]}
#   ● 好的，我来分析需求。
#   ● Bash(uv run pytest tests/ -v)
#     ⎿  9 passed in 1.2s
#   ● 所有测试通过。
#   ✻ 完成 (耗时: 312s, 花费: $0.15)

TRUNCATE_LEN=${TRUNCATE_LEN:-200}

stdbuf -oL jq -r --argjson maxlen "$TRUNCATE_LEN" '
  def truncate: if length > $maxlen then .[0:$maxlen] + "..." else . end;
  def indent: gsub("\n"; "\n       ");
  def tool_desc:
    if .name == "Bash" then
      "Bash(\(.input.description // (.input.command | tostring | .[0:50])))"
    elif .name == "Read" then
      "Read(\(.input.file_path | split("/") | last))"
    elif .name == "Edit" then
      "Edit(\(.input.file_path | split("/") | last))"
    elif .name == "Write" then
      "Write(\(.input.file_path | split("/") | last))"
    elif .name == "Grep" then
      "Grep(\(.input.pattern | tostring | .[0:30]))"
    elif .name == "Glob" then
      "Glob(\(.input.pattern))"
    else
      .name
    end;

  if .type == "assistant" then
    [
      .message.content[]? |
      if .type == "tool_use" then
        "\u001b[32m● \(tool_desc)\u001b[0m"
      elif .type == "text" then
        "● \(.text)"
      else
        empty
      end
    ] | .[]

  elif .type == "user" then
    [
      .message.content[]? | select(.type == "tool_result") |
      (.content // "" | tostring | truncate | indent) as $c |
      if ($c | length) == 0 then
        empty
      else
        "\u001b[2m  ⎿  \($c)\u001b[0m"
      end
    ] | .[]

  elif .type == "result" then
    "\u001b[33m✻ 完成 (耗时: \(.duration_ms / 1000 | floor)s, 花费: $\(.total_cost_usd // 0))\u001b[0m"

  else
    empty
  end
' 2>/dev/null || true
