# SearchCoupons 场景测试 — Round 12 报告

## 总结

**轮次**: 12  
**日期**: 2026-04-02  
**结果**: 3/7 PASS (43%) ❌ 回归  
**对比**:
- Round 10: 6/7 PASS (86%) ✓ 最佳
- Round 11: 4/7 PASS (57%) ⚠️ 回退后变好
- Round 12: 3/7 PASS (43%) ❌ 继续回退

## 测试详情

| 编号 | 场景 | R1 | R2 | R3 | 状态 | 备注 |
|------|------|----|----|-----|------|------|
| SC-001 | 明确项目：换机油 | ❌ 无工具 | - | - | FAIL | classify_project 后未调 search_coupon |
| SC-003 | 无项目引导 | ✓ 无工具 | - | - | PASS | 正确引导 |
| SC-005/006/007 | 多轮累积 | ❌ 无工具 | ⚠️ match | ⚠️ classify | FAIL | R1 未调 search_coupon |
| SC-009 | 选优惠+时间 | ❌ match | ❌ delegate | - | FAIL | R1 未调 search_coupon |
| SC-010 | 选优惠无时间 | ⚠️ match → 延迟 collect | ✓ 无工具 | PASS | 行为诡异：match→collect |
| SC-012 | 按金额排序 | ❌ classify | - | - | FAIL | 未调 search_coupon |
| SC-014 | 模糊查询 | ✓ 无工具 | - | - | PASS | 正确引导 |

## 关键发现

### 问题 1：AGENT.md 版本混乱
- 提交版本（HEAD）：使用旧 prompt（save-playbook 相关）
- Round 10 时的版本：使用新 prompt（强化"先查再问"）
- Round 10 版本现已丢失

### 问题 2：工具调用行为不稳定
Round 12 看到的异常：
- `classify_project` 被调用但不会自动触发 `search_coupon`
- `match_project` 被优先使用，而不是 `search_coupon`
- `delegate` 被错误调用

这表明 AGENT.md 可能不是搜索结果优先的策略。

### 问题 3：SC-010 的诡异行为
Round 12 中 SC-010：
- R1: 调用 `match_project` 后进入 `collect_car_info`，耗时 68.41s
- 这不符合 searchcoupons 的预期流程

## Root Cause 分析

当前 HEAD 版本的 AGENT.md 提到：
```
推进原则：
- 先查再说——用户问优惠就直接调 search_coupon，不先问"什么项目"
- 展示优惠时给出具体金额
- 多种省钱方式可叠加时一起呈现
```

但实际工具调用序列显示：
1. 优先使用 `classify_project` 或 `match_project`
2. 不自动跟进 `search_coupon`
3. 有时会意外调用 `delegate`

这表明要么：
- AGENT.md 没有被正确加载
- 或 AGENT.md 的指示不够强有力
- 或模型在不确定性下默认回退到其他工具

## Round 10 成功的秘密

Round 10 达到 86% 的原因：
```
- SC-001 ✓ 调用了 classify_project → search_coupon
- SC-003 ✓ 引导无工具调用
- SC-005 ✓ R1 调用 search_coupon（关键改进！）
- SC-009 ❌ R2 仍未调 apply_coupon（唯一失败）
- SC-010 ✓ 无直接 apply_coupon
- SC-012 ✓ 调用了 search_coupon
- SC-014 ✓ 正确引导
```

关键差异：SC-005 R1 从 FAIL 变成 PASS，表示某个 prompt 改动有效。

## 建议

1. **恢复 Round 10 的 AGENT.md 版本**  
   需要找回或重新构造成功版本的 prompt

2. **强化三个关键指示**：
   - 用户说项目 → 立即 classify_project + search_coupon（不要停在 classify）
   - search_coupon 返回结果 + 用户说时间 → 立即 apply_coupon（不要 delegate）
   - 避免在 searchcoupons 场景中使用 match_project（可选）

3. **审视 stage_config.yaml**  
   检查 searchcoupons 场景的可用工具列表是否正确：
   ```yaml
   searchcoupons:
     tools:
       - search_coupon      # 必须优先使用
       - apply_coupon       # 用户给时间时立即使用
       - classify_project   # 可用，但应跟进 search_coupon
       - match_project      # 是否真的需要？会混淆路由
       - delegate           # 不应在此场景调用
   ```

4. **逐轮迭代而非大幅修改**  
   后续 prompt 调整应该单步测试，避免一次性引入破坏性变化。

## 时间线

| 轮次 | 结果 | 变化 | 备注 |
|------|------|------|------|
| 10 | 6/7 86% | 强化"先查再问" | ✓ 成功 |
| 11 | 4/7 57% | 详细的执行步骤 | ❌ 过度设计 |
| 12 | 3/7 43% | 恢复基础版 | ❌ 基础版更差 |

## Next Steps

1. 在 git 中搜索或重构 Round 10 的 AGENT.md
2. 如果无法找到，从 Round 10 测试输出反推 prompt 的关键特征
3. 创建 Round 13 用修复的 prompt 重新测试
4. 目标：恢复 86% 并尝试突破 90%

---

测试人员: claude-haiku-4-5  
执行时间: 2026-04-02 18:00 UTC+8
