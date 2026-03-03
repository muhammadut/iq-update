# Logic Modifier — Edge Cases & Worked Examples
Load this file ONLY when an error condition fires, a special case is detected, or a rework instruction is received.

---

## WORKED EXAMPLES

### Example A: Add ELITECOMP Constant to mod_Common

The simplest Logic Modifier operation: insert a single `Public Const` line after
an existing constant. This is the "hello world" of logic insertion.

**Operation YAML (abbreviated):**

```yaml
id: "op-005-01"
srd: "srd-005"
pattern: "new_coverage_type"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
agent: "logic-modifier"
parameters:
  constant_name: "ELITECOMP"
  constant_type: "String"
  constant_value: '"Elite Comp."'
insertion_point:
  line: 34
  position: "after"
  context: 'After: Public Const NAMEDPERILS As String = "Named Perils"'
  section: "module-level constants (lines 1-60)"
duplicate_check: "ELITECOMP not found -- safe to add"
needs_new_file: false
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
```

**Step 1 -- Validate:** `agent: "logic-modifier"` -- OK. `pattern:
"new_coverage_type"` -- in supported set. `parameters.constant_name` present --
OK.

**Step 3 -- Read target file:** Read `mod_Common_SKHab20260101.vb` into lines
array. CRLF line endings detected.

**Step 4 -- Locate insertion point:**

```
Context: "After: Public Const NAMEDPERILS As String = \"Named Perils\""
Directive: "After:"
Anchor text: 'Public Const NAMEDPERILS As String = "Named Perils"'
Hint line: 34 (0-indexed: 33)

Strategy 1: Check line 33.
  lines[33] = '    Public Const NAMEDPERILS As String = "Named Perils"'
  Contains anchor text? YES
  Match count: 1 (unique)

Result: anchor_idx = 33, position_type = "after"
```

**Step 5a -- Generate constant:**

```
Input:
  constant_name = "ELITECOMP"
  constant_type = "String"
  constant_value = '"Elite Comp."'
  srd = "srd-005"

Generated line:
  '    Public Const ELITECOMP As String = "Elite Comp." 'srd-005'
```

**Step 6 -- Validate generated code:**

- Balanced keywords: no open/close pairs -- OK
- Duplicate check: "ELITECOMP not found" -- safe
- Indentation: 4 spaces -- multiple of 4 -- OK

**Step 7 -- Apply insertion:**

```
position_type = "after"
insert_at = anchor_idx + 1 = 34

Before insertion (lines 32-35):
  32: '    Public Const SINGLELIMIT As String = "Single Limit"'
  33: '    Public Const NAMEDPERILS As String = "Named Perils"'    <- anchor
  34: ''                                                            <- blank line
  35: '    Public Const COMPENHANCED As String = "Enhanced Comp"'

After insertion (lines 32-36):
  32: '    Public Const SINGLELIMIT As String = "Single Limit"'
  33: '    Public Const NAMEDPERILS As String = "Named Perils"'
  34: '    Public Const ELITECOMP As String = "Elite Comp." 'srd-005'  <- NEW
  35: ''
  36: '    Public Const COMPENHANCED As String = "Enhanced Comp"'
```

**Step 8 -- Verify:** Re-read file. Line 34 (0-indexed) matches generated code.
Surrounding lines unchanged.

**Operations log entry:**

```yaml
- operation: "op-005-01"
  agent: "logic-modifier"
  status: "COMPLETED"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  location: "module-level constants (lines 1-60)"
  changes:
    - line: 35
      description: "Add ELITECOMP constant after NAMEDPERILS"
      before: null
      after: "    Public Const ELITECOMP As String = \"Elite Comp.\" 'srd-005"
      change_type: "insert"
  summary:
    lines_added: 1
    lines_modified: 0
    lines_removed: 0
    started_at: "2026-01-15T11:05:05Z"
    completed_at: "2026-01-15T11:05:06Z"
```

---

### Example B: Add Rate Table Routing Case Block Inside Nested Select Case

The most complex common operation. Insert a Case block with a nested Select Case
for classification routing inside GetBasePremium_Home. Requires correct
indentation measurement and bottom-to-top awareness for same-file interaction
with the constant insertion (Example A).

**Operation YAML (abbreviated):**

