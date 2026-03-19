---
name: search-nearby-shops
description: 当用户想查找附近的汽修门店时（如"附近有什么修车的店"），搜索并展示门店列表。
when_to_use: 用户想找修车店、汽修店、养车门店、洗车店，或说"附近有什么修车的"、"找个口碑好的店"、"哪家修车靠谱"时使用。
---

# 搜索附近门店

当用户想查找附近的汽修/养车门店时使用。

## 前置条件

需要用户的位置信息（lat/lng）。获取方式：
- 如果 request_context 有 current_location → 直接使用
- 如果用户提到了位置（如"浦东"） → 调用 fuzzy_match_location
- 否则 → 调用 ask_user_location

获取到 lat/lng 后，立即执行 Step 1。

## 流程

### Step 1：搜索门店

获取到 lat/lng 后，使用 bash 执行搜索命令。

**重要**：`<skill-dir>` 替换为 Skill 工具返回的实际路径。所有脚本必须在 skill 目录下执行。

以下是常见场景的完整示例：

**基础查询（用户只说"找修车店"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61
```

**口碑好的（用户说"口碑好的"/"评分高的"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61 --order-by rating --min-rating 4
```

**靠谱的（用户说"生意好的"/"靠谱的"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61 --order-by tradingCount --min-trading-count 50
```

**综合好的（用户说"又好又靠谱"/"综合好的"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61 --order-by rating,tradingCount --min-rating 4 --min-trading-count 50
```

**特定服务（用户说"能洗车的"/"做保养的"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61 --keyword 洗车
```

**指定区域（用户说"浦东的"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61 --address-name 浦东
```

**指定品牌（用户说"途虎"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61 --keyword 途虎
```

**现在营业的（用户说"现在开着的"/"还营业的"）：**
```bash
cd <skill-dir> && python scripts/search_shops.py --lat 31.20 --lng 121.61 --opening-hour 14:30
```

以上示例中的参数可以自由组合。根据用户意图选择对应参数，直接执行。

**全部参数参考：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| --lat | float | 必填 | 纬度 |
| --lng | float | 必填 | 经度 |
| --keyword | str | 空 | 门店类型或特长（如"刹车专修"、"奔驰专修"、"洗车"） |
| --top | int | 5 | 返回数量，用户说"多找几家"可以加大 |
| --radius | int | 10000 | 搜索半径（米），用户说"近一点"可以缩小 |
| --order-by | str | distance | 排序：distance / rating / tradingCount，可组合如 "distance,rating" |
| --commercial-type | int | 无 | 商户类型（1=汽修门店） |
| --opening-hour | str | 无 | 营业时间筛选，格式 "HH:MM" |
| --province-id | int | 无 | 省份ID |
| --city-id | int | 无 | 城市ID |
| --district-id | int | 无 | 区县ID |
| --address-name | str | 无 | 地址名称搜索 |
| --package-ids | str | 无 | 服务项目ID，逗号分隔 |
| --min-rating | float | 无 | 最低评分（如 4.0） |
| --min-trading-count | int | 无 | 最低交易量（如 50） |

### Step 2：展示结果

将搜索结果用 ShopCard 卡片展示给用户。每家门店包含：
- 门店名称、地址（含省市区）、距离
- 评分、成交数
- 服务范围
- 联系电话
- 营业时间

## 规则

1. 必须先有位置信息才能搜索
2. 获取到位置后立即执行 bash 命令，不要向用户确认参数
3. 根据用户意图直接选择对应示例中的参数组合
4. 如果用户指定了品牌（如"途虎"），作为 --keyword 传入
5. 无结果时告知用户并建议扩大搜索范围或调整关键词
6. 如果 bash 执行报错（如文件找不到），如实告知用户搜索出错，不要编造门店数据

## 商户类型

- commercialType=1: 汽修门店