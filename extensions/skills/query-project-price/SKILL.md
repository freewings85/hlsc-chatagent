---
name: query-project-price
description: 当用户询问项目（服务）在门店的报价时（如"换机油多少钱"），查询指定门店的项目报价。
---

# 查询项目门店报价

当用户询问项目（服务）在门店的报价时，按以下流程执行。

## 前置条件

1. 需要 car_model_id — 参考 confirm-car-info skill 获取
2. 需要项目 ID（project_id）— 来自之前的项目搜索结果
3. 需要门店 ID（shop_id）— 来自之前的门店搜索或推荐结果

## 流程

### Step 1：查询项目门店报价

使用 bash 执行：

```bash
cd <skill-dir> && python scripts/get_project_price.py --project_ids 101,102 --car_model_id CAR-001 --shop_ids S001,S002
```

`<skill-dir>` 是系统注入的 skill 目录绝对路径，执行前必须先 cd 进去。

支持同时查询多个项目在多个门店的报价（多个 ID 用逗号分隔）。

可选参数：
- `--sort_by`：排序方式 — distance（默认）/ rating / price

### Step 2：展示结果

将报价结果整理后回复用户。每个门店下会列出各项目的报价方案，包含：
- 方案名称和价格（含工时和配件）
- 方案类型（如国际大厂、国产品质、原厂等）
- 保质期信息（如有）

## 规则

1. 必须先有 car_model_id 才能查询报价
2. project_id 和 shop_id 必须来自之前的搜索/推荐结果，不能编造
3. 区分项目（服务，含工时）和零部件（配件），本 skill 查项目报价
4. 返回的价格是门店项目报价（含工时和配件），可直接下单
