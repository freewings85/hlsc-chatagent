# 项目匹配 API

## POST http://localhost:50400/service_ai_datamanager/package/searchPackageByKeyword

将用户描述的养车需求关键词匹配到标准项目 ID，用于后续查报价、搜商户等。

### 请求体

```json
{
  "keyword": "洗车",          // 用户提到的项目关键词（必填）
  "top_k": 5                  // 返回数量上限（可选，默认 5）
}
```

### 响应

```json
{
  "status": 0,
  "result": [
    {
      "packageId": 1101,
      "packageName": "基础洗车"
    },
    {
      "packageId": 1102,
      "packageName": "精致洗车"
    }
  ]
}
```

### 响应字段说明

- `packageId` — 项目 ID（整数），用于调报价接口（quotations.md）的 `projectIds` 参数和商户搜索（shops.md）的 `projectIds` 参数
- `packageName` — 项目标准名称

### 使用场景

- 用户说"洗车" → 调此接口拿到洗车相关的 projectId（如 1101 基础洗车、1102 精致洗车）
- 拿到 projectId 后：
  - 传给 shops.md 的 `projectIds` 参数 → 筛选能做该项目的商户
  - 传给 quotations.md 的 `projectIds` 参数 → 查指定项目的报价

### 重要

- **需要 projectId 时必须先调此接口**，将用户描述的模糊项目名转为标准 projectId，不要靠项目名称字符串匹配
- 一个关键词可能匹配多个项目（如"洗车"→ 基础洗车 + 精致洗车），按需使用
