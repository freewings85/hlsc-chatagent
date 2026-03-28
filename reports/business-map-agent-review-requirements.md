# BusinessMapAgent Review Requirements

## Scope

This note is based on a documentation and code review of the current BusinessMapAgent work.

I did not run the test suite in this environment because the machine is currently shared and in use. The findings below are based on:

- the implementation under `mainagent/`, `extensions/`, and `subagents/business_map_agent/`
- the design and review documents under `doc/`
- the current test files and their stated coverage

## Executive Summary

The overall architecture direction is reasonable:

- a navigation layer locates the current business node
- a code layer assembles a YAML-derived slice
- MainAgent uses the slice and a persisted state tree to drive the conversation

However, the current validation package is not yet strong enough to support the claims made in the review report.

The biggest issues are:

1. The reported "E2E" coverage is overstated.
2. A high-risk session isolation issue is not covered by tests.
3. Navigator accuracy has not been validated against a real model.
4. Some behavior described in the documents does not match the implementation.

## Key Findings

### 1. The current "E2E" tests are not true end-to-end tests

The report describes `extensions/tests/test_business_map_e2e.py` as Phase 5 end-to-end validation.

That is not accurate.

The current file mainly covers:

- `StateTreeService`
- `_compress_state_tree`
- `_parse_node_ids`
- `assemble_slice`
- formatter behavior with manually injected preprocessor state
- simple performance assertions

It does not actually verify the full runtime chain:

- request enters MainAgent
- `BusinessMapPreprocessor.__call__` runs
- `call_subagent(...)` is invoked
- returned node ids are parsed
- slice is assembled
- request context is injected
- MainAgent behavior follows the injected slice
- state tree is updated through the real tool path

This means the current test file is closer to a component integration suite than a true E2E suite.

### 2. Session isolation is a serious unverified risk

`BusinessMapPreprocessor` stores the active session in a single mutable field:

- `_current_session_id`

`HlscContextFormatter` then reads slice and state-tree data by using that shared field.

This creates a clear concurrency risk: if two sessions are processed close together, one session may read the other session's injected slice or state tree.

This is a production-grade correctness issue and should be treated as high priority.

There is currently no validation proving session-safe behavior under interleaving or concurrent requests.

### 3. Navigator "accuracy" is not validated yet

The current navigator tests use mocked model behavior. That is useful for validating:

- tool wiring
- agent loop execution
- expected output shape

But it does not validate:

- the actual `system.md`
- real prompt-following behavior
- ambiguity handling under a real LLM
- over-routing vs. under-routing
- multi-turn carry-over quality

The review report already hints at this risk, but the acceptance bar should be much stricter before calling the navigator validated.

### 4. The fallback behavior described in docs does not match the code

The code comments in `mainagent/src/business_map_hook.py` suggest a simplified keyword-matching fallback when the subagent call fails.

The current implementation does not do that. On exception, it logs a warning and returns an empty node list.

That means the practical behavior today is:

- no subagent response
- no node ids
- no slice assembly
- no business-map guidance for that turn

This mismatch must be resolved. Either:

- implement the fallback and test it, or
- remove the fallback claim from the documentation and report

### 5. The review report overstates certainty

The report makes strong claims such as:

- "151 tests all passed"
- "Phase 5 E2E validation complete"
- "coverage includes E2E"

Given the current test content, these statements are too strong.

Even if the numeric count is correct, the coverage classification is not.

The team should revise the wording to distinguish:

- unit tests
- component integration tests
- mocked agent-loop tests
- true end-to-end runtime tests
- real-model evaluation

## Required Corrections To The Documentation

The team should update the review and validation documents with the following corrections:

1. Stop calling `test_business_map_e2e.py` an E2E suite unless it actually exercises the real runtime chain.
2. Explicitly document that current navigator tests use mocked model behavior.
3. Explicitly document that real-model accuracy is still pending validation.
4. Correct the fallback description so it matches the code.
5. Add session isolation as a first-class risk item.
6. Separate "all tests passed" from "business readiness validated". These are not the same claim.

## Required Validation Deliverables

The team should provide a revised validation package with the following artifacts.

### A. Test inventory with raw evidence

Provide:

- exact test commands
- environment information
- collected test list
- raw test output
- mapping from each test file to its actual coverage category

