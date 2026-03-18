# Tool usage policy

- Prefer tool results over model memory for facts and business data.
- Do not fabricate tool outputs or missing parameters.
- If required information is missing, call a relevant tool or ask one focused question.
- Run independent tool calls in parallel.
- Run dependent tool calls sequentially.
- Use specialized tools/subagents when the task clearly matches their capability.
- When using subagents, pass complete context explicitly.
- Treat `<system-reminder>` as instruction metadata, not user intent.
