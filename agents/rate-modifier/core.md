# Rate Modifier Agent — Core Contract

This file defines the universal rules for all rate modification operations.
Workers always load this file.

---

## Purpose

Make rate value changes -- Array6() values, Select Case factor tables, premium
arrays, included limit thresholds. This agent handles **purely mechanical value
substitutions** in existing VB.NET code. It NEVER creates new functions, adds
conditional logic, or restructures code -- those are the Logic Modifier's domain.

The Rate Modifier is the **HANDS** of the pipeline. Every instruction must be
unambiguous enough that a fresh Claude Code instance can follow them without
guessing. Precision is everything: one wrong digit in a rate table means incorrect
premiums for every policy in that territory.

**Dispatch model:** The `/iq-execute` orchestrator launches a modifier-agent that
reads `plan/execution_order.yaml` and processes operations in sequence. For each
operation tagged `agent: "rate-modifier"`, the modifier-agent loads THIS file and
follows these instructions. The modifier-agent handles snapshots, TOCTOU checks,
hash updates, and operation logging. This file focuses on **locating targets** and
**computing + applying changes**.

**File copies are NOT this agent's responsibility.** The file-copier-agent runs
BEFORE the modifier-agent and handles all file copies and .vbproj reference
updates. By the time the Rate Modifier starts, every target file MUST already
exist on disk. If a target file is missing, ABORT the operation.

## Pipeline Position

```
/iq-plan:    Intake -> Decomposer -> Analyzer -> Planner -> [GATE 1]
/iq-execute: File Copier -> MODIFIER -> Execution Reviewer -> [EXECUTED]
                            ^^^^^^^^
/iq-review:  Validator -> Diff -> Report -> [GATE 2] -> DONE
```

- **Upstream:** File-copier-agent (creates target files, updates .vbproj references,
  updates `execution/file_hashes.yaml`); Planner agent (provides
  `plan/execution_order.yaml` with approved operations and execution sequence)
- **Downstream:** Execution Reviewer (validates changes inline); Reviewer agent in
  /iq-review (consumes modified source files + `execution/operations_log.yaml`)
- **Parallel:** Logic Modifier (may run in parallel ONLY on **different files**;
  same-file operations are always sequential, bottom-to-top by line number)
- **Dispatch:** The modifier-agent reads `agent: "rate-modifier"` from each
  operation YAML and loads this file for execution instructions

---

## Input Schema

The Rate Modifier reads these files from the workstream directory
(`.iq-workstreams/changes/{workstream-name}/`):

### plan/execution_order.yaml (from Planner)

The execution plan provides the global operation sequence. The Rate Modifier
processes operations in the **exact order** listed in `execution_sequence[]`.

```yaml
planner_version: "1.0"
generated_at: "2026-02-27T11:00:00"
workflow_id: "20260101-SK-Hab-rate-update"
total_phases: 5
total_operations: 6
risk_level: "MEDIUM"

# File copies are handled by file-copier-agent (NOT this agent)
file_copies:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "sha256:a1b2c3d4..."
    vbproj_updates:
      - vbproj: "Saskatchewan/Home/20260101/..."
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"

# Per-file operation ordering (bottom-to-top by line reference)
file_operation_order:
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    - op_id: "op-004-02"
      line_ref: 4106      # highest line first
    - op_id: "op-004-01"
      line_ref: 4012
    - op_id: "op-002-01"
      line_ref: 2108

# Global execution sequence (the modifier-agent iterates this)
execution_sequence:
  - op_id: "op-004-02"
    phase: 4
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "rate-modifier"
  - op_id: "op-004-01"
    phase: 3
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "rate-modifier"
  - op_id: "op-002-01"
    phase: 2
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "rate-modifier"
```

**Key fields consumed by Rate Modifier:**

| Field | Purpose |
|-------|---------|
| `execution_sequence[].op_id` | Which operation YAML to read |
| `execution_sequence[].file` | Target file path (relative to carrier root) |
| `execution_sequence[].agent` | Must be `"rate-modifier"` for this agent |
| `file_operation_order` | Bottom-to-top order within each file |

Per-pattern YAML examples and field semantics are in `dispatch.md`.

### execution/file_hashes.yaml (from Planner, updated by file-copier)

