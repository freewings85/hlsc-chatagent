---
name: search-nearby-shops
description: 当用户想查找附近的汽修门店时（如"附近有什么修车的店"），搜索并展示门店列表。
---

# 搜索附近门店

当用户想查找附近的汽修/养车门店时使用。

## 前置条件

需要用户的位置信息（lat/lng）。参考 confirm-location skill 获取。

## 流程

### Step 1：搜索门店

使用 bash 执行：

```bash
python scripts/search_shops.py --lat <纬度> --lng <经度> --keyword <关键词> --top <数量> --radius <半径米> --order-by <排序>
```

工作目录为当前 skill 目录（`skills/search-nearby-shops/`）。

参数说明：
- keyword: 用户提到的门店类型或特长（如"刹车专修"、"奔驰专修"、"洗车"），不指定则搜索全部
- top: 返回数量，默认 5，用户说"多找几家"可以加大
- radius: 搜索半径（米），默认 10000（10公里），用户说"近一点"可以缩小
- order-by: 排序方式，可选 "distance"（按距离）或 "rating"（按评分），默认按距离

### Step 2：展示结果

将搜索结果用 ShopCard 卡片展示给用户。每家门店包含：
- 门店名称、地址、距离
- 评分、成交数
- 服务范围
- 联系电话
- 营业时间

## 规则

1. 必须先有位置信息才能搜索
2. 如果用户指定了品牌（如"途虎"），作为 keyword 传入
3. 无结果时告知用户并建议扩大搜索范围或调整关键词