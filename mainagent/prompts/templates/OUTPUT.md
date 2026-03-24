# Output

## `spec`

- For structured result data only.
- Do not use for greetings or simple confirmations.
- Use valid `type` and `props` only.

Supported `spec` types:

- `RecommendProjectsCard`
  - `props`: `{ vehicle_info?: { car_model_name?: string, mileage_km?: number, car_age_year?: number }, projects: [{ project_name: string, icon?: string, project_id?: string }] }`
- `ShopCard`
  - `props`: `{ shop_id: number, name: string, rating?: number, distance?: string, address?: string, phone?: string, tags?: string[], trading_count?: number, opening_hours?: string, images?: string[] }`
- `ProjectCard`
  - `props`: `{ name: string, laborFee: number, partsFee: number, totalPrice: number, duration?: string }`
- `AppointmentCard`
  - `props`: `{ shopName: string, projectName: string, time: string, price: number, status: string }`
- `PartPriceCard`
  - `props`: `{ name: string, items: [{ repairType: string, price: number }] }`
- `CouponCard`
  - `props`: `{ title: string, discount: string, minSpend?: number, expireDate?: string }`

Example:

你附近这两家可以看看。

```spec
{"type":"ShopCard","props":{"shop_id":48,"name":"张江汽修中心","rating":4.8,"distance":"2.3km","address":"浦东新区XX路100号","images":["https://example.com/shop48-1.jpg"]}}
{"type":"CouponCard","props":{"title":"新客立减50元","discount":"满300减50","expireDate":"2026-04-01"}}
```

要我帮你继续看哪家？

## `action`

- Use only when referring to a specific vehicle.
- Place it immediately after the related text.

Supported `action` types:

- only `change_car` for now
- fields: `{ "action": "change_car", "current_car_model_id": string }`

Example:

那我按 `2021款大众朗逸 1.5L` 继续帮你看。

```action
{"action":"change_car","current_car_model_id":"lavida_2021_15l"}
```

接下来帮你估个价。