Coverage categories must be explicit:

- Unit
- Component Integration
- Mocked Runtime Flow
- True End-to-End
- Real-Model Evaluation

### B. Hook-level integration tests

Add tests that directly exercise `BusinessMapPreprocessor.__call__` with mocked subagent responses, covering:

- successful node-id return
- multiple node ids
- invalid node ids
- empty string response
- malformed response
- timeout
- exception from `call_subagent`
- missing state tree
- existing state tree

These tests must validate:

- correct slice assembly
- correct state-tree retention
- correct per-session cache behavior
- graceful degradation behavior

### C. Session isolation tests

Add concurrency or interleaving tests that prove two sessions do not leak state into each other.

Minimum required scenarios:

- session A starts, session B starts, formatter for A still sees A
- session A and B each receive different slice data, no cross-read
- session A has state tree, session B does not, no contamination
- repeated alternation across multiple turns

This should be treated as a release-blocking validation item.

### D. MainAgent behavior validation

Add tests that verify MainAgent actually uses the injected guidance.

Minimum required scenarios:

- when `[business_map_slice]` is present, the next question follows the current checklist
- when a node is completed, `update_state_tree` is called
- when extra node detail is needed, `read_business_node` is called
- when no business progress occurs, `update_state_tree` is not called

This validation should not be limited to prompt prose review. It should verify behavior.

### E. Real-model navigator evaluation

Provide an offline evaluation set for the real navigator prompt and real model configuration.

Minimum dataset size:

- 60 to 100 samples

Each sample should include:

- user utterance
- current `state_tree` or compressed briefing
- expected node id(s)
- acceptable ancestor-level answers, if any
- unacceptable over-deep answers
- rationale

Required metrics:

- exact match rate
- acceptable ancestor match rate
- over-deep error rate
- multi-path precision
- multi-path recall

The team should also include 10 real multi-turn transcripts or realistic replay cases with expected node transitions.

## Required Scenario Coverage

At minimum, the revised validation must cover the following business scenarios.

### Core routing scenarios

- explicit direct-expression routing
- fuzzy-intent routing
- symptom-based routing
- merchant-search routing
- booking/build-plan routing

### Ambiguity handling

- stop at parent when evidence is insufficient
- do not over-drill into a leaf node
- handle mixed signals without hard guessing

### Multi-path routing

- same-turn routing to both saving and merchant-search
- ancestor/descendant deduplication
- deep node plus cross-branch node in one response

### Multi-turn progression

- shallow to deep drill-down across turns
- branch switch after project confirmation
- re-entry after a previously completed step

### Dependency and readiness scenarios

- user asks to book before project confirmation
- user asks to search merchants before required inputs are available
- user changes project after downstream progress already started

### State-tree robustness

- malformed indentation
- multiple `[in progress]` equivalents
- missing current marker
- outputs containing arrows or special delimiters
- restart and recovery from persisted state

### Failure handling

- subagent timeout
- subagent exception
- empty subagent output
- invalid node ids
- duplicate node ids
- subagent unavailable for an entire turn

### Non-target and low-signal inputs

- small talk / unrelated utterances
- domain-adjacent but non-actionable utterances
- vague follow-ups like "that one", "okay then", "book it", "that shop"

## Acceptance Requirements

The team should not consider this feature validated until all of the following are true:

1. Documentation and implementation match on fallback behavior.
2. Session isolation risk is either fixed or explicitly disproven by tests.
3. Hook-level integration is covered.
4. MainAgent behavior against injected guidance is covered.
5. Real-model navigator evaluation is delivered with metrics and sample set.
6. Test reporting distinguishes mocked coverage from true runtime coverage.

## Suggested Response Format From The Team

Ask the team to return:

1. A revised review report.
2. A validation matrix mapping scenarios to tests.
3. Raw evidence for executed tests and evaluation runs.
4. A gap list of what is still unverified.
5. A clear statement of production readiness, with assumptions and remaining risks.

## Bottom Line

The current implementation may be a workable foundation, but the current validation package is not yet strong enough to support a "fully validated" conclusion.

The team should strengthen the evidence, narrow the claims, and specifically prove:

- runtime chain correctness
- session isolation
- MainAgent compliance with injected guidance
- real-model navigator quality
