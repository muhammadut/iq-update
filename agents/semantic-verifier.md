# Agent: Semantic Verifier

## Purpose

Verify that each executed intent actually achieves what the developer approved in
the plan. Bridge the gap between structural validators (Python scripts that check
syntax and completeness) and semantic correctness (does the code change match the
original intent description?). Produce a reasoning chain for each intent that the
developer can follow at Gate 5.

**Core philosophy: REASON, THEN JUDGE.** For every intent, read the before/after
code, state what the intent required, show the arithmetic or logic check, and
declare MATCH or MISMATCH. Never silently pass — always show the reasoning.

## Pipeline Position

```
[EXECUTED] --> Validator --> Diff --> SEMANTIC VERIFIER --> Report --> [GATE 5]
                                     ^^^^^^^^^^^^^^^^^^
```

- **Upstream:** Validator agent (structural checks passed), Diff agent (diffs available)
- **Downstream:** Report agent (incorporates semantic findings into summary),
  Developer reviews at Gate 5

## Input Schema

```yaml
# Reads: analysis/intent_graph.yaml (intents with descriptions and target regions)
# Reads: analysis/code_understanding.yaml (FUBs under change_requests.{cr_id}.fub, function targets)
# Reads: execution/operations_log.yaml (what operations were performed)
# Reads: execution/snapshots/*.snapshot (pre-edit file copies)
# Reads: plan/execution_order.yaml (planned changes with values)
# Reads: plan/execution_plan.md (human-readable plan)
# Reads: parsed/requests/cr-NNN.yaml (original CR details with extracted values)
# Reads: all modified source files (current state after execution)
# Reads: manifest.yaml (workflow metadata)
```

## Output Schema

```yaml
# File: verification/semantic_verification.yaml
workflow_id: "20260101-SK-Hab-rate-update"
verified_at: "2026-01-15T11:12:00Z"
total_intents: 15
matched: 14
mismatched: 1
skipped: 0

results:
  - intent_id: "intent-001"
    cr_id: "cr-001"
    description: "Multiply territory 1 base rate by 1.042"
    verdict: "MATCH"
    reasoning: |
      Before: varRates = Array6(512.59, 28.73, ...) [line 448]
      After:  varRates = Array6(534.12, 29.94, ...) [line 448]
      Check:  512.59 × 1.042 = 534.12 ✓ (exact)
              28.73 × 1.042 = 29.94 ✓ (2dp match)
      All 9 values in Array6 scaled correctly.

  - intent_id: "intent-002"
    cr_id: "cr-001"
    description: "Multiply territory 2 base rate by 1.042"
    verdict: "MISMATCH"
    reasoning: |
      Before: varRates = Array6(66.48, ...) [line 452]
      After:  varRates = Array6(69.27, ...) [line 452]
      Check:  66.48 × 1.042 = 69.2722
              Rounded to 2dp: 69.27 ✓
              BUT second value: 18.50 × 1.042 = 19.277 → expected 19.28, got 19.27
      Mismatch on value index 2: expected 19.28, actual 19.27.
    severity: "WARNING"
    suggested_action: "Verify rounding convention — banker's rounding gives 19.28"

  - intent_id: "intent-008"
    cr_id: "cr-003"
    description: "Insert new Case 7500 block after Case 5000 in SetDisSur_Deductible"
    verdict: "MATCH"
    reasoning: |
      Before: No Case 7500 block in SetDisSur_Deductible [line 680-720]
      After:  Case 7500 inserted at line 698, between Case 5000 (line 690) and
              Case 10000 (line 705). Contains: dblDedDiscount = -0.25
      Structure: Correct insertion point, correct case value, correct assignment.
      Surrounding context preserved (Case 5000 and Case 10000 unchanged).
```

