# 项目检索

这份文档解决：
- 从用户自然语言里识别项目
- 从故障、触发条件、标准词反推项目

不要用这份文档去做：
- 项目详情解释
- 项目树浏览
- 报价比较

## 一、按关键词检索项目

### 接口

`${API_BASE_URL}/service_ai_datamanager/project/optimize/searchProjectPackageByKeyword`

### 什么时候用

- 用户说了一个项目名称或服务诉求
- 需要先拿到 `project_id`

### 入参

必填：
- `search_text`
- `top_k`
- `similarity_threshold`
- `vector_similarity_weight`

### 返回结果建议

```json
{
  "query": {
    "search_text": "更换刹车片"
  },
  "items": [
    {
      "project": {
        "project_id": 516,
        "project_name": "前刹车片更换",
        "contain_material": true,
        "vehicle_precision_requirement": "need_vin"
      },
      "match_data": {
        "similarity": 0.96
      }
    }
  ]
}
```

### 当前任务最重要的返回信息

- `project_id`
- `project_name`
- `contain_material`
- `vehicle_precision_requirement`

## 二、按标准词检索

### 接口

`${API_BASE_URL}/service_ai_datamanager/partprimary/optimize/searchPartPrimaryByKeyword`

### 什么时候用

- 先要识别标准词 / 标准配件
- 再通过标准词去反推项目

### 入参

必填：
- `search_text`
- `top_k`
- `similarity_threshold`
- `vector_similarity_weight`

### 当前任务最重要的返回信息

- `primary_part_id`
- `primary_part_name`

## 三、按触发条件检索

### 接口

`${API_BASE_URL}/service_ai_datamanager/projecttriggerconditions/optimize/searchprojecttriggerconditions`

### 什么时候用

- 用户说的是“场景”或“触发诉求”
- 需要从触发条件反推项目

### 当前任务最重要的返回信息

- `trigger_condition_id`
- `title`
- `content`
- `primary_part_ids`
- `related_project_ids`

## 四、按故障现象检索

### 接口

`${API_BASE_URL}/service_ai_datamanager/faultphenomenon/optimize/searchfaultphenomenon`

### 什么时候用

- 用户说的是故障表现
- 需要先从故障现象映射到项目

### 当前任务最重要的返回信息

- `fault_id`
- `title`
- `content`
- `primary_part_ids`
- `related_project_ids`

## 五、和其他文档的关系

- 需要项目树：
  - 读 `/apis/projects/catalog.md`
- 需要项目详情：
  - 读 `/apis/projects/details.md`
- 需要项目关系、历史项目、待服务项目：
  - 读 `/apis/projects/relations.md`
