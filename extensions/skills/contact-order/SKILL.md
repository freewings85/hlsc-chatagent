---
name: contact-order
description: 生成联系单，让商户带着用户需求信息主动联系用户
when_to_use: 用户选定了商户，要联系商户或让商户联系自己时
---

# 生成联系单

用户选好商户后，搞清楚用户的完整需求，生成联系单让商户主动联系用户。

## 执行步骤（严格按序执行，必须调用脚本，不要用文字模拟结果）

### 步骤 1：确认商户

确认用户选定的商户（shop_id 和 shop_name 必须来自 search_shops 返回的真实数据）。

### 步骤 2：明确用户需求

从对话上下文中梳理用户的完整需求：
- 要做什么项目（必须明确，来自 classify_project 返回的 project_id 和 project_name）
- 品牌偏好、预算、紧急程度等补充信息（有就记录，没有不追问）

### 步骤 3：判断是否需要车型

有些项目需要车型信息才能报价（如换机油、换轮胎、换刹车片等涉及零部件的项目），有些不需要（如洗车、美容、检测）。

如果项目需要车型且上下文中没有车型信息 → 调 `collect_user_car_info` 获取。
如果项目不需要车型或上下文已有车型 → 跳过。

### 步骤 4：生成联系单

从对话中总结用户需求作为 task_describe 参数。一句话，至少包含项目名称，有偏好和要求也写进去。不要编造用户没说过的内容。

执行脚本（3 个必传参数缺一不可，缺了脚本会报错）：
```bash
python {SCRIPTS_DIR}/create_contact_order.py --shop_id 商户ID --project_id 项目ID --task_describe "需求描述"
```
> `--car_model_id` 可选，上下文中有车型信息时加上。

- **shop_id**：必传，来自 search_shops 返回
- **project_id**：必传，来自 classify_project 返回
- **task_describe**：必传，从对话中总结的用户需求

脚本会返回 order_id，用 ContactOrderCard 展示给用户。不要自己编造 order_id。

