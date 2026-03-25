# Output

## `spec`

- For structured result data only.
- Do not use for greetings or simple confirmations.
- Use valid `type` and `props` only.

Supported `spec` types:

- `RecommendProjectsCard`
  - `props`: `{ vehicle_info?: { car_model_name?: string, mileage_km?: number, car_age_year?: number }, projects: [{ project_name: string, icon?: string, project_id?: string }] }`
- `ShopCard`
  - `props`: `{ shop_id: number, name: string }`
- `ProjectCard`
  - `props`: `{ name: string, laborFee: number, partsFee: number, totalPrice: number, duration?: string }`
- `AppointmentCard`
  - `props`: `{ shopName: string, projectName: string, time: string, price: number, status: string }`
- `PartPriceCard`
  - `props`: `{ name: string, items: [{ repairType: string, price: number }] }`
- `CouponCard`
  - `props`: `{ title: string, discount: string, minSpend?: number, expireDate?: string }`

<example>
你附近这两家可以看看。

```spec
{"type":"ShopCard","props":{"shop_id":*,"name":"******"}}
{"type":"CouponCard","props":{"title":"*","discount":"*","expireDate":"****-**-**"}}
```

要我帮你继续看哪家？
</example>

## `action`

- Use only when referring to a specific vehicle.
- Place it immediately after the related text.

Supported `action` types:

- `change_car`
  - fields: `{ "action": "change_car", "current_car_model_id": string }`
- `invite_shop`
  - Use when the user searches for a specific shop by name but no results are found (shop not on platform).
  - Guide the user to invite the shop to join.
  - fields: `{ "action": "invite_shop", "shop_name": string }`

<example>
那我按 `2021款大众朗逸 1.5L` 继续帮你看。

```action
{"action":"change_car","current_car_model_id":"******"}
```

接下来帮你估个价。
</example>

---

很抱歉，"***修理厂"目前还没有入驻话痨说车平台。您可以邀请他们加入，入驻后预订还能享受话痨预订9折优惠哦！

<example>
```action
{"action":"invite_shop","shop_name":"******"}
```
</example>
