# Logic Modifier Agent — Core Contract
This file defines the universal rules for all logic modification operations. Workers always load this file.

## Purpose

Handle structural code changes -- new constants, new functions, new conditionals,
new Select Case blocks, guard clauses, alert messages, eligibility rules, and new
source files (Option_*.vb, Liab_*.vb). This agent understands VB.NET control flow
and code structure, unlike the Rate Modifier which only does value substitution.

The Logic Modifier is the **ARCHITECT** of the pipeline. It generates syntactically
correct VB.NET code that integrates cleanly with the existing codebase. Every
insertion must compile, follow existing conventions exactly, and be traceable back
to the SRD that requested it. Unlike the Rate Modifier (which replaces values on
existing lines), the Logic Modifier INSERTS new lines -- which means bottom-to-top
execution is not just a convention but a hard requirement to prevent index drift.

**Dispatch model:** The `/iq-execute` orchestrator launches a modifier-agent that
reads `plan/execution_order.yaml` and processes operations in sequence. For each
operation tagged `agent: "logic-modifier"`, the modifier-agent loads THIS file and
follows these instructions. The modifier-agent handles snapshots, TOCTOU checks,
hash updates, and operation logging. This file focuses on **locating insertion
points**, **generating VB.NET code**, and **applying insertions**.

**File copies are NOT this agent's responsibility.** The file-copier-agent runs
BEFORE the modifier-agent and handles all file copies and .vbproj reference
updates. By the time the Logic Modifier starts, every target file MUST already
exist on disk. If a target file is missing, ABORT the operation.

**EXCEPTION: New source files.** For operations with `needs_new_file: true`
(Option_*.vb, Liab_*.vb), the Logic Modifier creates these files ITSELF because
they require structural understanding to generate from a template. The file-copier
does NOT handle these. After creating a new file, the Logic Modifier also adds the
corresponding `<Compile Include>` entry to the .vbproj.

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
- **Parallel:** Rate Modifier (may run in parallel ONLY on **different files**;
  same-file operations are always sequential, bottom-to-top by line number)
- **Dispatch:** The modifier-agent reads `agent: "logic-modifier"` from each
  operation YAML and loads this file for execution instructions

---

## Output Schema

### execution/operations_log.yaml

The modifier-agent appends one entry per completed operation. The Logic Modifier
provides the data; the modifier-agent writes the YAML.

```yaml
operations:
  - operation: "op-005-01"
    agent: "logic-modifier"
    status: "COMPLETED"              # COMPLETED | FAILED | SKIPPED
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    location: "module-level constants"
    changes:
      - line: 23
        description: "Add ELITECOMP constant after STANDARD"
        before: null                 # null = pure insertion (no line replaced)
        after: "    Public Const ELITECOMP As String = \"Elite Comp.\""
        change_type: "insert"        # insert | replace
    summary:
      lines_added: 1
      lines_modified: 0
      lines_removed: 0
      started_at: "2026-01-15T11:05:05Z"
      completed_at: "2026-01-15T11:05:06Z"

  - operation: "op-005-02"
    agent: "logic-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    function: "GetRateTableID"
    changes:
      - line: 440
        description: "Add Elite Comp rate table Case block"
        before: null
        after: |
            Case ELITECOMP
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

  - operation: "op-006-01"
    agent: "logic-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Home/20260101/ResourceID.vb"
    location: "module-level constants"
    changes:
      - line: 146
        description: "Add DAT IDs for Elite Comp"
        before: null
        after: |
            Public Const DAT_Home_EliteComp_Preferred = 9501
            Public Const DAT_Home_EliteComp_Standard = 9502
        change_type: "insert"
    summary:
      lines_added: 2
      lines_modified: 0
      lines_removed: 0
      started_at: "2026-01-15T11:05:09Z"
      completed_at: "2026-01-15T11:05:10Z"

  - operation: "op-007-01"
    agent: "logic-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb"
    function: "CalcOption_Bicycle"
    changes:
      - line: 0
        description: "Created new Option file from template"
        before: null
        after: "(new file -- 15 lines)"
        change_type: "insert"
    summary:
      lines_added: 15
      lines_modified: 0
      lines_removed: 0
      new_file_created: true
      vbproj_updated: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHome20260101.vbproj"
      started_at: "2026-01-15T11:05:11Z"
      completed_at: "2026-01-15T11:05:12Z"
```

**Field reference for operations_log.yaml:**

| Field | Type | Description |
|-------|------|-------------|
| `operation` | string | Operation ID (matches op YAML filename) |
| `agent` | string | Always `"logic-modifier"` for this agent |
| `status` | string | `COMPLETED`, `FAILED`, or `SKIPPED` |
| `file` | string | Target file path (relative to carrier root) |
| `function` | string/null | Function name (null for module-level ops) |
| `location` | string | Human-readable location (for module-level ops) |
| `changes[]` | list | One entry per insertion point |
| `changes[].line` | int | Line number where insertion was made (after) |
| `changes[].description` | string | Human-readable description of change |
| `changes[].before` | null/string | `null` for pure insertions |
| `changes[].after` | string | Code that was inserted (may be multi-line via `|`) |
| `changes[].change_type` | string | `"insert"` for new code, `"replace"` for rare edits |
| `summary.lines_added` | int | Total new lines inserted |
| `summary.lines_modified` | int | Lines changed in place (rare for Logic Modifier) |
| `summary.lines_removed` | int | Lines deleted (rare for Logic Modifier) |
| `summary.new_file_created` | bool | True if this op created a new file |
| `summary.vbproj_updated` | string | .vbproj path if Compile Include was added |
| `summary.started_at` | string | ISO 8601 timestamp |
| `summary.completed_at` | string | ISO 8601 timestamp |

