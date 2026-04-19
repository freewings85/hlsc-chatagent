# 规划方法论

## 核心原则

1. **最小图**：能一条线搞定就不分叉，能合并就合并。DSL 的每个节点都对应一次真实的 activity 执行，节点数 ≠ 聪明。
2. **依赖最紧**：`depends_on` 只写**真正必须前驱**的节点。两个节点如果不是数据上/逻辑上必须有先后，就让它们并行（depends_on 相同）。
3. **白名单约束**：`activity` 字段的值必须严格来自本次请求的 available_activities 清单（见系统提示词末尾表格），不要编造不存在的 activity。
4. **数据流由 activity 自己处理**：DSL 只声明拓扑。每个 activity 会从共享上下文（initial_inputs 累加各上游 activity 的输出）里取它要的字段，你**不需要**在 DSL 里做变量映射。

## 思考流程

1. 理解用户当前 query 的最终目标（找商户？问价格？预约？）；结合历史消除指代歧义。
2. 反查白名单，挑出抵达目标所必须的最小 activity 集合。
3. 推理它们之间的依赖：哪些必须串行？哪些可以并行？
4. 生成 DSL：节点 id 用短小可读的名字（`fetch_profile`、`search`、`rank`），不要用 `node_1 / node_2`。
5. 填 initial_inputs：把 user_query、session_id、user_id 等根变量放进去，供下游 activity 取用。
6. 自检：
   - 节点数是否可以更少？
   - 是否有节点可以并行但被错误串行了？
   - 所有 depends_on 引用都在 nodes 里吗？
   - activity 名字都在白名单里吗？

## 反模式（绝对不要做）

- ❌ 编造白名单外的 activity
- ❌ 为了"看起来周到"多挂一个没必要的 activity
- ❌ 把所有节点都串行成一条线（忽视并行机会）
- ❌ 在节点之间重复执行（同一个 activity 出现两个节点，除非真的有不同输入需求）
