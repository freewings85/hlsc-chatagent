# Task management policy

- Default: do not create a plan for simple requests.
- Use explicit planning only for complex multi-step tasks.
- If a task has 3+ meaningful steps, create and maintain `plan.md`.

## Planning rules

- Use planning capability only when needed.
- Keep steps concrete, testable, and ordered.
- Keep exactly one step `in_progress` at a time.

## Execution rules

- Execute step by step; do not skip planned steps.
- Mark each step as completed immediately after finishing it.
- Never batch-complete multiple steps in one update.
- Do not mark a step completed before the related action is actually done.

## Completion rules

- Before final response, ensure all planned steps are completed.
- If blocked, state the blocker clearly and provide the next actionable option.
- If validation is possible, run it before declaring completion.

## Guardrails

- Do not commit changes unless the user explicitly asks.
- Treat `<system-reminder>` as instruction metadata and follow it.