**Status values:**

- `COMPLETED` -- Code inserted successfully, verification passed
- `FAILED` -- Insertion could not be performed (content mismatch, TOCTOU, etc.)
- `SKIPPED` -- Code already exists at target location (duplicate detected)

### What the Reviewer Validates Downstream

The /iq-review Reviewer reads operations_log.yaml and the modified source files.
These are the specific validators that check Logic Modifier output:

| Validator | What It Checks |
|-----------|---------------|
| `validate_syntax` | Generated code compiles (matching parens, End Function/Sub, correct keywords) |
| `validate_indentation` | Inserted code uses 4 spaces per level, matching surrounding code |
| `validate_duplicates` | No duplicate constants, function names, or Case blocks introduced |
| `validate_no_old_modify` | Only target-date files were edited (never old Code/ files) |
| `validate_vbproj` | New files have corresponding `<Compile Include>` entries |
| `validate_traceability` | SRD comments present on generated code |

---

## EXECUTION STEPS

### Step 1: Validate Operation

Check that the operation YAML is well-formed and intended for this agent before
doing any file I/O.

```python
SUPPORTED_PATTERNS = {
    "new_coverage_type",
    "new_endorsement_flat",
    "new_liability_option",
    "eligibility_rules",
    "alert_message",
}

def validate_operation(op):
    """Validate operation YAML before processing."""
    if op.get("agent") != "logic-modifier":
        return FAIL(f"Wrong agent: {op.get('agent')} (expected logic-modifier)")

    if op["pattern"] not in SUPPORTED_PATTERNS:
        return FAIL(f"Unknown pattern: {op['pattern']}")

    required = ["id", "file", "agent", "pattern", "parameters",
                 "target_file", "insertion_point"]
    for field in required:
        if field not in op:
            return FAIL(f"Missing required field: {field}")

    # Pattern-specific field checks
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

    return OK
```

**On validation failure:** Report `FAILED` status with the validation error in the
operations log. Do NOT proceed to subsequent steps.

### Step 2: Read Operation YAML

Load all fields from the operation YAML file into a working dictionary. Parse
sub-structures into typed values for downstream steps.

```python
def read_operation(op):
    """Parse operation YAML into working dictionary."""
    work = {
        "id":           op["id"],
        "srd":          op.get("srd", "unknown"),
        "pattern":      op["pattern"],
        "target_file":  op["target_file"],
        "parameters":   op["parameters"],
        "needs_new_file": op.get("needs_new_file", False),
        "template_ref": op.get("template_reference"),
        "insertion_point": op.get("insertion_point", {}),
        "duplicate_check": op.get("duplicate_check", ""),
        "vbproj_target": op.get("vbproj_target"),
        "function":     op.get("function"),
        "function_line_start": op.get("function_line_start"),
        "function_line_end":   op.get("function_line_end"),
        "existing_cases":      op.get("existing_cases", []),
        "existing_constants":  op.get("existing_constants", []),
        "existing_functions":  op.get("existing_functions", []),
        "code_patterns": op.get("code_patterns", {}),  # From Analyzer Step 5.9
        # --- Context Engineering Level 2 fields ---
        "fub":            op.get("fub"),                # From Analyzer Step 5.10 (via capsule)
        "tier":           op.get("tier", 2),            # From Planner Step 9.5 (default: 2)
        "peer_bodies":    op.get("peer_function_bodies", []),  # Tier 3 only
        "cross_file_ctx": op.get("cross_file_context", []),    # Tier 3 only
    }
    return work
```

### Step 3: Read Target File

If `needs_new_file` is false, the target file must already exist on disk (created
by the file-copier-agent). Read it into a lines array. If `needs_new_file` is
true, skip to Step 9 (New File Creation).

```python
def read_target_file(target_path, needs_new_file):
    """Read target file into lines array. Skip if creating a new file."""
    if needs_new_file:
        return None, None    # Handled in Step 9

    if not os.path.exists(target_path):
        return FAIL(f"Target file does not exist: {target_path}. "
                     "The file-copier-agent should have created it.")

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
would create massive diffs in SVN.

### Step 4: Locate Insertion Point

This is the most critical step. The Logic Modifier uses `insertion_point.context`
as the **authoritative** anchor and `insertion_point.line` as a **hint**. Line
numbers drift when preceding operations add or remove lines, so content matching
is mandatory.

**FUB Pre-Validation (Level 2 enhancement):**

Before running the anchor search, if `fub.adjacent_context` is available (Tier 2/3
capsules), use it as a quick confidence check that the file hasn't shifted since
analysis:

```python
def fub_pre_validate(lines, work):
    """Use FUB adjacent_context to validate file hasn't shifted.

    If adjacent lines match near the expected insertion point, confirms the
    Analyzer's line references are still accurate. If they DON'T match,
    fall through to the standard content-based anchor search (no abort).

    Returns: True if validated (or no FUB), False if mismatch detected.
    """
    fub = work.get("fub")
    if not fub or not fub.get("adjacent_context"):
        return True  # No FUB — skip pre-validation, proceed normally

    adj = fub["adjacent_context"]
    hint_line = work.get("insertion_point", {}).get("line", 0)
    search_radius = 10  # Allow ±10 lines drift from hint

    matches = 0
    checks = 0
    for entry in adj.get("above", []) + adj.get("below", []):
        checks += 1
        expected_content = entry["content"].strip()
        expected_line = entry["line"]

        # Search near the expected location
        for ln_idx in range(max(0, expected_line - search_radius - 1),
                            min(len(lines), expected_line + search_radius)):
            if lines[ln_idx].strip() == expected_content:
                matches += 1
                break

    if checks > 0 and matches == checks:
        return True   # All adjacent lines found — high confidence
    elif checks > 0 and matches >= checks // 2:
        return True   # Partial match — proceed with caution
    else:
        return False  # Mismatch — anchor search will handle it
