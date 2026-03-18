查询用户去过的商户（上次去过或历史去过），返回商户列表。

参数说明：
- query_type: 查询类型
  - "latest": 上次去过的商户（默认 top=1）
  - "history": 历史去过的商户（默认 top=5）
- top: 返回数量

使用场景：
- "上次去的那家店叫什么" → query_type="latest", top=1
- "我之前去过哪些店" → query_type="history", top=5
- "最近去的那家修理厂" → query_type="latest", top=1

IMPORTANT: 此工具自动使用当前登录用户的身份查询，无需额外提供用户信息。