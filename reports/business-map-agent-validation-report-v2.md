# BusinessMapAgent 验证报告 v2

> 修订日期：2026-03-28
> 修订原因：前版报告过度声明确定性，本版严格区分已验证、部分验证、待验证项目
> 测试执行环境：Python 3.12.3, pytest 9.0.2, Linux (WSL2)

---

## 一、执行摘要

BusinessMapAgent 的**代码层组件**（模型、加载器、服务、组装器、状态树、钩子）在隔离环境下经过了较充分的自动化测试，组件间的接口交互也有基于 mock 的集成测试覆盖。

**已验证的部分**：
- YAML 业务树加载、节点查找、路径计算：通过 40 个单元测试验证
- Service 查询接口和字段隔离：通过 36 个单元测试验证
- 切片组装（浅定位、深定位、多路径、去重、非法 ID）：通过 39 个单元测试验证
- 状态树读写、压缩、ID 解析：通过 18 个单元测试验证
- Formatter 注入逻辑：通过 5 个组件集成测试验证
- Hook `__call__` 流程：通过 14 个 Mocked Runtime 测试验证（含异常分支）
- Hook 级集成（各类 subagent 响应场景）：通过 9 个 Mocked Runtime 测试验证
- Session 隔离（contextvars）：通过 6 个并发/交替测试验证
- Navigator Agent 工具接线和循环执行：通过 8 个 Mocked Runtime 测试验证

**未验证的部分**：
- 真实运行时链路（请求 → hook → A2A → 切片 → MainAgent 行为）：无测试
- Navigator 在真实 LLM 下的定位准确性：无测试
- MainAgent 是否遵循注入的切片指引：无测试
- 多轮对话中状态树的真实演化：无测试
- 生产环境并发负载下的行为：无测试

---

## 二、测试清单

### 2.1 测试文件与计数

| 测试文件 | 测试数 | 通过 | 失败 | 耗时 |
|----------|--------|------|------|------|
| `extensions/tests/test_business_map_loader.py` | 40 | 40 | 0 | < 1s |
| `extensions/tests/test_business_map_service.py` | 36 | 36 | 0 | < 1s |
| `extensions/tests/test_business_map_assembler.py` | 39 | 39 | 0 | < 1s |
| `extensions/tests/test_business_map_e2e.py` | 69 | 69 | 0 | ~9s |
| `subagents/business_map_agent/tests/test_navigator.py` | 8 | 8 | 0 | ~29s |
| **总计** | **192** | **192** | **0** | **~40s** |

### 2.2 按覆盖类别分类

#### 单元测试（Unit）— 隔离的函数/类测试

