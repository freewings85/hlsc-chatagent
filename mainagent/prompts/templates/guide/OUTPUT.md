# Output

## `action`

- `change_car`
  - Use only when your reply mentions a specific car model — provides an entry for user to correct it if wrong. Requires a valid current_car_model_id. Do NOT use when there is no car info yet — use the collect_car_info tool to collect car info from scratch.
  - fields: `{ "action": "change_car", "current_car_model_id": string }`

<example>
那我按 `2021款大众朗逸 1.5L` 继续帮你看。

```action
{"action":"change_car","current_car_model_id":"******"}
```

接下来帮你估个价。
</example>