```yaml
files:
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    hash: "sha256:abc123..."    # Updated by file-copier after copy
    size: 45230
    role: "target"              # "target" = file to be modified
```

**NOTE:** The modifier-agent reads and updates this file (not the Rate Modifier
directly). The hash is checked BEFORE each operation and updated AFTER. The Rate
Modifier receives the "go ahead" from the modifier-agent after TOCTOU passes.

### Rounding Field Contract

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

### Arithmetic Expression Contract

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

## Output Schema

### execution/operations_log.yaml

The modifier-agent appends one entry per completed operation. The Rate Modifier
provides the data; the modifier-agent writes the YAML.

```yaml
operations:
  - operation: "op-004-01"
    agent: "rate-modifier"
    status: "COMPLETED"              # COMPLETED | FAILED | SKIPPED
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    function: "GetLiabilityBundlePremiums"
    changes:
      - line: 4058
        description: "Farm > PRIMARYITEM > Enhanced Comp"
        before: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
        after:  "                        liabilityPremiumArray = Array6(0, 80, 166, 195, 219, 300)"
        values_changed: 5            # 0 unchanged (sentinel), 5 multiplied
      - line: 4062
        description: "Farm > PRIMARYITEM > ELITECOMP"
        before: "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
        after:  "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 334.02, 476.19)"
        values_changed: 2            # 4 zeros unchanged, 2 multiplied
    summary:
      lines_changed: 2
      values_changed: 7
      change_range: "2.6% to 3.2%"  # Min/max percentage change across all values
      started_at: "2026-01-15T11:05:00Z"
      completed_at: "2026-01-15T11:05:03Z"

  - operation: "op-002-01"
    agent: "rate-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    function: "SetDisSur_Deductible"
    changes:
      - line: 2202
        description: "Case 5000 > If blnFarmLocation Then (farm path)"
        before: "                    dblDedDiscount = -0.2"
        after:  "                    dblDedDiscount = -0.22"
        values_changed: 1
    summary:
      lines_changed: 1
      values_changed: 1
      change_range: "10.0%"          # -0.2 to -0.22 = 10% absolute change
      started_at: "2026-01-15T11:05:04Z"
      completed_at: "2026-01-15T11:05:04Z"

  - operation: "op-006-01"
    agent: "rate-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Code/Option_MedicalPayments_SKHome20260101.vb"
    function: "GetMedicalPaymentsPremium"
    changes:
      - line: 45
        description: "Main limit check"
        before: "            If intLimit = 5000 Then"
        after:  "            If intLimit = 10000 Then"
        values_changed: 1
    summary:
      lines_changed: 1
      values_changed: 1
      change_range: "100.0%"
      started_at: "2026-01-15T11:05:05Z"
      completed_at: "2026-01-15T11:05:05Z"
```

**Field reference for operations_log.yaml:**

| Field | Type | Description |
|-------|------|-------------|
| `operation` | string | Operation ID (matches op YAML filename) |
| `agent` | string | Always `"rate-modifier"` for this agent |
| `status` | string | `COMPLETED`, `FAILED`, or `SKIPPED` |
| `file` | string | Target file path (relative to carrier root) |
| `function` | string | Function name where change was made |
| `changes[]` | list | One entry per line modified |
| `changes[].line` | int | Actual line number where change was applied |
| `changes[].description` | string | From `target_lines[].context` |
| `changes[].before` | string | Exact line content before change (full line) |
| `changes[].after` | string | Exact line content after change (full line) |
| `changes[].values_changed` | int | Count of numeric values that changed |
| `summary.lines_changed` | int | Total lines modified in this operation |
| `summary.values_changed` | int | Total individual values modified |
| `summary.change_range` | string | Min/max percentage change (human-readable) |
| `summary.started_at` | string | ISO 8601 timestamp |
| `summary.completed_at` | string | ISO 8601 timestamp |

**Status values:**

- `COMPLETED` -- All target lines modified successfully, verification passed
- `FAILED` -- One or more lines could not be modified (content mismatch, TOCTOU, etc.)
- `SKIPPED` -- Value already matches target (no change needed) -- see Special Case 8.6

### What the Reviewer Validates Downstream

The /iq-review Reviewer reads operations_log.yaml and the modified source files.
These are the specific validators that check Rate Modifier output:

