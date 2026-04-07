# SS-006: 文字地址搜索

## 场景
用户不带位置 context，用文字说"南京西路附近有什么修理厂"。
Agent 应调 address service 解析地址后搜索。

## 预期
1. 调用 search_shops（address 参数非空）
2. 返回南京西路附近门店
3. 不应 interrupt 要求定位（因为用户给了文字地址）
