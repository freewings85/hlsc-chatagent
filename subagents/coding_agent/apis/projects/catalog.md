# 项目目录与项目树

这份文档解决：
- 查项目分类树
- 查基于车型和条件过滤后的项目树
- 查样本 VIN 推荐项目

不要用这份文档去做：
- 项目文本检索
- 项目详情解释
- 报价比较

## 一、项目分类树

### 接口

`${API_BASE_URL}/service_ai_datamanager/Category/optimize/allProjectCategoryTree`

### 什么时候用

- 需要完整分类结构
- 需要按分类浏览项目

### 返回结果建议

```json
{
  "items": [
    {
      "id": 1,
      "name": "常规养护类",
      "data_type": "category",
      "children": []
    }
  ]
}
```

## 二、按条件获取项目树

### 接口

`${API_BASE_URL}/service_ai_datamanager/project/optimize/maintainProjectTreeByCarKey`

### 什么时候用

- 已经有 `car_model_id`
- 需要基于车型、里程、车龄、标准词、项目等条件过滤项目树

### 入参

可选：
- `car_model_id`
- `primary_part_ids`
- `project_ids`
- `category_ids`
- `month`
- `mileage`

### 当前任务最重要的返回信息

- 项目树节点
- 每个节点的 `id`
- `name`
- `data_type`
- `children`

## 三、样本 VIN 推荐项目

### 接口

`${API_BASE_URL}/service_ai_datamanager/project/optimize/getSampleVinProjects`

### 什么时候用

- 需要快速拿一组推荐项目
- 可以接受样本 VIN 方式

### 入参

必填：
- `random_vin`

可选：
- `car_model_id`
- `month`
- `mileage`

### 当前任务最重要的返回信息

- `vehicle_info`
- `items[].project_id`
- `items[].project_name`

## 使用说明

- 如果任务目标只是“识别项目 id”，不要先来读这份文档
- 这份文档更偏目录浏览、条件过滤、推荐项目集合
