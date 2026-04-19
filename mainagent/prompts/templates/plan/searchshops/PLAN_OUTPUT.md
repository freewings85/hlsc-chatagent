# 输出规范（searchshops）

输出结构由系统侧 pydantic-ai 的 structured-output 强制约束，你产出的是**一个 Plan 对象**，字段如下：

- `plan_id`: string，短字符串，你自己生成（例 `"p-<短哈希>"`）
- `nodes`: array of `{id, activity, depends_on}`
- `initial_inputs`: object，至少包含 `user_query`；按需带 `session_id` / `user_id` / 其他根变量

## 硬约束

- `nodes[].id` DSL 内唯一；短小可读。
- `nodes[].activity` 必须来自请求的 available_activities 白名单，拼写一致。
- `nodes[].depends_on` 只能引用本 DSL 内已有的 id。不得有环。
- 至少一个节点。
- 不要在 DSL 外写任何自然语言解释。

## 合法示例（结构参考）

```json
{
  "plan_id": "p-abc123",
  "nodes": [
    {"id": "profile", "activity": "<白名单里"拉用户画像"类>",  "depends_on": []},
    {"id": "search",  "activity": "<白名单里"搜商户"类>",      "depends_on": ["profile"]},
    {"id": "rank",    "activity": "<白名单里"排序/打分"类>",   "depends_on": ["search"]},
    {"id": "reply",   "activity": "<白名单里"出用户回复"类>",  "depends_on": ["rank"]}
  ],
  "initial_inputs": {
    "user_query": "<当前用户 query 原样>",
    "session_id": "<透传>",
    "user_id":    "<透传>"
  }
}
```

> 上面示例里 activity 名字是**占位**，实际必须从请求末尾的白名单表格里挑。
