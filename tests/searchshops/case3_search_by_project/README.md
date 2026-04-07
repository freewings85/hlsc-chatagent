# SS-003: 按项目搜索门店

## 场景
用户问"哪家店能换轮胎"，验证 Agent 先 match_project 再 search_shops。

## 预期
1. 调用 match_project（关键词"轮胎"）
2. 调用 search_shops（带 project_ids）
3. 返回支持轮胎服务的门店
