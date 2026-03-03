# Module: Arithmetic Expressions

Handles Array6 lines containing arithmetic expressions (e.g., `30 + 10`). Load
this IN ADDITION to `modules/array6-multiply.md` when `has_expressions: true`.

**Prerequisites:** The worker MUST have already loaded `core.md`, `dispatch.md`,
and `modules/array6-multiply.md`.

---

## Arithmetic Expression Contract

When `has_expressions: true`, some `target_lines` entries will have:

```yaml
target_lines:
  - line: 1200
    content: "        liabilityPremiumArray = Array6(30 + 10, 36 + 13, 40 + 14, 36, 72)"
    context: "Territory 5 liability"
    rounding: "banker"
    value_count: 5
    has_expressions: true
    evaluated_args: [40, 49, 54, 36, 72]    # Pre-evaluated by Analyzer
```

| Field | Type | Description |
|-------|------|-------------|
| `has_expressions` | bool | True if this specific line has arithmetic |
| `evaluated_args` | list[float] | Pre-evaluated values for each argument |

**Rule:** When `evaluated_args` is present, multiply THOSE values by the factor
(not the raw expressions). Replace the ENTIRE expression with the computed result.
Example: `30 + 10` with factor 1.05 becomes `42` (40 * 1.05 = 42), NOT
`31.5 + 10.5`.

---

## Step 11: Handle Arithmetic Expressions

When a target line has `has_expressions: true`, the Array6 arguments contain VB.NET
arithmetic (e.g., `30 + 10`). Special handling is required.

**Rule:** When `evaluated_args` is provided by the Analyzer, use those pre-evaluated
values as the basis for multiplication. Replace each expression with its final
computed result (a single number).

```python
def handle_expression_line(line, tl, factor, rounding_mode):
    """Process an Array6 line that contains arithmetic expressions.

    Input line:
      "        liabilityPremiumArray = Array6(30 + 10, 36 + 13, 40 + 14, 36, 72)"

    With evaluated_args = [40, 49, 54, 36, 72] and factor = 1.05:
      "        liabilityPremiumArray = Array6(42, 51, 57, 38, 76)"

    The expressions are REPLACED with their evaluated-and-multiplied results.
    """
    evaluated = tl.get("evaluated_args")
    if not evaluated:
        return FAIL(
            f"Line has expressions but no evaluated_args: {line.strip()}"
        )

    # Compute new values from evaluated args
    # evaluated_args may contain None or string for variable names (e.g., basePremium)
    new_values = []
    for val in evaluated:
        # Skip non-numeric entries (variables like basePremium -> None or string)
        if val is None or isinstance(val, str):
            new_values.append(str(val) if val else "0")
            continue
        if val == 0:
            new_values.append("0")
            continue
        new_val = val * factor
        if rounding_mode == "banker":
            new_val = bankers_round(new_val)
            new_values.append(str(int(new_val)))
        elif rounding_mode == "none":
            new_values.append(format_vb_decimal(new_val))
        else:
            new_val = bankers_round(new_val)
            new_values.append(str(int(new_val)))

    # Replace the entire Array6(...) arg list
    import re
    match = re.search(r'(Array6\s*\()(.+?)(\))', line)
    if not match:
        return FAIL("Array6 not found on expression line")

    prefix = line[:match.start()]
    array6_open = match.group(1)
    close_paren = match.group(3)
    suffix = line[match.end():]

    new_line = prefix + array6_open + ", ".join(new_values) + close_paren + suffix
    return new_line
```

The `bankers_round` and `format_vb_decimal` functions are defined in
`modules/array6-multiply.md`.

---

## Why Replace Expressions with Plain Numbers?

The old code `30 + 10` was likely a historical artifact (e.g., base + adjustment).
After a rate update, the new rate IS the single number. Preserving the expression
form (`31.5 + 10.5`) would be misleading and harder to maintain.

---

## Worked Example: Arithmetic Expressions in Array6

**Operation YAML (abbreviated):**

```yaml
id: "op-005-01"
pattern: "base_rate_increase"
function: "GetLiabilityBundlePremiums"
parameters:
  factor: 1.05
rounding_resolved: "banker"
has_expressions: true
target_lines:
  - line: 1200
    content: "        liabilityPremiumArray = Array6(30 + 10, 36 + 13, 40 + 14, 36, 72)"
    context: "Territory 5 liability"
    rounding: "banker"
    value_count: 5
    has_expressions: true
    evaluated_args: [40, 49, 54, 36, 72]
```

**Step 11 -- Handle expression line:**

Use `evaluated_args` as the basis for multiplication:

```
evaluated_args: [40, 49, 54, 36, 72]
Factor: 1.05

40 * 1.05 = 42.00 -> 42
49 * 1.05 = 51.45 -> 51  (banker's: .45 rounds down since 51 is odd -> wait)
```

Let me recompute: `round(51.45)` in Python:
- 51.45 is NOT a .5 case (it's .45, which is < .5) -> rounds DOWN to 51. Correct.

```
49 * 1.05 = 51.45 -> 51
54 * 1.05 = 56.70 -> 57
36 * 1.05 = 37.80 -> 38
72 * 1.05 = 75.60 -> 76

Output: [42, 51, 57, 38, 76]
```

**Step 8 -- Apply:**

```
Before: "        liabilityPremiumArray = Array6(30 + 10, 36 + 13, 40 + 14, 36, 72)"
After:  "        liabilityPremiumArray = Array6(42, 51, 57, 38, 76)"
```

Note: The expressions `30 + 10`, `36 + 13`, `40 + 14` are REPLACED with their
evaluated-and-multiplied results. The plain numbers `36` and `72` are also
multiplied. The result is a clean Array6 with no arithmetic.

After applying changes, proceed to core.md Step 9 (write-back) and Step 10
(verification).