| Validator | What It Checks |
|-----------|---------------|
| `validate_array6` | Matching parens, arg count UNCHANGED from before, no empty args, values within reasonable range |
| `validate_completeness` | All territories updated, all LOBs handled, no target_lines skipped |
| `validate_no_old_modify` | Only target-date files were edited (never old Code/ files) |
| `validate_no_commented_code` | No commented lines were changed |
| `validate_value_sanity` | Rate changes within expected range (flags >50% change as suspicious) |

---

## EXECUTION STEPS

These steps define how the Rate Modifier processes a SINGLE operation. The
modifier-agent calls these steps for each operation in `execution_sequence` order.

Steps 1-4 handle setup and validation. Steps 5-6 locate the target. Steps 7-9
compute and apply the change. Step 10 verifies the result. Steps 11-12 handle
arithmetic expressions and edge cases.

### Step 1: Read and Validate Operation YAML

Read the operation file `analysis/operations/{op_id}.yaml` and validate that all
required fields are present and well-formed.

```
REQUIRED FIELDS (all operation types):
  - id              (string, matches filename)
  - file            (string, relative path)
  - function        (string, function name)
  - agent           (string, must be "rate-modifier")
  - pattern         (string, one of: base_rate_increase, factor_table_change, included_limits)
  - parameters      (object, pattern-specific)
  - target_file     (string, relative path -- from Analyzer)
  - file_hash       (string, sha256 -- from Analyzer)
  - function_line_start (int, >= 1)
  - function_line_end   (int, > function_line_start)
  - target_lines    (list, length >= 1)

REQUIRED PER target_lines[] ENTRY:
  - content         (string, non-empty)
  - line            (int, >= 1)
  - rounding        (string or null)

PATTERN-SPECIFIC REQUIRED FIELDS:

  base_rate_increase:
    - parameters.factor          (float, > 0)
    - parameters.scope           (string)
    - rounding_resolved          (string: "banker" | "none" | "mixed")

  factor_table_change:
    - parameters.case_value      (int or string)
    - parameters.old_value       (float)
    - parameters.new_value       (float)

  included_limits:
    - parameters.old_limit       (float)
    - parameters.new_limit       (float)
```

**Validation pseudocode:**

```python
def validate_operation(op):
    """Validate operation YAML before processing."""
    required = ["id", "file", "function", "agent", "pattern",
                "parameters", "target_file", "file_hash",
                "function_line_start", "function_line_end", "target_lines"]
    for field in required:
        if field not in op:
            return FAIL(f"Missing required field: {field}")

    if op["agent"] != "rate-modifier":
        return FAIL(f"Wrong agent: {op['agent']} (expected rate-modifier)")

    if op["pattern"] not in ("base_rate_increase", "factor_table_change", "included_limits"):
        return FAIL(f"Unknown pattern: {op['pattern']}")

    if op["function_line_end"] <= op["function_line_start"]:
        return FAIL("function_line_end must be > function_line_start")

    if len(op["target_lines"]) == 0:
        return FAIL("target_lines is empty -- nothing to modify")

    for tl in op["target_lines"]:
        if "content" not in tl or not tl["content"].strip():
            return FAIL(f"target_lines entry missing content at line {tl.get('line', '?')}")

    # Pattern-specific checks
    if op["pattern"] == "base_rate_increase":
        if "factor" not in op["parameters"]:
            return FAIL("base_rate_increase requires parameters.factor")
        if op["parameters"]["factor"] <= 0:
            return FAIL(f"factor must be > 0, got {op['parameters']['factor']}")
        if "rounding_resolved" not in op:
            return FAIL("base_rate_increase requires rounding_resolved")

    elif op["pattern"] == "factor_table_change":
        for f in ("case_value", "old_value", "new_value"):
            if f not in op["parameters"]:
                return FAIL(f"factor_table_change requires parameters.{f}")

    elif op["pattern"] == "included_limits":
        for f in ("old_limit", "new_limit"):
            if f not in op["parameters"]:
                return FAIL(f"included_limits requires parameters.{f}")

    return OK
```

**On validation failure:** Report `FAILED` status with the validation error in the
operations log. Do NOT proceed to subsequent steps.

### Step 2: Verify Target File Exists

The file-copier-agent should have already created the target file. Verify it exists.

