# Output

## `spec`

- For structured result data only.
- Do not use for greetings or simple confirmations.
- Use valid `type` and `props` only.

Supported `spec` types:

- `ShopCard`
  - `props`: `{ shop_id: number, name: string, address?: string, phone?: string, distance?: string, rating?: number }`

<example>
你附近这两家可以看看。

```spec
{"type":"ShopCard","props":{"shop_id":109,"name":"xx汽修","address":"xx市xx区xx路","phone":"xxx-xxxxxx","distance":"2.3km","rating":4.8}}
```

要我帮你联系哪家？
</example>

- `ContactOrderCard`
  - 联系单生成成功后展示。商户会主动联系用户。
  - `props`: `{ order_id: string, shop_name: string }`

<example>
已帮你生成联系单，商户会主动联系你！

```spec
{"type":"ContactOrderCard","props":{"order_id":"xxx-xxx-xxx","shop_name":"xx汽修"}}
```

商户收到通知后会尽快联系您确认服务细节。
</example>

## `action`

- `invite_shop`
  - Show an invite button when search_shops returns no results.
  - fields: `{ "action": "invite_shop" }`
