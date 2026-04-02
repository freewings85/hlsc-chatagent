# Output

## `spec`

- For structured result data only.
- Do not use for greetings or simple confirmations.
- Use valid `type` and `props` only.

Supported `spec` types:

- `CouponCard`
  - `props`: `{ shop_id: number, shop_name: string, activity_id: number, activity_name: string }`
- `ShopCard`
  - `props`: `{ shop_id: number, name: string, address?: string, phone?: string, distance?: string, rating?: number }`

<example>
帮你找到这些优惠。

```spec
{"type":"CouponCard","props":{"shop_id":*,"shop_name":"*","activity_id":*,"activity_name":"*"}}
{"type":"ShopCard","props":{"shop_id":*,"name":"******"}}
```

要我帮你看看哪个最划算？
</example>

## `action`

- `change_car`
  - Use only when your reply mentions a specific car model — provides an entry for user to correct it if wrong. Requires a valid current_car_model_id. Do NOT use when there is no car info yet — use the collect_car_info tool to collect car info from scratch.
  - fields: `{ "action": "change_car", "current_car_model_id": string }`

<example>
那我按 `2021款大众朗逸 1.5L` 继续帮你看。

```action
{"action":"change_car","current_car_model_id":"******"}
```

接下来帮你查优惠。
</example>