```
TARGET_PATH = {carrier_root} / {op.target_file}

IF TARGET_PATH does not exist on disk:
    ABORT operation
    status = "FAILED"
    error = "Target file does not exist: {op.target_file}. "
            "The file-copier-agent should have created it. "
            "Check execution/file_copies_log.yaml for errors."
    RETURN
```

**Why this matters:** The old skeleton said "CREATE NEW DATED COPY (if needed)."
That responsibility has moved to the file-copier-agent. The Rate Modifier must
NEVER copy files or update .vbproj references. If the target file is missing,
it means the file-copier failed or the execution plan is inconsistent.

### Step 3: Read Target File Content

Read the entire target file into memory as a list of lines. Preserve the original
line endings (CRLF or LF) for later restoration.

```python
def read_target_file(target_path):
    """Read file, detect line endings, return lines list."""
    with open(target_path, "rb") as f:
        raw = f.read()

    # Detect line ending style
    if b"\r\n" in raw:
        line_ending = "\r\n"    # Windows CRLF (typical for VB.NET)
    else:
        line_ending = "\n"      # Unix LF

    text = raw.decode("utf-8")
    lines = text.split(line_ending)

    return lines, line_ending
```

**Store the line ending style** -- it must be used when writing the file back.
VB.NET source files in this codebase typically use CRLF. Changing line endings
would create massive diffs in SVN and confuse future comparisons.

### Step 4: Locate Function by Name

Find the target function within the file. Use `function_line_start` as a hint
for efficient searching, but verify by signature match.

```python
def locate_function(lines, function_name, hint_start, hint_end):
    """Find function boundaries by name. Line numbers are 1-indexed hints.

    Returns (actual_start, actual_end) as 0-indexed line indices,
    or FAIL if function not found.
    """
    # VB.NET function signatures we need to match:
    #   Public Function GetBasePremium_Home(...)
    #   Private Function SetDisSur_Deductible(...)
    #   Public Sub GetLiabilityBundlePremiums(...)
    #   Friend Function GetMedicalPaymentsPremium(...)
    # Also: Protected, Shared, Overrides, Overloads combinations

    import re
    # Pattern: optional access modifier(s) + Function/Sub + exact name + open paren
    # Modifiers are optional — plain "Function GetX()" is legal VB.NET (defaults to Public)
    sig_pattern = re.compile(
        r'^\s*'                                         # Leading indentation
        r'(?:(?:Public|Private|Protected|Friend|Shared|Overrides|Overloads)\s+)*'  # Zero or more modifiers
        r'(?:Function|Sub)\s+'                          # Function or Sub keyword
        + re.escape(function_name)
        + r'\s*\(',                                     # Opening paren (with optional space)
        re.IGNORECASE
    )

    # Strategy 1: Search near the hint first (within +/- 50 lines)
    hint_idx = max(0, hint_start - 1 - 50)      # Convert 1-indexed to 0-indexed, expand window
    hint_end_idx = min(len(lines), hint_end + 50)

    for i in range(hint_idx, hint_end_idx):
        if sig_pattern.search(lines[i]):
            actual_start = i
            actual_end = find_function_end(lines, i)
            return (actual_start, actual_end)

    # Strategy 2: Full file scan (hint was wrong / lines drifted)
    for i in range(len(lines)):
        if sig_pattern.search(lines[i]):
            actual_start = i
            actual_end = find_function_end(lines, i)
            return (actual_start, actual_end)

    # Not found
    return FAIL(f"Function '{function_name}' not found in file")


def find_function_end(lines, start_idx):
    """Find the End Function / End Sub line starting from the function signature.

    Handles nested Function/Sub blocks by counting depth.
    """
    depth = 1
    end_pattern_func = re.compile(r'^\s*End\s+Function\b', re.IGNORECASE)
    end_pattern_sub  = re.compile(r'^\s*End\s+Sub\b', re.IGNORECASE)
    start_pattern    = re.compile(
        r'\b(Function|Sub)\s+\w+\s*\(', re.IGNORECASE
    )

    # Determine if we're looking for End Function or End Sub
    if re.search(r'\bFunction\b', lines[start_idx], re.IGNORECASE):
        end_pattern = end_pattern_func
        nest_keyword = "Function"
    else:
        end_pattern = end_pattern_sub
        nest_keyword = "Sub"

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        # Skip commented lines for depth tracking
        stripped = line.strip()
        if stripped.startswith("'"):
            continue

        # Check for nested Function/Sub (rare but possible)
        nest_match = re.search(r'\b' + nest_keyword + r'\s+\w+\s*\(', line, re.IGNORECASE)
        if nest_match:
            # Make sure it's not a comment, and not inside a string literal.
            # String check: count double-quote characters BEFORE the match position.
            # If odd, the match is inside a string (e.g., "The Function GetBasePrem()").
            if not stripped.startswith("'"):
                prefix = line[:nest_match.start()]
                quotes_before = prefix.count('"')
                if quotes_before % 2 == 0:  # Even = NOT inside a string
                    depth += 1

        if end_pattern.search(line):
            depth -= 1
            if depth == 0:
                return i

    # Fallback: if End Function/Sub not found, FAIL -- do not guess
    raise ValueError(f"End Function/Sub not found for function starting at line {start_idx + 1}. File may be corrupt or truncated.")
```

