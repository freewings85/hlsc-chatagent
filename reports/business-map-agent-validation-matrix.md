# BusinessMapAgent 验证矩阵

> 修订日期：2026-03-28
> 本矩阵将评审要求中的每个场景映射到具体测试，标注覆盖状态和覆盖类型。

---

## 状态标记说明

| 标记 | 含义 |
|------|------|
| ✅ Covered | 测试存在且通过 |
| ⚠️ Partial | 测试存在但仅覆盖部分场景 |
| ❌ Pending | 无测试，需要真实模型评估或真实 E2E |
| 🔧 Added | 本次新增的测试 |

---

## 1. 核心路由场景（Core Routing）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 直接表达路由（direct-expression） | test_navigator.py | test_shallow_navigation | ✅ Covered | Mocked Runtime — FunctionModel mock 模拟选择 project_saving |
| 模糊意图路由（fuzzy-intent） | test_navigator.py | test_deep_navigation | ✅ Covered | Mocked Runtime — FunctionModel mock 逐层下钻到 symptom_based |
| 症状描述路由（symptom-based） | test_navigator.py | test_deep_navigation | ⚠️ Partial | Mocked Runtime — mock 直接选择 symptom_based，但不验证真实 LLM 对症状描述的理解 |
| 商户搜索路由（merchant-search） | test_navigator.py | test_multi_path_navigation | ⚠️ Partial | Mocked Runtime — mock 返回 search 节点，不验证真实 LLM 的识别能力 |
| 预订/构建方案路由（booking/build-plan） | — | — | ❌ Pending | 无测试覆盖 booking 分支的 navigator 路由 |

**说明**：上述 Navigator 测试使用 FunctionModel mock，验证的是工具调用链和输出格式，不验证真实 LLM 面对实际用户表述时的路由准确性。每个场景的真实 LLM 准确性均为 ❌ Pending。

---

## 2. 模糊处理（Ambiguity Handling）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 信息不足时停在父节点 | test_navigator.py | test_stop_at_parent | ✅ Covered | Mocked Runtime — mock 模拟"不确定子节点"后输出父节点 ID |
| 不过度下钻到叶节点 | test_navigator.py | test_stop_at_parent | ⚠️ Partial | Mocked Runtime — mock 硬编码停在 project_saving，不验证真实 LLM 的判断阈值 |
| 处理混合信号不硬猜 | — | — | ❌ Pending | 需要真实 LLM 评估 |

---

## 3. 多路径路由（Multi-path Routing）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 同轮路由到 saving + merchant-search | test_navigator.py | test_multi_path_navigation | ✅ Covered | Mocked Runtime — mock 返回 confirm_saving, search |
| 同轮路由到 saving + merchant-search（切片组装） | test_business_map_assembler.py | TestAssembleSliceMultiPath (7 tests) | ✅ Covered | Unit — 验证多路径切片格式正确 |
| 祖先/后代去重 | test_business_map_assembler.py | TestAssembleSliceDedup (5 tests) | ✅ Covered | Unit — project_saving + fuzzy_intent 去重 |
| 祖先/后代去重 | test_business_map_e2e.py | TestMultiPathAssembly::test_ancestor_descendant_dedup | ✅ Covered | Component Integration |
| 深节点 + 跨分支节点同时输出 | test_business_map_e2e.py | TestMultiPathAssembly::test_cross_branch_deep_multi_path | ✅ Covered | Component Integration — fuzzy_intent（深度3）+ search（深度2）|
| 三分支同时命中 | test_business_map_e2e.py | TestMultiPathAssembly::test_three_branch_multi_path | ✅ Covered | Component Integration |

---

## 4. 多轮推进（Multi-turn Progression）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 浅到深渐进下钻 | test_business_map_e2e.py | TestProgressiveDrillDown (4 tests) | ✅ Covered | Component Integration — 验证 assemble_slice 在 project_saving → fuzzy_intent → merchant_search 的输出 |
| 项目确认后分支切换 | test_business_map_e2e.py | TestProgressiveDrillDown::test_round3_branch_switch | ✅ Covered | Component Integration — 验证切换到 merchant_search 后切片正确 |
| 已完成步骤的重新进入 | — | — | ❌ Pending | 需要真实多轮对话验证 |

