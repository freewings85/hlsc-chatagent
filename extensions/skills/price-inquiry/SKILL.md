---
name: price-inquiry
description: 当车主询问维修保养项目价格时，先澄清查哪种价格（行情参考价 or 门店报价），再调用对应脚本返回结果。
when_to_use: 车主问"多少钱"、"什么价格"、"大概费用"、"行情价"、"门店报价"等任何价格相关问题时使用。
---

# 价格查询 Skill

## 职责

统一承接所有"价格查询"意图，通过一轮澄清确定查询类型，再路由到正确的脚本。

## 前置条件

- project_ids 已通过 match_project 获取
- car_model_id 已知（L2 精度：品牌+车系+年款+排量）
- 如条件不满足，先引导补齐再进入本 skill

## 执行步骤

1. 阅读判断规则：`read <skill-fs-dir>/references/价格类型判断规则.md`
2. 判断用户意图是否已明确（见判断规则）
   - **已明确** → 直接跳到步骤 4
   - **不明确** → 进入步骤 3
3. 用一句话询问车主想查哪种价格：
   - "您想先看看这个项目的**市场行情参考价**，还是查一下**附近门店的实际报价**？"
   - 不要解释两者区别，除非车主追问
4. 根据结果执行对应脚本：

### 行情参考价

**重要**：`<skill-dir>` 替换为 Skill 工具返回的实际路径。所有脚本必须在 skill 目录下执行。

```bash
cd <skill-dir> && python scripts/query_market_price.py --project-ids 502 505 --car-model-id "xxx"
```

### 门店报价

需要 shop_ids（门店 ID 列表），可从 search_nearby_shops 或 get_visited_shops 获取。

```bash
cd <skill-dir> && python scripts/get_project_price.py --project-ids 502 505 --car-model-id "xxx" --shop-ids S001 S002
```

可选参数：`--lat 31.23 --lng 121.47 --distance-km 10 --min-rating 4.8 --sort-by distance`

## 返回格式

必须严格返回纯 JSON，不要包含任何额外文字、markdown 标记或解释说明。

## 完成标准

- 已向车主返回对应类型的价格结果
