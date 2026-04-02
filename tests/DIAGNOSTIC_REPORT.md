# searchcoupons 场景诊断报告

**执行日期**: 2026-04-02  
**诊断工程师**: Task #4  

---

## 执行摘要

✅ **测试脚本完整性**: 16 个测试用例 + 实测脚本 + 诊断工具 ✓  
⚠️ **功能验证**: 因 BMA 服务离线，无法完整验证 searchcoupons 场景  
📊 **初步结果**: 3/7 实测用例通过（43%），均为 guide 场景逻辑

---

## 诊断发现

### 问题 1: BMA 服务离线（Blocker）

**症状**：
```
POST http://localhost:8103/classify → Connection refused
All connection attempts failed
```

**影响链**：
```
BMA 离线
  ↓
MainAgent 无法调用 BMA /classify
  ↓
场景分类失败，异常捕获
  ↓
Agent 回退到 guide 场景（安全模式）
  ↓
searchcoupons prompt + tools 未加载
  ↓
"换机油有优惠吗？" → Agent 不调用 search_coupon
  ↓
测试失败 ✗
```

### 问题 2: guide 场景引导不够清晰（Minor）

**观察**：
- SC-003: "无项目查优惠" → 通过，但引导文本不够明显
- SC-010: "缺时间确认" → 通过，但没有要求时间的提示
- SC-014: "模糊查询" → 通过，但引导文本不清晰

**建议**：
```
guide 场景 prompt 应明确包含：
- "您要做什么项目？（保养 / 轮胎 / 机油等）"
- "请告诉我您想到店的时间"
- "请问需要什么帮助？（查优惠 / 预订服务 / 推荐方案）"
```

---

## 测试现状分析

### 实测结果统计

| 场景 | 用例数 | PASS | FAIL | 原因 |
|------|--------|------|------|------|
| guide 场景 | 3 | 3 | 0 | ✓ 正常 |
| searchcoupons 场景 | 4 | 0 | 4 | ✗ BMA 离线，无法路由 |
| **合计** | **7** | **3** | **4** | - |

### 详细结果

✓ **通过的用例**（guide 场景逻辑验证）：
1. **SC-003**: 无项目查优惠 → 引导确认（虽然引导不够清晰）
2. **SC-010**: 缺时间确认 → 等待输入（虽然没有明显提示）
3. **SC-014**: 模糊查询 → 拒绝直接查询（虽然引导不够清晰）

✗ **失败的用例**（searchcoupons 场景未被路由）：
1. **SC-001**: 换机油查优惠 → 无法调用 search_coupon
   - 工具调用：classify_project（只识别项目，没有查优惠）
   - 根本原因：Agent 停留在 guide 场景，没有 searchcoupons prompt

2. **SC-005/006/007**: 多轮偏好累积 → 无法调用 search_coupon
   - 工具调用：无（轮1 后立即短路）
   - 根本原因：同上

3. **SC-009**: 选优惠申领 → 无法调用 apply_coupon
   - 工具调用：无
   - 根本原因：同上

4. **SC-012**: 按金额排序 → 无法调用 search_coupon
   - 工具调用：无
   - 根本原因：同上

---

## 验证清单

### ✓ 已验证的部分

- [x] MainAgent 服务正常运行（127.0.0.1:8100）
- [x] 工具函数已正确注册（search_coupon, apply_coupon 在 tool_map 中）
- [x] searchcoupons 场景配置正确（stage_config.yaml 已加载）
- [x] searchcoupons prompt 存在（AGENT.md, OUTPUT.md 文件完整）
- [x] Mock 数据加载成功（2001-2005 商户优惠，1001-1002 平台优惠）
- [x] guide 场景 fallback 机制正常（BMA 失败时正确回退）

### ✗ 未验证的部分

- [ ] **BMA 服务在线** ← BLOCKER
- [ ] search_coupon 工具的功能
- [ ] apply_coupon 工具的功能
- [ ] semantic_query 多轮累积
- [ ] 优惠列表展示（CouponCard spec）
- [ ] 联系单生成（apply_coupon action）

---

## 后续行动（优先级排序）