```markdown
# File: verification/semantic_report.md

# Semantic Verification Report
Workflow: {workflow_id}
Verified: {timestamp}

## Summary
- **{matched}/{total}** intents verified as MATCH
- **{mismatched}** MISMATCH(es) found
- **{skipped}** skipped (no verifiable code change)

## Detailed Results

### ✓ MATCHED Intents

#### intent-001: Multiply territory 1 base rate by 1.042
- **CR:** cr-001
- **File:** Saskatchewan/Code/mod_Common_SKHab20260101.vb
- **Before (line 448):** `varRates = Array6(512.59, 28.73, ...)`
- **After  (line 448):** `varRates = Array6(534.12, 29.94, ...)`
- **Check:** 512.59 × 1.042 = 534.12 ✓ | 28.73 × 1.042 = 29.94 ✓
- **Verdict:** All 9 values scaled correctly.

### ✗ MISMATCHED Intents

#### intent-002: Multiply territory 2 base rate by 1.042 (WARNING)
- **File:** Saskatchewan/Code/mod_Common_SKHab20260101.vb
- **Issue:** Value index 2: expected 19.28, actual 19.27
- **Suggested action:** Verify rounding convention

## Recommendations
{If any mismatches: list recommended actions}
{If all match: "All intents verified. No semantic issues detected."}
```

## Verification Steps

### Step 1: Load Context

```
1. Read manifest.yaml for workflow_id, province, LOBs, effective_date
2. Read paths.md → extract vb_parser path and python_cmd
3. Read analysis/intent_graph.yaml for the full list of intents
4. Read analysis/code_understanding.yaml for FUBs and target metadata
5. Read plan/execution_order.yaml for planned values and operations
6. Read execution/operations_log.yaml for executed operations
7. Build a mapping: intent_id → {description, file, lines, cr_id, capability, target_kind}
```

### Step 2: For Each Intent — Verify Semantics

Process intents grouped by file (to minimize file reads). For each intent:

```
1. READ the relevant snapshot using path-encoded naming:
   snapshot_name = intent.file.replace("/", "__").replace("\\", "__") + ".snapshot"
   snapshot_path = execution/snapshots/{snapshot_name}
   (Example: "SK/Code/mod_Common_SKHab20260101.vb" → "SK__Code__mod_Common_SKHab20260101.vb.snapshot")
   - Extract the before-state around the target lines (±10 lines of context)

2. READ the current modified file
   - Extract the after-state at the same region

3. CLASSIFY the verification type based on intent capability:

   ┌─────────────────────────────────────────────────────────────────┐
   │ Capability            │ Verification Method                    │
   ├───────────────────────┼────────────────────────────────────────┤
   │ value_editing          │ Arithmetic check (Step 3a)            │
   │ structure_insertion    │ Structural placement check (Step 3b)  │
   │ file_creation          │ File existence + content check (3c)   │
   │ flow_modification      │ Control flow check (Step 3d)          │
   └─────────────────────────────────────────────────────────────────┘

4. PRODUCE reasoning chain and verdict (MATCH / MISMATCH)
```

### Step 3a: Arithmetic Verification (value_editing)

For rate changes, factor changes, and scalar value edits.

#### Step 3a.0: Parser-Backed Value Extraction (v0.4.0 Enhancement)

**Instead of Claude re-reading files to find values** (expensive, error-prone for
large files with duplicate lines), use the vb-parser to extract exact argument
values from both snapshot and current file. This gives the Python arithmetic
proofs **provably correct input data**, eliminating the weakest link in the
verification chain.

```
vb_parser = paths.md → vb_parser path

# Get the target function and target_kind from intent metadata
function_name = intent.function
target_kind = intent.target_kind  # call|assignment|constant|case_label

# --- Extract BEFORE values from snapshot (path-encoded name) ---
snapshot_name = intent.file.replace("/", "__").replace("\\", "__") + ".snapshot"
snapshot_path = execution/snapshots/{snapshot_name}
IF snapshot_path exists:
  snapshot_func = bash: {vb_parser} function {snapshot_path} {function_name}

  IF target_kind == "call":
    # Extract Array6/function call arguments at target lines
    before_targets = []
    for target_line in intent.target_lines:
      match = find_call_near_line(snapshot_func.function.calls,
                                   target_line.line,
                                   target_line.assignment_target)
      IF match:
        before_targets.append({
          "line": match.line,
          "args": match.arguments,      # parser-extracted exact args
          "name": match.name,
          "assignment_target": match.assignmentTarget
        })

  ELIF target_kind == "assignment":
    before_targets = []
    for asgn in snapshot_func.function.assignments:
      if asgn.line in [tl.line for tl in intent.target_lines]:
        before_targets.append({"line": asgn.line, "value": asgn.value})

  ELIF target_kind == "constant":
    snapshot_file = bash: {vb_parser} parse {snapshot_path}
    before_targets = []
    for const in snapshot_file.constants:
      if const.name in [tl.constant_name for tl in intent.target_lines]:
        before_targets.append({"line": const.line, "name": const.name, "value": const.value})

# --- Extract AFTER values from current file ---
current_path = codebase_root + "/" + intent.file
current_func = bash: {vb_parser} function {current_path} {function_name}

# Same extraction logic as above, applied to current_func
# (produces after_targets with parser-extracted values)

# --- Feed parser-extracted values to Python arithmetic ---
# The old_values and new_values below come from parser output,
# NOT from Claude reading the file. This is the key improvement:
# parser provenance eliminates misreads.
```

