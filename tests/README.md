# searchcoupons 场景测试套件

**状态**: 已完成 - 等待 BMA 服务启动后重测  
**最后更新**: 2026-04-02  
**测试工程师**: Task #4

---

## 快速开始

### 1. 前置条件

```bash
# 确保这些服务在线：
http://127.0.0.1:8100/health    # MainAgent ✓ 已启动
http://localhost:8103/classify   # BMA （需启动）❌ 离线
```

### 2. 执行测试

```bash
# 方式 A: 等待服务就绪后自动测试（推荐）
bash tests/wait_and_test.sh

# 方式 B: 直接运行测试脚本
cd mainagent && uv run python ../tests/test_searchcoupons_e2e.py

# 方式 C: 运行 BMA 诊断
cd mainagent && uv run python ../tests/diagnose_bma.py
```

### 3. 查看结果

- **简明报告**: `tests/searchcoupons_test_report.md`
- **详细诊断**: `tests/DIAGNOSTIC_REPORT.md`
- **用例设计**: `tests/test_searchcoupons_cases.py`

---

## 文件说明

### 测试用例和脚本

| 文件 | 说明 | 用途 |
|------|------|------|
| `test_searchcoupons_cases.py` | 16 个测试用例设计 | 参考、手动测试 |
| `test_searchcoupons_e2e.py` | 实测脚本（7 个函数） | 自动化测试执行 |
| `diagnose_bma.py` | BMA 诊断工具 | 检查 BMA 分类功能 |
| `wait_and_test.sh` | 轮询 + 自动测试 | 等待服务就绪自动测试 |

### 报告

| 文件 | 说明 | 何时阅读 |
|------|------|--------|
| `searchcoupons_test_report.md` | 初步测试结果（3 PASS / 4 FAIL） | 了解当前测试状态 |
| `DIAGNOSTIC_REPORT.md` | 详细诊断 + 根因分析 | 理解 BMA 离线问题 |
| `README.md` | 本文件 | 快速上手 |

---

## 测试用例覆盖范围

### 16 个完整设计的测试用例

#### 1. 明确项目查优惠 (2 个)
- **SC-001**: 换机油有优惠吗 → search_coupon(project_ids=['油耗'])
- **SC-002**: 换轮胎 + 支付宝偏好 → semantic_query 包含支付方式

#### 2. 无项目查优惠 (2 个)
- **SC-003**: "有什么优惠活动吗" → 引导确认项目
- **SC-004**: "北京现在有什么优惠" → 按城市查热门

#### 3. Semantic_query 多轮累积 (3 个)
- **SC-005**: 轮 1: "换机油的优惠"
- **SC-006**: 轮 2: 添加"支付宝的"
- **SC-007**: 轮 3: 添加"送洗车的"

#### 4. 没查到商户优惠 (1 个)
- **SC-008**: 无商户优惠 → 介绍平台九折

#### 5. Apply_coupon 流程 (2 个)
- **SC-009**: 选优惠 + 时间 → 生成联系单
- **SC-010**: 缺时间 → 引导确认

#### 6. 城市筛选 (1 个)
- **SC-011**: 上海做保养有什么优惠

#### 7. 排序需求 (2 个)
- **SC-012**: 最便宜的优惠 → sort_by='discount_amount'
- **SC-013**: 快要过期的 → sort_by='validity_end'

#### 8. 模糊查询 (1 个)
- **SC-014**: "有没有什么好的活动" → 引导明确

#### 9. 预订意图转换 (1 个)
- **SC-015**: 用户想预订 → 转换到预订流程

#### 10. 位置相关 (1 个)
- **SC-016**: "附近的优惠" → 按城市筛选

---

## 当前测试结果

### 执行摘要

```
总用例数: 16
实测用例: 7
通过: 3 (SC-003, SC-010, SC-014)
失败: 4 (SC-001, SC-005/006/007, SC-009, SC-012)
未测: 5 (需 BMA 启动后补测)
```

### 通过率分析

