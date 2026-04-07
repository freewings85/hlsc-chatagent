# SS-002: 按商户类型筛选

## 场景
用户问"附近有没有4S店"，验证 search_shops 传入 commercial_type 筛选。

## 预期
1. 调用 search_shops（带 commercial_type=[1]）
2. 只返回 4S 店类型的商户
3. 非 4S 店不出现在结果中