```yaml
id: "op-005-02"
srd: "srd-005"
pattern: "new_coverage_type"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
agent: "logic-modifier"
parameters:
  constant_name: "ELITECOMP"
  case_block_type: "rate_table_routing"
  classifications:
    - name: "STANDARD"
      dat_constant: "DAT_Home_EliteComp_Standard"
    - name: "PREFERRED"
      dat_constant: "DAT_Home_EliteComp_Preferred"
insertion_point:
  line: 3463
  position: "before_end_select"
  context: "Inside: Select Case objInscoCovItem.Fields.Item(...).Value (line 3442)"
  end_select_line: 3463
function: "GetBasePremium_Home"
function_line_start: 3400
function_line_end: 3500
duplicate_check: "Case ELITECOMP not found in Select Case -- safe to add"
needs_new_file: false
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
```

**Bottom-to-top ordering:** This operation targets line 3463 (inside
GetBasePremium_Home), while op-005-01 targets line 34 (module-level constant).
The execution plan orders op-005-02 FIRST because 3463 > 34.

After op-005-01 inserts 1 line at position 34, all line numbers after 34 shift by
+1. But op-005-02 already ran before op-005-01 (bottom-to-top), so there is no
drift.

**Step 4 -- Locate insertion point:**

```
Context: "Inside: Select Case objInscoCovItem.Fields.Item(...).Value (line 3442)"
Directive: "Inside:"
Anchor text: "Select Case objInscoCovItem.Fields.Item(...).Value"
Position: "before_end_select"

Strategy 1: Check hint line 3442 (0-indexed: 3441).
  lines[3441] contains "Select Case objInscoCovItem.Fields.Item"? YES
  Match count: verify uniqueness... 1 match in file -- OK

Now find End Select for this Select Case:
  end_select_line hint: 3463 (0-indexed: 3462)
  lines[3462].strip() = "End Select"? YES

Result: insert_idx = 3462, position_type = "before_end_select"
```

**Step 5b -- Generate Case block:**

```
Measure indentation from existing Cases:
  Scan backward from End Select (line 3462):
    lines[3461]: "                        End Select"    <- 24 spaces (inner End Select)
    lines[3460]: "                            Case PREFERRED..."  <- 28 spaces
    ...
    lines[3457]: "                    Case COMPENHANCED"  <- 20 spaces  <- THIS IS A CASE LINE

  case_indent = "                    " (20 spaces)
  body_indent = "                        " (24 spaces)
  nested_case_indent = "                            " (28 spaces)

Generated lines:
  "                    Case ELITECOMP 'srd-005"
  "                        Select Case strClassification"
  "                            Case STANDARD : intFileID = DAT_Home_EliteComp_Standard"
  "                            Case PREFERRED : intFileID = DAT_Home_EliteComp_Preferred"
  "                        End Select"
```

**Step 6 -- Validate:**

- Select Case / End Select: 1 open, 1 close -- balanced
- Duplicate: "Case ELITECOMP not found" -- safe
- Indentation: 20, 24, 28, 28, 24 -- all multiples of 4 -- OK

**Step 7 -- Apply insertion:**

```
position_type = "before_end_select"
insert_at = 3462 (the End Select line)

Before insertion (lines 3460-3463, 0-indexed):
  3460: "                            Case PREFERRED : intFileID = DAT_Home_EliteComp_Preferred"
  3461: "                        End Select"
  3462: "                End Select"   <- outer End Select (insertion BEFORE here)

Wait -- re-examining. The End Select at 3462 is the OUTER End Select (16 spaces).
The preceding lines have inner End Select at 3461 (24 spaces). The Case blocks
(COMPENHANCED, BROADESSENTIALS, etc.) are at 20 spaces.

After insertion (5 new lines inserted at index 3462):
  3460: "                            Case PREFERRED : intFileID = ..."
  3461: "                        End Select"
  3462: "                    Case ELITECOMP 'srd-005"                       <- NEW
  3463: "                        Select Case strClassification"             <- NEW
  3464: "                            Case STANDARD : intFileID = DAT_..."   <- NEW
  3465: "                            Case PREFERRED : intFileID = DAT_..."  <- NEW
  3466: "                        End Select"                                <- NEW
  3467: "                End Select"
```

**Operations log entry:**

```yaml
- operation: "op-005-02"
  agent: "logic-modifier"
  status: "COMPLETED"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  function: "GetBasePremium_Home"
  changes:
    - line: 3463
      description: "Add Elite Comp rate table Case block with STANDARD/PREFERRED routing"
      before: null
      after: |
        Case ELITECOMP 'srd-005
            Select Case strClassification
                Case STANDARD : intFileID = DAT_Home_EliteComp_Standard
                Case PREFERRED : intFileID = DAT_Home_EliteComp_Preferred
            End Select
      change_type: "insert"
  summary:
    lines_added: 5
    lines_modified: 0
    lines_removed: 0
    started_at: "2026-01-15T11:05:07Z"
    completed_at: "2026-01-15T11:05:08Z"
```

