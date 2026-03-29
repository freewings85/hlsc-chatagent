# update_state_tree 可靠性迭代日志

## Iteration 1: Tool Description + Instructions Enhancement

**日期**: 2026-03-28

### 变更内容

**两处变更（均不涉及 AGENT.md，保持弹性语气）：**

1. **Tool docstring** (`extensions/hlsc/tools/update_state_tree.py`)
   - 旧: "更新业务流程状态树到持久化文件。" + 格式说明 + "何时调用"列表
   - 新: "保存业务进度。用户确认、完成步骤、做出选择后必须立即调用，否则进度丢失。" + "调用时机（满足任一即调用）"列表
   - 关键改动：首行用后果驱动语气（"否则进度丢失"），去掉格式细节，聚焦触发条件

2. **_BUSINESS_MAP_INSTRUCTIONS** (`mainagent/src/hlsc_context.py`)
   - 旧: "节点完成或状态变化时调用 update_state_tree 更新进度"
   - 新: "用户确认、完成步骤、做出选择后，先调用 update_state_tree 保存进度，再回复用户"
   - 关键改动：明确时序（"先...再回复用户"），让模型理解工具调用应在回复之前

**辅助修复：**

3. **Eval 脚本** (`reports/run_update_state_tree_reliability.py`)
   - 修复：注入 `_BUSINESS_MAP_INSTRUCTIONS`，匹配真实系统行为
   - 之前的 eval 漏掉了这个上下文块，导致测试条件比实际更苛刻

### S2 结果

| 批次 | 通过率 | 详情 |
|------|--------|------|
| 原始基线 (旧 eval) | 3/5 (60%) | 2026-03-28 15:56 |
| 今日基线 (旧 docstring, 旧 eval) | 0/5 (0%) | 模型表现当日波动 |
| 仅改 docstring (无 instructions) | 0/5, 1/5 | 去掉格式说明后反而退步 |
| docstring + instructions 注入 (无时序) | 2/5, 2/5, 1/5 = 5/15 (33%) | 有提升但不够 |
| **最终版: docstring + 时序指令** | **5/5, 4/5, 4/5 = 13/15 (87%)** | 超过 80% 目标 |

### Navigator 影响

| 指标 | 变更前 | 变更后 |
|------|--------|--------|
| 精确匹配率 | 34.0% (17/50) | 70.0% (35/50) |
| 总可接受率 | 74.0% (37/50) | 94.0% (47/50) |

Navigator eval 不但没有退步，反而大幅改善（可能因为 `_BUSINESS_MAP_INSTRUCTIONS` 现在被正确注入到 eval 中）。

### 结论

**Verdict: KEEP**

核心洞察：让模型可靠地调用工具，最有效的信号不是工具描述本身，而是在上下文指令中明确**时序要求**（"先调用...再回复"）。工具描述的后果驱动语气也有辅助作用，但单独不够。
