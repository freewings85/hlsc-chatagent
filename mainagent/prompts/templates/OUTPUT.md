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
  - `props`: `{ name: string, labor_fee: number, parts_fee: number, total_price: number, duration?: string }`
- `AppointmentCard`
  - `props`: `{ shop_name: string, project_name: string, time: string, price: number, status: string }`
- `PartPriceCard`
  - `props`: `{ name: string, items: [{ repairType: string, price: number }] }`
- `CouponCard`
  - `props`: `{ shop_id: number, shop_name: string, activity_id: number, activity_name: string }`

<example>
你附近这两家可以看看。

```spec
{"type":"ShopCard","props":{"shop_id":*,"name":"******"}}
{"type":"CouponCard","props":{"shop_id":*,"shop_name":"*","activity_id":*,"activity_name":"*"}}
```

要我帮你继续看哪家？
</example>

## `action`

- Use only when referring to a specific vehicle.
- Place it immediately after the related text.

Supported `action` types:

- `change_car`
  - Use only when your reply mentions a specific car model — provides an entry for user to correct it if wrong. Requires a valid current_car_model_id. Do NOT use when there is no car info yet — use the collect_car_info tool to collect car info from scratch.
  - fields: `{ "action": "change_car", "current_car_model_id": string }`
- `invite_shop`
  - Show an invite button when search_shops returns no results.
  - fields: `{ "action": "invite_shop" }`

<example>
那我按 `2021款大众朗逸 1.5L` 继续帮你看。

```action
{"action":"change_car","current_car_model_id":"******"}
```

接下来帮你估个价。
</example>

---

<example>
这家店暂时没有入驻平台，您可以邀请他们加入。

```action
{"action":"invite_shop"}
```
</example>