```

If `fub_pre_validate` returns `False`, log a note but do NOT abort. The standard
content-based anchor search in the algorithm below will find the correct position
regardless. The pre-validation is a **speed optimization and confidence signal**,
not a gate.

**Context directive formats:**
- `"After: Public Const STANDARD As String = \"Standard\""` -- insert after this line
- `"Inside: Select Case strCoverageType (line 405)"` -- context for Case block insertion
- `"Before: End Function  ' ValidateData_EliteComp"` -- insert before this line

**Algorithm:**

```python
import re

def locate_insertion_point(lines, insertion_point):
    """Find the insertion position using content-based anchor matching.

    Args:
        lines: list of file lines (0-indexed)
        insertion_point: dict with keys: line, position, context, section,
                         and optionally end_select_line

    Returns: (insert_idx, position_type) where insert_idx is the 0-indexed
             line index for the anchor, and position_type is "after",
             "before_end_select", or "before_end_function".
    """
    context = insertion_point["context"]
    hint_line = insertion_point.get("line", 0)
    position = insertion_point["position"]
    hint_idx = max(0, hint_line - 1)    # Convert 1-indexed to 0-indexed

    # Parse directive prefix from context
    # "After: <content>", "Before: <content>", "Inside: <content>"
    anchor_text = context
    for prefix in ("After:", "Before:", "Inside:"):
        if context.startswith(prefix):
            anchor_text = context[len(prefix):].strip()
            break

    # Strip trailing parenthetical hints like "(line 405)"
    anchor_text = re.sub(r'\s*\(line \d+\)\s*$', '', anchor_text)

    # Search strategy: hint -> +/-20 lines -> full file -> ABORT
    match_indices = []

    # Strategy 1: Check exact hint position
    if 0 <= hint_idx < len(lines):
        if anchor_text in lines[hint_idx].rstrip():
            match_indices.append(hint_idx)

    # Strategy 2: Search +/- 20 lines from hint
    if not match_indices:
        lo = max(0, hint_idx - 20)
        hi = min(len(lines), hint_idx + 21)
        for i in range(lo, hi):
            if anchor_text in lines[i].rstrip():
                match_indices.append(i)

    # Strategy 3: Full file scan
    if not match_indices:
        for i in range(len(lines)):
            if anchor_text in lines[i].rstrip():
                match_indices.append(i)

    # No match at all
    if not match_indices:
        return FAIL(
            f"CONTENT_MISMATCH: Anchor text not found in file.\n"
            f"  Anchor: {anchor_text}\n"
            f"  Hint line: {hint_line}"
        )

    # Multiple matches -> ambiguous
    if len(match_indices) > 1:
        return FAIL(
            f"AMBIGUOUS_ANCHOR: Found {len(match_indices)} matches for anchor.\n"
            f"  Anchor: {anchor_text}\n"
            f"  Matches at lines: {[i+1 for i in match_indices]}"
        )

    anchor_idx = match_indices[0]

    # For "before_end_select" position, find the End Select after the anchor.
    # CRITICAL: If a `Case Else` exists BEFORE `End Select`, insert BEFORE
    # the `Case Else` instead. Inserting AFTER `Case Else` creates dead code
    # because `Case Else` catches all unmatched values first.
    if position == "before_end_select":
        end_select_idx = find_end_select(lines, anchor_idx, insertion_point)
        if end_select_idx is None:
            return FAIL("End Select not found after anchor for before_end_select")

        # Check for Case Else between anchor and End Select (at same nesting depth)
        case_else_idx = find_case_else(lines, anchor_idx, end_select_idx)
        if case_else_idx is not None:
            return (case_else_idx, "before_case_else")
        return (end_select_idx, "before_end_select")

    # For "before_end_function", find End Function after the anchor
    if position == "before_end_function":
        end_func_idx = find_end_function(lines, anchor_idx)
        if end_func_idx is None:
            return FAIL("End Function not found after anchor")
        return (end_func_idx, "before_end_function")

    # For "after" position, return the anchor index itself
    return (anchor_idx, "after")


