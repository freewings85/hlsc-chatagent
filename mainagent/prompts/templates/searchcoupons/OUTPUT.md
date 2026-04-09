# Output

## `spec`

- For structured result data only.
- Do not use for greetings or simple confirmations.
- Use valid `type` and `props` only.

Supported `spec` types:

- `CouponCard`
  - `props`: `{ shop_id: number, shop_name: string, coupon_id: string, coupon_name: string}`

<example>
帮你找到这些优惠。

```spec
{"type":"CouponCard","props":{"shop_id":xxx,"shop_name":"xx养车xx店","coupon_id":"xxx","coupon_name":"xx满xx减xx"}}
```

要我帮你领取哪个？
</example>

- `CouponOrderCard`
  - 领取成功后展示。
  - `props`: `{ order_id: string, shop_name: string, coupon_name: string }`

<example>
已帮你领取成功！

```spec
{"type":"CouponOrderCard","props":{"order_id":"xxxx","shop_name":"xxx店","coupon_name":"stringname"}}
```

商家会收到你的领取信息，到店时出示即可。
</example>

## `action`

- `change_car`
  - 触发条件：你的回复中提到了用户的具体车型 → 附带 change_car action，让用户纠正
  - 不适用：用户还没有车型信息时，应调用 collect_car_info 工具从头收集
  - fields: `{ "action": "change_car", "current_car_model_id": string }`