**Fallback:** If the parser cannot extract values (e.g., complex expressions,
non-standard patterns), fall back to Claude reading the snapshot/file directly.
Log: "Parser extraction unavailable for {intent_id}, using LLM read."

IMPORTANT: If parser extraction fails for ANY intent, include a WARNING in the
semantic_verification.yaml output:
  parser_fallback: true
  note: "Parser could not extract values for {intent_id}; verification based on Claude reading (lower confidence)"
This allows the developer at Gate 5 to see which verifications are parser-backed vs LLM-backed.

#### Step 3a.1: Python Arithmetic Check

**CRITICAL: Use Python for ALL arithmetic.** Do NOT compute multiplication or
rounding mentally. LLM mental math can produce subtle errors (e.g., off-by-one
cent on rounding). Use the `python_cmd` from paths.md to compute expected values.

```
1. Use parser-extracted old_value (from Step 3a.0) or extract from snapshot
2. Use parser-extracted new_value (from Step 3a.0) or extract from modified file
3. Read the planned operation:
   - If multiplicative: check old_value × factor = new_value (within rounding)
   - If replacement: check new_value matches planned value exactly
   - If additive: check old_value + delta = new_value

   **USE PYTHON FOR STEP 3:**
   For multiplicative checks, run:
     {python_cmd} -c "
     from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
     old = Decimal('{old_value}')
     factor = Decimal('{factor}')
     result = old * factor
     banker = result.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
     standard = result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
     print(f'exact={result} banker={banker} standard={standard}')
     "
   Compare the Python output against new_value. Report the Python result
   in the reasoning chain (e.g., "Python: 512.59 × 1.042 = 534.1198 → 534.12").
   Do NOT attempt to verify arithmetic by mental calculation.

4. Rounding tolerance:
   - If rounding mode is "banker": use Decimal rounding with ROUND_HALF_EVEN
   - If rounding mode is "none": exact match required
   - If rounding mode is "mixed": check both, note which was used
   - Tolerance window: ±0.01 for 2dp values, ±0.001 for 3dp values

5. For Array6 edits: verify ALL values in the array, not just the first
   - Count values: before and after must match
   - Check each value individually using Python (batch all values in one script)
   - Report which specific indices match/mismatch

   For Array6 batch verification, run a single Python script:
     {python_cmd} -c "
     from decimal import Decimal, ROUND_HALF_EVEN
     old_vals = [{old_val_1}, {old_val_2}, ...]
     new_vals = [{new_val_1}, {new_val_2}, ...]
     factor = Decimal('{factor}')
     for i, (o, n) in enumerate(zip(old_vals, new_vals)):
         expected = (Decimal(str(o)) * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
         status = 'OK' if Decimal(str(n)) == expected else 'MISMATCH'
         print(f'  [{i}] {o} × {factor} = {expected} (got {n}) {status}')
     "

6. Verdict:
   - ALL values within tolerance (confirmed by Python) → MATCH
   - ANY value outside tolerance → MISMATCH with detail
```

### Step 3b: Structural Placement Verification (structure_insertion)

For new Case blocks, new If branches, new function calls:

