---
name: publish-bidding
description: "发起竞价询价，向周边多家服务商发布竞价请求获取报价"
when_to_use: "用户说'询价'、'帮我询个价'、'比价'、'找门店报价'时触发。与查价格（立即返回参考价）不同，竞价是向门店发布需求等待各自报价。"
user-invocable: true
---

# 发起竞价（publish-bidding）

向周边多家服务商发布竞价请求，由各服务商分别报价，用户可以比较后选择。

## 流程

### 步骤 1：收集必要信息

从用户消息和上下文中收集以下信息。能推断的直接用，只有确实缺少的才向用户询问：

- **车型编码** (`car_model_id`)：必填。不可编造，必须通过工具查询获得精确值
- **车型名称** (`car_model_name`)：必填。与 car_model_id 一起获取
- **需求描述** (`description`)：必填，简要说明服务需求
- **项目 ID 列表** (`project_ids`)：必填，默认 `[10001]`

可选信息（有就传，没有不问）：
- `filters`：筛选条件（距离范围、最低评分）
- `context_params`：已知项目参数（VIN、里程数、照片等）
- `preferred_time`：期望服务时间

### 步骤 2：准备竞价数据

使用 bash 工具执行脚本，查询项目参数 schema 并构建完整的竞价数据：

```
bash("python {baseDir}/scripts/prepare_bidding.py '<json_args>'")
```

参数格式（JSON 字符串）：
```json
{
  "project_ids": [10001],
  "car_model_id": "benz_c_2023",
  "car_model_name": "奔驰C级 2023款",
  "description": "刹车片磨损需要更换",
  "filters": {"distance_km": {"min": 0, "max": 30}, "min_rating": 4.0},
  "context_params": {"mileage": 50000},
  "preferred_time": "这周末"
}
```

脚本返回完整的 task_data JSON。

### 步骤 3：展示确认卡片

使用 interrupt 工具向用户展示确认卡片：

```
interrupt(type="inquiry_confirm", data=<步骤2返回的JSON>)
```

**然后停止，不要继续执行。** 等待用户在下一轮消息中确认或取消。

### 步骤 4：处理用户反馈

用户回复后：
- **确认**：继续步骤 5
- **修改**：根据用户修改的内容更新数据，回到步骤 3
- **取消**：告知用户已取消，结束流程

### 步骤 5：提交询价

用户确认后，使用 bash 工具提交询价：

```
bash("python {baseDir}/scripts/submit_bidding.py '<task_data_json>'")
```

脚本调用后端 API 提交询价，返回 inquiry_id。

### 步骤 6：等待报价结果

使用 interrupt 工具展示等待报价卡片：

```
interrupt(type="inquiry_result", data='{"inquiry_task_id": "xxx", "inquiry_id": "xxx"}')
```

等待用户带着报价结果回来（前端会在收到报价后自动填充）。

### 步骤 7：展示结果

收到报价结果后，向用户展示各家报价对比，帮助用户选择最优方案。

## 注意事项

- 用户需求不明确（说不清修什么）时，不要发起竞价，应引导用户先进行故障诊断
- 使用上下文地址定位周边服务商
- 所有已知的项目参数都要传进去，不要遗漏
- 每个步骤完成后更新 plan.md 中的进度