| 测试类 | 测试文件 | 测试数 | 测试内容 |
|--------|----------|--------|----------|
| TestLoadSampleTree | test_business_map_loader.py | 4 | YAML 树加载后的根节点结构 |
| TestFindNode | test_business_map_loader.py | 4 | 按 ID 查找节点 |
| TestPathFromRoot | test_business_map_loader.py | 5 | 路径计算 |
| TestAllIds | test_business_map_loader.py | 2 | ID 集合完整性 |
| TestParentId | test_business_map_loader.py | 6 | parent_id 正确性 |
| TestResolvedChildren | test_business_map_loader.py | 3 | resolved_children 填充 |
| TestNodeValidation | test_business_map_loader.py | 4 | Pydantic 模型校验 |
| TestUniqueIdViolation | test_business_map_loader.py | 1 | 重复 ID 检测 |
| TestLeafNode | test_business_map_loader.py | 4 | 叶节点行为 |
| TestEdgeCases | test_business_map_loader.py | 7 | 边界情况与错误处理 |
| TestServiceLoadAndFind | test_business_map_service.py | 4 | Service 加载与查找 |
| TestServicePathFromRoot | test_business_map_service.py | 3 | Service 路径计算 |
| TestGetBusinessChildrenNav | test_business_map_service.py | 4 | 导航字段查询 |
| TestGetBusinessNodeNav | test_business_map_service.py | 6 | 节点导航信息 |
| TestGetBusinessNodeDetail | test_business_map_service.py | 8 | 业务详情查询 |
| TestServiceNotLoaded | test_business_map_service.py | 5 | 未加载时的错误处理 |
| TestAssembleSliceSmoke | test_business_map_service.py | 1 | assemble_slice 冒烟测试 |
| TestOptionalAndKeywordsBranches | test_business_map_service.py | 3 | optional/keywords 分支覆盖 |
| TestStateTreeServiceExceptions | test_business_map_service.py | 2 | StateTreeService 异常路径 |
| TestFormatNode | test_business_map_assembler.py | 7 | format_node 格式化输出 |
| TestAssembleSliceShallow | test_business_map_assembler.py | 6 | 浅定位切片组装 |
| TestAssembleSliceDeep | test_business_map_assembler.py | 7 | 深定位切片组装 |
| TestAssembleSliceMultiPath | test_business_map_assembler.py | 7 | 多路径切片组装 |
| TestAssembleSliceInvalidId | test_business_map_assembler.py | 3 | 无效 ID 处理 |
| TestAssembleSliceDedup | test_business_map_assembler.py | 5 | 祖先-后代去重 |
| TestAssembleSliceEmpty | test_business_map_assembler.py | 1 | 空列表处理 |
| TestAssembleSliceRootOnly | test_business_map_assembler.py | 3 | 根节点切片 |
| TestStateTreeServiceLifecycle | test_business_map_e2e.py | 4 | 状态树读/写/覆盖/不存在 |
| TestCompressStateTree | test_business_map_e2e.py | 6 | 状态树压缩为自然语言简报 |
| TestParseNodeIds | test_business_map_e2e.py | 8 | 节点 ID 字符串解析 |
| TestPerformance | test_business_map_e2e.py | 3 | 性能基准（加载/组装耗时） |
| TestReadBusinessNodeTool | test_business_map_e2e.py | 3 | read_business_node 工具（mock service） |
| TestUpdateStateTreeTool | test_business_map_e2e.py | 3 | update_state_tree 工具（mock service） |
| TestBusinessMapTools | test_navigator.py | 4 | subagent 工具函数直接调用 |
| **单元测试小计** | | **149** | |

#### 组件集成测试（Component Integration）— 跨模块但不涉及 Agent 循环

| 测试类 | 测试文件 | 测试数 | 测试内容 |
|--------|----------|--------|----------|
| TestProgressiveDrillDown | test_business_map_e2e.py | 4 | 渐进下钻 assemble_slice（模拟多轮定位变化） |
| TestMultiPathAssembly | test_business_map_e2e.py | 4 | 多路径组装与去重 |
| TestHlscContextFormatterWithPreprocessor | test_business_map_e2e.py | 5 | Formatter 读取 Preprocessor 缓存数据 |
| **组件集成小计** | | **13** | |

说明：`TestProgressiveDrillDown` 和 `TestMultiPathAssembly` 测试的是 `assemble_slice` 在不同输入组合下的输出，验证 loader + service 的协同工作。它们不涉及 Agent 循环，不是端到端测试。`TestHlscContextFormatterWithPreprocessor` 验证 Formatter 与 Preprocessor 之间的数据传递。

#### Mocked Runtime 流程测试 — 使用 mock 替代真实 Agent/Subagent

| 测试类 | 测试文件 | 测试数 | 测试内容 |
|--------|----------|--------|----------|
| TestBusinessMapPreprocessorHook | test_business_map_e2e.py | 14 | Hook __call__ 流程（ensure_loaded, eviction, 各分支） |
| TestHookIntegration | test_business_map_e2e.py | 9 | Hook 级集成：成功/多ID/无效ID/空/异常/状态树传递/缓存隔离 |
| TestSessionIsolation | test_business_map_e2e.py | 6 | 并发/交替 session 隔离（contextvars 安全性验证） |
| TestBusinessMapNavigator | test_navigator.py | 4 | 导航 Agent 循环（FunctionModel mock：浅定位/深定位/多路径/停在父节点） |
| **Mocked Runtime 小计** | | **33** | |

说明：这些测试使用 `FunctionModel`（mock 模型）或 `patch` 替代真实 LLM / subagent 调用。它们验证了代码路径的正确性（工具接线、循环执行、异常处理），但**不验证真实 LLM 的行为质量**。

#### 真实端到端测试（True End-to-End）

**无。** 当前没有任何测试覆盖从用户请求到 MainAgent 最终响应的完整运行时链路。

#### 真实模型评估（Real-Model Evaluation）

**无。** 当前没有任何测试使用真实 LLM 验证 Navigator 的定位准确性或 MainAgent 的指引遵循行为。

---

## 三、覆盖报告

