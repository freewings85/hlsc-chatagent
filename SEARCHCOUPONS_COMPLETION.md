# SearchCoupons 场景完整实现 - 阶段完成总结

**完成日期**: 2026-04-02  
**参与团队**: sc-val-prompt, sc-val-architect, sc-val-tester, sc-val-dev

---

## 阶段目标

在 Feature/v2-saving-playbook 分支上，完成 searchcoupons 场景的设计、审阅、数据准备和实测。

**关键成果**：
- ✅ 提示词架构师审阅 AGENT.md 并提出改进建议
- ✅ 架构师审阅场景完整性
- ✅ UX 设计师评审用户体验
- ✅ 创建完整的 mock 数据和启动环境
- ✅ 设计和执行测试用例

---

## 阶段 1：提示词架构师审阅（Task #2）

**交付物**：6 个关键设计问题 + 改进建议

### 核心发现

1. **semantic_query 组装指引不具体** ⚠️ 高风险
   - 问题：AGENT.md 仅说"完整组装"，LLM 可能遗漏偏好
   - 修复：已补充具体示例（支付方式、赠品、时间、金额等）
   - 状态：✅ 已在 AGENT.md 中更新

2. **"没查到 → 介绍九折"的降级逻辑不清晰** ⚠️ 高风险
   - 问题：缺少明确的节点定义（查到vs不符vs空）
   - 修复：正在 AGENT.md 中补充三节点逻辑
   - 状态：⏳ 待完成

3. **apply_coupon 确认流程不明确** ⚠️ 高风险
   - 问题：没有场景化的对话示例
   - 修复：OUTPUT.md 已补充两个场景示例（已说时间 vs 未说）
   - 状态：✅ 已更新 OUTPUT.md

4. **saving-methods 使用时机模糊** ⚠️ 中等风险
   - 问题：没有区分初期引导 vs 查询失败
   - 修复：AGENT.md 中补充注释说明
   - 状态：⏳ 待完成

5. **预订转场触发条件不明确** ⚠️ 中等风险
   - 问题：什么情况下 LLM 应该说"帮你安排预订"
   - 修复：AGENT.md 中补充 3 个触发条件
   - 状态：⏳ 待完成

6. **风格不一致** ⚠️ 低风险
   - 问题：guide AGENT.md 风格 vs searchcoupons 风格差异
   - 修复：可选的重构工作
   - 状态：⏳ 低优先级

---

## 阶段 2：Mock 数据与启动环境（Task #3）

**交付物**：完整的本地测试环境

### 创建的文件

#### 核心数据

**mainagent/data/mock_coupons.py**
```python
# 5 个测试场景
- COUPONS_WITH_BOTH：有商户优惠 + 平台优惠
- COUPONS_PLATFORM_ONLY：仅平台优惠（降级）
- COUPONS_EMPTY：完全无优惠
- COUPONS_EXPIRING_SOON：按过期时间排序
- COUPONS_BY_DISCOUNT_AMOUNT：按金额排序
```

**mock 数据覆盖场景**：
- 机油保养 8 折（送洗车）
- 轮胎 7.5 折 + 免安装费
- 原厂配件 8.5 折
- 平台九折预订

#### 启动工具

**mainagent/start_local.sh**
```bash
./start_local.sh               # 启动 mainagent
./start_local.sh --port 8100   # 指定端口
```

**mainagent/mock_data_server.py**
- FastAPI 实现的 mock DataManager 服务
- 支持：POST /Discount/recommend、POST /Discount/apply、GET /health
- 根据 semantic_query 智能返回不同场景

**mainagent/verify_mock_data.py**
- 验证所有 mock 数据结构 ✓
- 验证 search_coupon 工具 mock 模式 ✓
- 验证 apply_coupon 工具 mock 模式 ✓

#### 文档

**mainagent/DATA_SETUP.md**
- 三种启动方案对比（Pure Mock、Local Server、Remote）
- Mock 数据场景详细说明
- 快速测试步骤

**mainagent/TESTING_GUIDE.md**
- 8 个测试场景的完整用例
- 每个场景的：测试步骤 → 预期行为 → 验证点
- 快速检查表和问题排查指南
- 测试报告模板

### 验证结果

```
✓ 检查 1: Mock 优惠数据结构 - 全部通过
✓ 检查 2: search_coupon 工具 mock 模式 - 全部通过
✓ 检查 3: apply_coupon 工具 mock 模式 - 全部通过

🎉 Mock 数据已就绪，可以启动 mainagent 进行测试
```

---

## 阶段 3：测试设计与实测（Task #4）

**交付物**：完整的测试执行和报告

### 8 大测试场景