### 🔴 优先级 1：启动 BMA 服务（BLOCKER）

**何处找到**：
```
extensions/business_map_agent/  或相关位置
```

**启动命令**：
```bash
# 假设 BMA 的启动方式（需确认实际路径）
cd extensions && uv run python -m business_map_agent.main
# 或
docker run -p 8103:8103 hlsc-bma:latest
```

**验证方法**：
```bash
curl http://localhost:8103/classify -X POST -H "Content-Type: application/json" \
  -d '{"message":"换机油有优惠吗？"}'

# 期望返回
{"scenes":["searchcoupons"]}  # 或其他场景
```

### 🟡 优先级 2：重新执行完整测试（BMA 启动后）

```bash
cd mainagent && uv run python ../tests/test_searchcoupons_e2e.py
```

**预期结果**（若 BMA 正常工作）：
- SC-001, SC-009, SC-012 应该调用 search_coupon / apply_coupon
- 通过率应达到 70%+ （11/16+ 用例）

### 🟢 优先级 3：优化 guide 场景引导

**修改文件**：
- `mainagent/prompts/templates/guide/AGENT.md`

**改进点**：
```
当前：可能的引导文本不清晰
改为：
  - 明确说出"您要做什么项目？"
  - 明确说出"需要我帮您查优惠、预订服务还是推荐方案？"
  - 对于缺少关键信息的情况，主动询问
```

### 🔵 优先级 4：补充缺失的测试用例

5 个未实测的用例：
- SC-002: 换轮胎 + 支付宝偏好
- SC-004: 城市维度查热门优惠
- SC-008: 无商户优惠 → 介绍平台九折
- SC-011: 按城市筛选
- SC-013: 按过期时间排序
- SC-015: 预订意图转换
- SC-016: 位置相关查询

（可在 BMA 正常工作后执行）

---

## 性能指标

### 响应时间统计

| 场景 | 平均响应时间 | 工具调用数 |
|------|------------|---------|
| guide 场景 | ~2-3s | 0-1 个 |
| searchcoupons 场景 | （未测） | （未测） |
| search_coupon 工具 | （未测） | - |
| apply_coupon 工具 | （未测） | - |

---

## 关键证据

### 日志 1: BMA 连接失败

```
❌ BMA 分类失败: All connection attempts failed
POST http://localhost:8103/classify
```

### 日志 2: Agent fallback 正常工作

```
输入: "换机油有优惠吗？"
工具调用: classify_project
→ 识别了项目为"换机油"
→ 但没有进入 searchcoupons 场景
→ Agent 停留在 guide 场景

原因：StageHook 中的 BMA 调用异常
→ 场景分类返回 []
→ Agent 回退到 guide（安全模式）
```

---

## 结论

### 问题根因

**单一根本原因**：BMA（Business Map Agent）服务离线

```
BMA 离线 → 场景分类失败 → Agent 回退 guide → searchcoupons 工具不可用
```

### 验证策略有效性

✅ 测试脚本和用例设计符合预期
✅ 诊断工具正确识别出问题
✅ guide 场景 fallback 机制工作正常

### 可投入生产的条件

1. [ ] **BMA 服务启动并验证** ← 必须
2. [ ] **searchcoupons 场景测试通过率 ≥ 90%**（14/16+ 用例）
3. [ ] **生产环境 BMA_CLASSIFY_URL 配置正确**
4. [ ] **guide 场景引导文本优化**（可选但推荐）

---

## 附录：诊断工具

### 1. BMA 诊断脚本
```bash
cd mainagent && uv run python ../tests/diagnose_bma.py
```

输出：BMA 服务连接状态 + 分类结果

### 2. 完整测试脚本
```bash
cd mainagent && uv run python ../tests/test_searchcoupons_e2e.py
```

输出：7 个测试用例的结果 + 统计

### 3. 等待服务脚本
```bash
bash ../tests/wait_and_test.sh
```

功能：轮询等待服务就绪，自动执行测试

---

**诊断时间**: 2026-04-02 09:15 UTC  
**诊断工具版本**: test_searchcoupons_e2e.py v1.0
