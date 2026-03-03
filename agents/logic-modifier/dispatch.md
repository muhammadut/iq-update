# Logic Modifier — Dispatch

## Module Routing Table

**Note:** `measure_case_indent()` is defined in **core.md** (Shared Helper Functions
section) and available to ALL modules below. Modules that need it (case-block-insertion,
new-endorsement-file) do not need to load each other.

| Operation Pattern | Module to Load | Condition |
|---|---|---|
| new_coverage_type (constant) | modules/constant-insertion.md | constant_name present, no case_block_type |
| new_coverage_type (case block) | modules/case-block-insertion.md | case_block_type present |
| new_coverage_type (ResourceID) | modules/dat-constants.md | target file is ResourceID.vb |
| new_endorsement_flat | modules/new-endorsement-file.md | needs_new_file: true |
| new_liability_option | modules/new-endorsement-file.md | needs_new_file: true |
| eligibility_rules | modules/validation-function.md | -- |
| alert_message | modules/alert-message.md | -- |

## Cross-Cutting Branch
- If `needs_new_file: true` -> skip Steps 3-8, go directly to Step 9 in the module
- If `needs_new_file: false` -> normal Steps 3-8 flow from core.md

## When to Load Edge Cases
Load `edge-cases.md` ONLY when:
- An error condition fires
- The capsule flags `load_edge_cases: true`
- Content mismatch or ambiguous anchor detected
- A rework instruction is received

## Pattern-Specific Field Requirements

These are the field checks that `validate_operation()` (Step 1 in core.md) enforces
per pattern. Use this table to understand what fields each pattern requires before
routing to the appropriate module.

```python
# Pattern-specific field checks (from validate_operation in core.md Step 1)
p = op["parameters"]
pat = op["pattern"]

if pat == "new_coverage_type":
    if "constant_name" not in p and "case_block_type" not in p:
        return FAIL("new_coverage_type requires constant_name or case_block_type")

elif pat == "new_endorsement_flat":
    for f in ("endorsement_name", "province_code", "lob", "effective_date"):
        if f not in p:
            return FAIL(f"new_endorsement_flat requires parameters.{f}")
    if op.get("needs_new_file") is not True:
        return FAIL("new_endorsement_flat requires needs_new_file: true")

elif pat == "new_liability_option":
    for f in ("option_code", "call_target"):
        if f not in p:
            return FAIL(f"new_liability_option requires parameters.{f}")

elif pat == "eligibility_rules":
    for f in ("function_name", "function_type"):
        if f not in p:
            return FAIL(f"eligibility_rules requires parameters.{f}")

elif pat == "alert_message":
    for f in ("alert_text", "alert_action", "condition"):
        if f not in p:
            return FAIL(f"alert_message requires parameters.{f}")
```

## Routing Decision Tree

```
operation.pattern
  |
  +-- "new_coverage_type"
  |     |
  |     +-- target file ends with "ResourceID.vb"?
  |     |     YES -> modules/dat-constants.md (Step 5c)
  |     |
  |     +-- "case_block_type" in parameters?
  |     |     YES -> modules/case-block-insertion.md (Step 5b)
  |     |
  |     +-- "constant_name" in parameters?
  |           YES -> modules/constant-insertion.md (Step 5a)
  |
  +-- "new_endorsement_flat"
  |     +-> modules/new-endorsement-file.md (Step 5d + Step 9 + Step 10)
  |
  +-- "new_liability_option"
  |     +-> modules/new-endorsement-file.md (Step 5d + Step 9 + Step 10)
  |
  +-- "eligibility_rules"
  |     +-> modules/validation-function.md (Step 5e)
  |
  +-- "alert_message"
        +-> modules/alert-message.md (Step 5f)
```