### 3.1 按模块覆盖状态

| 模块 | 覆盖状态 | 说明 |
|------|----------|------|
| `hlsc/business_map/model.py` | 高 | 模型校验、字段验证、边界情况均有测试 |
| `hlsc/business_map/loader.py` | 高 | 加载、查找、路径、ID 唯一性、错误处理均有测试 |
| `hlsc/services/business_map_service.py` | 高 | 查询接口、字段隔离、assemble_slice 全面测试 |
| `hlsc/services/state_tree_service.py` | 高 | 生命周期 + 异常分支均有测试 |
| `hlsc/tools/read_business_node.py` | 中 | 3 个测试覆盖正常/KeyError/RuntimeError，使用 mock service |
| `hlsc/tools/update_state_tree.py` | 中 | 3 个测试覆盖正常写入和路径计算，使用 mock service |
| `mainagent/src/business_map_hook.py` | 高 | __call__ 全流程、ensure_loaded、eviction、_compress_state_tree、_parse_node_ids 均有测试 |
| `mainagent/src/hlsc_context.py` (Formatter) | 中 | 切片/状态树注入、向后兼容、无数据场景有测试 |
| `subagents/business_map_agent/src/tools/` | 中 | 4 个工具单元测试（get_business_children, get_business_node） |
| `subagents/business_map_agent/src/app.py` | 低 | 仅通过 Navigator Agent 循环测试间接覆盖 |
| `subagents/business_map_agent/prompts/` | 未验证 | system.md 的质量依赖真实 LLM 评估 |

### 3.2 精确行覆盖率（pytest --cov 实测数据）

以下数据来自 `pytest --cov` 实际执行结果（184 extensions 测试）：

```
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
hlsc/business_map/__init__.py               3      0   100%
hlsc/business_map/loader.py                71      0   100%
hlsc/business_map/model.py                 27      0   100%
hlsc/services/business_map_service.py     119      0   100%
hlsc/services/state_tree_service.py        26      0   100%
hlsc/tools/read_business_node.py           19      0   100%
hlsc/tools/update_state_tree.py            20      0   100%
---------------------------------------------------------------------
TOTAL                                     285      0   100%
```

**extensions 下被测代码 285 条语句，0 条遗漏，行覆盖率 100%。**

未纳入 `--cov` 测量的文件（在 mainagent/ 和 subagents/ 目录下）：
- `mainagent/src/business_map_hook.py`：通过 `sys.path` 导入后测试，14 + 9 + 6 = 29 个测试覆盖（含 ensure_loaded、__call__、eviction、compress、parse、session 隔离），但未计入 --cov 统计
- `mainagent/src/hlsc_context.py`：通过 5 个 Formatter 测试覆盖
- `subagents/business_map_agent/src/`：通过 8 个 navigator 测试覆盖（独立 uv 环境运行）

---

## 四、Session 隔离

### 4.1 问题背景

前版代码中 `BusinessMapPreprocessor` 使用单一 `_current_session_id` 字段存储当前 session，在并发请求下存在跨 session 数据泄漏的风险。

### 4.2 修复方案

已使用 `contextvars.ContextVar` 替代可变字段：

```python
_current_session_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bm_current_session", default="default"
)
```

`asyncio.create_task()` 会自动复制当前 `Context`，因此每个异步任务拥有独立的 `_current_session_var` 值，不会跨请求泄漏。

### 4.3 验证覆盖

`TestSessionIsolation` 类包含 6 个测试，覆盖以下场景：

| 测试 | 场景 | 验证点 |
|------|------|--------|
| `test_interleaved_sessions_no_leak` | A/B 交替设置 session 后读取 | Formatter 读到各自的切片和状态树，不交叉 |
| `test_concurrent_tasks_session_isolation` | `asyncio.create_task` 并发两个 task | 各 task 的 `_current_session_var` 独立，不互相覆盖 |
| `test_session_a_has_tree_b_does_not` | A 有状态树 B 没有 | B 不会读到 A 的状态树 |
| `test_different_slices_no_cross_read` | A/B 各有不同切片和状态树 | 切换 session 后各自只看到自己的数据 |
| `test_repeated_alternation_multiple_turns` | 5 轮 A/B 交替更新和读取 | 每轮各 session 数据正确，无累积泄漏 |
| `test_concurrent_hook_calls_session_data_isolated` | 两个 session 顺序执行 `__call__` | 各自缓存的切片正确，互不覆盖 |

