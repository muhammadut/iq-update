# Module: Factor Table & Const Changes

Handles `factor_table_change` and `included_limits` patterns.

**Prerequisites:** The worker MUST have already loaded `core.md` and `dispatch.md`.

---

## Step 6: Validate Current Values (factor_table_change / included_limits)

Before modifying anything, verify that the current line content matches what the
operation YAML expects. See core.md Step 6 for the shared `value_appears_on_line`
helper.

```python
def validate_current_values(lines, located_targets, op):
    """Verify current values match the operation's expectations.

    For factor_table_change: check that old_value appears on the line.
    For included_limits: check that old_limit appears on the line.
    """
    pattern = op["pattern"]

    for tl, line_idx in located_targets:
        current_line = lines[line_idx]

        # Skip commented lines -- safety check (Analyzer should have excluded)
        if current_line.strip().startswith("'"):
            return FAIL(
                f"Line {line_idx + 1} is commented out. "
                "Analyzer should have excluded this. Aborting."
            )

        if pattern == "factor_table_change":
            old_val = op["parameters"]["old_value"]
            # Verify old_value appears on the line
            if not value_appears_on_line(current_line, old_val):
                return FAIL(
                    f"Expected old_value {old_val} not found on line {line_idx + 1}: "
                    f"{current_line.strip()}"
                )

        elif pattern == "included_limits":
            old_limit = op["parameters"]["old_limit"]
            if not value_appears_on_line(current_line, old_limit):
                return FAIL(
                    f"Expected old_limit {old_limit} not found on line {line_idx + 1}: "
                    f"{current_line.strip()}"
                )

    return OK
```

---

## Step 7b: factor_table_change -- Simple Value Substitution

For `factor_table_change` operations, replace the old value with the new value
on the target line(s).

```python
def compute_factor_change(line, old_value, new_value):
    """Replace old_value with new_value on a factor table line.

    Args:
        line: the full source line (with indentation)
        old_value: the value to find (float)
        new_value: the replacement value (float)

    Returns: new line string, or FAIL if old_value not found.
    """
    old_str = format_vb_number(old_value)
    new_str = format_vb_number(new_value)

    # Find and replace the FIRST occurrence of old_value on this line
    # Use word-boundary-aware replacement to avoid partial matches
    # e.g., don't replace "0.2" inside "0.25"
    import re

    # Build a pattern that matches the value as a standalone token
    # Allow for VB.NET formatting variations: -0.20 vs -0.2
    patterns_to_try = [old_str]
    # Also try with trailing zero: -0.2 -> -0.20
    if "." in old_str:
        patterns_to_try.append(old_str + "0")
    # Try without trailing zero: -0.20 -> -0.2
    if old_str.endswith("0") and "." in old_str:
        patterns_to_try.append(old_str.rstrip("0"))

    for try_str in patterns_to_try:
        escaped = re.escape(try_str)
        # Lookbehind/ahead to avoid matching inside larger numbers
        # Include '-' in lookbehind to prevent matching "0.2" inside "-0.2"
        pattern = r'(?<![.\d\-])' + escaped + r'(?![.\d])'
        if re.search(pattern, line):
            new_line = re.sub(pattern, new_str, line, count=1)
            return new_line

    return FAIL(f"old_value '{old_str}' not found on line: {line.strip()}")
```

**NEVER round factor values.** Factor values like `-0.22` are exact. The
`rounding` field for factor_table_change target lines is always `null`.

The `format_vb_number` function is defined in `core.md` (Shared Helper Functions
section), available to all modules.

---

## Step 7c: included_limits -- Simple Limit Substitution

For `included_limits` operations, replace the old limit with the new limit.

```python
def compute_limit_change(line, old_limit, new_limit):
    """Replace old_limit with new_limit on a limit check line.

    Args:
        line: the full source line
        old_limit: current limit value (float)
        new_limit: new limit value (float)

    Returns: new line string.
    """
    old_str = format_vb_number(old_limit)
    new_str = format_vb_number(new_limit)

    import re
    escaped = re.escape(old_str)
    pattern = r'(?<![.\d])' + escaped + r'(?![.\d])'

    if re.search(pattern, line):
        new_line = re.sub(pattern, new_str, line, count=1)
        return new_line

    return FAIL(f"old_limit '{old_str}' not found on line: {line.strip()}")
```

**NEVER round limit values.** Limits are exact integers or decimals as specified
by the SRD.

---

## Step 8: Apply Change (factor_table_change / included_limits)

The `compute_factor_change()` and `compute_limit_change()` functions from Step 7b/7c
already produce the complete new line with formatting preserved, because they use
regex substitution on the original line (replacing only the numeric value).

After applying changes, proceed to core.md Step 9 (write-back) and Step 10
(verification).

---

## Case 7: Const Declaration as Rate Value

**Context:** Some rates are defined as constants:

```vb
Const ACCIDENTBASE = 200
```

**Rule:** When the operation targets a `Const` declaration, the Analyzer's
`target_lines[].content` will include the `Const` keyword. The Rate Modifier
replaces the value after the `=` sign using the same factor_table_change logic:

```
parameters:
  old_value: 200
  new_value: 210
```

**Step 7b applies:** Find `200` on the line, replace with `210`.

```
Before: "        Const ACCIDENTBASE = 200"
After:  "        Const ACCIDENTBASE = 210"
```

**Note:** The `Const` keyword and variable name are preserved. Only the numeric
value changes. Factor values in Const declarations are treated exactly like inline
values in Select Case blocks.
