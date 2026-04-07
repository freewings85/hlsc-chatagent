# 地址解析 API

## POST ${ADDRESS_SERVICE_URL}/api/address/geocode

将地址文本转为经纬度坐标 + 行政区划信息。

### 请求体

```json
{
  "address": "淮海中路",     // 地址文本（必填）
  "city": "上海"             // 城市限定（可选，提高解析精度）
}
```

### 响应

```json
{
  "status": 0,
  "result": {
    "address": "淮海中路",
    "formattedAddress": "xxxxx",
    "latitude": 31.2195,
    "longitude": 121.4737,
    "province": "上海市",
    "city": "上海市",
    "district": "黄浦区",
    "adcode": "310101"
  }
}
```

### 使用场景

- 用户说"南京西路附近" → address="南京西路" → 拿到 lat/lng → 传给 shop/coupon search API
- 用户说"北京朝阳区" → address="北京朝阳区" → 拿到 lat/lng + district="朝阳区"

### 注意

- 地址越具体解析越准确（"上海南京西路" 比 "南京西路" 好）
- city 参数可选但建议传，避免"南京西路"被解析到南京市
