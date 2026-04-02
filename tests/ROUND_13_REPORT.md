# SearchCoupons 场景测试 — Round 13 报告

## 总结

**轮次**: 13  
**日期**: 2026-04-02  
**结果**: 5/7 PASS (71%) ⚠️ 部分恢复  
**AGENT.md**: 重写，强化 search_coupon 和 apply_coupon 优先级

## 测试详情

| 编号 | 场景 | 工具调用 | 状态 |
|------|------|---------|------|
| SC-001 | 明确项目 | classify_project → search_coupon | ✓ PASS |
| SC-003 | 无项目引导 | 无工具 | ✓ PASS |
| SC-005 R1 | 多轮累积 R1 | delegate, classify_project (无 search_coupon) | ❌ FAIL |
| SC-005 R2 | 多轮累积 R2 | classify_project → search_coupon | ✓ OK |
| SC-005 R3 | 多轮累积 R3 | 无工具 | ⚠️ WARN |
| SC-009 R1 | 选优惠+时间 R1 | classify_project → search_coupon | ✓ OK |
| SC-009 R2 | 选优惠+时间 R2 | 无工具 | ❌ FAIL (未调 apply_coupon) |
| SC-010 | 选优惠无时间 | classify_project → search_coupon | ✓ PASS |
| SC-012 | 按金额排序 | classify_project → search_coupon | ✓ PASS |
| SC-014 | 模糊查询 | 无工具，有引导 | ✓ PASS |

## 关键发现

### 进展
- SC-001 恢复到 PASS ✓
- SC-012 恢复到 PASS ✓
- 整体 71% 虽不如 Round 10 的 86%，但比 Round 12 的 43% 好很多

### 仍存在的问题

1. **SC-005 R1 第一次调用时不触发 search_coupon**
   - 现象：调用了 delegate + classify_project，但没有 search_coupon
   - 第2轮时正常调用 search_coupon
   - Root cause：模型在第1轮的判断不同？还是多轮对话积累的影响？

2. **SC-009 R2 用户说时间但 apply_coupon 未被调用**
   - 用户："我要这个8折的，下午2点去"
   - 期望：apply_coupon("2001", "101", "下午2点")
   - 实际：无工具，代理询问确认

## AGENT.md 重写内容

新版本特点：
```markdown
## 推进策略（严格执行）

### 第一优先：search_coupon
- 用户提项目 → classify_project → search_coupon（链式调用）
- 不要先问信息，直接查

### 第二优先：apply_coupon
- 用户说意愿词 + 时间 → 立即调（不要再问）
- 从 search_coupon 最新结果的 top-1 coupon 提取参数
- 不要纠结描述与实际不一致
```

目标是减少模型的决策自由度，强制执行 search_coupon 和 apply_coupon 的调用。

## 为何 SC-005 R1 和 SC-009 R2 仍然失败？

分析：
1. **SC-005 R1** 是第一次调用，用户输入"帮我看看换机油的优惠"
   - 可能被路由到 orchestrator（delegate）而非 searchcoupons
   - 或者 BMA 分类结果导致了多场景路由

2. **SC-009 R2** 用户输入有二义性（"8折" vs "满500减80"）
   - 模型识别出不匹配，选择了保守的确认策略而非直接调用

## 与 Round 10 的对比

Round 10 成功版本的特征（推测）：
- 可能更强调"绝不迟疑"
- 可能有更具体的参数提取示例
- 可能避免了 delegate/match_project 的干扰

Round 13 的改进方向：
- ✓ 明确了工具优先级
- ✓ 简化了决策逻辑
- ❌ 仍未完全消除 SC-005 R1 的问题
- ❌ 仍未完全解决 SC-009 R2 的问题

## 建议

### 短期（Round 14）
1. 在 SC-005 和 SC-009 的 AGENT.md 中添加**极其具体的示例**
2. 特别针对"参数不匹配"情况的处理（8折 vs 满500减80）
3. 考虑是否需要在 OUTPUT.md 中添加约束

### 中期（Round 15+）
1. 研究 BMA 的多场景分类是否干扰了 SC-005 R1
2. 调查为什么 SC-005 R1 会调用 delegate
3. 分析模型的"谨慎确认"倾向，找到参数/策略来降低

### 长期
1. 考虑在代码层面（而非 prompt 层面）强制 apply_coupon 调用
2. 或者通过 tool constraints 来限制模型的选择空间

---

测试人员: claude-haiku-4-5  
执行时间: 2026-04-02 18:30 UTC+8
