# 行情参考价与轮胎报价

这份文档解决：
- 查项目的行业参考价
- 查轮胎报价

不要用这份文档去做：
- 附近商户实时比价

## 一、行业参考价

### 接口

`${API_BASE_URL}/service_ai_datamanager/quotation/optimize/quotationIndustryByPackageId`

### 什么时候用

- 已经有 `project_ids`
- 已经有 `car_model_id`
- 想看某个项目的大致行情区间

### 入参

必填：
- `car_model_id`
- `project_ids`

### 返回结构建议

```json
{
  "query": {
    "project_ids": [502],
    "car_model_id": "lavida_2021_15l"
  },
  "items": [
    {
      "quotation": {
        "project_id": 502,
        "project_name": "机油/机滤更换",
        "plan_name": "默认方案",
        "plan_type": "DOMESTIC_QUALITY",
        "total_price": 66,
        "price_text": "34-66"
      }
    }
  ]
}
```

### 当前任务最重要的返回信息

- `quotation.project_id`
- `quotation.project_name`
- `quotation.plan_name`
- `quotation.plan_type`
- `quotation.total_price`
- `quotation.price_text`

## 二、轮胎报价

### 接口

`${API_BASE_URL}/service_ai_datamanager/quotation/optimize/findATireQuote`

### 什么时候用

- 已经有轮胎规格
- 想查轮胎报价

### 入参

必填：
- `tire_specifications`

### 当前任务最重要的返回信息

- `quotation.project_id`
- `quotation.project_name`
- `quotation.plan_name`
- `quotation.total_price`
- `quotation.price_text`

## 使用说明

- 行情参考价和附近商户实时报价不是一回事
- 如果任务是“哪家店最便宜”，不要优先读这份文档
- 如果任务是“这个项目大概值多少钱”，优先读这份文档
