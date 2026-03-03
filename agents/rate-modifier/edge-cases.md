# Rate Modifier -- Edge Cases & Worked Examples

Load this file ONLY when an error condition fires, a special case is detected,
or a rework instruction is received.

**Prerequisites:** The worker MUST have already loaded `core.md` and `dispatch.md`,
plus the relevant module for the operation type.

---

## WORKED EXAMPLES

### Example A: Simple Array6 Multiply (5% Increase, 9 Territories, Banker's Rounding)

**Operation YAML (abbreviated):**

```yaml
id: "op-001-01"
pattern: "base_rate_increase"
function: "GetBasePremium_Home"
parameters:
  factor: 1.05
  scope: "all_territories"
rounding_resolved: "banker"
function_line_start: 300
function_line_end: 420
target_lines:
  - line: 352
    content: "                Case 1 : varRates = Array6(basePremium, 233, 274, 319, 372, 432, 502)"
    context: "Territory 1"
    rounding: "banker"
    value_count: 7
  - line: 353
    content: "                Case 2 : varRates = Array6(basePremium, 255, 300, 349, 407, 473, 549)"
    context: "Territory 2"
    rounding: "banker"
    value_count: 7
  - line: 354
    content: "                Case 3 : varRates = Array6(basePremium, 198, 233, 271, 316, 367, 426)"
    context: "Territory 3"
    rounding: "banker"
    value_count: 7
```

**Step-by-step execution:**

**Step 4 -- Locate function:** Search for `GetBasePremium_Home` near line 300.
Found: `Public Function GetBasePremium_Home(` at line 298 (0-indexed: 297).
Function end: `End Function` at line 425 (0-indexed: 424).

**Step 5 -- Locate target lines:** For each target_line, find by content match:
- Line 352 content matches at index 351 -- OK
- Line 353 content matches at index 352 -- OK
- Line 354 content matches at index 353 -- OK

**Step 6 -- Validate current values:**
- Line 352: parse Array6 -> `[basePremium, 233, 274, 319, 372, 432, 502]`
  - 7 args, matches value_count=7 -- OK
  - basePremium is a variable -- will skip in multiplication
- Lines 353, 354: similar validation passes

**Step 7a -- Compute new values for Territory 1 (line 352):**

```
Input:  [basePremium, 233, 274, 319, 372, 432, 502]
Factor: 1.05
Rounding: banker

basePremium  -> variable, keep as-is
233 * 1.05 = 244.65 -> round(244.65) = 245  (not a .5 case)
274 * 1.05 = 287.70 -> round(287.70) = 288
319 * 1.05 = 334.95 -> round(334.95) = 335
372 * 1.05 = 390.60 -> round(390.60) = 391
432 * 1.05 = 453.60 -> round(453.60) = 454
502 * 1.05 = 527.10 -> round(527.10) = 527

Output: [basePremium, 245, 288, 335, 391, 454, 527]
```

**Step 7a -- Compute for Territory 2 (line 353):**

```
255 * 1.05 = 267.75 -> 268
300 * 1.05 = 315.00 -> 315
349 * 1.05 = 366.45 -> 366
407 * 1.05 = 427.35 -> 427
473 * 1.05 = 496.65 -> 497
549 * 1.05 = 576.45 -> 576

Output: [basePremium, 268, 315, 366, 427, 497, 576]
```

**Step 7a -- Compute for Territory 3 (line 354):**

```
198 * 1.05 = 207.90 -> 208
233 * 1.05 = 244.65 -> 245
271 * 1.05 = 284.55 -> 285  (banker's: .55 rounds up because 284 is even)
316 * 1.05 = 331.80 -> 332
367 * 1.05 = 385.35 -> 385
426 * 1.05 = 447.30 -> 447

Output: [basePremium, 208, 245, 285, 332, 385, 447]
```