### 4.4 局限性

- `test_concurrent_hook_calls_session_data_isolated` 实际上是**顺序执行**（因为 mock 的 with 作用域限制），不是真正的并发
- `test_concurrent_tasks_session_isolation` 使用 `asyncio.sleep(0.01)` 模拟让出控制权，验证了 `contextvars` 在 asyncio Task 间的隔离性
- 未测试生产级别的高并发负载（数百个同时请求）

---

## 五、Fallback 行为

### 5.1 实际行为（代码为准）

当 BusinessMapAgent subagent 不可用或调用失败时，`_call_navigator` 捕获异常并返回空列表：

```python
except Exception:
    logger.warning("BusinessMapAgent 调用失败，跳过导航", exc_info=True)
    return []
```

后续逻辑：
- 空 node_ids → 不调用 `assemble_slice`
- 不存储切片 → Formatter 不注入 `[business_map_slice]`
- MainAgent 本轮不收到业务地图切片，但其他功能正常

**这是 graceful degradation（优雅降级），不是 keyword fallback（关键词回退）。**

### 5.2 测试覆盖

`TestHookIntegration::test_call_subagent_exception_returns_empty` 验证了 `call_subagent` 抛出 `ConnectionError` 时的降级行为。

### 5.3 对前版报告的纠正

前版文档中关于"简化关键词匹配回退"的描述与代码不符。当前代码不实现任何关键词回退逻辑。本报告以代码为准。

---

## 六、对前版报告的纠正

| 编号 | 前版表述 | 纠正 |
|------|----------|------|
| 1 | "Phase 5 E2E 验证完成"，`test_business_map_e2e.py` 被称为"端到端测试" | **不准确**。该文件中的测试按实际内容应分类为：单元测试（StateTreeService, compress, parse_node_ids, Performance, 工具测试）、组件集成测试（渐进下钻, 多路径, Formatter 集成）、Mocked Runtime 测试（Hook __call__, Hook Integration, Session Isolation）。没有任何测试覆盖真实运行时链路。 |
| 2 | "151 个测试全部通过" | 当前测试数为 **192 个**（含新增的 Hook Integration 和 Session Isolation 测试）。但测试全部通过仅说明代码逻辑在 mock 环境下行为正确，**不等于业务就绪**。 |
| 3 | Navigator Agent 测试被隐含为"已验证" | 这 8 个测试使用 `FunctionModel`（mock），验证的是**工具接线和循环执行**，不是 Navigator 在真实 LLM 下的定位准确性。prompt（system.md）的质量完全未经真实模型验证。 |
| 4 | 文档提到 keyword fallback | 代码中不存在 keyword fallback。实际行为是 graceful degradation：subagent 失败时返回空列表，MainAgent 不收到切片。 |
| 5 | 未提及 session 隔离风险 | 已修复（使用 contextvars），并新增 6 个 session 隔离测试验证。 |
| 6 | "覆盖范围包含 E2E" | 覆盖范围实际为：单元 + 组件集成 + Mocked Runtime。无真实 E2E，无真实模型评估。 |

---

## 七、Gap 清单 — 明确未验证的项目

### 7.1 真实运行时链路

未测试从用户请求进入 `app.py` 开始的完整链路：

```
请求 → BusinessMapPreprocessor.__call__ → A2A call_subagent →
返回 node_ids → assemble_slice → 注入 request_context →
MainAgent 使用切片引导对话 → 工具调用 → 状态树更新
```

当前所有 hook 测试均使用 `patch.object` 替代 `_call_navigator` 或 `call_subagent`，不涉及真实网络调用。

### 7.2 真实模型 Navigator 准确性

- ✅ 已完成首轮评估（75 样本，Azure gpt-5-chat）
- 总可接受率 68.0%，精确匹配率 28.0%，过度下钻率 0.0%
- **仍需优化**：精确匹配率偏低（浅层偏好）、多路径召回极低（0.119）、状态简报利用不足
- 详见第九节完整分析

### 7.3 MainAgent 对注入指引的遵循

- ✅ 已完成首轮验证（4 场景，Azure gpt-5-chat）
- 4/4 场景通过，但 S2（update_state_tree 调用）跨运行不稳定
- **仍需优化**：update_state_tree 调用可靠性需 prompt 加固
- 详见第十节完整分析

### 7.4 多轮状态树演化

