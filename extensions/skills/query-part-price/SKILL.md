---
name: query-part-price
description: 当用户询问零部件价格时（如"刹车片多少钱"），按流程搜索零部件并查询平台参考价格。
---

# 查询零部件价格

当用户询问零部件（配件）的价格时，按以下流程执行。

## 前置条件

1. 需要 car_model_id — 参考 confirm-car-info skill 获取
2. 需要用户提到的零部件关键词

## 流程

### Step 1：搜索零部件

使用 bash 执行：

```bash
cd <skill-dir> && python scripts/search_parts.py --keyword 刹车片 --car_model_id CAR-001
```

`<skill-dir>` 是系统注入的 skill 目录绝对路径，执行前必须先 cd 进去。

返回匹配的零部件列表（精确匹配 + 模糊匹配）。

### Step 2：确认零部件

- 如果精确匹配到 1 个 → 直接用
- 如果精确匹配到多个或只有模糊匹配 → 告知用户匹配结果，让用户确认
- 如果没有匹配 → 告知用户未找到

### Step 3：查询价格

确认 part_id 后，使用 bash 执行：

```bash
cd <skill-dir> && python scripts/get_part_price.py --part_ids 123 --car_model_id CAR-001
```

支持同时查询多个零部件的价格（多个 part_id 用逗号分隔）。

### Step 4：展示结果

将价格结果整理后回复用户。价格分为三个档次：
- 国际大厂（INTERNATIONAL_BRAND）
- 国产品质（DOMESTIC_QUALITY）
- 原厂（ORIGINAL）

注意：返回的是零部件平台参考价格（仅配件），不含工时费用。可提示用户如需了解含工时的更换服务报价。

## 详细说明

如需了解 API 返回格式的详细说明，参考 REFERENCE.md。

## 规则

1. 必须先有 car_model_id 才能搜索零部件
2. 零部件的 part_id 必须来自 search_parts 的返回结果，不能编造
3. 区分零部件（配件）和项目（服务），本 skill 只查配件价格