---

### Example C: Create New Option_Bicycle File from Template

A `needs_new_file: true` operation that creates a new endorsement handler from
an existing template, then adds the `<Compile Include>` entry to the .vbproj.

**Operation YAML (abbreviated):**

```yaml
id: "op-007-01"
srd: "srd-007"
pattern: "new_endorsement_flat"
file: "Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb"
agent: "logic-modifier"
parameters:
  endorsement_name: "Bicycle"
  province_code: "SK"
  lob: "Home"
  effective_date: "20260101"
  premium_structure: "flat"
  coverage_options:
    - label: "A"
      premium: 25
    - label: "B"
      premium: 50
needs_new_file: true
template_reference:
  file: "Saskatchewan/Code/Option_IdentityTheft_SKHome20250901.vb"
  file_hash: "sha256:template123..."
target_file: "Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb"
vbproj_target: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
```

**Step 1 -- Validate:** Pattern `new_endorsement_flat` -- OK. `needs_new_file:
true` -- OK. Required fields present.

**Step 3 -- Read target file:** `needs_new_file` is true -- skip to Step 9.

**Step 9 -- Create new file:**

Read template `Option_IdentityTheft_SKHome20250901.vb`:

```vb
Partial Public Module modOption_IdentityTheft
    'Attribute VB_Name = "modOption_IdentityTheft"
    'Option Explicit
    Function Option_IdentityTheft() As Short
        Dim intPrem As Short
        Dim msg As String = String.Empty
        ...
        intPrem = 35
        ...
        Option_IdentityTheft = intPrem
    End Function

End Module
```

Extract template name: `"IdentityTheft"` (from `modOption_IdentityTheft`).

Apply transformations:
- `modOption_IdentityTheft` -> `modOption_Bicycle`
- `Option_IdentityTheft` -> `Option_Bicycle` (function name + return line)
- `"modOption_IdentityTheft"` -> `"modOption_Bicycle"` (VB_Name attribute)

Result after transformation:

```vb
Partial Public Module modOption_Bicycle
    'srd-007
    'Attribute VB_Name = "modOption_Bicycle"
    'Option Explicit
    Function Option_Bicycle() As Short
        Dim intPrem As Short
        Dim msg As String = String.Empty
        ...
        intPrem = 25
        ...
        Option_Bicycle = intPrem
    End Function

End Module
```

Note: No `Imports` statement (Option files do not use Imports). Premium value
replaced from 35 to 25 (first coverage option). The multi-option Select Case for
labels A/B would be handled during template structure review.

Write to `Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb`.

**Step 10 -- Update .vbproj:**

Read `Cssi.IntelliQuote.PORTSKHOME20260101.vbproj`. Find the ItemGroup containing
other `Option_*` Compile Include entries.

Check idempotency: `..\..\Code\Option_Bicycle_SKHome20260101.vb` not present.

Insert before `</ItemGroup>`:

```xml
		<Compile Include="..\..\Code\Option_Bicycle_SKHome20260101.vb"/>
```

Tab indentation (2 tabs) matches existing entries.

**Operations log entry:**

```yaml
- operation: "op-007-01"
  agent: "logic-modifier"
  status: "COMPLETED"
  file: "Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb"
  function: "Option_Bicycle"
  changes:
    - line: 0
      description: "Created new Option file from template Option_IdentityTheft"
      before: null
      after: "(new file -- 15 lines)"
      change_type: "insert"
  summary:
    lines_added: 15
    lines_modified: 0
    lines_removed: 0
    new_file_created: true
    vbproj_updated: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
    started_at: "2026-01-15T11:05:11Z"
    completed_at: "2026-01-15T11:05:12Z"
```

---

## SPECIAL CASES

### 1. Duplicate Detected

**Trigger:** The `duplicate_check` field from the Analyzer indicates the constant,
function, or Case block already exists, OR the Logic Modifier discovers a duplicate
during Step 6 validation.

**Action:** Return `SKIPPED` status. Do NOT insert anything.

```yaml
status: "SKIPPED"
error: "DUPLICATE_DETECTED: Public Const ELITECOMP already exists at line 35. "
       "No insertion performed."
```

