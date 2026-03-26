# 项目关系与用户项目历史

这份文档解决：
- 标准词映射项目
- 源项目映射业务项目
- 查相关项目
- 查用户历史项目
- 查用户待服务项目

## 一、标准词映射项目

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/project/getProjectPackageByPrimaryNameId`

### 什么时候用

- 已经拿到 `primary_part_ids`
- 需要映射到 `project_ids`

### 入参

必填：
- `primary_part_ids`

### 当前任务最重要的返回信息

- `project_id`
- `project_name`

## 二、源项目映射业务项目

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/project/getProjectPackageByProjectId`

### 什么时候用

- 已经拿到另一套源项目 id
- 需要转换成当前业务使用的 `project_id`

### 入参

必填：
- `source_project_ids`

### 当前任务最重要的返回信息

- `project_id`
- `project_name`
- `source_project_id`

## 三、相关项目

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/project/getRelatedProjectPackageByPackage`

### 什么时候用

- 已经有一个或多个 `project_id`
- 想查相关项目或连带项目

### 入参

必填：
- `project_ids`

### 当前任务最重要的返回信息

- `project_id`
- `project_name`
- `relation_type`

## 四、用户历史项目

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/project/getHistoryPackage`

### 什么时候用

- 查用户历史上做过哪些项目
- 想知道某类项目是否做过、做过多少次

### 入参

必填：
- `user_id`

可选：
- `shop_ids`

### 返回结果建议

```json
{
  "query": {
    "user_id": "10001",
    "mode": "history"
  },
  "items": [
    {
      "project_id": 522,
      "project_name": "玻璃去油膜",
      "total": 1
    }
  ]
}
```

## 五、用户待服务项目

### 接口

`http://127.0.0.1:9000/service_ai_datamanager/project/getPendingPackage`

### 什么时候用

- 查用户当前待服务项目

### 入参

必填：
- `user_id`

可选：
- `shop_ids`

### 当前任务最重要的返回信息

- `project_id`
- `project_name`
- `total`

## 使用说明

- 这份文档重点是“关系”和“历史”
- 如果任务只是项目文本检索，回到 `/apis/projects/search.md`