**说明**：渐进下钻测试验证的是 `assemble_slice` 对不同 node_ids 输入的输出正确性。它不涉及 Navigator 的多轮定位决策，也不涉及状态树在真实对话中的演化。

---

## 5. 依赖与就绪场景（Dependency and Readiness）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 项目未确认就要求预订 | — | — | ❌ Pending | 需要真实 LLM 评估 Navigator 和 MainAgent 的行为 |
| 必需输入不足就搜索商户 | — | — | ❌ Pending | 需要真实 LLM 评估 |
| 下游已有进展后更换项目 | — | — | ❌ Pending | 需要真实多轮对话验证状态树回退 |

**说明**：依赖检查逻辑存在于 YAML 节点的 `depends_on` 字段和 MainAgent Prompt 中。当前测试验证了 `depends_on` 字段能被正确加载和格式化（`TestGetBusinessNodeDetail::test_detail_contains_depends_on`），但不验证 MainAgent 是否遵循这些依赖约束。

---

## 6. 状态树健壮性（State-tree Robustness）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 畸形缩进 | — | — | ❌ Pending | _compress_state_tree 使用简单行解析，不依赖缩进深度，但未专门测试畸形缩进 |
| 多个 [进行中] 等价标记 | test_business_map_e2e.py | TestCompressStateTree::test_full_state_tree | ⚠️ Partial | Unit — 测试了 [进行中] + ← 当前 的组合，但未测试非标准等价标记 |
| 缺少当前标记 | test_business_map_e2e.py | TestCompressStateTree::test_only_completed_items | ✅ Covered | Unit — 全部完成 → 无"当前在做"部分 |
| 输出包含箭头或特殊分隔符 | test_business_map_e2e.py | TestCompressStateTree::test_full_state_tree | ⚠️ Partial | Unit — 测试了 → 箭头在 [完成] 行中，但未测试其他特殊字符 |
| 从持久化状态恢复 | test_business_map_e2e.py | TestStateTreeServiceLifecycle (4 tests) | ✅ Covered | Unit — 写入/读取/覆盖/不存在 |
| 空状态树 | test_business_map_e2e.py | TestCompressStateTree::test_empty_state_tree | ✅ Covered | Unit |
| 全部未开始 | test_business_map_e2e.py | TestCompressStateTree::test_only_pending_items | ✅ Covered | Unit — 返回空简报 |
| 空白行干扰 | test_business_map_e2e.py | TestCompressStateTree::test_whitespace_only_lines_ignored | ✅ Covered | Unit |

---

## 7. 失败处理（Failure Handling）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| subagent 超时 | — | — | ❌ Pending | 未专门测试超时场景（但异常处理路径与下面的 exception 测试相同） |
| subagent 抛异常 | test_business_map_e2e.py | TestHookIntegration::test_call_subagent_exception_returns_empty | 🔧 Added | Mocked Runtime — ConnectionError → 空列表 |
| subagent 返回空输出 | test_business_map_e2e.py | TestHookIntegration::test_empty_string_response_no_slice | 🔧 Added | Mocked Runtime — 空字符串 → 不组装切片 |
| 无效 node_id | test_business_map_e2e.py | TestHookIntegration::test_invalid_node_ids_gracefully_ignored | 🔧 Added | Mocked Runtime — 无效 ID → assemble_slice 返回空 |
| 无效 node_id（切片层面） | test_business_map_assembler.py | TestAssembleSliceInvalidId (3 tests) | ✅ Covered | Unit — 无效 ID 被忽略，有效 ID 正常组装 |
| 重复 node_id | test_business_map_assembler.py | TestAssembleSliceDedup (5 tests) | ✅ Covered | Unit — 祖先-后代去重逻辑 |
| subagent 整轮不可用 | test_business_map_e2e.py | TestBusinessMapPreprocessorHook::test_call_hook_not_loaded_returns_early | ✅ Covered | Mocked Runtime — ensure_loaded 失败 → 直接返回 |
| assemble_slice 异常 | test_business_map_e2e.py | TestBusinessMapPreprocessorHook::test_call_hook_assemble_exception | ✅ Covered | Mocked Runtime — RuntimeError → 不崩溃，不存储切片 |
| navigator 返回畸形文本 | test_business_map_e2e.py | TestHookIntegration::test_malformed_response_parses_valid_ids_only | 🔧 Added | Mocked Runtime — 逗号分隔解析行为 |
| 服务未加载 | test_business_map_service.py | TestServiceNotLoaded (5 tests) | ✅ Covered | Unit — 各查询方法抛 RuntimeError |
| 服务未加载（工具层） | test_business_map_e2e.py | TestReadBusinessNodeTool::test_runtime_error_not_loaded | ✅ Covered | Unit |