**When this happens:** A previous partial execution already applied this operation,
or the file was manually edited. SKIPPED is NOT an error -- it is safe and
expected during re-execution.

### 2. Content Mismatch

**Trigger:** The anchor text from `insertion_point.context` is not found anywhere
in the file after all three search strategies (hint, +/-20, full scan).

**Action:** ABORT with `CONTENT_MISMATCH` error. Do NOT attempt fuzzy matching.

```yaml
status: "FAILED"
error: "CONTENT_MISMATCH: Anchor text not found in file.\n"
       "  Anchor: Public Const STANDARD As String = \"Standard\"\n"
       "  Hint line: 22\n"
       "  File may have been manually edited since analysis."
recovery: "Re-run /iq-plan to regenerate analysis with current file state."
```

### 3. Template Not Found

**Trigger:** `needs_new_file: true` but `template_reference.file` does not exist
on disk.

**Action:** ABORT with `FILE_NOT_FOUND` error. Flag for developer intervention.

```yaml
status: "FAILED"
error: "FILE_NOT_FOUND: Template file does not exist: "
       "Saskatchewan/Code/Option_IdentityTheft_SKHome20250901.vb. "
       "Developer must provide a valid template or create the file manually."
recovery: "Verify template path in the operation YAML. "
          "If the template was renamed or moved, update the plan."
```

### 4. Cross-Province Shared File

**Trigger:** The target file path contains a cross-province reference (a file
listed in `config.yaml["cross_province_shared_files"]`, e.g., `Code/PORTCommonHeat.vb`
for Portage Mutual -- located in the top-level Code/ directory, not a province's
Code/ directory).

**Action:** REFUSE the operation. Log `CROSS_PROVINCE_VIOLATION`.

```yaml
status: "FAILED"
error: "CROSS_PROVINCE_VIOLATION: Target file '{target_file}' is a "
       "cross-province shared file (per config.yaml cross_province_shared_files). "
       "The Logic Modifier NEVER modifies these files. "
       "This must be handled manually by the developer."
recovery: "Remove this operation from the plan or flag for manual handling."
```

**Detection:** Check if the target file path starts with `Code/` (top-level) rather
than `{Province}/Code/`. Cross-province files affect ALL provinces and require
manual coordination.

### 5. Multiple Valid Insertion Points

**Trigger:** The anchor text matches more than one line in the file (Step 4 returns
AMBIGUOUS_ANCHOR).

**Action:** ABORT. Do NOT guess which match is correct.

```yaml
status: "FAILED"
error: "AMBIGUOUS_ANCHOR: Found 3 matches for anchor text.\n"
       "  Anchor: Select Case strClassification\n"
       "  Matches at lines: [405, 1220, 3115]\n"
       "  Cannot determine correct insertion point."
recovery: "The Analyzer should provide a more specific anchor. "
          "Re-run /iq-plan with narrower context."
```

**Why this matters:** `Select Case strClassification` appears in multiple functions
within mod_Common. The Analyzer should provide a function-scoped context (e.g.,
`"Inside: Select Case strClassification"` with `function: "GetBasePremium_Home"`
and `function_line_start/end`). If the context is insufficient, the operation
must fail rather than insert code in the wrong location.

### 6. Empty Case Block at Insertion Point

**Trigger:** The Case block immediately before the insertion point has no body
(e.g., `Case 500000` with no statements, as seen in Liab_RentedDwelling_Home).

**Action:** Handle correctly -- insert the new Case block as a sibling, not inside
the empty Case.

```
Existing code:
                Case 500000          <- empty Case (no body)
                Case 1000000
                    intPrem = 18
                End Select

New Case insertion (before End Select):
                Case 500000
                Case 1000000
                    intPrem = 18
                Case 3000000         <- NEW (inserted before End Select)
                    intPrem = 24
                End Select
```

**In VB.NET, empty Case blocks do NOT fall through** (unlike C/C++). `Case
500000` simply does nothing and exits the Select Case. The Logic Modifier must
recognize empty Cases as valid syntax and insert the new Case at the correct
position (before End Select) without attempting to merge with or attach to the
empty Case.

---

## 10. Error Handling

### CONTENT_MISMATCH -- Anchor Line Not Found

**Trigger:** The `insertion_point.context` anchor text cannot be found in the
target file. All three search strategies failed:
1. Hint line number -- exact line does not contain the anchor text
2. Window search -- +/-20 lines around the hint contain no match
3. Full scan -- no line in the entire file matches the stripped anchor

**Action:** ABORT the operation. Log as FAILED.

