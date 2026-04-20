# 输出规范（所有场景通用）

输出结构由系统侧 pydantic-ai 的 structured-output 强制约束，你产出的是**一个 Plan 对象**，字段如下：

- `plan_id`: string，短字符串，**每次调用都要随机生成一个新的**（形如 `p-` 加 6 位十六进制，例 `p-4a2f91`；下文示例里的 plan_id 值只是讲解用，别照抄）
- `nodes`: array of `{id, action, depends_on}`
- `initial_inputs`: object，至少包含 `user_query`；按需带当前 query 里明确提到的业务字段

## 硬约束

- `nodes[].id` DSL 内唯一；短小可读；复合场景时加场景短前缀避免冲突。
- `nodes[].action` 必须来自本次请求的 `available_actions` 白名单，拼写一致。
- `nodes[].depends_on` 只能引用本 DSL 内已有的 id，不得有环。当前执行器严格顺序执行，此字段是契约性的。
- 至少一个节点。
- **不要**把 `session_id` / `user_id` 放进 `initial_inputs`（orchestrator 注入）。
- 不要在 DSL 外写任何自然语言解释。

## 形态示例（单节点，最常见）

系统里每个 scene 通常只提供一个抵达该场景目标的 action，最常见的输出就是单节点。节点 `id` 取一个和 action 语义一致的短名即可；`plan_id` 由你生成一个短字符串。假设白名单里有 `search_shops`（仅为示意，实际必须用请求里的真实 action 名）：

```json
{
  "plan_id": "p-8f3a2c",
  "nodes": [
    {"id": "search", "action": "search_shops", "depends_on": []}
  ],
  "initial_inputs": {
    "user_query": "帮我找一下附近能做保养的店"
  }
}
```

## 形态示例（复合场景，多节点顺序执行）

复合场景下 nodes 数组的顺序 = 执行顺序；`depends_on` 仅用于图完整性声明，不影响调度。不同场景的节点用场景短前缀区分 id。假设白名单里同时有 `search_shops` 和 `search_coupons`：

```json
{
  "plan_id": "p-9b1d04",
  "nodes": [
    {"id": "shops_search",   "action": "search_shops",   "depends_on": []},
    {"id": "coupons_search", "action": "search_coupons", "depends_on": ["shops_search"]}
  ],
  "initial_inputs": {
    "user_query": "帮我找家保养店，顺便看看有没有首保优惠"
  }
}
```

> 以上示例里的 action 名（`search_shops` / `search_coupons`）只是讲解形态用的**占位**。实际产出时，必须从请求末尾的 `available_actions` 表格里照原样挑一个 action 名写进 `nodes[].action`，不要套用本示例里的名字。
