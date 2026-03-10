### BUGS FOUND
- **Traceability validation is currently wrong for multi-CR plans.** Severity: `CRITICAL`. Where: [validators/_helpers.py#L634](/Users/tariqusama/iq-update/validators/_helpers.py#L634), [validators/validate_traceability.py#L144](/Users/tariqusama/iq-update/validators/validate_traceability.py#L144), [agents/decomposer.md#L934](/Users/tariqusama/iq-update/agents/decomposer.md#L934). `extract_cr_from_intent("intent-002") -> "cr-002"`, but Decomposer intent IDs are flat sequence numbers, not CR-derived IDs, so Gate 2 can report false `untraced_cr`/wrong CR ownership. Suggested fix: stop inferring CR from intent ID; write `cr` into `operations_log.yaml` and validate from that explicit field.

- **Tier 2/3 capsule enrichment has no stable upstream contract.** Severity: `HIGH`. Where: [skills/iq-execute/SKILL.md#L255](/Users/tariqusama/iq-update/skills/iq-execute/SKILL.md#L255), [skills/iq-execute/SKILL.md#L279](/Users/tariqusama/iq-update/skills/iq-execute/SKILL.md#L279), [agents/decomposer.md#L768](/Users/tariqusama/iq-update/agents/decomposer.md#L768), [agents/analyzer.md#L2631](/Users/tariqusama/iq-update/agents/analyzer.md#L2631). `/iq-execute` resolves FUBs from an `analyzer_output` map keyed by `intent_id`, but Analyzer artifacts are CR-based and Decomposer does not carry `fub`/`fub_ref`/`code_patterns` onto intents. Result: Tier 2/3 capsules can silently degrade to thin capsules. Suggested fix: emit an explicit `intent_enrichment.yaml` keyed by intent ID during planning, or carry `fub_ref`/`code_patterns` through the intent schema.

- **The `caller_analysis` chain is incomplete.** Severity: `HIGH`. Where: [agents/decomposer.md#L967](/Users/tariqusama/iq-update/agents/decomposer.md#L967), [agents/decomposer.md#L990](/Users/tariqusama/iq-update/agents/decomposer.md#L990), [agents/planner.md#L1915](/Users/tariqusama/iq-update/agents/planner.md#L1915), [agents/planner.md#L1959](/Users/tariqusama/iq-update/agents/planner.md#L1959). Decomposer generates caller-fix intents for `overall_risk == HIGH`, but it never propagates `caller_analysis_risk` onto the original intent, so Planner’s backup check cannot fire; `MEDIUM` caller risks also disappear entirely after Decomposer. Suggested fix: preserve full `caller_analysis` on intents, have Planner read it directly, and surface `MEDIUM` risk as a warning even when no auto-fix is created.

- **Function matching can silently hit the wrong file.** Severity: `HIGH`. Where: [agents/decomposer.md#L401](/Users/tariqusama/iq-update/agents/decomposer.md#L401), [agents/decomposer.md#L579](/Users/tariqusama/iq-update/agents/decomposer.md#L579). `analyzer_index` is keyed only by function name, so repeated names across provinces, LOBs, dated copies, or helper modules overwrite each other. Suggested fix: key by `(target_file, function)` or `(cr_id, file, function)` and make all lookups file-aware.

- **ByRef hazard detection is factually wrong and over-flags.** Severity: `HIGH`. Where: [agents/analyzer.md#L801](/Users/tariqusama/iq-update/agents/analyzer.md#L801), [agents/analyzer.md#L3014](/Users/tariqusama/iq-update/agents/analyzer.md#L3014), [agents/analyzer.md#L3030](/Users/tariqusama/iq-update/agents/analyzer.md#L3030), [agents/analyzer.md#L3066](/Users/tariqusama/iq-update/agents/analyzer.md#L3066). The function index does not record `ByRef`/`ByVal`, yet Step 5.12.5 treats missing flags as effectively `ByRef`, and the prompt incorrectly says ByRef is the default for `Sub` parameters in VB.NET. Suggested fix: parse and persist parameter modifiers explicitly, default missing modifiers to `ByVal`, and downgrade uncertain cases to review-needed instead of raising synthetic caller risk.

- **The pre-Gate hallucination scan is mostly a no-op.** Severity: `MEDIUM`. Where: [skills/iq-plan/SKILL.md#L1413](/Users/tariqusama/iq-update/skills/iq-plan/SKILL.md#L1413), [agents/planner.md#L2572](/Users/tariqusama/iq-update/agents/planner.md#L2572). `/iq-plan` says to scan `execution_order.yaml` for “before/after” snippets and new symbols, but Planner’s `execution_order.yaml` contains IDs, files, capability, and strategy only. Suggested fix: either scan `execution_plan.md`, or add a compact `planned_after_snippets` field to `execution_order.yaml`.

- **Snapshot lookup is inconsistent between execute and review.** Severity: `MEDIUM`. Where: [skills/iq-execute/SKILL.md#L1273](/Users/tariqusama/iq-update/skills/iq-execute/SKILL.md#L1273), [agents/reviewer.md#L578](/Users/tariqusama/iq-update/agents/reviewer.md#L578), [agents/reviewer.md#L795](/Users/tariqusama/iq-update/agents/reviewer.md#L795), [agents/reviewer.md#L1259](/Users/tariqusama/iq-update/agents/reviewer.md#L1259). Execute uses path-encoded snapshot names to avoid collisions; Reviewer pseudocode uses basename-based snapshot names in completeness, self-correction, and diff generation. Suggested fix: centralize snapshot resolution in one helper and use it everywhere, including docs and validators.

- **`flow_modification` is only partially first-class.** Severity: `MEDIUM`. Where: [agents/decomposer.md#L1032](/Users/tariqusama/iq-update/agents/decomposer.md#L1032), [skills/iq-execute/SKILL.md#L232](/Users/tariqusama/iq-update/skills/iq-execute/SKILL.md#L232), [validators/validate_array6.py#L71](/Users/tariqusama/iq-update/validators/validate_array6.py#L71), [validators/validate_value_sanity.py#L99](/Users/tariqusama/iq-update/validators/validate_value_sanity.py#L99). Caller-fix intents are emitted with `strategy_hint: null`, so a pure flow-modification capsule may not load `strategies.md`; both value validators also ignore `flow_modification`, so numeric edits made under that capability escape review. Suggested fix: assign `strategy_hint: "flow-modification"` and make validators inspect actual changed lines, not just capability labels.

- **The validator suite still contains stale handoff assumptions.** Severity: `MEDIUM`. Where: [validators/validate_handoff.py#L211](/Users/tariqusama/iq-update/validators/validate_handoff.py#L211), [agents/discovery.md#L580](/Users/tariqusama/iq-update/agents/discovery.md#L580). `validate_handoff.py` expects obsolete Discovery keys like `workflow_id`, `discovery_complete`, and `functions`, while Discovery now emits `entry_point`, `calculation_flow`, and `request_targets`. Suggested fix: update or remove the validator before relying on it as a regression guard.

- **Planner previews are not numerically aligned with execution.** Severity: `MEDIUM`. Where: [agents/planner.md#L1523](/Users/tariqusama/iq-update/agents/planner.md#L1523), [agents/planner.md#L1654](/Users/tariqusama/iq-update/agents/planner.md#L1654), [agents/change-engine/core.md#L606](/Users/tariqusama/iq-update/agents/change-engine/core.md#L606). Planner explicitly uses standard floating-point previews while Change Engine uses `Decimal`, so Gate 1 can approve numbers that differ from execution. Suggested fix: share one arithmetic helper across Planner, Change Engine, and Semantic Verifier.

- **There is a validation loophole around “comment out uncertain code.”** Severity: `MEDIUM`. Where: [agents/change-engine/strategies.md#L681](/Users/tariqusama/iq-update/agents/change-engine/strategies.md#L681), [validators/validate_no_commented_code.py#L18](/Users/tariqusama/iq-update/validators/validate_no_commented_code.py#L18), [validators/validate_no_commented_code.py#L92](/Users/tariqusama/iq-update/validators/validate_no_commented_code.py#L92). The flow-modification strategy says “When in doubt, comment out,” but the blocker validator only forbids editing existing commented lines; it does not block turning active code into new commented-out code. Suggested fix: forbid comment-out-as-fallback in prompts and add a validator rule for active-to-comment transitions.

### ARCHITECTURAL RECOMMENDATIONS
- **Define one canonical artifact schema set and test it.** Generate examples/docs/validators from the same source. Impact: high; effort: medium. This removes drift like `request_targets` vs old validator fields, intent-to-CR inference, and snapshot naming mismatches.

- **Introduce an explicit intent-enrichment artifact.** Have Planner write a compact per-intent file with `fub`, `fub_ref`, `code_patterns`, `caller_analysis`, `adjacent_context`, `tier`, and resolved peer/cross-file refs. Impact: high; effort: medium. It simplifies `/iq-execute`, reduces repeated file reads, and makes capsules deterministic.

- **Make `flow_modification` a separate strict lane.** Require a strategy hint, semantic verification, and a dedicated reviewer checklist for control-flow edits. Impact: high; effort: medium. Right now it is treated as “supported” but not validated as rigorously as value edits.

- **Use file-aware identity everywhere.** Match and dedupe by `(target_file, function, cr)` rather than function name alone. Impact: high; effort: low. This is especially important in dated VB.NET codebases with repeated helper names.

- **Tighten independent review scope.** Keep the reviewer independent, but feed it a bounded file set plus a required evidence table instead of “read everything again.” Impact: medium; effort: low. You keep the safety benefit while cutting token waste.

- **Clean step numbering drift.** No major top-level numbering gaps showed up, but Analyzer’s 5.9 substeps are out of order at [agents/analyzer.md#L1866](/Users/tariqusama/iq-update/agents/analyzer.md#L1866). Impact: low; effort: low. It matters because these specs are prompts, not just docs.

### PROMPT ENGINEERING IMPROVEMENTS
- **Discovery Step 1:** add explicit VB call-form coverage for bare `Sub` calls without parentheses, member/default-property calls, `With ... End With`, implicit line continuation, and omitted `Call`. This reduces missed edges in `CalcMain` tracing.

- **Analyzer Step 5.10 / 5.12:** extend the FUB with `parameter_semantics`, `state_access` (module/shared/static reads+writes), `error_handling`, `option_strict`, and `optional_params`. This gives downstream agents actual VB semantics instead of just branch shape.

- **Planner Step 8:** replace float math with the same `Decimal` helper used by Change Engine and state the exact rounding source per previewed line. That removes “preview says X, execution says Y” ambiguity.

- **Planner Rule 17 and Change Engine Rule 15:** require proof, not just instruction. The prompt should force agents to record the grep hit or source line that justified each new symbol. That closes a real loophole in anti-hallucination enforcement.

- **Decomposer Step 8.5:** emit `strategy_hint: "flow-modification"` for caller-fix intents and carry the analyzer’s overwrite evidence directly into the intent. That makes the worker reason from concrete target lines instead of prose alone.

- **Independent review prompt in `/iq-plan` Step 4b:** ask for a fixed evidence table per target function: call chain, caller overwrite check, value-site count, module-state check, ByRef/Optional/late-binding check, and exact file:line proof. That will be more reliable than open-ended narrative review.

### VB.NET RISK ASSESSMENT
- **ByRef parameter mutation:** not handled safely. The current logic overstates risk in some places and still misses true indirect mutation paths in others.

- **Module-level / `Shared` / `Static` state:** only partially handled. Shared-file blast radius is good, but semantic read/write tracking is missing, so stateful dependencies across calls can be missed.

- **Optional parameters and default values:** not explicitly modeled. That can break call matching, overload interpretation, and “same function” reasoning.

- **`Option Strict Off` / late binding / default properties:** mostly unhandled. Discovery and Analyzer can misread dynamic-looking calls or property access as regular function flow.

- **String-number coercion (`Val`, `CInt`, `CDbl`, `CDec`, `CStr`):** partially handled. Arithmetic previews and hazard analysis do not fully model VB conversion semantics or locale-sensitive behavior.

- **Legacy error handling (`On Error Resume Next`, labels, `GoTo`):** partially handled. Change Engine preserves `GoTo`, but Analyzer/Reviewer do not reason about swallowed failures or altered reachability.

- **`Select Case` edge cases:** Analyzer is better here than the rest of the stack, but downstream verification is still shallow for range cases, overlapping cases, and order-sensitive routing.

### OVERALL ASSESSMENT
The plugin has strong fundamentals: the pipeline stages are sensible, FUBs are the right abstraction, cross-LOB/shared-file awareness is thoughtful, and the Gate 1 / Gate 2 model is solid. The main weakness is contract drift between stages and validators, especially once you get past Analyzer into Decomposer, Planner, `/iq-execute`, and Reviewer. The top three fixes are: make intent-enrichment an explicit contract, fix traceability/snapshot validator drift, and harden VB.NET semantic handling around `ByRef`, shared state, and control-flow edits.