## shop_search_info 结构
描述文字 + json结构

正在查询商户中...
```json
{
  "orderBy": "排序，可选值: distance / rating / tradingCount",
  "limit": "返回数量上限，整数",
  "query": "查询树"
}
```

没有 query 就无法搜索；其他字段用户没讲就留空。

查询树节点三种 op：
- `LEAF` = 一个叶子条件，用 `params` 放字段
- `AND` = children 全部命中
- `OR`  = children 任一命中

### LEAF params 可用字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| shop_type | str | 用户原话里对商户类型的描述，原样传；用户没说不填 |
| shop_name | str | 用户原话里提到的具体商户名称，原样传；用户没说不填 |
| location_text | str | 用户原话里的位置描述，任何粒度**不拆、不猜**；用户说"附近/这边"不算明确位置，不填 |
| use_current_location | bool | 用户说"附近/这边/当前位置"之类要用当前定位时 true；否则不填 |
| min_rating | number | 用户明确给出的最低评分（1-5 数字）；用户没给具体数字就不填 |
| has_activity | bool | 用户明确说要有优惠活动时 true；否则不填 |
| project_keywords | list[str] | 用户原话里对养车服务的描述（如项目名），原样传；用户没说不填 |
| equipment_keywords | list[str] | 用户原话里对设备的描述，原样传；用户没说不填 |
| radius | integer | 搜索半径，单位米；**只有用户明说距离数字**才填（"3公里内"→3000）。"附近"不算明确距离 |
| fuzzy_keywords | list[str] | 用户原话里对商户的其他要求描述（营业时间、价格偏好之类），原样传；不放位置/商户/项目名；用户没说不填 |

字段说明里**不列具体候选值**：防止 LLM 在用户没提到时照着说明回填。任何字段都只抽用户原话里明确说过的词，说明本身不是取值源。

位置字段的职责分工：LLM 只负责把用户原话放进 `location_text`，或用 `use_current_location` 表达"用当前定位"的意图。城市归属 / 粒度解析 / 坐标解析都由后端完成，不要让模型自己拼城市或拆字段。

### 示例1

正在查询商户中...
```json
{
  "query": {
    "op": "LEAF",
    "params": { "shop_type": "xxx", "location_text": "xxx" }
  }
}
```

### 示例2

正在查询商户中...
```json
{
  "query": {
    "op": "AND",
    "children": [
      { "op": "LEAF", "params": { "location_text": "xxx" } },
      {
        "op": "OR",
        "children": [
          { "op": "LEAF", "params": { "shop_type": "xxx" } },
          { "op": "LEAF", "params": { "shop_type": "xxx" } }
        ]
      }
    ]
  }
}