---

## 8. 非目标与低信号输入（Non-target and Low-signal Inputs）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 闲聊/无关话题 | — | — | ❌ Pending | 需要真实 LLM 评估 Navigator 是否正确输出空或根节点 |
| 领域相关但不可操作的话题 | — | — | ❌ Pending | 需要真实 LLM 评估 |
| 模糊跟进语（"那个"、"好的"、"订了"、"那家店"） | — | — | ❌ Pending | 需要真实 LLM 评估多轮上下文理解 |

---

## 9. Hook 级集成（Section B — 评审要求）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 成功返回 node_id | test_business_map_e2e.py | TestHookIntegration::test_successful_node_id_slice_assembled | 🔧 Added | Mocked Runtime |
| 多个 node_id | test_business_map_e2e.py | TestHookIntegration::test_multiple_node_ids_multi_path_slice | 🔧 Added | Mocked Runtime |
| 无效 node_id | test_business_map_e2e.py | TestHookIntegration::test_invalid_node_ids_gracefully_ignored | 🔧 Added | Mocked Runtime |
| 空字符串响应 | test_business_map_e2e.py | TestHookIntegration::test_empty_string_response_no_slice | 🔧 Added | Mocked Runtime |
| 畸形响应 | test_business_map_e2e.py | TestHookIntegration::test_malformed_response_parses_valid_ids_only | 🔧 Added | Mocked Runtime |
| call_subagent 异常 | test_business_map_e2e.py | TestHookIntegration::test_call_subagent_exception_returns_empty | 🔧 Added | Mocked Runtime |
| 无状态树文件 | test_business_map_e2e.py | TestHookIntegration::test_missing_state_tree_briefing_empty | 🔧 Added | Mocked Runtime |
| 有状态树文件 | test_business_map_e2e.py | TestHookIntegration::test_existing_state_tree_briefing_contains_completed | 🔧 Added | Mocked Runtime |
| per-session 缓存隔离 | test_business_map_e2e.py | TestHookIntegration::test_per_session_cache_no_overwrite | 🔧 Added | Mocked Runtime |
| 超时 | — | — | ❌ Pending | 未专门测试，但 Exception 路径已覆盖 |
| 切片组装验证 | test_business_map_e2e.py | TestBusinessMapPreprocessorHook::test_call_hook_success_with_slice | ✅ Covered | Mocked Runtime |
| 状态树保留验证 | test_business_map_e2e.py | TestBusinessMapPreprocessorHook::test_call_hook_success_with_slice | ✅ Covered | Mocked Runtime — 验证 state_tree 被缓存 |
| 降级行为验证 | test_business_map_e2e.py | TestBusinessMapPreprocessorHook::test_call_hook_navigator_returns_empty | ✅ Covered | Mocked Runtime |

---

## 10. Session 隔离（Section C — 评审要求）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| A 开始 → B 开始 → formatter 读 A 仍是 A | test_business_map_e2e.py | TestSessionIsolation::test_interleaved_sessions_no_leak | 🔧 Added | Mocked Runtime |
| A/B 各收到不同切片，无交叉读取 | test_business_map_e2e.py | TestSessionIsolation::test_different_slices_no_cross_read | 🔧 Added | Mocked Runtime |
| A 有状态树 B 没有，无污染 | test_business_map_e2e.py | TestSessionIsolation::test_session_a_has_tree_b_does_not | 🔧 Added | Mocked Runtime |
| 多轮反复交替 | test_business_map_e2e.py | TestSessionIsolation::test_repeated_alternation_multiple_turns | 🔧 Added | Mocked Runtime — 5 轮交替 |
| asyncio Task 并发隔离（contextvars） | test_business_map_e2e.py | TestSessionIsolation::test_concurrent_tasks_session_isolation | 🔧 Added | Mocked Runtime — asyncio.create_task |
| 并发 hook 调用数据隔离 | test_business_map_e2e.py | TestSessionIsolation::test_concurrent_hook_calls_session_data_isolated | 🔧 Added | Mocked Runtime |

