# Rate Modifier — Dispatch Table

This file routes each operation to the correct module card(s). Workers always
load this file after `core.md`.

---

## Operation Type YAML Examples & Field Semantics

### analysis/operations/op-{SRD}-{NN}.yaml (from Analyzer)

Each operation YAML contains everything the Rate Modifier needs: target file,
function name, line hints, content patterns, rounding rules, and computed values.
Three operation types are supported:

#### Type 1: base_rate_increase (Array6 multiply)

```yaml
id: "op-004-01"
srd: "srd-004"
title: "Multiply liability bundle premiums by 1.03"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "GetLiabilityBundlePremiums"
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "base_rate_increase"
parameters:
  factor: 1.03               # Multiplicative factor to apply
  scope: "all_territories"   # "all_territories" | "specific" (with territory list)
  rounding: "auto"           # Original -- resolved by Analyzer below
# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
function_line_start: 4012
function_line_end: 4104
rounding_resolved: "mixed"   # "banker" | "none" | "mixed"
rounding_detail: |
  Lines with integer Array6 values: banker rounding
  Lines with decimal Array6 values: no rounding
target_lines:
  - line: 4058
    content: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
    context: "Farm > PRIMARYITEM > Enhanced Comp"
    rounding: "banker"       # Per-line rounding decision
    value_count: 6
  - line: 4062
    content: "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
    context: "Farm > PRIMARYITEM > ELITECOMP"
    rounding: "none"         # Has decimals -- don't round
    value_count: 6
skipped_lines:
  - line: 4043
    content: "            liabilityPremiumArray = Array6(0, 0, 0, 0, 0, 0)"
    reason: "Default initialization (all zeros)"
  - line: 4091
    content: "            If IsItemInArray(coverageItem.Code, Array6(COVITEM_PRIMARY...))"
    reason: "Array6 inside IsItemInArray() -- membership test, not a rate"
has_expressions: false
```

**Field semantics for base_rate_increase:**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.factor` | float | Multiplicative factor (e.g., 1.03 = 3% increase) |
| `parameters.scope` | string | `"all_territories"` or `"specific"` |
| `parameters.rounding` | string | Original from Decomposer -- IGNORE, use resolved |
| `rounding_resolved` | string | Analyzer's decision: `"banker"`, `"none"`, or `"mixed"` |
| `target_lines[].rounding` | string | Per-line: `"banker"`, `"none"`, or `null` |
| `target_lines[].content` | string | **Authoritative match key** -- exact line content |
| `target_lines[].line` | int | Line number HINT (may drift) |
| `target_lines[].context` | string | Human-readable location description |
| `target_lines[].value_count` | int | Number of numeric args in the Array6 call |
| `skipped_lines[]` | list | Lines the Analyzer intentionally excluded (for audit) |
| `has_expressions` | bool | True if ANY target line has arithmetic expressions |
| `function_line_start` | int | First line of function (hint for search window) |
| `function_line_end` | int | Last line of function (hint for search window) |

#### Type 2: factor_table_change

```yaml
id: "op-002-01"
srd: "srd-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
function: "SetDisSur_Deductible"
agent: "rate-modifier"
pattern: "factor_table_change"
parameters:
  case_value: 5000           # Select Case value to find
  old_value: -0.20           # Current value (for verification)
  new_value: -0.22           # Replacement value
# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
function_line_start: 2108
function_line_end: 2227
target_lines:
  - line: 2202
    content: "                    dblDedDiscount = -0.2"
    context: "Case 5000 > If blnFarmLocation Then (farm path)"
    rounding: null           # Factor -- NEVER round
  - line: 2205
    content: "                    dblDedDiscount = -0.25"
    context: "Case 5000 > Else (non-farm path)"
    rounding: null
candidates_shown: 2
developer_confirmed: true    # Developer chose which code paths to modify
analysis_notes: |
  Case 5000 has two code paths. Developer chose farm path only (line 2202).
```

**Field semantics for factor_table_change:**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.case_value` | int/string | The Select Case value to locate |
| `parameters.old_value` | float | Expected current value (verification) |
| `parameters.new_value` | float | New value to write |
| `target_lines[]` | list | Lines the developer chose to modify |
| `candidates_shown` | int | Total matching lines shown to developer |
| `developer_confirmed` | bool | Developer explicitly approved these targets |
| `analysis_notes` | string | Context from the Analyzer's findings |

**IMPORTANT:** When `candidates_shown > len(target_lines)`, it means the developer
saw multiple matching values and chose a SUBSET. Only modify the lines listed in
`target_lines`. The other candidates were intentionally excluded.

#### Type 3: included_limits

```yaml
id: "op-006-01"
srd: "srd-006"
title: "Increase Medical Payments limit from 5000 to 10000"
file: "Saskatchewan/Code/Option_MedicalPayments_SKHome20260101.vb"
function: "GetMedicalPaymentsPremium"
agent: "rate-modifier"
pattern: "included_limits"
parameters:
  limit_name: "Medical Payments"   # Human label
  old_limit: 5000.0                # Current limit value
  new_limit: 10000.0               # New limit value
# -- Added by Analyzer --
source_file: "Saskatchewan/Code/Option_MedicalPayments_SKHome20250901.vb"
target_file: "Saskatchewan/Code/Option_MedicalPayments_SKHome20260101.vb"
needs_copy: true
file_hash: "sha256:abc123..."
function_line_start: 30
function_line_end: 78
target_lines:
  - line: 45
    content: "            If intLimit = 5000 Then"
    context: "Main limit check"
    rounding: null           # Limit -- NEVER round
```

**Field semantics for included_limits:**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.limit_name` | string | Human-readable label for logging |
| `parameters.old_limit` | float | Expected current limit value |
| `parameters.new_limit` | float | New limit value |
| `target_lines[].content` | string | Exact line content to match |

---

## Module Routing Table

**Note:** `format_vb_number()`, `format_vb_decimal()`, and `detect_decimal_places()`
are defined in **core.md** (Shared Helper Functions section) and available to ALL
modules below. No module needs to load another module for these helpers.

| Operation Pattern | Module to Load | Sub-Conditions |
|---|---|---|
| base_rate_increase | modules/array6-multiply.md | Default |
| base_rate_increase + rounding_resolved="mixed" | modules/array6-multiply.md + modules/mixed-rounding.md | Per-line rounding |
| base_rate_increase + has_expressions=true | modules/array6-multiply.md + modules/expressions.md | Arithmetic expressions |
| factor_table_change | modules/factor-table.md | Includes Const declarations |
| included_limits | modules/factor-table.md | Same logic as factor_table_change |

## When to Load Edge Cases

Load `edge-cases.md` ONLY when:
- An error condition fires (TOCTOU, Content Mismatch, etc.)
- The capsule flags `load_edge_cases: true`
- A sentinel value (-999) or all-zero Array6 is detected
- A rework instruction is received from the execution-reviewer