**On failure:** If the function is not found, report `FAILED` with the error. Do
NOT attempt to guess or search for similar names -- the Analyzer should have
verified the function exists. A missing function means the file content changed
since analysis.

### Step 5: Locate Target Lines Within Function

For each entry in `target_lines[]`, find the matching line by **content match**
within the function boundaries. Line numbers are hints, content is authoritative.

```python
def locate_target_lines(lines, func_start, func_end, target_lines):
    """Find each target line by content within the function.

    Returns a list of (target_line_spec, actual_line_idx) tuples.
    actual_line_idx is 0-indexed into the lines array.
    """
    results = []

    for tl in target_lines:
        expected_content = tl["content"]
        hint_line = tl["line"]             # 1-indexed
        hint_idx = hint_line - 1           # 0-indexed

        # Strategy 1: Check exact hint location first
        if func_start <= hint_idx <= func_end:
            if lines[hint_idx].rstrip() == expected_content.rstrip():
                results.append((tl, hint_idx))
                continue

        # Strategy 2: Search within function boundaries by content
        found = False
        for i in range(func_start, func_end + 1):
            if lines[i].rstrip() == expected_content.rstrip():
                results.append((tl, i))
                found = True
                break

        if not found:
            # Strategy 3: Fuzzy match -- strip whitespace and compare
            # This handles cases where indentation shifted slightly
            expected_stripped = expected_content.strip()
            for i in range(func_start, func_end + 1):
                if lines[i].strip() == expected_stripped:
                    results.append((tl, i))
                    found = True
                    break

        if not found:
            return FAIL(
                f"Target line not found in function "
                f"(hint line {hint_line}): {expected_content[:80]}..."
            )

    return results
```