| 场景 | 通过率 | 说明 |
|------|--------|------|
| guide 场景 | 100% | 引导逻辑正确 ✓ |
| searchcoupons 场景 | 0% | BMA 离线，无法路由 ✗ |

### 根本原因

**BMA 服务离线** → 无法分类为 searchcoupons 场景 → Agent 回退 guide 场景 → search_coupon 工具不可用

---

## 诊断结果

### ✅ 已验证

- [x] MainAgent 服务运行正常（127.0.0.1:8100）
- [x] 工具函数已注册（search_coupon, apply_coupon）
- [x] searchcoupons 场景配置完整
- [x] Mock 数据加载成功（2001-2005 商户 + 1001-1002 平台）
- [x] Guide 场景 fallback 机制正常

### ❌ 被 Block 的验证

- [ ] BMA 服务在线（❌ localhost:8103 无响应）
- [ ] search_coupon 功能（需 BMA 启动）
- [ ] apply_coupon 功能（需 BMA 启动）
- [ ] 多轮对话 semantic_query 累积（需 BMA 启动）

---

## 后续行动

### 🔴 优先级 1: 启动 BMA

**检查 BMA 状态**:
```bash
curl http://localhost:8103/classify \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"message":"换机油有优惠吗？"}'

# 期望返回
# {"scenes":["searchcoupons"]}  或其他场景
```

**启动 BMA**（命令需确认）:
```bash
cd extensions && uv run python -m business_map_agent.main
# 或
docker run -p 8103:8103 hlsc-bma:latest
```

### 🟡 优先级 2: 重新执行完整测试

```bash
cd mainagent && uv run python ../tests/test_searchcoupons_e2e.py
```

**预期通过率**: 70-90%（取决于 searchcoupons 场景实现）

### 🟢 优先级 3: 补充缺失的 5 个用例

```
SC-002, SC-004, SC-008, SC-011, SC-013, SC-015, SC-016
```

---

## 性能指标

### 响应时间 (ms)

| 用例 | 响应时间 | 工具调用 |
|------|---------|--------|
| SC-001（预期） | ~500-1000 | classify_project + search_coupon |
| SC-003（实际） | ~3120 | 无（guide 场景） |
| SC-010（实际） | ~70 | 无（guide 场景） |

---

## 常见问题

### Q: 为什么 search_coupon 没有被调用?

**A**: BMA 离线导致场景分类失败。Agent 回退到 guide 场景，没有 searchcoupons prompt。

### Q: 如何验证 BMA 是否正常工作?

**A**: 
```bash
cd mainagent && uv run python ../tests/diagnose_bma.py
```

如果输出 `❌ All connection attempts failed`，说明 BMA 离线。

### Q: 如何确保 searchcoupons 场景被正确加载?

**A**: 检查 Agent 日志中的 `current_scene` 字段：
```
current_scene=searchcoupons  ✓ 正确
current_scene=guide         ✗ 说明 BMA 失败
```

### Q: 测试脚本是否可以用其他方式运行?

**A**: 是的，三种方式都可以：
```bash
# 方式 1: 自动等待 + 测试
bash tests/wait_and_test.sh

# 方式 2: 直接运行
cd mainagent && uv run python ../tests/test_searchcoupons_e2e.py

# 方式 3: 在 IDE 中运行 test_searchcoupons_e2e.py
```

---

## 联系方式

- **测试框架**: Task #4 (sc-val-tester)
- **问题反馈**: 见 DIAGNOSTIC_REPORT.md

---

## 版本历史

| 版本 | 日期 | 内容 |
|------|------|------|
| v1.0 | 2026-04-02 | 初始版本 - 16 个用例 + 诊断 |

---

## 相关文档

- `mainagent/prompts/templates/searchcoupons/AGENT.md` — searchcoupons 场景 prompt
- `mainagent/prompts/templates/searchcoupons/OUTPUT.md` — 输出格式规范
- `extensions/hlsc/tools/prompts/search_coupon.md` — search_coupon 工具说明
- `extensions/hlsc/tools/prompts/apply_coupon.md` — apply_coupon 工具说明