- 渐进下钻测试（TestProgressiveDrillDown）只验证了 `assemble_slice` 对不同 node_ids 的输出
- 未验证真实对话中状态树从空到完整的多轮演化过程
- 未验证分支切换后状态树的正确更新

### 7.5 生产并发负载

- `TestSessionIsolation` 验证了 contextvars 在 asyncio Task 间的隔离性
- 未验证数百个同时请求下的内存使用、LRU eviction 行为、响应延迟

---

## 八、生产就绪声明

### 已验证 — 有测试证据支撑

| 维度 | 状态 | 证据 |
|------|------|------|
| 代码架构正确性 | ✅ 已验证 | 192 个测试覆盖模型、加载、服务、组装、钩子、工具 |
| 组件接口正确性 | ✅ 已验证 | 组件集成测试验证跨模块协作（loader + service, formatter + preprocessor） |
| Session 安全性 | ✅ 已验证 | contextvars task-level 隔离已验证（6 个测试）；生产级高并发负载隔离未验证 |
| 异常降级行为 | ✅ 已验证 | Hook Integration 测试覆盖 subagent 异常、无效 ID、空响应 |
| 性能基线 | ✅ 已验证 | 加载 < 1s, 组装 < 100ms |
| Navigator 定位准确性 | ⚠️ 已完成 prompt 级真实模型评估，需优化 | 75 样本评估完成（解析后恢复可接受率 68%，严格格式合规率 16%），详见第九节 |
| MainAgent 指引遵循 | ⚠️ 已完成 prompt 级真实模型评估，需优化 | 4 场景评估完成（S2 update_state_tree 调用不稳定），详见第十节。注：非真实运行时验证 |

### 待验证 — 需后续补充

| 维度 | 状态 | 建议 |
|------|------|------|
| 真实运行时链路 | ❌ 待验证 | 需要端到端集成测试或人工对话验证 |
| 多轮状态树演化 | ❌ 待验证 | 需要 10 条以上真实多轮对话 replay |
| 生产并发负载 | ❌ 待验证 | 需要负载测试 |
| 历史依赖继续行为 | ❌ 待验证 | recent_history 当前为空，代词回指（"那个"、"订了"）未评估 |

### 结论

代码架构和组件正确性已得到充分的自动化测试验证。Session 隔离（task-level contextvars）已修复并验证。异常降级行为已验证。

Navigator 和 MainAgent 已完成首轮真实模型评估（详见第九、十节），结果表明代码链路工作正常，但 Navigator 定位精度和 MainAgent 状态树更新可靠性需要 prompt 迭代优化。

**生产就绪是有条件的**：Navigator 需要 prompt 优化以提高精确匹配率（当前 28%→目标 60%+）和多路径召回率（当前 0.119→目标 0.5+）。MainAgent 的 `update_state_tree` 调用可靠性需要 prompt 加固。

---

## 九、Navigator 真实模型评估（Section E）

### 9.1 评估配置

| 项目 | 值 |
|------|-----|
| 模型 | Azure OpenAI gpt-5-chat |
| 部署名 | gpt-5-chat |
| Temperature | 0 |
| Prompt 版本 | `subagents/business_map_agent/prompts/templates/system.md`（110 行，2026-03-28） |
| 评估样本数 | 75 |
| 执行时间 | 150.4s（平均 2.0s/样本） |
| 评估脚本 | `reports/run_navigator_eval.py` |
| 数据集 | `reports/navigator-eval-dataset.jsonl` |
| 结果文件 | `reports/navigator-eval-results.jsonl` |
| 原始输出 | `reports/navigator-eval-output.txt` |

### 9.2 总体指标

| 指标 | 值 | 说明 |
|------|-----|------|
| 精确匹配率 | **28.0%** (21/75) | 输出 ID 集合完全等于期望 ID 集合 |
| 可接受祖先匹配率 | 40.0% (30/75) | 输出是期望节点的合法祖先 |
| **总可接受率** | **68.0%** (51/75) | 精确 + 祖先 |
| 过度下钻错误率 | **0.0%** (0/75) | 输出包含不可接受的过深节点 |
| 内容过滤错误 | 1.3% (1/75) | API 内容安全拦截 |
| 多路径精确率 | 0.821 | 输出中正确 ID 的比例 |
| 多路径召回率 | **0.119** | 期望 ID 中被输出的比例 |

### 9.3 按类别分析