Wait -- let me verify 284.55 with banker's rounding:
- 284.55 is NOT a .5 case (it's .55, which is > .5) -> rounds UP to 285. Correct.

**Step 8 -- Apply changes:**

```
Before: "                Case 1 : varRates = Array6(basePremium, 233, 274, 319, 372, 432, 502)"
After:  "                Case 1 : varRates = Array6(basePremium, 245, 288, 335, 391, 454, 527)"

Before: "                Case 2 : varRates = Array6(basePremium, 255, 300, 349, 407, 473, 549)"
After:  "                Case 2 : varRates = Array6(basePremium, 268, 315, 366, 427, 497, 576)"

Before: "                Case 3 : varRates = Array6(basePremium, 198, 233, 271, 316, 367, 426)"
After:  "                Case 3 : varRates = Array6(basePremium, 208, 245, 285, 332, 385, 447)"
```

Note: indentation (16 spaces), `Case N : varRates = ` prefix, separator `, ` all
preserved exactly.

**Step 10 -- Verify:** Re-read lines 352-354, confirm they match the "After" values.

**Operations log entry:**

```yaml
- operation: "op-001-01"
  agent: "rate-modifier"
  status: "COMPLETED"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  function: "GetBasePremium_Home"
  changes:
    - line: 352
      description: "Territory 1"
      before: "                Case 1 : varRates = Array6(basePremium, 233, 274, 319, 372, 432, 502)"
      after:  "                Case 1 : varRates = Array6(basePremium, 245, 288, 335, 391, 454, 527)"
      values_changed: 6
    - line: 353
      description: "Territory 2"
      before: "                Case 2 : varRates = Array6(basePremium, 255, 300, 349, 407, 473, 549)"
      after:  "                Case 2 : varRates = Array6(basePremium, 268, 315, 366, 427, 497, 576)"
      values_changed: 6
    - line: 354
      description: "Territory 3"
      before: "                Case 3 : varRates = Array6(basePremium, 198, 233, 271, 316, 367, 426)"
      after:  "                Case 3 : varRates = Array6(basePremium, 208, 245, 285, 332, 385, 447)"
      values_changed: 6
  summary:
    lines_changed: 3
    values_changed: 18
    change_range: "4.9% to 5.2%"
    started_at: "2026-01-15T11:05:00Z"
    completed_at: "2026-01-15T11:05:01Z"
```

---

### Example B: Factor Table Change (Case 5000 Deductible, Single Code Path)

**Operation YAML (abbreviated):**

```yaml
id: "op-002-01"
pattern: "factor_table_change"
function: "SetDisSur_Deductible"
parameters:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22
function_line_start: 2108
function_line_end: 2227
target_lines:
  - line: 2202
    content: "                    dblDedDiscount = -0.2"
    context: "Case 5000 > If blnFarmLocation Then (farm path)"
    rounding: null
candidates_shown: 2
developer_confirmed: true
analysis_notes: |
  Case 5000 has two code paths. Developer chose farm path only (line 2202).
```

**Step-by-step execution:**

**Step 4 -- Locate function:** Search for `SetDisSur_Deductible`. Found at line 2108.

**Step 5 -- Locate target line:** Content match for
`"                    dblDedDiscount = -0.2"` within function [2108, 2227].
Found at index 2201 (line 2202).

**Step 6 -- Validate:** Check that `-0.2` (equivalent to `-0.20`) appears on the line.
The line reads `dblDedDiscount = -0.2` -- old_value `-0.20` formatted as `-0.2`.
Match confirmed.

**Step 7b -- Compute:** Simple substitution: `-0.2` -> `-0.22`.

```python
old_str = format_vb_number(-0.20)  # -> "-0.2"
new_str = format_vb_number(-0.22)  # -> "-0.22"
# Replace "-0.2" with "-0.22" on the line
```

**CAUTION with VB.NET formatting:** `-0.20` displays as `-0.2` in VB.NET (trailing
zero stripped). The `format_vb_number` function handles this. When searching, try
BOTH forms.

**Step 8 -- Apply:**

```
Before: "                    dblDedDiscount = -0.2"
After:  "                    dblDedDiscount = -0.22"
```

Indentation (20 spaces) preserved. Only the numeric value changed.

**Note on partial match prevention:** The regex `(?<![.\d])-0\.2(?![.\d])` ensures
we match `-0.2` but NOT `-0.25` (which appears on the next line in the non-farm
path). The negative lookbehind `(?<![.\d])` prevents matching a digit or dot before,
and the negative lookahead `(?![.\d])` prevents matching a digit or dot after. This
is critical when the same function has values like `-0.2` and `-0.25`.

**Operations log entry:**

```yaml
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
    change_range: "10.0%"
    started_at: "2026-01-15T11:05:04Z"
    completed_at: "2026-01-15T11:05:04Z"
```

---

### Example D: Multi-Code-Path Factor Table (Farm vs Non-Farm)

This example shows a Case block where the Analyzer found TWO matching values but
the developer chose to modify BOTH paths (unlike Example B where only one was chosen).

**Operation YAML (abbreviated):**

```yaml
# NOTE: This YAML is INTENTIONALLY INVALID -- it shows the problem scenario.
# The Analyzer would NOT produce this. See explanation below for correct form.
id: "op-003-01"
pattern: "factor_table_change"
function: "SetDisSur_Deductible"
parameters:
  case_value: 5000
  old_value: -0.20       # But line 2205 has -0.25, not -0.20!
  new_value: -0.22
target_lines:
  - line: 2202
    content: "                    dblDedDiscount = -0.2"
    context: "Case 5000 > If blnFarmLocation Then (farm path)"
    rounding: null
  - line: 2205
    content: "                    dblDedDiscount = -0.25"
    context: "Case 5000 > Else (non-farm path)"
    rounding: null
candidates_shown: 2
developer_confirmed: true
analysis_notes: |
  Case 5000 has farm (-0.2) and non-farm (-0.25) paths.
  Developer chose BOTH: farm -0.2 -> -0.22, non-farm -0.25 -> -0.27.
```

The problem: `old_value: -0.20` and `new_value: -0.22` in parameters, but line 2205
has `-0.25` (not `-0.20`). The operation has TWO replacements with DIFFERENT
old/new values. How does the YAML handle this?

**Answer:** When `candidates_shown > 1` and the developer chose multiple paths
with DIFFERENT target values, the Analyzer creates **separate operations** for
each code path (or the parameters include per-line overrides). In the standard
contract, each `target_lines[]` entry is modified with the SAME parameters.

**For this example, assume the developer wants the SAME percentage change applied
to both paths.** The Decomposer would create two separate operations:

```yaml
# op-003-01: farm path
parameters:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22
target_lines:
  - line: 2202
    content: "                    dblDedDiscount = -0.2"

# op-003-02: non-farm path
parameters:
  case_value: 5000
  old_value: -0.25
  new_value: -0.27
target_lines:
  - line: 2205
    content: "                    dblDedDiscount = -0.25"
```

**Execution for op-003-01:**

```
Before: "                    dblDedDiscount = -0.2"
After:  "                    dblDedDiscount = -0.22"
```

**Execution for op-003-02** (runs after op-003-01, bottom-to-top means 2205 > 2202
so op-003-02 runs first):

```
Before: "                    dblDedDiscount = -0.25"
After:  "                    dblDedDiscount = -0.27"
```

**Key insight:** The execution plan ensures bottom-to-top ordering within the same
file. Line 2205 is processed before line 2202. Since these are simple value
substitutions (no line additions/removals), the order doesn't affect results, but
the convention is maintained for safety.

---

### Example F: Value Already Matches Target (No Change Needed)

**Scenario:** A previous partial execution already applied this change, or the
source file was manually updated.

**Operation YAML (abbreviated):**

```yaml
id: "op-007-01"
pattern: "factor_table_change"
function: "SetDisSur_Deductible"
parameters:
  case_value: 1000
  old_value: -0.075
  new_value: -0.08
target_lines:
  - line: 2180
    content: "                Case 1000 : dblDedDiscount = -0.075"
    context: "Case 1000 deductible factor"
    rounding: null
```

**Step 5 -- Locate target line:** Search for content
`"                Case 1000 : dblDedDiscount = -0.075"`.

**Scenario A: Content found, old_value present** -- Normal execution proceeds.

**Scenario B: Content NOT found, but a line with new_value IS found:**

```
Actual line: "                Case 1000 : dblDedDiscount = -0.08"
```

The value is already `-0.08` (the target). The change has already been applied.

**Action:** Log as `SKIPPED` (not `FAILED` and not `COMPLETED`):

```yaml
- operation: "op-007-01"
  agent: "rate-modifier"
  status: "SKIPPED"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  function: "SetDisSur_Deductible"
  changes: []
  skip_reason: "Value already matches target: -0.08 at line 2180"
  summary:
    lines_changed: 0
    values_changed: 0
```

**How to detect this:** When `validate_current_values` fails because old_value is
not found, check if new_value IS present on a line that otherwise matches the
content pattern:

```python
def check_already_applied(line, old_value, new_value):
    """Check if the change was already applied to this line.

    Returns True if new_value is found where old_value was expected.
    """
    old_str = format_vb_number(old_value)
    new_str = format_vb_number(new_value)

    # Old value NOT on line but new value IS on line
    if not value_appears_on_line(line, old_value) and value_appears_on_line(line, new_value):
        return True
    return False
```

For `base_rate_increase`, this is more complex: parse the Array6 args, multiply
each by the factor, and check if the current values already match the expected
post-multiplication values.

---

## SPECIAL CASES

### Case 1: Sentinel Value -999 Encountered

**Context:** VB.NET code uses `-999` as an error sentinel in rate tables:

```vb
dblDedDiscount = -999        ' Error -- invalid deductible
```

**Rule:** NEVER modify a line containing the sentinel value `-999`. The Analyzer
should have excluded these from `target_lines`, but the Rate Modifier must check
as a safety net.

**Detection:**

```python
def contains_sentinel(line):
    """Check if a line contains the -999 error sentinel."""
    import re
    return bool(re.search(r'(?<!\d)-999(?!\d)', line))
```

**Action:** If a `target_lines` entry points to a line containing `-999`:
1. Log a WARNING: `"Sentinel value -999 found on target line {N}. Skipping."`
2. Skip this specific line (do NOT abort the entire operation)
3. Continue with remaining target lines
4. Include in the operations log with `skip_reason: "sentinel_value"`

### Case 2: All-Zero Array6 (Default Initialization)

**Context:** Functions often initialize arrays to zeros before populating:

```vb
liabilityPremiumArray = Array6(0, 0, 0, 0, 0, 0)
```

**Rule:** The Analyzer puts these in `skipped_lines`, not `target_lines`. But as
a safety check: if ALL values in a target_lines Array6 are zero, skip it.

**Detection:** After parsing Array6 args, check if all numeric values are 0.

```python
def is_all_zero_array6(parsed_args):
    """Check if all non-variable args are zero."""
    for arg in parsed_args:
        if arg["is_variable"]:
            continue
        if arg["value"] is not None and arg["value"] != 0:
            return False
    return True
```

**Action:** Skip the line, log `skip_reason: "all_zero_initialization"`. This is
NOT an error -- it's expected behavior.

### Case 3: Array6 Inside IsItemInArray (Non-Rate -- Safety Check)

**Context:** Array6 is used for membership tests as well as rate values:

```vb
If IsItemInArray(coverageItem.Code, Array6(COVITEM_PRIMARY, COVITEM_EXTENDED)) Then
```

**Rule:** The Analyzer MUST have excluded these (they appear in `skipped_lines`).
But if one somehow appears in `target_lines`, the Rate Modifier must catch it.

**Detection:** Check if the line contains `IsItemInArray` and the Array6 is inside it:

```python
def is_membership_test(line):
    """Check if Array6 is used as a membership test, not a rate."""
    import re
    # Pattern: IsItemInArray(something, Array6(...))
    return bool(re.search(r'IsItemInArray\s*\(.*Array6\s*\(', line))
```

**Action:** ABORT this specific line. Log as:
```yaml
status: "FAILED"
error: "Array6 is inside IsItemInArray() -- this is a membership test, not a rate. "
       "The Analyzer should have excluded this line. Aborting operation."
```

### Case 4: Commented Line Matches Content Pattern

**Context:** Old rate values are sometimes left as comments:

```vb
                    'CET 2017/07/14. Jira IQPORT-3036
                    'dblDedDiscount = -0.15   <-- Old value, commented out
                    dblDedDiscount = -0.2     <-- Current value, active
```

**Rule:** NEVER modify commented lines. The `target_lines[].content` from the
Analyzer should only contain active code lines, but the Rate Modifier must verify.

**Detection:** Check if the first non-whitespace character is a single quote `'`:

```python
def is_commented(line):
    """Check if a line is commented out in VB.NET."""
    stripped = line.strip()
    return stripped.startswith("'")
```

**Action:** If a target line is commented, ABORT the operation with an error. This
indicates a mismatch between analysis and execution -- the file may have changed.

### Case 5: String Case Values vs Numeric Case Values

**Context:** Some Select Case blocks use string values:

```vb
Select Case sewerBackupCoverage
    Case "5000" : premiumArray = Array6(50, 50, 50, 70, ...)
    Case "10000" : premiumArray = Array6(96, 96, 96, 135, ...)
End Select
```

While others use numeric values:

```vb
Select Case intDeductible
    Case 500 : dblDis = -0.06
    Case 1000 : dblDis = -0.08
End Select
```

**Rule:** The content match in Step 5 handles this automatically because it matches
the FULL line content (including quotes). The Rate Modifier does not need to
distinguish between string and numeric Case values -- it only modifies the VALUE
on the line, not the Case label.

**Caution:** When the `parameters.case_value` is `5000` but the actual code has
`"5000"` (string), the Analyzer's `target_lines[].content` will include the quotes.
The Rate Modifier matches by content, so this works transparently.

### Case 6: Multiple Variable Assignments in Same Function

**Context:** A function may have multiple variables being set:

```vb
Function GetLiabilityBundlePremiums(...)
    liabilityPremiumArray = Array6(0, 78, 161, ...)     ' Main liability
    sewerPremiumArray = Array6(50, 50, 50, ...)         ' Sewer backup
    waterPremiumArray = Array6(30, 30, 30, ...)         ' Water damage
End Function
```

**Rule:** The `target_lines[].content` field identifies the EXACT line, including
the variable name on the left side. Content matching ensures we modify the correct
variable assignment. The Rate Modifier never searches by variable name alone.

**Action:** No special handling needed. Content match is the authoritative locator.
The different variable names (`liabilityPremiumArray` vs `sewerPremiumArray`) make
the content strings unique.

### Case 7: Const Declaration as Rate Value

See `modules/factor-table.md` for Const declaration handling (same module covers
this case).

### Case 8: CRLF vs LF Line Endings

**Context:** VB.NET source files typically use CRLF (`\r\n`) line endings, but
some files may use LF (`\n`) only, especially if edited on different platforms.

**Rule:** Detect the line ending style when reading the file (Step 3) and preserve
it when writing back (Step 9). NEVER change line endings.

**Detection:** Check for `\r\n` in the raw bytes. If found, use CRLF. Otherwise LF.

**Why this matters:** Changing line endings creates massive SVN diffs and confuses
developers reviewing changes. A rate update that changes 3 values should show 3
lines in the diff, not 4,000 lines.

### Case 9: Tab vs Space Indentation Preservation

**Context:** VB.NET source code in this codebase uses **4 spaces per level** for
indentation. However, .vbproj files use tabs. Some code files may have mixed
indentation.

**Rule:** The Rate Modifier copies the leading whitespace from the ORIGINAL line
exactly. It does not re-indent, normalize tabs to spaces, or change whitespace in
any way.

**Implementation:** The `apply_array6_change()` function in Step 8 preserves
everything before the `Array6(` token. For factor changes, the regex substitution
preserves the entire line except the numeric value.

### Case 10: Value with Trailing Comment on Same Line

**Context:** Some rate lines have inline comments:

```vb
                Case 500 : dblDis = -0.06   'RJB 20191201 IQPORT-4732
```

**Rule:** Preserve the trailing comment. The Rate Modifier only changes the numeric
value. The regex substitution in Step 7b replaces `count=1` (first occurrence only),
which targets the value, not the comment text.

For Array6 lines, the `apply_array6_change()` function preserves the `suffix`
(everything after the closing parenthesis), which includes any trailing comment:

```
Before: "        premiumArray = Array6(50, 60, 70)  'Updated 2025"
After:  "        premiumArray = Array6(53, 64, 74)  'Updated 2025"
```

The comment `'Updated 2025` is part of the suffix and passes through unchanged.

---

## Error Handling

### TOCTOU Failure

**Trigger:** The modifier-agent detects that the file hash does not match
`execution/file_hashes.yaml` before starting an operation.

**Who detects:** modifier-agent (not the Rate Modifier itself).

**Action:** The modifier-agent aborts the operation and logs:

```yaml
- operation: "op-001-01"
  agent: "rate-modifier"
  status: "FAILED"
  error: "TOCTOU_FAILURE: File hash mismatch for mod_Common_SKHab20260101.vb. "
         "Expected sha256:abc123, actual sha256:def456. "
         "File was modified since plan approval."
  recovery: "Re-run /iq-plan to regenerate analysis and plan."
```

**Recovery:** The developer must re-run `/iq-plan` to get fresh analysis. The
execution cannot continue on a file that changed unexpectedly.

### Content Mismatch (Target Line Not Found)

**Trigger:** Step 5 (locate target lines) or Step 6 (validate current values)
fails because the expected content does not match any line in the function.

**Possible causes:**
1. A preceding operation in the same file added/removed lines (line drift beyond
   what content matching can handle)
2. Manual edits between analysis and execution
3. Wrong function identified by Analyzer

**Action:** Log `FAILED` with details:

```yaml
- operation: "op-002-01"
  agent: "rate-modifier"
  status: "FAILED"
  error: "CONTENT_MISMATCH: Target line not found in function SetDisSur_Deductible "
         "(lines 2108-2227). Expected: 'dblDedDiscount = -0.2' (hint line 2202)."
  recovery: "Check if file was manually edited. Re-run /iq-plan if needed."
```

**Recovery:** The modifier-agent may attempt the next operation in the sequence.
Content mismatches on one operation do not automatically abort the entire execution.

### Value Already Matches Target

**Trigger:** Step 6 finds that the current value already equals the new_value
(the change was already applied, possibly by a previous partial execution).

**Action:** Log `SKIPPED` (see Example F above). This is not an error.

### Rework Protocol

**Trigger:** The execution-reviewer (within /iq-execute) finds an issue with a
completed operation and sends a rework instruction.

**Rework message format:**

```
execution-reviewer -> modifier: "REWORK: {op_id, issue, fix_instruction}"
```

**Process:**
1. The modifier-agent receives the rework message
2. It re-dispatches to the Rate Modifier with the ORIGINAL operation YAML
3. The Rate Modifier re-executes from Step 3 (re-read file) through Step 10 (verify)
4. The `fix_instruction` may specify additional constraints (e.g., "use 2 decimal
   places instead of integer rounding on line 4062")
5. Maximum **2 rework attempts** per operation

**After 2 failed rework attempts:**

```yaml
- operation: "op-002-01"
  agent: "rate-modifier"
  status: "FAILED"
  error: "PERSISTENT_FAILURE: Rework failed after 2 attempts. "
         "Issue: {issue_description}. "
         "Last fix attempted: {fix_instruction}."
  recovery: "Manual developer intervention required."
```

The modifier-agent escalates `PERSISTENT_FAILURE` to the /iq-execute orchestrator,
which halts execution and reports to the developer.

### Argument Count Changed

**Trigger:** After applying an Array6 change, verification (Step 10) detects that
the number of arguments changed (e.g., a comma was accidentally added or removed).

**Action:** This should NOT happen with the `apply_array6_change()` approach
(which rebuilds the arg list from parsed values). But if detected:

1. Restore the original line from the before value in the changes log
2. Log `FAILED` with `error: "ARG_COUNT_CHANGED"`
3. This triggers a rework cycle

### Unknown Pattern Type

**Trigger:** The operation YAML has a `pattern` value not in
`{base_rate_increase, factor_table_change, included_limits}`.

**Action:**

```yaml
status: "FAILED"
error: "UNKNOWN_PATTERN: '{pattern}' is not supported by the Rate Modifier. "
       "Supported: base_rate_increase, factor_table_change, included_limits."
```

This indicates a pipeline misconfiguration -- the Decomposer assigned the wrong
agent type.

---

## NOT YET IMPLEMENTED (Future Enhancements)

- **Batch Array6 multiply:** Currently processes each target line individually.
  Future versions could batch all Array6 lines in a function into a single
  operation for performance (read function once, modify all lines, write once).
  This would reduce file I/O for functions with 20+ territories.

- **Auto-detect rounding from context:** Currently relies on the Analyzer's
  pre-resolved `rounding` field. Future versions could independently verify
  rounding by checking if values are integers or decimals, providing a safety
  check on the Analyzer's decision.

- **Multi-value factor_table_change:** Currently supports single old_value ->
  new_value per operation. Future versions could support a mapping of multiple
  old/new value pairs in a single operation, reducing the number of operations
  for large factor table rewrites.

- **Inline diff preview:** Before applying a change, generate a colored diff
  preview and present to the developer for confirmation. Currently the
  developer approves at Gate 1 (plan level) and Gate 2 (review level), but
  not at the individual line level during execution.

- **Value range validation during compute:** Check that computed values fall
  within expected ranges BEFORE applying (e.g., a premium going from $500 to
  $50,000 is likely an error). Currently this validation happens post-hoc in
  the Reviewer.

- **Undo individual operations:** Currently the only undo mechanism is
  restoring from the per-file snapshot (which undoes ALL operations on that
  file). Future versions could support undoing individual operations by
  tracking per-operation diffs.

- **Parallel Array6 processing:** For operations that target multiple functions
  in the same file, processing could be parallelized at the function level
  (since functions don't overlap in line ranges). Currently all operations
  on a file are strictly sequential.

<!-- IMPLEMENTATION: Phase 07 -->
