# BusinessMapAgent V4 Final Review

## Findings

### Medium

1. S6 conclusion still over-claims what the evidence proves.

The current wording says:

- "This is a YAML content granularity issue, not a code or prompt defect."

That is stronger than the evidence supports.

What the current evidence actually proves is narrower:

- in the current prompt + current slice design + current YAML content, the model does not naturally self-initiate `read_business_node` in the two S6 scenarios
- S5 proves the tool path works when the prompt/slice explicitly makes the need visible

What it does **not** prove:

- that prompt design is not a contributing factor
- that slice design is not a contributing factor
- that runtime tool affordance is not a contributing factor
- that YAML content granularity is the only root cause

References:

- [business-map-agent-validation-report-v2.md](/mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent/reports/business-map-agent-validation-report-v2.md#L476)
- [business-map-agent-validation-report-v2.md](/mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent/reports/business-map-agent-validation-report-v2.md#L482)
- [naturalistic-read-node-eval-output.txt](/mnt/e/Documents/github/com.celiang.hlsc.service.ai.chatagent/reports/naturalistic-read-node-eval-output.txt)

Required wording change:

- replace the root-cause statement with a bounded conclusion such as:
  "The current evidence suggests that YAML specificity is one important factor, but this evaluation does not isolate YAML from prompt, slice-construction, or tool-affordance effects."

## Overall Assessment

Apart from the wording issue above, this revision is materially better and mostly internally consistent.

The package now has:

- explicit live-model navigator metrics
- prompt-level live-model MainAgent evidence
- raw artifacts and runnable evaluation scripts
- a clear negative finding for naturalistic `read_business_node`

That is enough for a substantially stronger review package.

## Residual Risks

These are no longer documentation-coherence issues, but they remain product-validation risks:

- true runtime MainAgent validation is still pending
- real multi-turn replay validation is still pending
- `update_state_tree` call reliability is still weak at 60%
- navigator exact match, state-dependent routing, multi-path recall, and strict format compliance are still below acceptance-level quality

## Suggested Message To The Team

Thanks. This revision is much stronger and I do not see any new blocking validation gaps.

I only need one final wording correction in the report: please soften the S6 root-cause conclusion. The current evidence shows that, under the current prompt/slice/YAML setup, the model does not naturally invoke `read_business_node` in those naturalistic cases. It does not yet prove that YAML granularity is the only cause or that prompt/slice factors are excluded.

If you revise that sentence to keep the conclusion evidence-bounded, I would consider this review package in good shape for this round.