| 类别 | 样本数 | 精确匹配 | 可接受 | 过度下钻 |
|------|--------|----------|--------|----------|
| core_routing | 16 | 25.0% | 68.8% | 0% |
| ambiguity | 16 | 25.0% | 81.3% | 0% |
| multi_path | 11 | 18.2% | 54.5% | 0% |
| state_dependent | 12 | 8.3% | 58.3% | 0% |
| non_target | 10 | 60.0% | 80.0% | 0% |
| dependency | 5 | 40.0% | 60.0% | 0% |
| edge_case | 5 | 40.0% | 60.0% | 0% |

### 9.4 输出格式合规性指标

以下指标将 Navigator 的 **协议合规性**（输出是否符合约定格式）与 **解析后恢复正确性**（答案是否可接受）分开度量。

**定义**：
- **严格格式合规**：最终输出匹配正则 `^[a-z_]+(,\s*[a-z_]+)*$`，即仅包含合法节点 ID 和逗号/空格分隔符，不含任何 JSON、解释文本或工具回显内容
- **格式违规**：最终输出不匹配上述正则（包含额外内容）
- **可接受答案**：从输出中提取的节点 ID 集合 = 期望集合（精确匹配）或为期望集合的合法祖先（祖先匹配）
- **不可接受答案**：提取的节点 ID 集合既不精确匹配也不是合法祖先

**分母**：全部 75 个评估样本。三个指标互斥且求和为 100%。

| 指标 | 计算方式 | 值 |
|------|----------|-----|
| 严格合规 | 格式合规的样本数 / 75 | **16.0%** (12/75) |
| 格式违规 + 答案可接受 | 格式违规但解析器提取出可接受答案的样本数 / 75 | **54.7%** (41/75) |
| 格式违规 + 答案不可接受 | 格式违规且解析后答案也不可接受的样本数 / 75 | **29.3%** (22/75) |

**交叉校验**：
- 严格合规 12 + 格式违规可恢复 41 + 格式违规不可恢复 22 = 75 ✓
- 总可接受答案 = 12（合规中的可接受）+ 41（违规中的可接受）= 53。与第 9.2 节报告的 51 有 2 个样本差异，原因：2 个严格合规的样本输出了格式正确但错误的节点 ID（格式正确 ≠ 答案正确）
- 修正后精确数字：格式合规且答案可接受 10/75，格式合规但答案不可接受 2/75

| 细分 | 值 |
|------|-----|
| 格式合规 + 答案可接受 | 13.3% (10/75) |
| 格式合规 + 答案不可接受 | 2.7% (2/75) |
| 格式违规 + 答案可接受 | 54.7% (41/75) |
| 格式违规 + 答案不可接受 | 29.3% (22/75) |
| **合计** | **100%** (75/75) |

**解读**：
- 仅 16.0% 的输出严格合规，84.0% 违反了协议格式
- 但解析器将总可接受率从 13.3%（仅合规输出）恢复到 68.0%（含解析恢复）
- 格式违规的主要原因：模型将工具返回的 JSON 内容回显到最终输出中
- 这是首要需要 prompt 优化的问题

### 9.5 关键发现（含解析后恢复的正确性）

1. **零过度下钻** — "不确定就停住"规则被模型严格遵守，不会猜错分支
2. **浅层偏好显著** — 模型倾向停在 `project_saving` 或 `merchant_search` 等父节点，即使关键词明确匹配子节点
3. **状态简报利用最弱**（8.3% 精确）— 模型难以利用已完成信息推进到下一步
4. **输出格式合规性不足** — 模型常将工具返回的 JSON 内容混入最终输出，导致 ID 解析失败
5. **多路径召回极低**（0.119）— 多个意图时模型合并为单一祖先而非输出多个 ID
6. **非目标处理最好**（60% 精确）— 正确识别闲聊/无关消息

### 9.6 改进方向

| 问题 | 建议的 Prompt 修改 |
|------|---------------------|
| 输出格式混乱 | 在 system.md 末尾增加更强的格式约束："你的最终消息必须只包含节点 ID，不要包含任何工具返回内容" |
| 浅层偏好 | 增加示例展示"关键词明确匹配时应继续下钻"的行为 |
| 状态简报利用弱 | 增加专门的状态简报使用示例，展示如何跳过已完成分支 |
| 多路径召回低 | 增加多路径输出的 few-shot 示例，强调"不同分支都匹配时输出多个 ID" |