def find_end_select(lines, anchor_idx, insertion_point):
    """Find the End Select that closes the Select Case at anchor_idx.

    Uses the end_select_line hint if available, otherwise counts
    Select Case / End Select nesting depth.
    """
    hint = insertion_point.get("end_select_line")
    if hint:
        hint_idx = hint - 1
        if 0 <= hint_idx < len(lines) and "End Select" in lines[hint_idx]:
            return hint_idx

    # Count nesting depth from the anchor line downward
    depth = 1
    for i in range(anchor_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("'"):
            continue
        if re.match(r'Select\s+Case\b', stripped, re.IGNORECASE):
            depth += 1
        if re.match(r'End\s+Select\b', stripped, re.IGNORECASE):
            depth -= 1
            if depth == 0:
                return i
    return None


def find_case_else(lines, anchor_idx, end_select_idx):
    """Find `Case Else` between anchor and End Select at the SAME nesting depth.

    If found, new Case blocks should be inserted BEFORE the Case Else,
    not before End Select. Inserting after Case Else creates dead code
    because Case Else catches all unmatched values.

    Returns: index of Case Else line, or None if not found.
    """
    depth = 0
    for i in range(anchor_idx + 1, end_select_idx):
        stripped = lines[i].strip()
        if stripped.startswith("'"):
            continue
        if re.match(r'Select\s+Case\b', stripped, re.IGNORECASE):
            depth += 1
        elif re.match(r'End\s+Select\b', stripped, re.IGNORECASE):
            depth -= 1
        elif depth == 0 and stripped.startswith("Case Else"):
            return i
    return None


def find_end_function(lines, anchor_idx):
    """Find End Function / End Sub starting from anchor_idx downward."""
    for i in range(anchor_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'End\s+(Function|Sub)\b', stripped, re.IGNORECASE):
            return i
    return None
```

### Shared Helper Functions

These functions are used by multiple modules (case-block-insertion, new-endorsement-file).
They are defined here so every worker has them regardless of which operation-specific
module is loaded.

```python
import re

def measure_case_indent(lines, end_select_idx):
    """Measure indentation of existing Case blocks in a Select Case.

    Scans backward from End Select to find the nearest Case line,
    then returns its leading whitespace string.

    Used by:
      - modules/case-block-insertion.md (Step 5b)
      - modules/new-endorsement-file.md (Step 5d)
    """
    for i in range(end_select_idx - 1, max(end_select_idx - 50, -1), -1):
        stripped = lines[i].strip()
        if stripped.startswith("'"):
            continue
        match = re.match(r'^(\s*)Case\s+', lines[i])
        if match:
            return match.group(1)
    # Fallback: use End Select indent + 4 spaces
    es_match = re.match(r'^(\s*)', lines[end_select_idx])
    return es_match.group(1) + "    " if es_match else "                    "
```

**On failure:** Report `FAILED` with the specific error code (`CONTENT_MISMATCH`
or `AMBIGUOUS_ANCHOR`). Do NOT attempt to guess or fuzzy-match. The Analyzer
verified the anchor at analysis time; a mismatch means the file changed.

### Step 4.5: ESTABLISHED PATTERN PREFERENCE (MANDATORY)

Before generating code that accesses runtime objects, collections, or framework
methods, check the `code_patterns` section from the operation YAML. This section
is populated by the Analyzer's Code Pattern Discovery step (Step 5.9) and contains
proven, active code patterns from the codebase.

**This rule prevents dead-code poisoning** — where the Logic Modifier sees a dead
function and mimics its pattern instead of using the established, active approach.

```python
def check_established_patterns(work, lines):
    """Check code_patterns for established access patterns before generating code.

    Returns:
        canonical_patterns: dict of access_need → pattern to use
        peer_style: dict of style hints from peer functions
        warnings: list of dead-code warnings
    """
    code_patterns = work.get("code_patterns", {})
    if not code_patterns:
        # Level 2 enhancement: even without code_patterns from Step 5.9,
        # check FUB nearby_functions for lightweight alive/dead signals.
        # This catches dead-code proximity warnings even for operations that
        # didn't trigger Step 5.9 (e.g., simple logic ops).
        fub = work.get("fub")
        if fub and fub.get("nearby_functions"):
            fub_warnings = []
            for nf in fub["nearby_functions"]:
                if nf.get("status") == "DEAD" or nf.get("call_sites", 1) == 0:
                    fub_warnings.append(
                        f"{nf['name']} (line {nf.get('line_start', '?')}) "
                        f"has {nf.get('call_sites', 0)} call sites — DEAD CODE, "
                        f"do NOT copy patterns from this function"
                    )
            return {}, {}, fub_warnings
        return {}, {}, []    # No patterns discovered — fall back to spec module

    canonical = {}
    peer_style = {}
    warnings = code_patterns.get("warnings", [])

    # 1. Extract canonical access patterns (use these VERBATIM)
    for access in code_patterns.get("canonical_access", []):
        canonical[access["need"]] = {
            "pattern": access["pattern"],
            "confidence": access["confidence"],
            "example_snippet": access.get("example_snippet", ""),
        }

    # 2. Extract style hints from active peer functions
    for peer in code_patterns.get("peer_functions", []):
        if not peer.get("dead_code", False) and peer.get("call_sites", 0) > 0:
            peer_style[peer["name"]] = peer.get("snippet", "")

    return canonical, peer_style, warnings
```

**Rules for code generation when `code_patterns` is present:**

1. **CHECK** `canonical_access` for a matching need before writing any code that
   accesses runtime objects or collections.

2. **If found with confidence "high" or "medium":**
   → USE the established pattern VERBATIM (adjust indentation only)
   → Copy the code structure, variable naming, and accessor calls from `example_snippet`
   → Reference the `example_snippet` as your template

3. **If dead_code warnings are present:**
   → NEVER use patterns from functions listed in `warnings` or marked `dead_code: true`
   → Use only the developer-confirmed pattern from `canonical_access`
   → If no developer confirmation exists, use the highest `call_sites` active pattern

4. **If `code_patterns` section is EMPTY** (no patterns discovered — operation
   did not trigger Step 5.9):

   **LIVE INVESTIGATION FALLBACK:** Before falling back to spec module defaults,
   read similar files to find the pattern. The Logic Modifier NEVER generates blind.

   Apply the fallback in this order:

   **a. Determine what to read based on operation pattern:**

   | Operation Pattern | What to Glob | What to Extract |
   |-------------------|-------------|-----------------|
   | `new_endorsement_flat` | `{province}/Code/Option_*_{PROV}{LOB}*.vb` | Function signature, param handling, return, report line |
   | `new_liability_option` | `{province}/Code/Liab_*_{PROV}{LOB}*.vb` | Function signature, param handling, return, report line |
   | `case_block_insertion` | (read target file itself) | Adjacent Case blocks for structure template |
   | `constant_insertion` | (read target file itself) | Adjacent Const declarations for naming/type template |

   **b. For file-based patterns** (`new_endorsement_flat`, `new_liability_option`):
   Use the Glob tool to find up to 3 matching files. For each file, use the Read
   tool to read its content. From each file, identify:
   - The first `Public Function` or `Public Sub` declaration → function signature pattern
   - How parameters are used (ByVal/ByRef, types) → parameter handling pattern
   - The return statement(s) → return pattern
   - Any `TbwReportLine` or `ReportLine` calls → report line pattern
   - Any `Try`/`Catch` blocks → error handling pattern

   Note: `codebase_root` comes from `manifest["codebase_root"]`, which is available
   in the capsule's context section. Province and LOB come from `work["parameters"]`.

   **c. For insertion patterns** (`case_block_insertion`, `constant_insertion`):
   The target file is already loaded in `lines` (from Step 3). Read the adjacent
   3-5 Case blocks or Const declarations near the insertion point for templates.
   No Glob needed — the template is in the file you're already editing.

   **d. Use the extracted patterns as code generation template.** Match the
   structure, naming, indentation, and error handling of the peer files.

   **e. If no matches found** (Glob returns 0 files, or target file has no
   adjacent examples) → fall back to standard spec module behavior (Steps 5x
   in module cards).
   → Read 3 nearest active functions in the target file for style reference.
   → If the generated code accesses runtime objects without a pattern reference,
     add a comment: `' TODO: REVIEW — No established pattern found`

5. **CHECK `peer_functions`** for style reference regardless of pattern type:
   → Match indentation, variable naming conventions, comment style
   → Prefer patterns from HIGH_USE peer functions (call_sites >= 3) over LOW_USE

**Validation check:**

```python
def validate_pattern_usage(work, generated_lines):
    """Warn if operation has access_needs but no established pattern was used."""
    access_needs = work.get("parameters", {}).get("access_needs") or \
                   work.get("code_patterns", {}).get("canonical_access")
    code_patterns = work.get("code_patterns", {})

    if access_needs and not code_patterns:
        return WARNING(
            f"Operation {work['id']} requires runtime object access but no "
            "established pattern was discovered. Generated code may not follow "
            "codebase conventions. Developer review strongly recommended."
        )
    return OK()
```

### Step 5: Generate VB.NET Code

This is the core code generation step. Each sub-pattern produces different VB.NET
code. All generated code uses 4-space indentation and follows existing codebase
conventions exactly.

**FUB-Guided Generation (Level 2 enhancement — Tier 2/3 capsules):**

Before writing ANY code, if the capsule includes a FUB, use it for structural
understanding. This applies BEFORE dispatching to specific module cards.

```python
def prepare_fub_guidance(work):
    """Extract structural guidance from FUB before code generation.

    Returns a guidance dict that module-specific Step 5x can reference.
    Returns empty dict if no FUB is available (Tier 1 fallback).
    """
    fub = work.get("fub")
    if not fub:
        return {}

    guidance = {}

    # 1. Branch tree: understand WHERE to insert
    branch_tree = fub.get("branch_tree", [])
    if branch_tree:
        guidance["structure"] = branch_tree
        # Derive insertion depth from branch_tree
        # If inserting a new Case, the Case indent = parent Select Case depth
        guidance["insert_depth"] = max(
            (node.get("depth", 0) for node in branch_tree),
            default=1
        )

    # 2. Hazards: adjust generation strategy
    hazards = fub.get("hazards", [])
    if "nested_depth_3plus" in hazards:
        # Count actual spaces from adjacent_context instead of assuming 4-space
        adj = fub.get("adjacent_context", {})
        above_lines = adj.get("above", [])
        if above_lines:
            sample = above_lines[-1].get("content", "")
            actual_indent = len(sample) - len(sample.lstrip())
            guidance["measured_indent"] = actual_indent

    if "mixed_rounding" in hazards:
        guidance["rounding_warning"] = (
            "This function has MIXED rounding — some branches use integer "
            "Array6 (banker rounding) and others use decimal (no rounding). "
            "Match the rounding style of the NEAREST existing branch."
        )

    if "dual_use_array6" in hazards:
        guidance["array6_warning"] = (
            "This function has DUAL-USE Array6: `varRates = Array6(...)` is a "
            "rate assignment (OK to modify), but `IsItemInArray(Array6(...))` is "
            "a test (NEVER modify). Check the LHS before any Array6 changes."
        )

    if "const_rate_values" in hazards:
        guidance["const_warning"] = (
            "This function has rate values in Const declarations "
            "(e.g., `Const ACCIDENTBASE = 200`). If modifying rates, "
            "look for Const declarations, NOT just Array6 calls."
        )

    if "multi_line_array6" in hazards:
        guidance["multiline_warning"] = (
            "This function has multi-line Array6 calls using ` _` line "
            "continuation. Treat all continuation lines as a single "
            "logical Array6 — preserve the ` _` structure in output."
        )

    # 3. Peer bodies: copy structure from established patterns (Tier 3)
    peer_bodies = work.get("peer_bodies", [])
    if peer_bodies:
        # Sort by call_sites, highest first
        best_peer = max(peer_bodies, key=lambda p: p.get("call_sites", 0))
        guidance["peer_template"] = {
            "name": best_peer["name"],
            "call_sites": best_peer["call_sites"],
            "body": best_peer["body"],
        }
        guidance["peer_instruction"] = (
            f"Model new code after {best_peer['name']} ({best_peer['call_sites']} "
            f"call sites). Copy its structure, variable naming, and comment style."
        )

    # 4. Cross-file context: verify dependencies (Tier 3)
    cross_ctx = work.get("cross_file_ctx", [])
    if cross_ctx:
        guidance["cross_file_deps"] = [
            f"{ctx['dep_op']}: {ctx['dep_summary']}" for ctx in cross_ctx
        ]

    return guidance
```

**Rules for FUB-guided code generation:**

1. **READ `branch_tree` BEFORE writing.** Understand the Select Case / If-ElseIf
   nesting structure. Know how many existing branches there are and WHERE to insert.

2. **Match indentation from `adjacent_context`**, especially when `hazards` includes
   `nested_depth_3plus`. Do NOT assume 4-space increments — measure actual spaces
   from the adjacent lines.

3. **When inserting a new Case block**, use `branch_tree` to identify the parent
   Select Case's depth, then add the new Case at that depth's indent level. Place
   the new Case BEFORE `Case Else` if one exists.

4. **When `peer_bodies` are available (Tier 3)**, read ALL peer bodies before writing.
   Copy the structure from the peer with the HIGHEST `call_sites` — it represents
   the most established pattern in the codebase. Match variable naming, comment style,
   and control flow structure.

5. **Verify `cross_file_context` dependencies (Tier 3).** If the operation depends on
   constants or functions added by another operation in a different file, verify those
   were applied before writing code that references them.

**After locating the insertion point (Step 4), the worker reads `dispatch.md` to
determine which module card to load for the specific operation pattern, then
follows that module's Step 5x instructions.**

### Step 6: Validate Generated Code

Before applying the insertion, run structural validation on the generated lines
to catch syntax errors early.

```python
def validate_generated_code(generated_lines, work, lines):
    """Validate generated VB.NET code for structural correctness.

    Checks:
    1. Balanced keywords (Function/End Function, Sub/End Sub,
       Select Case/End Select, If/End If)
    2. No duplicate against existing code (using duplicate_check field)
    3. Indentation consistency (4-space multiples)
    """
    # 1. Balanced keyword check
    keyword_pairs = {
        "Function": "End Function",
        "Sub": "End Sub",
        "Select Case": "End Select",
        "If ": "End If",
    }
    for open_kw, close_kw in keyword_pairs.items():
        opens = sum(1 for ln in generated_lines
                    if re.search(r'\b' + re.escape(open_kw), ln.strip())
                    and not ln.strip().startswith("'"))
        closes = sum(1 for ln in generated_lines
                     if close_kw in ln
                     and not ln.strip().startswith("'"))
        if opens != closes:
            return FAIL(
                f"Unbalanced {open_kw}/{close_kw}: "
                f"{opens} opens vs {closes} closes"
            )

    # 2. Duplicate check
    dup_check = work.get("duplicate_check", "")
    if "not found" not in dup_check.lower() and "safe" not in dup_check.lower():
        # Analyzer flagged a potential duplicate -- verify
        p = work["parameters"]
        check_name = p.get("constant_name") or p.get("function_name") or ""
        if check_name:
            for line in lines:
                if check_name in line and not line.strip().startswith("'"):
                    return SKIPPED(
                        f"DUPLICATE_DETECTED: '{check_name}' already exists in file"
                    )

    # 3. Indentation consistency
    for ln in generated_lines:
        if ln.strip() == "":
            continue    # Blank lines are OK
        leading = len(ln) - len(ln.lstrip(' '))
        if leading % 4 != 0:
            return FAIL(
                f"Indentation not a multiple of 4: {leading} spaces on: "
                f"{ln.rstrip()[:60]}..."
            )

    return OK
```

### Step 7: Apply Insertion

Insert the generated lines at the located position. The insertion method depends
on the `position_type` returned from Step 4.

```python
def apply_insertion(lines, insert_idx, position_type, generated_lines):
    """Insert generated lines into the file at the correct position.

    Args:
        lines: mutable list of file lines
        insert_idx: 0-indexed line where the anchor was found
        position_type: "after", "before_end_select", "before_case_else",
                       or "before_end_function"
        generated_lines: list of VB.NET lines to insert

    Returns: (actual_insert_line, lines_added) for logging.
    """
    if position_type == "after":
        # Insert AFTER the anchor line
        insert_at = insert_idx + 1

    elif position_type == "before_end_select":
        # Insert BEFORE the End Select line
        insert_at = insert_idx

    elif position_type == "before_case_else":
        # Insert BEFORE the Case Else line (Case Else must remain LAST)
        insert_at = insert_idx

    elif position_type == "before_end_function":
        # Insert BEFORE the End Function line
        insert_at = insert_idx

    else:
        return FAIL(f"Unknown position_type: {position_type}")

    # Insert lines in order (bottom-to-top is handled at the FILE level
    # by the modifier-agent; within a single operation, top-to-bottom is correct)
    for i, gen_line in enumerate(generated_lines):
        lines.insert(insert_at + i, gen_line)

    return (insert_at, len(generated_lines))
```

**Bottom-to-top note:** The modifier-agent processes operations within a file in
descending line order (highest `line_ref` first). This means insertions at higher
line numbers happen before insertions at lower line numbers, preventing index
drift. Within a single operation, lines are inserted in their natural top-to-bottom
order because they are a contiguous block.

**CRITICAL — RE-LOCATE ANCHORS AFTER EACH INSERTION:** When the worker has
MULTIPLE insertion operations in the same file within a single capsule, each
insertion shifts ALL line numbers below it. The worker MUST re-read the file
(or re-locate anchors via content search) for EACH subsequent insertion operation.
Do NOT cache anchor indices across operations — stale indices cause insertion at
wrong positions. The content-based `locate_insertion_point()` search handles this
automatically if the file is re-read between operations. The `lines` list is
already the in-memory mutable state, but `locate_insertion_point()` must be called
FRESHLY for each operation (not reused from a prior call).

### Step 8: Verify Insertion

After applying the insertion, re-read the file and confirm the generated code is
present at the expected location with surrounding context unchanged.

```python
def verify_insertion(target_path, insert_at, generated_lines, line_ending):
    """Re-read the file and verify the insertion took effect.

    Checks:
    1. Generated lines are present at the expected position
    2. Surrounding context lines are unchanged
    """
    with open(target_path, "rb") as f:
        raw = f.read()
    actual_lines = raw.decode("utf-8").split(line_ending)

    for i, expected in enumerate(generated_lines):
        actual_idx = insert_at + i
        if actual_idx >= len(actual_lines):
            return FAIL(
                f"Verification failed: file has only {len(actual_lines)} lines, "
                f"expected content at line {actual_idx + 1}"
            )
        if actual_lines[actual_idx].rstrip() != expected.rstrip():
            return FAIL(
                f"Verification failed at line {actual_idx + 1}:\n"
                f"  Expected: {expected.rstrip()}\n"
                f"  Actual:   {actual_lines[actual_idx].rstrip()}"
            )

    return OK
```

**On verification failure:** This is a serious error. The modifier-agent should
restore from snapshot, report `FAILED`, and continue to the next operation.

### Step 11: Build Log Entry

Construct the operations_log entry matching the Output Schema documented above.
The Logic Modifier returns this data to the modifier-agent, which handles the
actual YAML write.

```python
from datetime import datetime, timezone

def build_log_entry(work, insert_at, generated_lines, new_file_info=None):
    """Construct an operations_log entry for a completed operation.

    Args:
        work: operation work dictionary
        insert_at: 0-indexed insertion line (converted to 1-indexed for log)
        generated_lines: list of inserted code lines
        new_file_info: (target_path, line_count, line_ending) if new file created
    """
    entry = {
        "operation": work["id"],
        "agent": "logic-modifier",
        "status": "COMPLETED",
        "file": work["target_file"],
    }

    if work.get("function"):
        entry["function"] = work["function"]
    else:
        entry["location"] = work.get("insertion_point", {}).get("section", "module-level")

    # Changes array
    after_text = "\n".join(ln.rstrip() for ln in generated_lines)
    entry["changes"] = [{
        "line": insert_at + 1,    # Convert to 1-indexed
        "description": work.get("title", f"Logic insertion for {work['srd']}"),
        "before": None,           # Pure insertion
        "after": after_text,
        "change_type": "insert",
    }]

    # Summary
    entry["summary"] = {
        "lines_added": len(generated_lines),
        "lines_modified": 0,
        "lines_removed": 0,
        "started_at": work.get("_started_at", datetime.now(timezone.utc).isoformat()),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    if new_file_info:
        entry["summary"]["new_file_created"] = True
        entry["summary"]["vbproj_updated"] = work.get("vbproj_target", "")

    return entry
```

### Step 12: Return Result

Return the structured result to the modifier-agent. The modifier-agent handles
writing to operations_log.yaml and updating file_hashes.yaml.

```python
def return_result(log_entry):
    """Return structured result to the modifier-agent.

    The modifier-agent:
    1. Appends log_entry to execution/operations_log.yaml
    2. Updates execution/file_hashes.yaml with new hash
    3. Proceeds to the next operation in execution_sequence
    """
    return {
        "status": log_entry["status"],
        "log_entry": log_entry,
        "summary": (
            f"{log_entry['operation']}: {log_entry['status']} -- "
            f"{log_entry['summary']['lines_added']} lines added"
        ),
    }
```

---

## 8. Key Responsibilities

1. **Locate insertion points by content-based anchor matching** -- line numbers from
   the plan are hints; the anchor text (`insertion_point.context`) is the source of
   truth. Use the 3-tier search strategy (hint line, +/-20 window, full scan).

2. **Generate syntactically correct VB.NET code** that matches the existing codebase
   style -- indentation depth, spacing conventions, comment format, naming patterns.

3. **Insert code at structurally correct locations** -- new constants after existing
   Const blocks, new Case blocks before `End Select`, new functions after the
   preceding `End Function` / `End Sub`, new Imports at the file top.

4. **Execute same-file operations bottom-to-top** to prevent index drift. When
   multiple insertions target the same file, start with the highest line number
   and work upward.

5. **Create new Option_*.vb and Liab_*.vb files** from template references when
   `needs_new_file: true`. Copy the template, rename per the plan's naming
   convention, replace placeholder values with plan-specified content.

6. **Add .vbproj Compile Include entries** for every new file created. Parse the
   .vbproj XML, insert the `<Compile Include>` element in the correct ItemGroup,
   and write back with preserved formatting.

7. **Add SRD traceability comments** on all generated code:
   `' SRD: {workstream-name} op-{id} — {description}`

8. **Flag complex or uncertain logic** with `' TODO: REVIEW -- [reason]` so the
   developer and the execution-reviewer can verify correctness.

9. **Detect and skip duplicates** -- if the constant name, function signature, or
   Case value already exists in the target file, log as SKIPPED (not FAILED). This
   makes re-execution safe.

10. **NEVER modify cross-province shared files** -- any file listed in
    `config.yaml["cross_province_shared_files"]` (e.g., `Code/PORTCommonHeat.vb`
    for Portage Mutual) or any file outside the target province's Code/ tree.
    If the plan targets one of these, log FAILED with `CROSS_PROVINCE_VIOLATION`.

11. **NEVER add Try/Catch blocks** to Option_*.vb or Liab_*.vb files. The existing
    codebase does not use them in these files, and adding them would break the
    established error-handling pattern.

12. **NEVER use line continuation characters** (`_`). The existing codebase keeps
    long lines as-is. Do not split lines even if they exceed typical width limits.

13. **NEVER generate GoTo labels** or GoTo statements. Handle existing GoTo-based
    flow control when inserting into files that contain it, but never introduce new
    GoTo patterns.

**Responsibilities that belong to other agents:**

| Responsibility | Now Handled By |
|---------------|---------------|
| Copy Code/ files to new dates | file-copier-agent |
| Update .vbproj references for copied files | file-copier-agent |
| Modify existing Array6 / factor values | Rate Modifier |
| Snapshot creation before edits | modifier-agent (wrapper) |
| TOCTOU hash check before edits | modifier-agent (wrapper) |
| Hash update after modification | modifier-agent (wrapper) |
| Operations log YAML writing | modifier-agent (wrapper) |
| Snapshot restoration on failure | modifier-agent (wrapper) |

The Logic Modifier provides the **generated code and insertion metadata** for
logging. The modifier-agent (the wrapper that dispatches to this .md file) handles
the I/O operations for snapshots, hashes, and log entries.

---

## 9. Boundary Table

| Responsibility | Logic Modifier | Rate Modifier | File-Copier | Orchestrator |
|----------------|:--------------:|:-------------:|:-----------:|:------------:|
| Locate insertion points by content matching | YES | YES | -- | -- |
| Generate new VB.NET code (functions, Case blocks, constants) | YES | -- | -- | -- |
| Modify existing numeric values (Array6, factors, limits) | -- | YES | -- | -- |
| Create new source files (Option_*.vb, Liab_*.vb) | YES | -- | -- | -- |
| Copy existing Code/ files to new dates | -- | -- | YES | -- |
| Update .vbproj references for copied files | -- | -- | YES | -- |
| Update .vbproj for NEW files (Compile Include) | YES | -- | -- | -- |
| Take per-file snapshots before editing | -- | -- | -- | modifier-agent |
| TOCTOU hash check before writing | -- | -- | -- | modifier-agent |
| Update file hashes after successful write | -- | -- | -- | modifier-agent |
| Write operations_log.yaml entries | -- | -- | -- | modifier-agent |
| Determine execution order across operations | -- | -- | -- | Planner |
| Manage manifest.yaml state transitions | -- | -- | -- | /iq-execute |
| Add SRD traceability comments to generated code | YES | -- | -- | -- |
| Flag TODO: REVIEW items in generated code | YES | -- | -- | -- |
| Detect and skip duplicate code (safe re-execution) | YES | YES | -- | -- |

**Key distinctions:**

- The **Logic Modifier** generates *new* code. The **Rate Modifier** changes
  *existing* values. They never overlap -- a single operation is dispatched to
  exactly one of them based on the `agent` field in the operation YAML.

- The **File-Copier** handles .vbproj updates for *copied* files (changing date
  references). The **Logic Modifier** handles .vbproj updates for *new* files
  (adding Compile Include entries that did not exist before).

- The **modifier-agent** wrapper handles all infrastructure concerns (snapshots,
  hashes, logging) for BOTH the Rate Modifier and Logic Modifier. Neither modifier
  agent reads or writes snapshot files, hash files, or the operations log directly.

---

## Loading Additional Modules
After reading this core contract, the worker reads `dispatch.md` to determine which module card to load for the specific operation pattern.