**CRITICAL: Content match, not line number.** The Analyzer generates line numbers
from the SOURCE file. After the file-copier creates the target file, line numbers
should be identical (it's a copy), but if any preceding operation in the same file
added or removed lines, numbers will drift. Content match handles this.

**Whitespace handling:** Compare with `.rstrip()` first (trailing whitespace may
differ). If that fails, try `.strip()` (leading whitespace may have shifted). If
BOTH fail, the line content has changed and the operation should ABORT.

### Shared Helper Functions

These functions are used by multiple modules (core, array6-multiply, factor-table).
They are defined here so every worker has them regardless of which operation-specific
module is loaded.

```python
def format_vb_number(value):
    """Format a number as VB.NET would display it.

    VB.NET trims trailing zeros: -0.20 -> -0.2, 5000.0 -> 5000
    """
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        # Remove trailing zeros but keep at least one decimal
        s = f"{value:.10f}".rstrip("0").rstrip(".")
        return s
    return str(int(value))


def format_vb_decimal(value, original_precision=2):
    """Format a decimal value preserving the ORIGINAL source precision.

    Args:
        value: the computed decimal result
        original_precision: number of decimal places in the ORIGINAL value
                           (detected from the source code, default 2)

    Rules:
      - If result is a whole number, show as integer: 324.00 -> 324
      - Otherwise round to the original precision (not hardcoded 2dp)
      - Trim trailing zeros: 334.020 -> 334.02
    """
    if value == int(value):
        return str(int(value))
    # Round to the same precision as the original value
    rounded = round(value, original_precision)
    if rounded == int(rounded):
        return str(int(rounded))
    s = f"{rounded:.{original_precision}f}".rstrip("0")
    return s


def detect_decimal_places(raw_str):
    """Detect how many decimal places a value string has.

    Examples:
        "324.29"  -> 2
        "324.295" -> 3
        "324"     -> 0
        "-0.075"  -> 3
    """
    if "." in raw_str:
        return len(raw_str.rstrip().split(".")[1])
    return 0
```

These helpers are referenced by:
- `value_appears_on_line()` (Step 6 below)
- `modules/array6-multiply.md` (Step 7a multiply logic)
- `modules/factor-table.md` (Step 7b/7c value substitution)

### Step 6: Validate Current Values Match Expected

Before modifying anything, verify that the current line content matches what the
operation YAML expects. This is the TOCTOU check at the line level (complementing
the file-level hash check done by the modifier-agent).

See the pattern-specific module for Step 6 validation details:
- `base_rate_increase` validation: see `modules/array6-multiply.md`
- `factor_table_change` / `included_limits` validation: see `modules/factor-table.md`

The shared `value_appears_on_line` helper is defined here:

```python
def value_appears_on_line(line, value):
    """Check if a numeric value appears on a line of VB.NET code.

    Handles integer/float equivalence: -0.20 matches -0.2, 5000.0 matches 5000.
    """
    import re
    # Normalize: remove trailing zeros after decimal point
    # -0.20 -> -0.2, 5000.0 -> 5000
    str_val = format_vb_number(value)

    # Also try the raw string representation
    raw_str = str(value)

    # Search for either form as a standalone numeric token
    # \b doesn't work well with minus signs, so use lookahead/lookbehind
    for candidate in (str_val, raw_str):
        # Escape for regex, allow optional trailing zeros
        pattern = re.escape(candidate)
        # Include \- in lookbehind to prevent matching 0.2 inside -0.2
        if re.search(r'(?<![.\d\-])' + pattern + r'(?![.\d])', line):
            return True

    return False
```

### Step 7: Compute New Values

This is the core computation step. Different patterns have different computation
logic. See the pattern-specific module for Step 7 details:
- `base_rate_increase`: see `modules/array6-multiply.md` (Step 7a)
- `factor_table_change`: see `modules/factor-table.md` (Step 7b)
- `included_limits`: see `modules/factor-table.md` (Step 7c)

### Step 8: Apply Change (String Replacement Preserving Formatting)

See the pattern-specific module for Step 8 details:
- `base_rate_increase` (Array6): see `modules/array6-multiply.md`
- `factor_table_change` and `included_limits`: see `modules/factor-table.md`

**CRITICAL: Substring replacement, not line replacement.** When modifying a value
on a line, ALWAYS replace only the matched value substring, preserving everything
else on the line — including trailing inline comments and their alignment.

Example: `Private Const ACCIDENTBASE As Double = 0.3     'Base Surcharge`
- CORRECT: Replace `0.3` with `0.35` → `Private Const ACCIDENTBASE As Double = 0.35     'Base Surcharge`
- WRONG: Replace the entire line → comment and alignment are lost

```python
def replace_value_in_line(line, old_value_str, new_value_str):
    """Replace a numeric value in a VB.NET line, preserving everything else.

    This handles:
    - Array6 arguments: replace individual arg within the comma-separated list
    - Const declarations: replace value after `=`, preserve trailing `'comment`
    - Factor assignments: replace value after `=`, preserve trailing content
    """
    # Find the old value's position and replace ONLY that substring
    # Use word-boundary-aware search to avoid partial matches
    import re
    pattern = re.escape(old_value_str)
    match = re.search(r'(?<![.\d\-])' + pattern + r'(?![.\d])', line)
    if match:
        return line[:match.start()] + new_value_str + line[match.end():]
    return None  # Value not found -- caller should handle
```

This preserves:
- Trailing inline comments (`'Base Surcharge`)
- Whitespace alignment between value and comment
- Any other content on the line (VB.NET allows multiple statements separated by `:`)
- Leading indentation

### Step 9: Write Modified Line Back to File

After computing the new line content for ALL target lines in this operation,
apply the changes to the in-memory lines array.

```python
def apply_all_changes(lines, located_targets, new_lines_map, line_ending):
    """Apply all computed changes to the lines array.

    Args:
        lines: list of file lines (mutable)
        located_targets: list of (target_line_spec, actual_line_idx)
        new_lines_map: dict mapping actual_line_idx -> new_line_content
        line_ending: "\r\n" or "\n"

    Apply changes in REVERSE line order (bottom-to-top) within this operation.
    NOTE: For in-place line replacement (lines[idx] = new_line), bottom-to-top
    is not strictly required since indices don't shift. However, we maintain
    this convention as a safety net for future patterns that may INSERT lines
    (which WOULD cause index drift). The modifier-agent also processes
    operations bottom-to-top within a file for the same reason.
    """
    # Sort by line index descending
    sorted_indices = sorted(new_lines_map.keys(), reverse=True)

    changes_log = []
    for idx in sorted_indices:
        old_line = lines[idx]
        new_line = new_lines_map[idx]

        # Apply the change
        lines[idx] = new_line

        # Record for operations_log
        changes_log.append({
            "line": idx + 1,   # Convert to 1-indexed for logging
            "before": old_line.rstrip(),
            "after": new_line.rstrip()
        })

    return changes_log
```

**IMPORTANT: Bottom-to-top within the operation.** Even though the current Rate
Modifier operations do not add or remove lines (only modify existing lines),
applying bottom-to-top is a safety habit that prevents bugs if future operation
types insert lines.

After applying changes, write the file back to disk:

```python
def write_file(lines, target_path, line_ending):
    """Write modified lines back to file, preserving original line endings."""
    content = line_ending.join(lines)
    with open(target_path, "wb") as f:
        f.write(content.encode("utf-8"))
```

### Step 10: Verify Change Was Applied Correctly

After writing the file, re-read the modified lines and verify the changes took
effect. This catches file system errors, encoding issues, or logic bugs.

```python
def verify_changes(target_path, changes_log, line_ending):
    """Re-read the file and verify each changed line matches expected.

    Returns OK or FAIL with details of the first mismatch.
    """
    # Re-read the file
    with open(target_path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    actual_lines = text.split(line_ending)

    for change in changes_log:
        line_num = change["line"]        # 1-indexed
        expected = change["after"]
        actual = actual_lines[line_num - 1].rstrip()

        if actual != expected:
            return FAIL(
                f"Verification failed at line {line_num}:\n"
                f"  Expected: {expected}\n"
                f"  Actual:   {actual}"
            )

    return OK
```

**On verification failure:** This is a serious error. The modifier-agent should:
1. Attempt to restore from snapshot
2. Report `FAILED` status
3. Continue to next operation (if any)

### Step 11: Handle Arithmetic Expressions

When a target line has `has_expressions: true`, special handling is required.
See `modules/expressions.md` for the full protocol.

### Step 12: Handle Edge Cases

See the Special Cases section in `edge-cases.md` for detailed handling.
During execution, check for these conditions at the appropriate step:

| Edge Case | Check At Step | Action |
|-----------|---------------|--------|
| Sentinel value (-999) | Step 6 (validate) | Skip line, log warning |
| All-zero Array6 | Step 7a (compute) | Skip zeros (0 * anything = 0) |
| IsItemInArray(Array6) | Step 5 (locate) | Should be in skipped_lines; if found, ABORT |
| Commented line | Step 6 (validate) | ABORT -- Analyzer should have excluded |
| String Case values | Step 7b (compute) | Match string exactly, including quotes |
| Multiple variables | Step 5 (locate) | Content match handles this |
| Const declaration | Step 7b (compute) | Replace value after `=` sign |
| CRLF vs LF | Step 3 (read) | Detect and preserve |
| Tab vs space indent | Step 8 (apply) | Copy leading whitespace exactly |
| Trailing comment | Step 8 (apply) | Preserve everything after Array6 close paren |
| Short overflow | Step 7 (compute) | See SHORT OVERFLOW CHECK below |

**SHORT OVERFLOW CHECK:** After computing new values, check if any value exceeds
the VB.NET `Short` range (-32768 to 32767). Many rating functions return `Short`
(`As Short`), and assigning a value outside this range causes a runtime
`OverflowException`. If the function's return type is `Short` (check from FUB
`return_type` or Pattern Library) AND any computed value exceeds 32767 or is
below -32768, emit a WARNING in the operation result:

```python
def check_short_overflow(new_values, return_type):
    """Warn if computed values would overflow VB.NET Short."""
    if return_type and return_type.lower() == "short":
        for v in new_values:
            try:
                num = float(v)
                if num > 32767 or num < -32768:
                    return f"WARNING: Value {v} exceeds Short range (-32768..32767)"
            except ValueError:
                continue
    return None
```

---

## Key Responsibilities

1. **Verify target file exists** before any modification (file-copier creates it)
2. **Locate targets by content match** -- line numbers are hints, content is truth
3. **Compute new values correctly** per pattern type and rounding rules
4. **Apply banker's rounding** (round half to even) for integer Array6 values only
5. **Never round factors, limits, or decimal rate values**
6. **Preserve exact VB.NET formatting** -- indentation, spacing, line endings, comments
7. **Skip commented lines** -- never modify code starting with `'`
8. **Handle arithmetic expressions** using pre-evaluated args from Analyzer
9. **Log every change** with before/after for the operations log
10. **Verify changes after writing** by re-reading the modified file
11. **Execute bottom-to-top** within each operation's target lines
12. **Detect already-applied changes** and report as SKIPPED (not FAILED)

**Responsibilities that moved to other agents:**

| Responsibility | Now Handled By |
|---------------|---------------|
| File copying (Code/ files) | file-copier-agent |
| .vbproj `<Compile Include>` updates | file-copier-agent |
| Snapshot creation | modifier-agent (wrapper) |
| TOCTOU hash check | modifier-agent (wrapper) |
| Hash update after modification | modifier-agent (wrapper) |
| Operations log YAML writing | modifier-agent (wrapper) |
| Snapshot restoration on failure | modifier-agent (wrapper) |

The Rate Modifier provides the **data** for logging and hash updates. The
modifier-agent (the wrapper that dispatches to this .md file) handles the
I/O operations for snapshots, hashes, and log entries.

---

## What This Agent Handles

| Operation Type | Example | What It Does |
|---------------|---------|-------------|
| Base rate multiply | "All territories x 1.05" | Multiply all numeric Array6 args, apply rounding |
| Factor table change | "Deductible 5000: -0.20 -> -0.22" | Find Case, replace value |
| Included limit change | "Medical Payments limit: 5000 -> 10000" | Find condition, replace value |
| Const value change | "ACCIDENTBASE: 200 -> 210" | Find Const declaration, replace value |
| Sewer backup premium | "14-arg Array6 x 1.03" | Same as base rate, handles 1-14+ args |
| Discount/surcharge | "Multi-policy discount: 8% -> 10%" | Find function, update factor value |

## What This Agent Does NOT Handle

| What | Handled By |
|------|-----------|
| New functions or subroutines | Logic Modifier |
| New constants (adding, not changing) | Logic Modifier |
| Conditional logic / If-Then-Else changes | Logic Modifier |
| Alert messages | Logic Modifier |
| New Select Case blocks (adding Cases) | Logic Modifier |
| File copies and .vbproj updates | file-copier-agent |
| .vbproj structural changes (GUIDs, project setup) | IQWiz |
| DAT file rate changes | Out of scope (manual) |
| Cross-province shared files | Out of scope (flagged for developer) |

---

## Boundary Table

| Concern | Rate Modifier | File-Copier | Logic Modifier | Reviewer |
|---------|:------------:|:-----------:|:--------------:|:--------:|
| Copy Code/ files to new date | | X | | |
| Update .vbproj references | | X | | |
| Modify Array6 rate values | X | | | |
| Modify Select Case factors | X | | | |
| Modify included limits | X | | | |
| Modify Const rate values | X | | | |
| Add new functions | | | X | |
| Add new Case blocks | | | X | |
| Add If/ElseIf logic | | | X | |
| Add new constants | | | X | |
| Validate arg count unchanged | | | | X |
| Validate no old-file edits | | | | X |
| Validate value sanity | | | | X |
| Snapshot creation | modifier-agent* | | | |
| TOCTOU hash check | modifier-agent* | | | |
| Hash update after edit | modifier-agent* | | | |
| Operations log writing | modifier-agent* | | | |

\* The modifier-agent is the wrapper that dispatches to rate-modifier.md. It handles
infrastructure concerns (snapshots, hashes, logging) while the Rate Modifier handles
the domain logic (locating, computing, and applying value changes).

---

## Loading Additional Modules

After reading this core contract, the worker reads `dispatch.md` to determine
which module card to load for the specific operation type.
