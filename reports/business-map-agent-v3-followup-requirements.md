# BusinessMapAgent V3 Follow-up Requirements

## Context

The latest update is a meaningful improvement.

In particular, it now includes:

- live-model navigator evaluation
- live-model MainAgent behavior evaluation
- a labeled navigator dataset and scored results
- executable evaluation scripts

This is a real step forward.

However, there are still several issues that must be addressed before the validation package can be considered fully coherent and acceptance-ready.

## Additional Follow-up Requirements

### 1. Rename or separate the current MainAgent behavior evaluation

The current `MainAgent behavior evaluation` is not true MainAgent runtime validation.

The script:

- manually constructs the prompt
- manually injects `[business_map_slice]` and `[state_tree]`
- registers mock `update_state_tree` and `read_business_node` tools

This is useful and should be kept, but it is more accurately described as:

- prompt-level live-model behavior evaluation
- or simulated MainAgent behavior evaluation

It is not the same as validating the real runtime path through:

- `create_agent_app()`
- actual hook execution
- actual request-context injection
- actual runtime tool registration and invocation

Required action:

- rename the current section accordingly, or
- add a separate section for true runtime validation

### 2. Prove the `read_business_node` path with a live-model case

The current behavior evaluation does not actually prove the `read_business_node` path.

In the provided scenario, `read_business_node` was not called and was treated as optional.

That explanation is reasonable, but it means the path itself remains unproven.

Required action:

- add at least one live-model scenario where `read_business_node` is genuinely required to complete the task
- show that the model actually invokes it
- include the raw output and tool call trace

### 3. Add explicit output-format compliance metrics for Navigator

The navigator evaluation currently uses `parse_node_ids()` with recovery heuristics.

That means the current metrics mostly evaluate:

- whether the correct ids can be recovered after parsing

But this does not cleanly measure protocol compliance.

Required action:

add separate metrics for:

- strict format compliance rate
  - final output contains only valid node ids and delimiters, with no extra JSON, explanation, or tool echo
- contaminated-but-recoverable rate
  - final output violates the format, but the parser can still recover an acceptable answer
- hard-invalid rate
  - final output violates the format and cannot be recovered into an acceptable answer

This is especially important because the current report already identifies JSON/tool-output contamination as a real issue.

### 4. Synchronize the validation matrix with the v2 report

The validation matrix is now inconsistent with the updated v2 report.

The main report says live-model evaluation has been completed for Section D and Section E, while the matrix still marks them as pending.

Required action:

- update the matrix so that it is fully consistent with the current report
- distinguish between:
  - completed live-model evaluation
  - completed true runtime validation
  - still-pending validation items

### 5. Provide raw evidence for the repeated-run `update_state_tree` reliability claim

The report states that `update_state_tree` reliability is approximately 33% across repeated runs.

That may be true, but this claim needs supporting evidence.

Required action:

provide:

- number of repeated runs
- repeated-run command
- per-run outcome summary
- raw logs or run artifacts
- exact scoring rule used to classify success/failure

Without that evidence, the 33% reliability statement is only an assertion.

## Recommended Terminology

To keep the report precise, use the following distinctions:

- `Live-model prompt-level evaluation`
- `True runtime validation`
- `Recovered correctness after parsing`
- `Strict output-format compliance`

Avoid using one label to cover all of these at once.

## Bottom Line

The latest package is substantially better than the previous version.

But before acceptance, I still need:

1. accurate naming of the MainAgent behavior evaluation
2. one live-model case that actually proves `read_business_node`
3. explicit Navigator format-compliance metrics
4. synchronized reporting between the matrix and the main report
5. raw evidence for the repeated-run `update_state_tree` reliability claim
