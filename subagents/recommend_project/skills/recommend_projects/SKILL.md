---
name: recommend_projects
description: 当用户想知道车辆需要做什么保养/维修项目时（如"推荐什么项目"、"该做什么保养了"、"跑了xx公里需要做什么"），根据车辆状况智能推荐养车项目。
---

# 养车推荐项目

## 前置条件

### car_age_year（必须）
- 用户提到了车龄 → 直接换算成年份
- 用户未提及 → 向用户询问，告知必须提供车龄

### car_model_id（可选）
- 上下文中已有 car_model_id → 直接使用
- 用户提到了车型相关信息，根据车型关键词模糊匹配车型信息
- 都没有 → 跳过，不影响推荐

## 输入信息

从用户描述和上下文中提取以下信息：

- car_age_year: 车龄（年）
- mileage_km: 当前里程数（公里）— 可选
- car_model_id: 车型编码 — 可选
- car_model_name: 车型名称 — 可选

## 初步筛选策略

根据 car_age_year 选择 **唯一匹配** 的 category_ids，严格按以下规则判断：

- car_age_year < 2 → category_ids = [5]（改装升级类）
- 2 <= car_age_year < 6 → category_ids = [3,4]（美容养护类, 轮胎与轮毂类）
- car_age_year >= 6 → category_ids = [2]（检测/维修类）

## 查询推荐项目

根据车辆信息（VehicleInfo）和初筛后的项目分类列表（category_ids）查询推荐养车项目。

## 返回格式

必须严格返回纯 JSON，不要包含任何额外文字、markdown标记或解释说明。
