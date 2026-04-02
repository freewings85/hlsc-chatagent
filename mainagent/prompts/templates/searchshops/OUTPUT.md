# Output

## `spec`

- For structured result data only.
- Do not use for greetings or simple confirmations.
- Use valid `type` and `props` only.

Supported `spec` types:

- `ShopCard`
  - `props`: `{ shop_id: number, name: string }`

<example>
你附近这两家可以看看。

```spec
{"type":"ShopCard","props":{"shop_id":*,"name":"******"}}
```

要我帮你继续看哪家？
</example>

## `action`

- `invite_shop`
  - Show an invite button when search_shops returns no results.
  - fields: `{ "action": "invite_shop" }`

<example>
这家店暂时没有入驻平台，您可以邀请他们加入。

```action
{"action":"invite_shop"}
```
</example>