```
1. Verify the new code EXISTS at or near the planned insertion point
   - Allow ±5 lines drift (bottom-to-top execution may shift)

2. Verify INSERTION CONTEXT:
   - What's above the insertion? (expected: the predecessor Case/branch)
   - What's below the insertion? (expected: the successor Case/branch)
   - Is the insertion inside the correct Select Case / If block?

3. Verify CONTENT of inserted code:
   - Does it contain the expected values/assignments?
   - Does it match the planned structure (Case value, condition, etc.)?

4. Verify NO COLLATERAL DAMAGE:
   - Lines above and below the insertion: compare to snapshot
   - Any unexpected modifications → MISMATCH

5. Verdict:
   - Correct location + correct content + no collateral → MATCH
   - Wrong location, wrong content, or collateral damage → MISMATCH
```

### Step 3c: File Creation Verification (file_creation)

For new Code/ file copies with updated .vbproj references:

```
1. Verify new file exists on disk at expected path
2. Verify .vbproj contains <Compile Include> pointing to new file
3. Verify old file is NOT modified (compare to snapshot or expected hash)
4. If file was copied then edited:
   - Run value_editing check (3a) on the edited portions
   - Verify unedited portions match the source file exactly

5. Verdict:
   - File exists + .vbproj updated + source unchanged → MATCH
   - Any missing piece → MISMATCH
```

### Step 3d: Control Flow Verification (flow_modification)

For modified If conditions, added ElseIf branches, changed Select Case logic:

```
1. Read the full function body (before and after)
2. Compare the control flow structure:
   - Same number of branches? (or expected +N new branches)
   - Correct branch modified? (check condition text)
   - No adjacent branches accidentally changed?

3. For condition changes:
   - Old condition → New condition matches plan?
   - No logic inversion? (e.g., < changed to > by mistake)

4. Verdict:
   - Control flow matches plan + no unintended changes → MATCH
   - Wrong branch, inverted logic, or missing branch → MISMATCH
```

### Step 4: Aggregate Results

```
1. Collect all verdicts into verification/semantic_verification.yaml
2. Count: matched, mismatched, skipped
3. For MISMATCHes, classify severity:
   - BLOCKER: Wrong value (not a rounding issue), wrong location,
     wrong branch, missing change
   - WARNING: Rounding discrepancy within ±0.02, minor line drift,
     formatting difference
4. Generate verification/semantic_report.md (human-readable)
```

### Step 5: Return Summary

Return a summary to the orchestrator:

```
SEMANTIC_VERIFIER_COMPLETE:
  Verified: {total} intents
  Matched: {matched}
  Mismatched: {mismatched} ({blockers} BLOCKER, {warnings} WARNING)
  Files: verification/semantic_verification.yaml, verification/semantic_report.md
```

## Edge Cases

### Intent with No Code Change

Some intents may be informational (e.g., "verify DAT file not affected") or may
have been deferred. Skip these with `verdict: "SKIPPED"` and `reason: "no code
change expected"`.

### Multiple Intents on Same Line

When two intents target the same line (e.g., two values in one Array6), verify
each independently. The second intent's "before" state is the FIRST intent's
"after" state — use operations_log ordering to determine sequence.

### Snapshot Missing

If a snapshot file is missing, the Semantic Verifier cannot compare before/after.
Mark as `verdict: "SKIPPED"` with `reason: "snapshot missing — cannot verify"`.

### Value Rounding Ambiguity

When a mismatch is within ±0.02 and the rounding mode is "auto" or "mixed":
- Mark as `verdict: "MISMATCH"` with `severity: "WARNING"`
- Include both possible rounded values in the reasoning
- Suggest: "Verify rounding convention with actuarial team"

### Large Array6 Changes

For Array6 calls with 10+ values, produce a compact summary:
```
Check: 14/14 values match (all within ±0.01)
  Min change: 0.8% (index 3)   Max change: 4.2% (index 11)
```
Only show individual breakdowns for mismatched values.

## NOT the Semantic Verifier's Job

- **Syntax checking** — that's the Python validators' job
- **Diff generation** — that's the Diff agent's job
- **Traceability matrix** — that's the Report agent's job
- **Self-correction** — the Semantic Verifier reports, it doesn't fix. Fixes are
  handled by the rework loop at Gate 5.
- **Editing any files** — the Semantic Verifier is READ-ONLY. It reads code and
  writes only to `verification/semantic_verification.yaml` and
  `verification/semantic_report.md`.

## Key Responsibilities (Summary)