```yaml
- operation: "op-003-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "CONTENT_MISMATCH: Anchor line not found in CalcOption_SKHome20260101.vb. "
         "Expected: 'End Select  '' Deductible' near line 412. "
         "All 3 search strategies exhausted."
  recovery: "Re-run /iq-plan to regenerate analysis with current file state."
```

### AMBIGUOUS_ANCHOR -- Multiple Lines Match

**Trigger:** The stripped anchor text matches more than one line in the target
file. The Logic Modifier cannot determine which match is the correct insertion
point.

**Action:** ABORT the operation. Log as FAILED with all match locations.

```yaml
- operation: "op-003-02"
  agent: "logic-modifier"
  status: "FAILED"
  error: "AMBIGUOUS_ANCHOR: 3 lines match 'End Select' in mod_Common_SKHab20260101.vb "
         "at lines 418, 592, 1034. Cannot determine correct insertion point."
  recovery: "Analyzer must provide a more specific anchor (include trailing comment or "
            "adjacent lines) and re-run /iq-plan."
```

### DUPLICATE_DETECTED -- Code Already Exists

**Trigger:** The `duplicate_check` field indicates the target already exists, OR
the Logic Modifier's own pre-insertion scan finds:
- A Const with the same name and value
- A Function/Sub with the same signature
- A Case block with the same case value in the same Select Case

**Action:** Log as SKIPPED. This is safe and expected during re-execution.

```yaml
- operation: "op-004-01"
  agent: "logic-modifier"
  status: "SKIPPED"
  reason: "DUPLICATE_DETECTED: Case 3000000 already exists in Select Case at line 418 "
          "of Liab_RentedDwelling_Home_SKHome20260101.vb. No insertion needed."
```

### FILE_NOT_FOUND -- Target File Missing

**Trigger:** `needs_new_file: false` in the operation YAML, but the target file
does not exist on disk. The file-copier should have created it in a prior step.

**Action:** ABORT. Log as FAILED.

```yaml
- operation: "op-005-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "FILE_NOT_FOUND: CalcOption_SKHome20260101.vb does not exist. "
         "Expected file-copier to have created it (needs_new_file: false)."
  recovery: "Verify file-copier completed successfully. Re-run /iq-execute if needed."
```

### TEMPLATE_NOT_FOUND -- Template Reference Missing

**Trigger:** `needs_new_file: true` and the operation references a
`template_reference.file` that does not exist on disk.

**Action:** ABORT. Log as FAILED. Flag for developer.

```yaml
- operation: "op-006-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "TEMPLATE_NOT_FOUND: Template file Option_WaterDamage_SKHome20250601.vb "
         "does not exist at SK/Code/Option_WaterDamage_SKHome20250601.vb."
  recovery: "Developer must verify the template path in the plan. The referenced file "
            "may have been renamed or moved."
```

### CROSS_PROVINCE_VIOLATION -- Shared File Targeted

**Trigger:** The target file path matches a cross-province shared file pattern:
- `Code/PORTCommon*.vb` (at the root Code/ level)
- `Code/mod_VICC*.vb` (at the root Code/ level)
- Any file path outside the target province's `{Province}/Code/` directory

**Action:** REFUSE the operation. Log as FAILED.

```yaml
- operation: "op-007-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "CROSS_PROVINCE_VIOLATION: Target file '{target_file}' is a "
         "cross-province shared module (per config.yaml cross_province_shared_files). "
         "Automated modification is prohibited."
  recovery: "Developer must apply this change manually."
```

### VBPROJ_PARSE_ERROR -- Cannot Parse Project File

**Trigger:** The .vbproj file cannot be parsed as valid XML when the Logic
Modifier attempts to add a new `<Compile Include>` entry.

**Action:** ABORT. Log as FAILED.

```yaml
- operation: "op-008-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "VBPROJ_PARSE_ERROR: Failed to parse "
         "Cssi.IntelliQuote.PORTSKHome20260101.vbproj as XML. "
         "Malformed element at line 47."
  recovery: "Developer must inspect and fix the .vbproj manually, then re-run."
```

### UNKNOWN_PATTERN -- Unsupported Operation Pattern

**Trigger:** The operation YAML contains a `pattern` value not in the supported
set: `{new_coverage_type, new_endorsement_flat, new_liability_option,
eligibility_rules, alert_message}`.

**Action:** ABORT. Log as FAILED.