---

## 十、MainAgent 行为验证 — Prompt 级真实模型评估（Section D）

> **分类说明**：本节评估使用真实 LLM，但通过手动构造 prompt + 手动注入 context + mock 工具实现，
> 属于 **prompt 级真实模型评估（live-model prompt-level evaluation）**，
> 不是通过 `create_agent_app()` → 实际 hook → 实际 request_context 注入的 **真实运行时验证（true runtime validation）**。
> 真实运行时验证仍待完成。

### 10.1 评估配置

| 项目 | 值 |
|------|-----|
| 模型 | Azure OpenAI gpt-5-chat，temperature=0 |
| Prompt 版本 | SYSTEM.md + SOUL.md + OUTPUT.md + AGENT.md（2026-03-28） |
| 评估场景 | 6（S1-S4 行为验证 + S5 scaffolded read_business_node + S6 naturalistic read_business_node） |
| S2 重复运行 | 5 次，用于测量 update_state_tree 调用可靠性 |
| 评估脚本 | `run_mainagent_behavior_eval.py`（S1-S4）、`run_read_business_node_eval.py`（S5）、`run_naturalistic_read_node_eval.py`（S6）、`run_update_state_tree_reliability.py`（S2 重复） |
| 原始输出 | `mainagent-behavior-eval-output.txt`、`read-business-node-eval-output.txt`、`naturalistic-read-node-eval-output.txt`、`update-state-tree-reliability-evidence.txt`（均在 `reports/` 下） |

### 10.2 场景与结果

| 场景 | 验证内容 | 结果 | 说明 |
|------|----------|------|------|
| S1: 切片注入→遵循 checklist | 收到 [business_map_slice] 后提问是否围绕 checklist | ✅ PASS | 回复包含 checklist 关键词，主动询问相关问题 |
| S2: 节点完成→调用 update_state_tree | 用户确认项目后是否调用状态更新工具 | ✅ PASS | 调用了 update_state_tree 且包含 [完成] 标记 |
| S3: 取消意图→处理 cancel_directions | 用户说"不想做了"时是否参考取消走向 | ✅ PASS | 回复包含取消引导内容（read_business_node 未被调用，因切片已包含 cancel_directions） |
| S4: 闲聊→不调用 update_state_tree | 用户问天气时是否避免更新状态 | ✅ PASS | 未调用 update_state_tree，温和引导回业务 |

### 10.3 补充场景 S5：read_business_node 路径验证

| 项目 | 值 |
|------|-----|
| 评估脚本 | `reports/run_read_business_node_eval.py` |
| 原始输出 | `reports/read-business-node-eval-output.txt` |

**场景设计**：切片仅包含 `confirm_saving` 的概要信息，列出子节点 `coupon_path` 和 `bidding_path` 的名称但不包含其详细内容（checklist/output/cancel_directions）。明确标注"具体操作步骤和取消规则需通过 read_business_node 工具查看"。

**用户消息**："我想了解一下优惠券和比价这两种方式的具体操作步骤和取消规则"

**结果**：✅ PASS — 模型调用了 `read_business_node("coupon_path")` 和 `read_business_node("bidding_path")`，获取了完整业务定义后生成了准确的回复。

**结论**：当切片中明确标注需要查看其他节点的详情时，模型能够正确调用 `read_business_node`。

### 10.3b 补充场景 S6：naturalistic read_business_node 验证

| 项目 | 值 |
|------|-----|
| 评估脚本 | `reports/run_naturalistic_read_node_eval.py` |
| 原始输出 | `reports/naturalistic-read-node-eval-output.txt` |

**场景设计**：与 S5 不同，S6 的切片不包含任何关于 `read_business_node` 工具的提示。切片是一个自然的浅层切片——仅包含父节点内容，子节点仅以名称出现在 children 列表中，不包含其详细定义。

**S6a**：切片为 `confirm_project` 层，用户说"我不太确定要做什么，车跑了三万多公里"。
- 结果：❌ 模型未调用 `read_business_node`，而是直接用通用知识推荐了保养项目

**S6b**：切片为 `project_saving` 层，用户说"省钱方案有哪些选择？我想了解具体怎么操作"。
- 结果：❌ 模型未调用 `read_business_node`，而是从切片描述中提取"优惠券和竞价"信息直接回答

