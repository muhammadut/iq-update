# Module: Mixed Rounding

Specialization of Array6 Multiply for operations where `rounding_resolved = 'mixed'`.
Load this IN ADDITION to `array6-multiply.md`.

**Prerequisites:** The worker MUST have already loaded `core.md`, `dispatch.md`,
and `modules/array6-multiply.md`.

---

## Rounding Field Contract (3-Level Resolution Chain)

The rounding chain flows through three levels of specificity:

```
parameters.rounding       (original from Decomposer -- "auto", IGNORE)
    |
    v
rounding_resolved         (Analyzer's decision: "banker" | "none" | "mixed")
    |
    v
target_lines[].rounding   (per-line: "banker" | "none" | null)
```

**Resolution rules:**

| `rounding_resolved` | `target_lines[].rounding` | Action |
|---------------------|---------------------------|--------|
| `"banker"` | `"banker"` on all lines | Apply banker's rounding to all values |
| `"none"` | `"none"` on all lines | Preserve exact decimal results |
| `"mixed"` | Mix of `"banker"` and `"none"` | Use per-line `rounding` field |
| (any) | `null` | Value is explicit (factor, limit) -- no rounding |

**ALWAYS use `target_lines[].rounding` as the authoritative per-line decision.**
The `rounding_resolved` field is for operation-level context only.

---

## Per-Line Rounding in compute_new_array6_values

When `rounding_resolved = "mixed"`, the `compute_new_array6_values` function
(defined in `modules/array6-multiply.md`) is called once per target line, with
the per-line `rounding_mode` extracted from `target_lines[].rounding`:

```python
for tl, line_idx in located_targets:
    rounding_mode = tl.get("rounding")  # "banker", "none", or null
    parsed_args = parse_array6_args(lines[line_idx])
    new_values = compute_new_array6_values(parsed_args, factor, rounding_mode)
    # ... apply via apply_array6_change (see array6-multiply.md Step 8)
```

The `rounding_mode` parameter in `compute_new_array6_values` controls behavior:
- `"banker"` -- applies `bankers_round()` to each value, outputs integers
- `"none"` -- preserves decimals via `format_vb_decimal()`
- `null` -- preserves original format (integer->integer, decimal->decimal)

---

## Worked Example: Mixed Rounding Function (Integer + Decimal Array6)

**Operation YAML (abbreviated):**

```yaml
id: "op-004-01"
pattern: "base_rate_increase"
function: "GetLiabilityBundlePremiums"
parameters:
  factor: 1.03
rounding_resolved: "mixed"
target_lines:
  - line: 4058
    content: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
    context: "Farm > PRIMARYITEM > Enhanced Comp"
    rounding: "banker"
    value_count: 6
  - line: 4062
    content: "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
    context: "Farm > PRIMARYITEM > ELITECOMP"
    rounding: "none"
    value_count: 6
```

**Step 7a -- Compute for line 4058 (rounding: "banker"):**

```
Input:  [0, 78, 161, 189, 213, 291]
Factor: 1.03

0   * 1.03 = 0      -> 0     (zero stays zero)
78  * 1.03 = 80.34   -> 80
161 * 1.03 = 165.83  -> 166
189 * 1.03 = 194.67  -> 195
213 * 1.03 = 219.39  -> 219
291 * 1.03 = 299.73  -> 300

Output: [0, 80, 166, 195, 219, 300]
```

**Step 7a -- Compute for line 4062 (rounding: "none"):**

```
Input:  [0, 0, 0, 0, 324.29, 462.32]
Factor: 1.03

0      * 1.03 = 0        -> 0
0      * 1.03 = 0        -> 0
0      * 1.03 = 0        -> 0
0      * 1.03 = 0        -> 0
324.29 * 1.03 = 334.0187 -> 334.02  (2 decimal places, no banker's rounding)
462.32 * 1.03 = 476.1896 -> 476.19

Output: [0, 0, 0, 0, 334.02, 476.19]
```

**Step 8 -- Apply:**

```
Before: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
After:  "                        liabilityPremiumArray = Array6(0, 80, 166, 195, 219, 300)"

Before: "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
After:  "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 334.02, 476.19)"
```

**Key insight:** The `rounding` field is resolved PER LINE, not per function. In
this function, line 4058 uses banker's rounding (all integer values), while line
4062 uses no rounding (decimal values). The `rounding_resolved: "mixed"` at the
operation level is informational only -- always use `target_lines[].rounding`.

After applying changes, proceed to core.md Step 9 (write-back) and Step 10
(verification).
