# 输出规范（所有场景通用）

输出结构由系统侧 pydantic-ai 的 structured-output 强制约束，你产出的是**一个 Plan 对象**，字段如下：

- `plan_id`: string，短字符串，你自己生成（例 `"p-<短哈希>"`）
- `nodes`: array of `{id, action, depends_on}`
- `initial_inputs`: object，至少包含 `user_query`；按需带 `session_id` / `user_id` / 其他根变量

## 硬约束

- `nodes[].id` DSL 内唯一；短小可读；复合场景时加场景短前缀避免冲突（见 PLAN_SOUL「处理复合场景」）。
- `nodes[].action` 必须来自本次请求的 `available_actions` 白名单，拼写一致。
- `nodes[].depends_on` 只能引用本 DSL 内已有的 id，不得有环。
- 至少一个节点。
- 不要在 DSL 外写任何自然语言解释。

## 合法示例（单场景 searchshops）

```json
{
  "plan_id": "p-abc123",
  "nodes": [
    {"id": "profile", "action": "<白名单里"拉用户画像"类>", "depends_on": []},
    {"id": "search",  "action": "<白名单里"搜商户"类>",     "depends_on": ["profile"]},
    {"id": "rank",    "action": "<白名单里"排序/打分"类>",  "depends_on": ["search"]},
    {"id": "reply",   "action": "<白名单里"出用户回复"类>", "depends_on": ["rank"]}
  ],
  "initial_inputs": {
    "user_query": "<当前用户 query 原样>",
    "session_id": "<透传>",
    "user_id":    "<透传>"
  }
}
```

## 合法示例（复合场景 searchshops + searchcoupons）

共用上游 `profile`，商户搜索和优惠搜索并行，最后一个 reply 节点统一出回复：

```json
{
  "plan_id": "p-xyz789",
  "nodes": [
    {"id": "profile",        "action": "<拉画像>",     "depends_on": []},
    {"id": "shops_search",   "action": "<搜商户>",     "depends_on": ["profile"]},
    {"id": "coupons_search", "action": "<搜优惠>",     "depends_on": ["profile"]},
    {"id": "shops_rank",     "action": "<商户排序>",   "depends_on": ["shops_search"]},
    {"id": "reply",          "action": "<出用户回复>", "depends_on": ["shops_rank", "coupons_search"]}
  ],
  "initial_inputs": {
    "user_query": "<当前 query>"
  }
}
```

> 示例里 action 名字是**占位**，实际必须从请求末尾的 `available_actions` 表格里挑。