```yaml
- operation: "op-009-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "UNKNOWN_PATTERN: 'base_rate_increase' is not supported by the Logic Modifier. "
         "Supported: new_coverage_type, new_endorsement_flat, new_liability_option, "
         "eligibility_rules, alert_message. This operation should be routed to Rate Modifier."
```

This indicates a pipeline misconfiguration -- the Decomposer assigned the wrong
agent type for this operation.

### KEYWORD_IMBALANCE -- Generated Code Has Unmatched Keywords

**Trigger:** Step 6 (structural validation) detects that the generated VB.NET code
has unmatched keyword pairs:
- `Function` without `End Function`
- `Sub` without `End Sub`
- `If` without `End If` (multi-line If blocks)
- `Select Case` without `End Select`
- `For` without `Next`

**Action:** Re-generate the code block once with explicit keyword-balancing
instructions. If the second attempt still has imbalanced keywords: ABORT, log
as FAILED.

```yaml
- operation: "op-010-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "KEYWORD_IMBALANCE: Generated code for SetDiscount_WaterDamage has "
         "'Select Case' without matching 'End Select' after 2 generation attempts."
  recovery: "Developer must write this function manually or provide a more complete "
            "template reference."
```

### Rework Protocol

**Trigger:** The execution-reviewer (within /iq-execute) finds an issue with a
completed Logic Modifier operation and sends a rework instruction.

**Rework message format:**

```
execution-reviewer -> modifier: "REWORK: {op_id, issue, fix_instruction}"
```

**Process:**
1. The modifier-agent receives the rework message
2. It re-dispatches to the Logic Modifier with the ORIGINAL operation YAML plus
   the `fix_instruction` as an additional constraint
3. The Logic Modifier re-executes from Step 3 (re-read file) through Step 10
   (verify insertion)
4. The `fix_instruction` may specify constraints such as:
   - "Use 4-space indentation instead of tab"
   - "Add Case Else before End Select"
   - "Include trailing comment matching adjacent Cases"
5. Maximum **2 rework attempts** per operation

**After 2 failed rework attempts:**

```yaml
- operation: "op-003-01"
  agent: "logic-modifier"
  status: "FAILED"
  error: "PERSISTENT_FAILURE: Rework failed after 2 attempts. "
         "Issue: Generated Case block missing Case Else. "
         "Last fix attempted: Add Case Else with default value 0."
  recovery: "Manual developer intervention required."
```

The modifier-agent escalates `PERSISTENT_FAILURE` to the /iq-execute orchestrator,
which halts execution and reports to the developer.

---

## 11. NOT YET IMPLEMENTED (Future Enhancements)

1. **Auto-detect naming convention from context** -- Currently requires the
   Analyzer to provide exact function/constant naming in the operation YAML.
   Future versions could scan nearby functions in the same file to infer naming
   patterns (e.g., `SetDiscount_` prefix vs `SetDisSur_` prefix) and validate
   that the plan-specified name follows the local convention.

2. **Multi-function generation** -- Currently handles one function per operation.
   Future versions could generate related function groups in a single operation
   (e.g., `SetDefaults_WaterDamage` + `ValidateData_WaterDamage` +
   `CalcMain` routing entry), ensuring internal consistency across the group.

3. **Template library** -- Currently uses a single `template_reference` file per
   operation. Future versions could maintain a curated template library organized
   by operation type and province, with best-practice patterns extracted from
   the existing codebase. This would reduce reliance on the Analyzer finding a
   suitable existing file to use as a template.

4. **Inline diff preview** -- Before inserting generated code, produce a colored
   diff preview showing the file before and after, and present it to the developer
   for confirmation. Currently the developer approves at Gate 1 (plan level) and
   Gate 2 (review level), but does not see individual insertions during execution.

5. **Cross-file consistency validation** -- Verify that a new constant added to
   `mod_Common` is properly referenced in `CalcMain`, `ResourceID`, and
   `CalcOption`. Currently each operation is validated independently; future
   versions could perform cross-operation verification within the same workstream
   to catch missing linkages.

6. **Intelligent Case ordering** -- Currently inserts new Case blocks immediately
   before `End Select` (the safe default). Future versions could analyze existing
   Case values (numeric, alphabetical, logical grouping) and insert new Cases
   in the ordering that matches the existing pattern, rather than always appending
   at the end.

7. **Function dependency graph** -- When generating a new function that calls other
   functions in the same file, verify that all callees exist. Currently this check
   is limited to what the Analyzer provides; future versions could build a
   lightweight call graph from the target file to detect missing dependencies.

---

<!-- IMPLEMENTATION: Phase 08 -->