---

## 11. MainAgent 行为验证（Section D — Prompt 级真实模型评估）

> 注：以下评估通过手动构造 prompt + 手动注入 context + mock 工具 + 真实 LLM 完成，
> 属于 **prompt 级真实模型评估**，不是通过 `create_agent_app()` 的真实运行时验证。

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| [business_map_slice] 存在时下一问题跟随 checklist | run_mainagent_behavior_eval.py | S1 | ✅ Covered | Prompt 级真实模型评估 — 4/4 PASS |
| 节点完成时调用 update_state_tree | run_mainagent_behavior_eval.py | S2 | ⚠️ Partial | Prompt 级真实模型评估 — 调用不稳定（详见重复运行证据） |
| 需要详情时调用 read_business_node | run_read_business_node_eval.py | S5 | 🔧 Added | Prompt 级真实模型评估 — 详见第十节补充 |
| 无业务进展时不调用 update_state_tree | run_mainagent_behavior_eval.py | S4 | ✅ Covered | Prompt 级真实模型评估 — 4/4 PASS |
| 真实运行时验证（create_agent_app 路径） | — | — | ❌ Pending | 需要真实运行时集成测试 |

---

## 12. 真实模型 Navigator 评估（Section E — 已完成）

| 场景 | 测试文件 | 测试名 | 状态 | 覆盖类型 |
|------|----------|--------|------|----------|
| 离线评估数据集（75 样本） | navigator-eval-dataset.jsonl | — | ✅ Covered | 75 样本，7 个类别 |
| exact match rate | run_navigator_eval.py | — | ✅ Covered | 28.0% (21/75) |
| acceptable ancestor match rate | run_navigator_eval.py | — | ✅ Covered | 40.0% (30/75)，总可接受 68.0% |
| over-deep error rate | run_navigator_eval.py | — | ✅ Covered | 0.0% (0/75) |
| multi-path precision | run_navigator_eval.py | — | ✅ Covered | 0.821 |
| multi-path recall | run_navigator_eval.py | — | ⚠️ Partial | 0.119 — 远低于可接受水平，需 prompt 优化 |
| 严格输出格式合规率 | run_navigator_eval.py | — | ⚠️ Partial | 16.0% (12/75) — 需 prompt 优化 |
| 10 条真实多轮对话 replay | — | — | ❌ Pending | 未创建 |

---

## 汇总统计

| 覆盖类型 | 场景数 | ✅ Covered | ⚠️ Partial | 🔧 Added | ❌ Pending |
|----------|--------|-----------|-----------|---------|----------|
| 核心路由 | 5 | 2 | 2 | 0 | 1 |
| 模糊处理 | 3 | 1 | 1 | 0 | 1 |
| 多路径路由 | 6 | 6 | 0 | 0 | 0 |
| 多轮推进 | 3 | 2 | 0 | 0 | 1 |
| 依赖与就绪 | 3 | 0 | 0 | 0 | 3 |
| 状态树健壮性 | 8 | 5 | 2 | 0 | 1 |
| 失败处理 | 11 | 5 | 0 | 4 | 2 |
| 非目标输入 | 3 | 0 | 0 | 0 | 3 |
| Hook 级集成 | 13 | 3 | 0 | 9 | 1 |
| Session 隔离 | 6 | 0 | 0 | 6 | 0 |
| MainAgent 行为 | 5 | 2 | 1 | 1 | 1 |
| 真实模型评估 | 8 | 5 | 2 | 0 | 1 |
| **总计** | **74** | **31** | **8** | **20** | **15** |

**关键结论**：
- 代码层场景覆盖充分（多路径、状态树、失败处理、Hook 集成、Session 隔离）
- Navigator 真实模型评估已完成（75 样本），但精确匹配率和格式合规率需 prompt 优化
- MainAgent 行为已通过 prompt 级真实模型评估（4 场景），update_state_tree 调用稳定性需加固
- 仍有 15 个场景待验证：主要集中在依赖检查、非目标输入、多轮对话 replay 和真实运行时集成