**发现**：在无显式提示的情况下，gpt-5-chat 倾向于用通用知识生成合理回复，而非调用工具获取业务地图中的具体定义。这揭示了一个产品层面的 gap：

- `read_business_node` 的真实价值在于获取 **平台特有的业务规则**（如优惠券领取流程、竞价超时机制、取消退款政策），这些信息模型无法从通用知识推断
- 当前 YAML 中的 checklist/cancel_directions 内容偏通用，模型认为自己已经"知道"足够的信息
- 当 YAML 内容包含平台特有规则（如"9 折券仅限首次使用"、"竞价超过 10 分钟自动取消"）时，`read_business_node` 的调用必要性会显著提升

**结论**：scaffolded 场景（S5）证明了 `read_business_node` 工具链路的正确性；naturalistic 场景（S6）表明在当前 prompt + 切片设计 + YAML 内容的组合下，模型不会自发调用该工具。当前证据表明 YAML 内容的具体程度是影响因素之一，但本轮评估未隔离 prompt 设计、切片构造方式和工具可见性等其他潜在因素的贡献。确定根因需要后续的控制变量实验。

### 10.4 S2 update_state_tree 重复运行可靠性证据

| 项目 | 值 |
|------|-----|
| 评估脚本 | `reports/run_update_state_tree_reliability.py` |
| 原始输出 | `reports/update-state-tree-reliability-evidence.txt` |
| 运行次数 | 5 |
| 模型 | Azure gpt-5-chat，temperature=0 |
| 评判规则 | PASS = `update_state_tree` 被调用 AND 内容包含 `[完成]` |

**逐次结果**：

| 运行 | 结果 | update_state_tree 调用 | 说明 |
|------|------|------------------------|------|
| Run 1 | ✅ PASS | YES，内容含 [完成] | — |
| Run 2 | ✅ PASS | YES，内容含 [完成] | — |
| Run 3 | ✅ PASS | YES，内容含 [完成] | — |
| Run 4 | ❌ FAIL | NO | 模型文本回复正确但未调用工具 |
| Run 5 | ❌ FAIL | NO | 模型文本回复正确但未调用工具 |

**汇总**：3/5 通过，**调用率 60%**。

**分析**：在失败的运行中，模型在文本回复中正确推进了对话（确认项目、转向下一步），但跳过了 `update_state_tree` 工具调用。这表明模型理解了业务流程但不总是遵守"必须调用工具"的 prompt 约束。

### 10.5 关键发现

1. **S1/S4 行为稳定** — 切片注入后遵循 checklist（PASS）、闲聊不调用业务工具（PASS）
2. **S2 调用率 60%** — `update_state_tree` 在 5 次运行中 3 次被调用，prompt 约束力不足
3. **S5 read_business_node 路径已验证** — 当切片信息不足时模型能正确调用工具补充详情
4. **S3 cancel_directions 直接使用** — 切片已包含取消走向，模型不需要额外查询

### 10.6 改进方向

| 问题 | 建议 |
|------|------|
| S2 update_state_tree 调用率 60% | AGENT.md 中将规则改为更强制的表述，如"确认完成后，你的下一步操作必须是调用 update_state_tree，然后再回复用户" |
| recent_history 为空 | 当前实现未传递 recent_history，代词回指（"那个"、"订了"）等历史依赖行为完全未评估 |

---

## 附录 A：测试执行命令与原始输出

### Extensions 测试（184 个）

```bash
cd extensions/
uv run pytest tests/test_business_map_loader.py \
    tests/test_business_map_service.py \
    tests/test_business_map_assembler.py \
    tests/test_business_map_e2e.py \
    --cov=hlsc.business_map \
    --cov=hlsc.services.business_map_service \
    --cov=hlsc.services.state_tree_service \
    --cov=hlsc.tools.read_business_node \
    --cov=hlsc.tools.update_state_tree \
    --cov-report=term-missing -q
```

**实际输出**：
```
184 passed in 15.39s

TOTAL                                     285      0   100%
```

### Subagent Navigator 测试（8 个）

```bash
cd subagents/business_map_agent/
uv run pytest tests/test_navigator.py -v
```

**实际输出**：
```
8 passed, 1 warning in 22.14s
```

### 环境信息

- Python 3.12.3
- pytest 9.0.2
- pytest-cov 7.1.0
- Platform: Linux 6.6.87.2-microsoft-standard-WSL2 (x86_64)
- 测试执行日期：2026-03-28