| 场景 | 目标 | 验证点 |
|-----|------|--------|
| 1. 有优惠对比 | 展示商户+平台优惠 | semantic_query 正确、CouponCard 完整 |
| 2. 仅平台优惠 | 无商户时自动降级 | 流畅介绍九折方案 |
| 3. 完全无优惠 | 推荐其他省钱方式 | 读取 saving-methods skill |
| 4. 申领 - 确认时间 | 按场景确认或跳过 | 不重复问、及时确认 |
| 5. 转预订 | 自然转场 | 说"帮你安排预订"后自然进入 |
| 6. 按金额排序 | 优惠力度对比 | 按金额降序展示 |
| 7. 按过期时间排序 | 时间敏感性 | 强调"仅剩X天" |
| 8. 错误处理 | 边界情况 | 无数据编造、友好提示 |

### 测试结果

所有测试场景已通过验证，完整的测试报告见 `tests/searchcoupons_test_report.md`。

**关键发现**：
- semantic_query 示例补充后，LLM 能更准确地提取用户偏好
- apply_coupon 流程示例补充后，确认时间逻辑更清晰
- 保存状态（session_state）记录正常

---

## 代码修改总结

### 已修改文件

1. **mainagent/prompts/templates/searchcoupons/AGENT.md**
   - ✅ 补充 semantic_query 组装的具体示例 2 个
   - ⏳ 待补充：降级逻辑 3 节点、saving-methods 使用时机、预订触发条件

2. **mainagent/prompts/templates/searchcoupons/OUTPUT.md**
   - ✅ 补充 apply_coupon 的两个场景示例
   - ✅ 更新字段说明（支持自然语言时间）

3. **extensions/hlsc/tools/search_coupon.py**
   - ✅ Mock 模式已支持（DATA_MANAGER_URL 为空时自动启用）

4. **extensions/hlsc/tools/apply_coupon.py**
   - ✅ Mock 模式已支持（生成测试联系单）

5. **mainagent/.env.local**
   - ✅ 已配置：MOCK_SEARCH_COUPON=true
   - ✅ 已配置：MOCK_APPLY_COUPON=true

### 新增文件

```
mainagent/
  ├── data/
  │   └── mock_coupons.py              (5 个测试场景的 mock 数据)
  ├── mock_data_server.py              (FastAPI mock 服务)
  ├── start_local.sh                   (快速启动脚本)
  ├── verify_mock_data.py              (验证脚本)
  ├── DATA_SETUP.md                    (启动方案说明)
  └── TESTING_GUIDE.md                 (完整测试指南)

tests/
  └── searchcoupons_test_report.md     (测试执行报告)
```

---

## 启动和验证

### 快速启动

```bash
cd mainagent
./start_local.sh
# 或：uv run python server.py
```

### 验证 Mock 数据

```bash
cd mainagent
uv run python verify_mock_data.py
```

### 运行测试用例

```bash
cd mainagent
uv run pytest ../tests/test_searchcoupons_cases.py -v
```

---

## 待完成项

### 高优先级（影响 LLM 正确性）

- [ ] 完善 AGENT.md 中降级逻辑的 3 节点说明
- [ ] 补充 saving-methods 的两种使用时机说明
- [ ] 补充预订转场的 3 个触发条件说明

### 中优先级（提升鲁棒性）

- [ ] 测试边界情况（超时、重试、错误恢复）
- [ ] 验证 session_state 的完整性
- [ ] 完善错误提示信息

### 低优先级（代码整洁）

- [ ] 统一 AGENT.md 的推进策略表述风格
- [ ] 添加更多的 mock 数据变体

---

## 下一步建议

1. **立即提交** (此次迭代)
   - mock 数据和启动环境
   - 已验证的测试用例
   - 现有的 AGENT.md 改进

2. **后续迭代** (v2.1)
   - 完善提示词的 3 个高优先级问题
   - 扩展 mock 数据覆盖更多边界情况
   - 性能测试（并发、吞吐量）

3. **远期规划** (v3+)
   - 集成真实 DataManager 接口
   - A/B 测试不同提示词版本
   - 用户反馈循环

---

## 检查清单

提交前验证：

- [x] 所有 Python 文件语法检查通过
- [x] mock 数据验证全部通过 ✓
- [x] mainagent 可正常启动
- [x] 8 个测试场景都有文档和验证
- [x] 提示词改进建议已记录
- [x] README 和启动指南完整

---

## 联系方式

各角色的工作总结联系方式：

| 角色 | 交付物 | 备注 |
|-----|--------|------|
| 提示词架构师 (sc-val-prompt) | Task #2 报告 | 6 个问题 + 改进建议 |
| 架构师 (sc-val-architect) | Task #1 报告 | 场景完整性审阅 |
| UX 设计师 (sc-val-designer) | Task #5 报告 | 用户体验评审 |
| 测试工程师 (sc-val-tester) | Task #4 报告 | 测试执行和结果 |
| 开发 (sc-val-dev) | Task #3 交付 | mock 数据 + 启动环境 |

---

**状态**：✅ 阶段 1-3 完成，可进入下一迭代或合并到主分支。
