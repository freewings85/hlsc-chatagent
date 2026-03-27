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
- car_model_id 必须来自上下文中已有的 car_model_id 字段，如果没有，传空字符串 ""，**严禁编造任何值**

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
cd <skill-dir> && python scripts/query_market_price.py --project-ids 502 505 --car-model-id ""
```

### 门店报价

需要 shop_ids（门店 ID 列表），可从 search_nearby_shops 或 get_visited_shops 获取。

```bash
cd <skill-dir> && python scripts/query_shop_price.py --project-ids 502 505 --car-model-id "" --shop-ids S001 S002
```

IMPORTANT: --car-model-id 只能填上下文中已有的真实值，没有则填 ""（空字符串）。"unknown"、"SUV"、"sedan" 等都属于编造，严禁使用。


## 返回格式

- 门店报价（query_shop_price）：直接用文字描述结果，不要使用任何 spec 卡片
- 行情参考价（query_market_price）：直接用文字描述结果，不要使用任何 spec 卡片

向车主展示价格时，必须明确包含每个项目的具体价格数值（如"标准洗车（轿车）：30元"），后续预订时需要用到这些价格。

## 后续引导

价格结果返回后，主动告知车主可选的下一步操作：
1. **选择商户报价预订** — 选择某个商户的报价直接预订（plan_mode=standard，走 `booking-execution`，price 填入该商户的预约价格）
2. **一口价委托预订** — 由车主出一口价，委托推送给多家商户（plan_mode=commission，走 `booking-execution`）
3. **多商户竞价预订** — 车主给出项目要求，推送给多家商户，由商户竞价报价（plan_mode=bidding，走 `booking-execution`）
4. **继续查报价** — 如果之前查的是行情参考价，可以继续查附近门店的实际报价再决定


## 完成标准

- 已向车主返回对应类型的价格结果
- 已告知车主后续可选操作