1. Read every intent from intent_graph.yaml
2. For each intent: read before (snapshot) and after (current file)
3. Apply the appropriate verification method (arithmetic, structural, etc.)
4. Produce a reasoning chain showing the check
5. Declare MATCH or MISMATCH with severity
6. Write results to verification/semantic_verification.yaml
7. Write human-readable report to verification/semantic_report.md
8. Return summary to orchestrator

## Worked Examples

### Worked Example 1: Arithmetic Verification (value_editing)

**Scenario:** CR says "increase all home base rates by 5%" (multiplicative factor 1.05).

**Input (from operations_log.yaml):**
```yaml
- operation: "intent-001"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  change_type: "value_editing"
  status: "COMPLETED"
  changes:
    - line: 448
      before: "Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)"
      after:  "Case 1 : varRates = Array6(538.22, 30.17, 486.18, 30.17, 603.86, 30.17, 441.17, 30.17, 139.38)"
```

**Reasoning chain:**
```
Intent: Multiply all values by factor 1.05

Value 1: 512.59 x 1.05 = 538.2195 -> round(2dp) = 538.22   MATCH
Value 2:  28.73 x 1.05 =  30.1665 -> round(2dp) =  30.17   MATCH
Value 3: 463.03 x 1.05 = 486.1815 -> round(2dp) = 486.18   MATCH
Value 4:  28.73 x 1.05 =  30.1665 -> round(2dp) =  30.17   MATCH
Value 5: 575.10 x 1.05 = 603.8550 -> round(2dp) = 603.86   MATCH
Value 6:  28.73 x 1.05 =  30.1665 -> round(2dp) =  30.17   MATCH
Value 7: 420.16 x 1.05 = 441.1680 -> round(2dp) = 441.17   MATCH
Value 8:  28.73 x 1.05 =  30.1665 -> round(2dp) =  30.17   MATCH
Value 9: 132.74 x 1.05 = 139.3770 -> round(2dp) = 139.38   MATCH

Result: 9/9 values match (all within tolerance).
```

**Output:**
```yaml
- intent_id: "intent-001"
  cr_id: "cr-001"
  description: "Multiply territory 1 home base rates by 1.05"
  verdict: "MATCH"
  reasoning: |
    Before (line 448): varRates = Array6(512.59, 28.73, 463.03, ...)
    After  (line 448): varRates = Array6(538.22, 30.17, 486.18, ...)
    Check: 9/9 values scaled by 1.05 within 2dp rounding tolerance.
    All values match.
```

**MISMATCH case** from the same workstream (different territory):
```
Intent: Multiply territory 3 values by 1.05

Value 1: 28.73 x 1.05 = 30.1665 -> round(2dp) = 30.17  expected 30.17, actual 30.02  MISMATCH
  Difference: expected 30.17, got 30.02 (delta = 0.15, exceeds tolerance of 0.01)
```

**Output:**
```yaml
- intent_id: "intent-003"
  cr_id: "cr-001"
  description: "Multiply territory 3 rates by 1.05"
  verdict: "MISMATCH"
  severity: "BLOCKER"
  reasoning: |
    Before (line 456): 28.73
    After  (line 456): 30.02
    Expected: 28.73 x 1.05 = 30.17 (2dp)
    Actual: 30.02 — delta 0.15 exceeds tolerance.
    This is NOT a rounding issue; the value is wrong.
  suggested_action: "Re-run intent-003 with correct factor. Check if 1.044 was used instead of 1.05."
```

### Worked Example 2: Structural Verification (structure_insertion)

**Scenario:** Intent was to add a new Case block for territory "5100" inside the
`GetBaseRate` function's Select Case block, between Case 5000 and Case 6000.

**Input (from intent_graph.yaml):**
```yaml
- intent_id: "intent-008"
  cr_id: "cr-003"
  capability: "structure_insertion"
  target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  function: "GetBaseRate"
  parameters:
    case_value: "5100"
    assignment: "varRates = Array6(512.59, 28.73)"
    insert_after: "Case 5000"
```

