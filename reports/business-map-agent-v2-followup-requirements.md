# BusinessMapAgent V2 Follow-up Requirements

## Context

The v2 validation report is materially better than v1. It correctly narrows several earlier claims and clearly separates:

- unit tests
- component integration tests
- mocked runtime tests
- unverified runtime behavior

However, there is still one important follow-up requirement.

## Additional Requirement

The report currently treats the following items as pending because they require a real LLM:

- `D. MainAgent behavior validation`
- `E. Real-model navigator evaluation`

This is not a sufficient closure reason in this repository.

The repository already supports live-model execution:

- shared LLM configuration exists in `sdk/agent_sdk/_config/settings.py`
- model creation exists in `sdk/agent_sdk/_agent/model.py`
- live-model environment templates already exist for MainAgent and subagents
- the repository already contains real-LLM end-to-end test patterns under `mainagent/tests/e2e/`

Therefore, these items should not be treated as blocked prerequisites. They should be treated as unfinished validation work.

## Required Update To The Validation Plan

Please revise the validation plan so that items D and E are explicitly treated as required next-step validation using the existing live-model configuration.

## Required Deliverables

Please provide the following for the next revision.

### 1. Live-model validation plan

Provide:

- model / deployment name
- environment used
- prompt version / prompt source
- execution method
- scoring method
- pass/fail thresholds

### 2. MainAgent behavior validation using a real LLM

Validate the following with a live model:

- when `[business_map_slice]` is injected, the next user-facing question follows the current checklist
- when a node is completed, `update_state_tree` is called
- when more node detail is needed, `read_business_node` is called
- when there is no business progress, `update_state_tree` is not called

### 3. Real-model navigator evaluation

Provide a labeled evaluation set with at least 60 to 100 samples.

Required metrics:

- exact match rate
- acceptable ancestor match rate
- over-deep error rate
- multi-path precision
- multi-path recall
- error analysis

### 4. Raw evidence

Provide:

- executed commands
- raw output
- dataset file
- scored result file
- representative failure cases

## Additional Scope Requirement

If `recent_history` remains empty in the current implementation, the report must explicitly state that history-dependent continuation behavior is still not evaluated.

Examples include:

- pronoun-like follow-ups
- continuation turns such as "that one", "okay then", "book it", "that shop"
- context carry-over that depends on recent dialogue rather than only the current turn and state tree

## Session Isolation Wording

The wording on session safety should remain precise.

Preferred wording:

- `contextvar-based task-level session isolation validated`
- `full concurrent runtime isolation under production-like load not yet validated`

Avoid broader wording that suggests production-grade concurrency behavior has already been fully proven.

## Bottom Line

V2 is a meaningful improvement, but D and E should now be treated as required validation work, not as blocked-by-prerequisite items.
