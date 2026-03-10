# Contract Registry — Human-Readable Guide

**Source of truth:** `contract_registry.yaml` (this file is documentation only)

## How to Use

1. **Writing an agent?** Check `artifacts` for your inputs/outputs. Use the
   `required_fields` to validate your output before writing.

2. **Debugging a handoff failure?** Find the artifact in the registry, check
   the producer and consumers, verify the required fields are present.

3. **Adding a new artifact?** Add it to `contract_registry.yaml` with path,
   producer, consumers, and required_fields. Update `validate_handoff.py`.

## Identity Rules

| Rule | Description |
|------|-------------|
| CR Ownership | `intent.cr` is authoritative. Never infer CR from intent ID. |
| Function Key | `(target_file, function_name)` is the unique key. Bare function names are ambiguous. |
| Snapshot Naming | `filepath.replace("/", "__").replace("\\", "__") + ".snapshot"` — path-encoded. |
| Numeric Precision | Python `Decimal` with `ROUND_HALF_EVEN` everywhere. |

## Artifact Flow

```
/iq-plan:
  Intake ──→ change_requests.yaml ──→ Understand ──→ code_understanding.yaml ──→ Plan
  Plan ──→ intent_graph.yaml + execution_plan.md + execution_order.yaml + file_hashes.yaml
  ──→ [GATE 1: Developer approves]

/iq-execute:
  [GATE 2a: source preflight]
  File-Copy Worker
  [GATE 2b: target preflight] ──→ parser-cache/*.json
  Change Engine Workers ──→ operations_log.yaml + snapshots/
  [GATE 4: aggregate verify]

/iq-review:
  Validator ──→ validator_results.yaml (+ corrections.yaml if self-corrected)
  Diff ──→ diff_report.md + changes.diff
  Semantic Verifier ──→ semantic_verification.yaml + semantic_report.md
  Report ──→ traceability_matrix.md + change_summary.md
  [GATE 5: Developer approves]
```

## Removed Artifacts (v0.3.3 → v0.4.0)

| Old Artifact | Replacement |
|-------------|-------------|
| `analysis/code_discovery.yaml` | `analysis/code_understanding.yaml` |
| `analysis/analyzer_output/cr-NNN-analysis.yaml` | `code_understanding.yaml` → `change_requests.{cr_id}.fub` |
| `analysis/files_to_copy.yaml` | `code_understanding.yaml` → `change_requests.{cr_id}.needs_copy` |

## Enums

| Enum | Values |
|------|--------|
| capability | value_editing, structure_insertion, file_creation, flow_modification |
| target_kind | call, assignment, constant, case_label, code_block |
| intent_origin | direct_cr, caller_fix, rework |
| gate_names | Gate 1, Gate 2a, Gate 2b, Gate 3, Gate 4, Gate 5 |