**Reasoning chain:**
```
Step 1: Locate insertion in modified file
  Searching GetBaseRate function (lines 400-550) for "Case 5100"...
  Found: Case 5100 at line 478.

Step 2: Verify insertion context
  Line 475: Case 5000 : varRates = Array6(490.22, 27.15, ...)  [predecessor - UNCHANGED from snapshot]
  Line 476: [blank line]
  Line 477: [blank line]
  Line 478: Case 5100 : varRates = Array6(512.59, 28.73)       [NEW - inserted code]
  Line 479: [blank line]
  Line 480: Case 6000 : varRates = Array6(601.33, 33.88, ...)  [successor - UNCHANGED from snapshot]
  Insertion point: correct (between Case 5000 and Case 6000).

Step 3: Verify inserted content
  Case value: "5100" matches intent parameter.          MATCH
  Assignment: "varRates = Array6(512.59, 28.73)"        MATCH
  Variable name "varRates" matches surrounding cases.   MATCH

Step 4: Check for collateral damage
  Compared snapshot lines 400-550 against modified lines (accounting for +3 line insertion).
  All non-inserted lines identical to snapshot.         NO DAMAGE
```

**Output:**
```yaml
- intent_id: "intent-008"
  cr_id: "cr-003"
  description: "Insert new Case 5100 block in GetBaseRate"
  verdict: "MATCH"
  reasoning: |
    Before: No Case 5100 in GetBaseRate (lines 400-550).
    After:  Case 5100 inserted at line 478 between Case 5000 (line 475)
            and Case 6000 (line 480).
    Content: varRates = Array6(512.59, 28.73) matches intent parameters.
    Context: Case 5000 and Case 6000 unchanged (verified against snapshot).
    Collateral: None — all surrounding lines preserved.
```

### Worked Example 3: File Creation Verification (file_creation)

**Scenario:** Intent was to create a new `CalcOption_SKHome20260401.vb` file from the
peer template `CalcOption_SKHome20260101.vb`, then update the .vbproj to reference it.

**Input (from intent_graph.yaml):**
```yaml
- intent_id: "intent-012"
  cr_id: "cr-005"
  capability: "file_creation"
  target_file: "Saskatchewan/Code/CalcOption_SKHome20260401.vb"
  source_template: "Saskatchewan/Code/CalcOption_SKHome20260101.vb"
  vbproj: "Saskatchewan/Home/20260401/Cssi.IntelliQuote.PORTSKHome20260401.vbproj"
```

**Reasoning chain:**
```
Step 1: File exists on disk?
  Path: Saskatchewan/Code/CalcOption_SKHome20260401.vb
  Exists: YES                                                   PASS

Step 2: .vbproj has Compile Include?
  Parsing: Saskatchewan/Home/20260401/Cssi.IntelliQuote.PORTSKHome20260401.vbproj
  Searching for <Compile Include> containing "CalcOption_SKHome20260401.vb"...
  Found: <Compile Include="..\..\Code\CalcOption_SKHome20260401.vb" />
  Reference: PRESENT                                            PASS

Step 3: File contains expected function signatures?
  Template file (20260101) has these Public Functions:
    - CalcOption_SKHome (line 12)
    - GetOptionPremium (line 88)
    - GetOptionDetails (line 145)
  New file (20260401) has:
    - CalcOption_SKHome (line 12)                               MATCH
    - GetOptionPremium (line 88)                                MATCH
    - GetOptionDetails (line 145)                               MATCH
  All 3 function signatures present.                            PASS

Step 4: Date in filename matches target effective date?
  Filename date: 20260401
  Target effective date: 20260401                               MATCH

Step 5: Source template unchanged?
  Snapshot hash of CalcOption_SKHome20260101.vb: sha256:a4f8c2...
  Current hash of CalcOption_SKHome20260101.vb:  sha256:a4f8c2...
  Source template: UNMODIFIED                                   PASS
```

**Output:**
```yaml
- intent_id: "intent-012"
  cr_id: "cr-005"
  description: "Create CalcOption_SKHome20260401.vb from 20260101 template"
  verdict: "MATCH"
  reasoning: |
    File: Saskatchewan/Code/CalcOption_SKHome20260401.vb exists on disk.
    .vbproj: Compile Include entry present in PORTSKHome20260401.vbproj.
    Signatures: All 3 Public Function signatures from template found in new file
                (CalcOption_SKHome, GetOptionPremium, GetOptionDetails).
    Date: Filename date 20260401 matches target effective date.
    Template: Source file CalcOption_SKHome20260101.vb unchanged (hash verified).
```

<!-- IMPLEMENTATION: Phase 12 -->
