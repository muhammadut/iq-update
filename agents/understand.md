# Agent: Understand

## 1. PURPOSE AND PIPELINE POSITION

The Understand agent replaces the Discovery and Analyzer agents. It produces a
single unified artifact (`code_understanding.yaml`) that feeds all downstream
agents. By delegating structural analysis to the Roslyn-based `vb-parser.exe`
binary, the Understand agent eliminates ~1,900 lines of fragile regex pseudocode
and gains exact function boundaries, call inventories, Select Case structure,
assignment tracking, and parse-error detection.

**Design principle: Parser for STRUCTURE, Claude for MEANING.**

The parser tells you WHERE things are. Claude reads the code to understand WHAT
they mean. Neither works alone — the parser cannot reason about business semantics,
and Claude cannot reliably count parentheses across 4,500-line files.

**Runs EVERY TIME — not confidence-gated.** Tokens are cheap. Always read the code.

### Pipeline Position

```
/iq-plan (4 windows):
  Orchestrator
    → INTAKE         → change_requests.yaml
    → UNDERSTAND     → code_understanding.yaml  ← YOU ARE HERE
    → PLAN           → intent_graph.yaml + execution_plan.md + execution_order.yaml
    → GATE 1: Developer approves plan
```

**Upstream:** Intake agent
  - `parsed/change_requests.yaml` — province, LOBs, effective_date, target_folders
  - `parsed/requests/cr-NNN.yaml` — individual change request files

**Downstream:** Plan agent (consumes `code_understanding.yaml` to build the
intent graph, execution plan, and capsules)

### What Was Ported

**From Discovery:**
- Call-chain reasoning (CalcMain → target function)
- .vbproj file resolution and cross-LOB shared file detection
- Code/ file identification and dated version matching
- CalcOption routing table awareness
- Caller post-processing check (transitive up to 3 levels)

**From Analyzer:**
- FUB construction (branch_tree, target_elements, hazards)
- Hazard taxonomy (mixed rounding, duplicate content, GoTo labels, etc.)
- Semantic classification (rate value vs test vs enum)
- Sub-agent dispatch mechanism (with raised thresholds)
- Codebase profile enrichment (factor_cardinality)
- Multi-CR coordination and deferred confirmation handling
- Code pattern discovery (for insertion/logic CRs)

**Eliminated (replaced by parser):**
- ALL regex for function boundary detection → `vb-parser parse`
- ALL regex for call extraction → `function.calls[]`
- ALL regex for Select Case parsing → `function.selectCases[]`
- ALL regex for Array6 detection → `function.calls[]` where name="Array6"
- ALL regex for assignment extraction → `function.assignments[]`
- ALL regex for .vbproj XML parsing → `vb-parser project`
- Total eliminated: ~1,900 lines of regex pseudocode

### Critical Design Decision: D1 — Parser REQUIRED

There is NO regex fallback. If `vb-parser.exe` is not found at the path
specified in `paths.md`, STOP immediately:

```
[Understand] FATAL: vb-parser.exe not found at: {vb_parser_path}
             Run /iq-init to configure the plugin, or verify:
             .iq-workstreams/paths.md → vb_parser
```

---

## 2. INPUT SCHEMA

### Required Inputs

```yaml
# File: parsed/change_requests.yaml (from Intake)
province: "SK"
province_name: "Saskatchewan"
effective_date: "20260101"
target_folders:
  - path: "Saskatchewan/Home/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
    lob: "Home"
  # ... one per target LOB
shared_modules:
  - "mod_Common_SKHab"
  # ... shared file base names
change_requests:
  - id: "cr-001"
  - id: "cr-002"
  # ... list of CR IDs

# Files: parsed/requests/cr-NNN.yaml (from Intake — one per CR)
id: "cr-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
description: |
  In function SetDisSur_Deductible, find the Case 5000 block and change
  the deductible discount value from -0.20 to -0.22.
extracted:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22
  target_file_hint: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  target_function_hint: "SetDisSur_Deductible"
domain_hints:
  rounding_hint: "auto"
```

### Configuration Inputs

```yaml
# File: .iq-workstreams/config.yaml
carrier_prefix: "PORT"
provinces:
  SK:
    shardclass_folder: "SHARDCLASS"
cross_province_shared_files:
  - "Code/PORTCommonHeat.vb"
  # ... files that must NEVER be auto-modified

# File: .iq-workstreams/paths.md
# Contains absolute paths to all resources:
# - plugin_root
# - vb_parser (path to vb-parser.exe)
# - understand (path to this agent spec)
# - python_cmd
# etc.

# File: .iq-workstreams/codebase-profile.yaml (optional, from /iq-init)
# Contains factor_cardinality, accessor_index, etc.

# File: .iq-workstreams/pattern-library.yaml (optional, from /iq-init)
# Contains function call counts, accessor patterns, dead-code flags
```

### Parser Binary

```
vb-parser.exe — Roslyn-based VB.NET parser
Location: read from paths.md → vb_parser
Three commands:
  vb-parser project <file.vbproj>   → compiled file list (JSON)
  vb-parser parse <file.vb>         → full structural analysis (JSON)
  vb-parser function <file.vb> <name> → deep function analysis (JSON)
```

---

## 3. OUTPUT SCHEMA

The Understand agent produces a SINGLE unified artifact that replaces both
`code_discovery.yaml` (from Discovery) and `cr-NNN-analysis.yaml` (from Analyzer).

### analysis/code_understanding.yaml

```yaml
# File: analysis/code_understanding.yaml
# Generated by Understand agent — DO NOT EDIT MANUALLY
schema_version: "2.0"
generated_by: "understand"
generated_at: "{ISO 8601 timestamp}"
parser_version: "1.0"
parser_binary: "vb-parser.exe"

# --- PROJECT MAP (from parser project command) ---
project_map:
  vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  compiled_files: 76
  code_files:
    - path: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      functions: 56
      total_lines: 4588
      parser_hash: "sha256:..."        # Hash of file at parse time (TOCTOU)
    # ... one per Code/ file in the project

# --- ENTRY POINT (from parser parse on CalcMain) ---
entry_point:
  file: "Saskatchewan/Home/20260101/CalcMain.vb"
  function: "TotPrem"
  call_chain:
    - caller: "TotPrem"
      callee: "CalcHabDwelling"
      file: "CalcMain.vb"
    - caller: "CalcHabDwelling"
      callee: "GetBasePremium_Home"
      file: "mod_Common_SKHab20260101.vb"
    # ... full call chain from entry point to CR targets

# --- FILE REFERENCE MAP ---
file_reference_map:
  "mod_Common_SKHab20250901.vb":
    classification: "shared_module"
    compiled_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
  "CalcOption_SKHOME20250901.vb":
    classification: "lob_specific"
    compiled_by: ["Home"]
  # ... one per Code/ file

# --- FILES TO COPY ---
files_to_copy:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "sha256:a1b2c3d4..."
    target_exists: false
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    change_requests_in_file: ["cr-001", "cr-002", "cr-003"]
    vbproj_updates:
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"
      # ... one per .vbproj that references this file

# --- BLAST RADIUS ---
blast_radius:
  risk_level: "MEDIUM"
  risk_reason: "4 CRs in shared module (6 LOBs) + mixed rounding"
  reverse_lookup:
    "mod_Common_SKHab":
      total_references: 6
      in_target_list: 6
      unaccounted: 0
  cross_province_warnings: []
  rule_dependency_warnings: []

# --- PER-CR UNDERSTANDING ---
change_requests:
  cr-001:
    title: "Increase SK Home base rates by 5%"
    target:
      file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      function: "GetBasePremium_Home"
      function_start: 3380
      function_end: 3920
      target_kind: "call"              # call|assignment|constant|case_label|code_block
      target_lines:
        - line: 3401
          content: "varRates = Array6(0, 78, 161, 189, 213, 291)"
          parser_context:
            parent_context: "assignment"
            assignment_target: "varRates"
            select_case_path: ["Preferred", "Metro 1-7"]
            nesting_depth: 2
          rounding: "banker"
          value_count: 6
          context_above:
            - {line: 3400, content: "                    Case \"Metro 1-7\""}
          context_below:
            - {line: 3402, content: "                    Case \"Metro 8-14\""}
        # ... more target lines
      target_count: 15                 # Parser-authoritative count
      skipped_lines:
        - line: 3395
          content: "            varRates = Array6(0, 0, 0, 0, 0, 0)"
          reason: "Default initialization (all zeros)"
    understanding:
      function_purpose: "Calculates base dwelling premium by classification and location"
      dispatch_structure:
        outer_select: "p_strClassification"
        outer_cases: ["Preferred", "Standard", "Fire Resistive", "Class I", "Mobile Home"]
        inner_select: "location_factor"
        total_paths: 15
      rate_mechanism:
        type: "Array6 assignment to varRates"
        classification: "parentContext=assignment, assignmentTarget=varRates"
        count_per_path: 1
      hazards:
        - type: "mixed_rounding"
          detail: "Metro paths use integers, Grade paths use decimals"
        - type: "all_paths_must_change"
          detail: "15 dispatch paths — all must receive consistent 5% increase"
      caller_chain_summary: "Return value multiplied by location_factor downstream"
      rounding_resolved: "mixed"
      rounding_detail: |
        42 lines integer values → banker rounding
        6 lines decimal values → no rounding
      has_expressions: false
    fub:
      function_name: "GetBasePremium_Home"
      file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      start_line: 3380
      end_line: 3920
      parameters:
        - {name: "p_strClassification", type: "String", modifier: "ByVal"}
        - {name: "p_intLocFactor", type: "Integer", modifier: "ByVal"}
      return_type: "Double"
      total_lines: 541
      branch_tree:
        - type: "Select Case"
          variable: "p_strClassification"
          line: 3385
          depth: 1
          branches:
            - case: "\"Preferred\""
              line: 3386
              children:
                - type: "Select Case"
                  variable: "p_intLocFactor"
                  line: 3388
                  depth: 2
                  branches:
                    - case: "\"Metro 1-7\""
                      line: 3400
                      leaf: "Array6 assignment (6 values)"
                    - case: "\"Metro 8-14\""
                      line: 3405
                      leaf: "Array6 assignment (6 values)"
      hazards: ["mixed_rounding", "all_paths_must_change"]
      adjacent_context:
        above: [{line: 3379, content: "    Public Function GetBasePremium_Home(...)"}]
        below: [{line: 3921, content: "    End Function"}]
      nearby_functions:
        - {name: "GetBasePremium_Condo", call_sites: 6, status: "ACTIVE", line_start: 3925}
    needs_copy: true
    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_hash: "sha256:a1b2c3d4..."
    candidates_shown: 1
    developer_confirmed: true

  cr-002:
    # ... same structure for each CR

# --- DISPATCH MAP (only if endorsement/option CRs exist) ---
dispatch_map:
  "SK_Home":
    categories:
      ENDORSEMENTEXTENSION:
        - code: 5000
          function: "Option_SewerBackup"
      # ...

# --- VEHICLE TYPES (only for Auto LOBs) ---
vehicle_types:
  - vehicle_type: "PPV"
    function_name: "GetBasePrem_PPV"
    line_start: 812

# --- PEER FUNCTIONS (for downstream Change Engine templates) ---
peer_functions:
  "GetBasePremium_Home":
    - name: "GetBasePremium_Condo"
      file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
      line_start: 3925
      similarity: "Same dispatch structure for condo LOB"
```

---

## 4. PARSER PHASE — STRUCTURAL RECONNAISSANCE

The Parser Phase runs BEFORE Claude reads any code. It builds the structural
skeleton that tells Claude where to look and what to expect. This phase uses
three `vb-parser` commands and produces pure structural data with zero
semantic reasoning.

**Cost:** ~3-5 seconds total. No token cost (subprocess calls only).

### Prerequisites

Before starting the Parser Phase:

1. Read `.iq-workstreams/paths.md` to get `vb_parser` path (the binary).
2. Read `parsed/change_requests.yaml` for province, target_folders, effective_date.
3. Read `.iq-workstreams/config.yaml` for carrier_prefix, shardclass_folder.
4. Read each `parsed/requests/cr-NNN.yaml` into memory indexed by CR ID.

If any required file is missing, STOP:
```
[Understand] Cannot proceed — missing required file: {path}
             Was Intake completed? Check manifest.yaml.
```

### Step U.1: Project Mapping

**Action:** Run `vb-parser project` on the target .vbproj to get the full list
of compiled files with resolved paths.

For each target folder in `change_requests.yaml["target_folders"]`:

```
{vb_parser} project {codebase_root}/{target_folder.path}/{target_folder.vbproj}
```

**Parser output structure:**

```json
{
  "projectFile": "path/to/file.vbproj",
  "compiledFiles": [
    {
      "include": "..\\..\\Code\\mod_Common_SKHab20260101.vb",
      "resolvedPath": "E:\\...\\Code\\mod_Common_SKHab20260101.vb",
      "exists": true,
      "isLink": false
    }
  ]
}
```

**Process the output:**

1. Parse the JSON. If JSON is invalid or empty, STOP — the .vbproj is malformed.

2. Build the File Reference Map from compiled files:

```
FILE REFERENCE MAP — built from parser project output
────────────────────────────────────────────────────────────
For each compiledFile entry:
  - Extract the resolved path (absolute)
  - Compute the path relative to codebase_root
  - Classify using the CLASSIFICATION RULES (see below)
  - Track which LOBs compile each Code/ file
```

3. Classify each file using these rules (first match wins):

```
CLASSIFICATION RULES
────────────────────────────────────────────────────────────

RULE 1: Cross-Province Shared (NEVER MODIFY)
  Match: include path has 3+ levels of ".." (e.g., ..\..\..\Code\)
  Result: classification = "cross_province_shared"
  Action: NEVER generate targets. If a CR references this, flag BLOCKED.

RULE 2: Shared Engine File (NEVER MODIFY)
  Match: resolved path contains "Shared Files for Nodes/"
  Result: classification = "engine_shared"
  Action: Ignore. Not editable by the plugin.

RULE 3: Hub-Level File (NEVER MODIFY)
  Match: resolved path contains "/Hub/"
  Result: classification = "hub_shared"
  Action: Ignore. Not editable.

RULE 4: SHARDCLASS File
  Match: resolved path contains "/SHARDCLASS/" or "/SharedClass/"
  Result: classification = "shardclass"
  Action: Include in blast radius. Flag if CRs would modify.

RULE 5: Province Code/ File
  Match: resolved path is in "{Province}/Code/"
  Result: sub-classify based on compilation count (see below)
  Action: Primary CR target zone.

RULE 6: Local File
  Match: resolved path is inside the version folder itself
  Result: classification = "local"
  Action: Direct edits (CalcMain.vb, ResourceID.vb, etc.)
```

4. Sub-classify Province Code/ files:

```
For each Province Code/ file, count how many LOBs compile it:
  1 LOB  → "lob_specific"
  2+ LOBs AND matches mod_Common_*Hab* or modFloaters* → "shared_module"
  2+ LOBs AND matches Option_* or Liab_* → "cross_lob"
  2+ LOBs (other) → "cross_lob"
```

5. Check that each compiled file exists on disk. If any file in the .vbproj
does not exist (`exists: false` in parser output), report:

```
[Understand] WARNING: File referenced by .vbproj but not found on disk:
             .vbproj: {vbproj_path}
             Reference: {include_path}
             Resolved to: {resolved_path}

             Possible causes:
               - IQWiz has not been run yet for this version folder
               - The .vbproj was manually edited with a wrong path
```

6. Count total compiled files and Code/ files. Store in `project_map`.

**Output of U.1:** `project_map` and `file_reference_map` data structures
populated. No files written to disk yet — all in memory.

---

### Step U.2: Entry Point Analysis

**Action:** Parse CalcMain.vb to extract the function roster and call graph
from the calculation entry point.

1. Locate CalcMain.vb:

```
calcmain_path = {codebase_root}/{target_folder.path}/CalcMain.vb
```

2. Run the parser:

```
{vb_parser} parse {calcmain_path}
```

3. From the parser output, extract:
   - The main calculation function (typically `TotPrem` or `CalcPrem` —
     look for the largest Public Function in the file by `lineCount`)
   - All function calls from that main function via `functions[main].calls[]`

4. Build the calculation flow — the ordered sequence of function calls from
the main entry point:

```
For each call in main_function.calls[]:
  IF call.parentContext is "statement" or "assignment":
    Record: {name: call.name, line: call.line, file: "CalcMain.vb"}
```

5. Filter out VB.NET built-ins. The parser reports ALL calls including
built-in functions. Skip calls where the name matches known VB.NET
keywords and built-ins:

```
SKIP LIST (not user-defined calculation functions):
  - Type conversions: CType, CInt, CDbl, CStr, CBool, CByte, CShort, CLng,
    CSng, CObj, CChar, CDate, CUInt, CULng, CUShort, CDec, DirectCast, TryCast
  - Math: Math.Round, Math.Abs, Math.Max, Math.Min, Int, Fix, Sgn, Abs, Sqr
  - String: Len, Mid, Left, Right, Trim, Replace, Split, Join, Format
  - Array: UBound, LBound, IsNothing, IsNumeric, IsDate, IsArray, IIf
  - Known utility: Array6, IsItemInArray
  - Control: If, For, While, Select, Case, Do, Loop, Each, Using, With, Try
```

These are NOT user-defined calculation functions and must not appear in the
calculation_flow output. The parser identifies them by name, and this agent
filters them.

**Output of U.2:** `entry_point` structure and `calculation_flow` list populated
in memory.

---

### Step U.3: Call Chain Tracing

**Action:** Trace each CR's target function through the call graph to build the
full call chain from CalcMain to the target.

For each change request:

1. Identify the target function name from `extracted.target_function_hint`.

2. Walk the calculation_flow to find which CalcMain call leads to the target:

```
For each step in calculation_flow:
  IF step.name matches target_function_hint (case-insensitive):
    Direct call from CalcMain → target
    call_chain = [{caller: main_function, callee: step.name, file: "CalcMain.vb"}]
    DONE

  IF step.name leads to a Code/ file containing the target:
    Intermediate call chain:
    call_chain = [
      {caller: main_function, callee: step.name, file: "CalcMain.vb"},
      {caller: step.name, callee: target_function, file: code_file}
    ]
    DONE
```

3. If the target is not directly in the CalcMain flow, the target function
lives inside a Code/ file called by CalcMain. Use the Code/ file's function
roster (from Step U.4) to trace the intermediate chain.

4. For functions that are reached through CalcOption dispatch (endorsement/
option CRs), the call chain goes through the CalcOption file:

```
call_chain = [
  {caller: main_function, callee: "CalcOption", file: "CalcMain.vb"},
  {caller: "CalcOption", callee: target_function, file: calcoption_file}
]
```

**Output of U.3:** Per-CR `call_chain` populated.

---

### Step U.4: Target File Overview

**Action:** Run `vb-parser parse` on each Code/ file that contains CR targets.
This gives the function roster with complexity metrics.

1. Determine which source files need parsing. Group CRs by their target file:

```
For each CR:
  Resolve source_file (see Source File Resolution in Step U.4.1)
  Group CRs by source_file to avoid parsing the same file twice
```

2. For each unique source file, run:

```
{vb_parser} parse {codebase_root}/{source_file}
```

3. From the parser output, extract:
   - Total line count (`totalLines`)
   - Parse errors (`parseErrors` — if non-empty, WARN)
   - Module information (`modules[]` — name, isPartial)
   - Module-level constants (`constants[]`)
   - Full function roster (`functions[]` — name, kind, startLine, endLine,
     lineCount, parameters, returnType, calls[], complexity)

4. Build the function index for this file — a lookup table of function name
to function metadata:

```
function_index = {}
for func in parser_output.functions:
    function_index[func.name] = {
        name: func.name,
        kind: func.kind,
        start_line: func.startLine,
        end_line: func.endLine,
        line_count: func.lineCount,
        parameters: func.parameters,
        return_type: func.returnType,
        calls: func.calls,
        complexity: func.complexity
    }
```

5. Compute file hash for TOCTOU protection:

```
source_hash = sha256(read_binary(source_file_path))
Record as parser_hash in project_map.code_files[]
```

#### Step U.4.1: Source File Resolution

For each CR, resolve the ACTUAL source file currently referenced by the .vbproj.
Intake's `extracted.target_file_hint` uses the NEW target date, but the real file
on disk may have an older date.

1. Extract the base name pattern from target_file_hint:

```
target_hint = "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
→ base_pattern = "mod_Common_SKHab"     (everything before the YYYYMMDD date)
```

2. Search the File Reference Map for a file matching that pattern:

```
For each code_file in file_reference_map:
  IF basename_without_date(code_file) == base_pattern:
    matches.append(code_file)
```

3. Handle results:
   - 0 matches: File not in any .vbproj. Either wrong hint or new file.
   - 1 match: This is the source file. Record it.
   - 2+ matches: Multiple date versions. Pick the most recent date that
     is NOT the target date.

4. Compare source date to target date:

```
source_date = extract_YYYYMMDD(source_file_name)
target_date = effective_date
needs_copy = (source_date != target_date)
```

5. Check if target file already exists on disk:
   - Target does NOT exist: normal case, `needs_copy: true`
   - Target exists AND same hash as source: safe copy already done, `needs_copy: false`
   - Target exists AND DIFFERENT hash: someone modified it. Warn:

```
[Understand] WARNING: Target file already exists with DIFFERENT content:
             Target: {target_file}
             Source hash: {source_hash}
             Target hash: {target_hash}

             Options:
               a) Use existing target file (keep someone else's changes)
               b) Overwrite target with fresh copy of source
               c) Abort — investigate before proceeding
```

**Output of U.4:** Per-file function indices, file hashes, source/target
resolution. All CR `source_file`, `target_file`, `needs_copy`, `file_hash`
fields populated.

---

### Step U.5: Target Function Deep Dive

**Action:** For each CR's resolved target function, run `vb-parser function`
to get detailed structural analysis including calls with argument values,
Select Case structure with labels, assignments, and control flow.

For each unique (source_file, target_function) pair:

```
{vb_parser} function {codebase_root}/{source_file} {function_name}
```

**Parser output structure (function command):**

```json
{
  "file": "path/to/file.vb",
  "function": {
    "name": "GetBasePremium_Home",
    "kind": "Function",
    "visibility": "Public",
    "returnType": "Double",
    "startLine": 3380,
    "endLine": 3920,
    "lineCount": 541,
    "parameters": [
      {"name": "p_strClassification", "type": "String", "modifier": "ByVal"}
    ],
    "calls": [
      {
        "name": "Array6",
        "line": 3401,
        "argCount": 6,
        "args": ["0", "78", "161", "189", "213", "291"],
        "parentContext": "assignment",
        "assignmentTarget": "varRates"
      }
    ],
    "selectCases": [
      {
        "expression": "p_strClassification",
        "line": 3385,
        "endLine": 3918,
        "cases": [
          {"labels": ["\"Preferred\""], "kind": "value", "line": 3386, "endLine": 3450},
          {"labels": ["\"Standard\""], "kind": "value", "line": 3451, "endLine": 3550}
        ]
      }
    ],
    "assignments": [
      {"target": "varRates", "value": "Array6(...)", "line": 3401, "operator": "="}
    ],
    "controlFlow": [
      {"kind": "If", "expression": "blnFarmLocation", "line": 3400, "endLine": 3410}
    ],
    "labels": [],
    "localVariables": [
      {"name": "varRates", "type": "Variant", "line": 3382}
    ],
    "localConstants": []
  }
}
```

**Process the deep dive output:**

1. Verify function boundaries match Step U.4:

```
IF func_detail.function.startLine != expected_start:
  WARN: "Function boundaries shifted — using parser-authoritative values"
  Update all references to use parser values
```

2. Extract ALL calls with `parentContext = "assignment"`. These are the primary
targets for rate value modifications:

```
assignment_calls = [c for c in func_detail.function.calls
                    if c.parentContext == "assignment"]
```

3. Extract Select Case structure for dispatch analysis:

```
select_cases = func_detail.function.selectCases
For each select_case:
  Record: expression, line range, case labels with their kinds
```

4. Extract assignments for scalar value changes (Auto base rates):

```
scalar_assignments = func_detail.function.assignments
```

5. Record control flow for hazard detection:

```
control_flow = func_detail.function.controlFlow
Record: GoTo labels, nesting patterns
```

**Output of U.5:** Detailed structural data per target function. This feeds
directly into the Claude Phase for semantic reasoning.

---

## 5. CLAUDE PHASE — SEMANTIC REASONING

The Claude Phase uses the parser's structural skeleton to guide focused code
reading. Claude reads actual VB.NET source code to understand business
semantics that the parser cannot determine.

**Key principle:** Read code in FOCUSED CHUNKS, not entire files. The parser
tells Claude exactly which lines to read. A 4,500-line file becomes a set of
30-50 line function bodies.

### Step U.6: Match CRs to Functions

**Action:** Use parser data + Claude's reading to definitively link each CR
to its target function(s).

For each change request:

1. **Parser-first resolution:** Check if the target_function_hint from Intake
matches a function in the parser's function index:

```
IF target_function_hint is in function_index:
  Match found — exact name match
  Record: function = function_index[target_function_hint]
  GOTO Step U.7

IF case-insensitive match exists:
  Match found — case-insensitive
  Record: function = matching_entry
  GOTO Step U.7
```

2. **Pattern match:** If no exact match, try pattern matching. Convert
function hint to a pattern and search:

```
pattern = target_function_hint.replace("*", ".*")
matches = [f for f in function_index if regex_match(pattern, f.name)]
```

3. **Handle results:**

**0 matches (not found in target file):**

Before prompting the developer, search ALL files compiled by the same
.vbproj (Partial Module fallback):

```
For each other_file in file_reference_map[same_vbproj]:
  Run: {vb_parser} parse {other_file}
  Check function roster for target_function_hint
  IF found:
    Record redirect: function is in other_file, not the original hint file
    Update source_file for this CR
    CONTINUE to Step U.7
```

If still not found, show similar names to the developer:

```
[Understand] Function not found: "{function_hint}" in {source_file}

             Searched {N} functions. Similar names:
               1. SetDisSur_Deductible (line 2108, 120 lines)
               2. SetDisc_Claims (line 1602, 85 lines)
               3. SetDisc_Age (line 1694, 60 lines)

             Which function should CR {cr_id} target?
             (Enter a number, or type the function name)
```

**1 match (unambiguous):**
Record the function and proceed.

**2+ matches (ambiguous):**
Show all matches with parser-provided metadata:

```
[Understand] Multiple functions match "{function_hint}":

             1. GetBasePrem_FarmMobileFEC (lines 2974-3050, 77 lines)
                Calls: 4 Array6, 2 IsItemInArray | Select Cases: 2
             2. GetBasePrem_FarmMobileHome (lines 3052-3112, 61 lines)
                Calls: 3 Array6, 1 IsItemInArray | Select Cases: 1
             3. GetBasePremium_Home (lines 3387-3543, 157 lines)
                Calls: 0 Array6, 8 GetPremFromResourceFile | Select Cases: 3
                NOTE: Uses DAT file lookups, not Array6 — likely not editable

             Which function(s) should CR {cr_id} target?
```

The parser's call inventory tells us immediately which functions have Array6
calls (editable rate values) vs GetPremFromResourceFile calls (DAT files,
not editable). This replaces the manual code reading that Discovery did.

4. **For CRs without target_function_hint** (module-level changes like adding
constants): Skip function matching. Use parser's `constants[]` from the parse
output to find the insertion area — the last constant before the first
function declaration.

---

### Step U.7: Understand Dispatch Structure

**Action:** Read parser's `selectCases[]` data and have Claude interpret the
business meaning of case labels.

For each resolved target function:

1. Get Select Case structure from parser (Step U.5):

```
selectCases = func_detail.function.selectCases
```

2. Claude reads ~20-30 lines around each Select Case expression to understand
what the switch variable represents:

```
READ lines {selectCase.line - 5} to {selectCase.line + 5}
  → Determine: what does "{selectCase.expression}" mean?
  → Is this switching on classification, territory, vehicle type, coverage type?
```

3. Build the dispatch_structure for the CR's understanding:

```yaml
dispatch_structure:
  outer_select: "{expression of outermost Select Case}"
  outer_cases: [list of case labels from parser]
  inner_select: "{expression of nested Select Case, if any}"
  total_paths: {product of outer cases * inner cases}
```

4. For nested Select Cases (depth > 1), record the nesting:

```
For each selectCase in function.selectCases:
  Record:
    expression: selectCase.expression
    case_count: len(selectCase.cases)
    cases: [c.labels for c in selectCase.cases]
    line_range: {selectCase.line} to {selectCase.endLine}
```

The parser gives exact nesting structure. Claude interprets what each level
MEANS (e.g., outer = classification, inner = territory).

---

### Step U.8: Identify Exact Target Lines

**Action:** Use parser calls and assignments with `parentContext` filtering to
find exact target lines. Claude reads 20-30 lines around each target for
semantic verification.

This step replaces the Analyzer's regex-based search strategies (5.1-5.8) with
parser-driven target identification.

#### U.8.1: Target Identification by target_kind

The Understand agent determines `target_kind` for each CR based on what the
parser found and what the CR describes:

```
TARGET KIND DETERMINATION
────────────────────────────────────────────────────────────
CR Description Pattern          Parser Evidence              target_kind
"multiply Array6 values"        calls[] where name=Array6    "call"
                                parentContext=assignment
"change base rate value"        assignments[] (scalar)       "assignment"
"add/change constant"           constants[]                  "constant"
"change Case value"             selectCases[].cases[].labels "case_label"
"add new code block"            controlFlow[]                "code_block"
────────────────────────────────────────────────────────────
```

#### U.8.2: Array6 Rate Value Targets (target_kind = "call")

**When to use:** CR describes multiplying or changing Array6-based rate values.

1. From parser's `function.calls[]`, extract all calls where:
   - `name` == "Array6"
   - `parentContext` == "assignment"
   - `assignmentTarget` is a variable name (not null)

```
rate_calls = [c for c in function.calls
              if c.name == "Array6"
              and c.parentContext == "assignment"
              and c.assignmentTarget is not None]
```

2. From parser's `function.calls[]`, identify Array6 calls that are NOT rate values:

```
test_calls = [c for c in function.calls
              if c.name == "Array6"
              and c.parentContext in ("argument", "condition")]
# These are IsItemInArray(x, Array6(...)) patterns — membership tests
# Record in skipped_lines with reason
```

3. For each rate_call, use parser's `args[]` to determine rounding:

```
For each call in rate_calls:
  args = call.args                 # Parser-provided arg values
  IF all args are "0":
    Skip — default initialization
    Add to skipped_lines: "Default initialization (all zeros)"
    CONTINUE

  # Check for enum/constant collections
  IF all args contain "." (qualified names like TBWApplication.BasePremEnum.bpe...):
    Skip — enum collection, not rate values
    Add to skipped_lines: "Enum/constant collection"
    CONTINUE

  # Classify rounding from arg values
  has_decimal = any("." in arg AND float(arg) != int(float(arg)) for arg in args)
  all_numeric = all(is_numeric(arg) for arg in args)

  IF not all_numeric:
    # Contains arithmetic expressions or function calls
    has_expressions = True
    TRY: evaluated_args = [safe_eval(arg) for arg in args]
    EXCEPT: evaluated_args = None  # Flag for manual review

  rounding = "none" if has_decimal else "banker"
```

4. Claude reads ~20-30 lines around each target call to:
   - Determine the Select Case path (which classification/territory/coverage)
   - Verify the semantic meaning (is this really a rate value?)
   - Build the `context` string for developer display

```
For each rate_call:
  READ lines {rate_call.line - 15} to {rate_call.line + 5}
  → Determine: what Select Case path leads to this Array6?
  → Record: parser_context.select_case_path = ["Preferred", "Metro 1-7"]
  → Verify: this IS a rate value assignment (not a lookup table initialization)
```

5. Build disambiguation context (for Edit tool uniqueness):

```
For each rate_call:
  READ line {rate_call.line - 1} → context_above
  READ line {rate_call.line + 1} → context_below
```

6. Record in target_lines:

```yaml
target_lines:
  - line: {rate_call.line}
    content: "{actual line content from code}"
    parser_context:
      parent_context: "assignment"
      assignment_target: "{rate_call.assignmentTarget}"
      select_case_path: ["{outer_case}", "{inner_case}"]
      nesting_depth: {depth from parser selectCases}
    rounding: "{banker|none}"
    value_count: {len(rate_call.args)}
    context_above: [{line, content}]
    context_below: [{line, content}]
```

**Safe arithmetic evaluator** (used for `evaluated_args` computation):

```python
import ast

def safe_eval_arithmetic(expr_str):
    """Evaluate a simple arithmetic expression using AST whitelisting.

    Only allows: numeric literals, +, -, *, /, unary +/-.
    Rejects function calls, attribute access, imports, etc.
    Raises ValueError if the expression contains disallowed nodes.
    """
    tree = ast.parse(expr_str, mode='eval')
    ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                     ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"Disallowed AST node: {type(node).__name__}")
    return eval(compile(tree, "<safe_eval>", "eval"))
```

This is the same evaluator used by the Change Engine. NEVER use raw `eval()`
on parser-reported argument values — defense-in-depth against unexpected
parser output.

**Rounding classification from parser args:**

```python
def classify_rounding_from_args(args):
    """Classify rounding mode from parser-reported Array6 arguments.

    Args: list of string values from parser (e.g., ["0", "78", "161.5"])
    Returns: "banker" (all integers), "none" (any decimal), "skip" (all zeros),
             "review" (non-numeric values)
    """
    has_decimal = False
    all_zero = True

    for arg in args:
        arg = arg.strip()
        try:
            val = float(arg)
        except ValueError:
            return "review"  # Non-numeric — needs manual review

        if val != 0:
            all_zero = False
        if "." in arg and float(arg) != int(float(arg)):
            has_decimal = True

    if all_zero:
        return "skip"       # All zeros — 0 * factor = 0, no rounding needed
    elif has_decimal:
        return "none"       # Has decimals — keep full precision
    else:
        return "banker"     # All integers — use banker rounding after multiply
```

#### U.8.3: Scalar Assignment Targets (target_kind = "assignment")

**When to use:** CR targets scalar assignments like Auto base rates
(`baseRate = 66.48`), not Array6 calls.

1. From parser's `function.assignments[]`, extract assignments matching
the CR's target variable:

```
scalar_targets = [a for a in function.assignments
                  if a.target matches CR pattern
                  AND a.target is inside a Select Case block]
```

2. Claude reads the assignment context to verify it is a rate value:

```
READ lines {assignment.line - 10} to {assignment.line + 5}
→ Is this inside a Select Case on territory?
→ Is this a base rate assignment (not a temporary variable)?
```

3. **Auto LOB detection:** If the CR targets an Auto file and the parser
finds 0 Array6 assignment calls but DOES find scalar assignments inside
Select Case blocks, inform the developer:

```
[Understand] Function "{function_name}" has 0 Array6 assignments.
             Found {N} scalar base rate assignments (baseRate = {value}).
             Auto LOB base rates use scalar assignments, not Array6 tables.
```

#### U.8.4: Select Case Factor Table Targets (target_kind = "case_label")

**When to use:** CR describes changing a specific Case value in a factor table.

1. From parser's `function.selectCases[]`, find the Select Case block
that contains the target case value:

```
For each selectCase in function.selectCases:
  For each case_entry in selectCase.cases:
    IF str(target_case_value) in case_entry.labels:
      Match found at line {case_entry.line}
      case_block_lines = {case_entry.line} to {case_entry.endLine}
```

2. The parser's case structure gives us EXACT nesting without depth-tracking
regex. If the target case_value appears at multiple nesting levels:

```
IF found at exactly ONE depth:
  Use that match
IF found at MULTIPLE depths:
  Show ALL to developer with parser-provided context
IF found at ZERO depths:
  Report CASE_NOT_FOUND
```

3. Claude reads the case block body to find value assignments:

```
READ lines {case_entry.line} to {case_entry.endLine}
→ Find all variable assignments
→ Track If/Else conditions (farm vs non-farm paths)
→ Record each assignment as a target_line
```

4. Show ALL values to the developer (show-don't-guess):

```
[Understand] CR {cr_id}: Case {case_value} in {function_name} has {N} value assignments:

             1. Line {L1}: {variable} = {value1}
                Context: Case 5000 > If blnFarmLocation Then (farm path)

             2. Line {L2}: {variable} = {value2}
                Context: Case 5000 > Else (non-farm path)

             The change request says change from {old_value} to {new_value}.
             Which value(s) should be changed?
               a) Only line {L1} (matches old_value)
               b) Only line {L2}
               c) Both lines
               d) None (skip this CR)
```

#### U.8.5: Constant Targets (target_kind = "constant")

**When to use:** CR targets a module-level or function-local constant.

1. From parser's file-level `constants[]`, find the target constant:

```
For constant in parser_output.constants:
  IF constant.name matches CR's target:
    Record: line, current value, type
```

2. For function-local constants, use `function.localConstants[]`.

3. For insertion CRs (adding new constants), find the insertion point:

```
last_constant_line = max(c.line for c in parser_output.constants)
first_function_line = min(f.startLine for f in parser_output.functions)
insertion_point = last_constant_line  # Insert after the last constant
```

#### U.8.6: Code Block Targets (target_kind = "code_block")

**When to use:** CR describes adding new code blocks (structure_insertion).

1. Use parser's `controlFlow[]` and `selectCases[]` to find the insertion point.

2. Claude reads the surrounding code to determine exact placement:

```
READ lines around the insertion point (10 lines above, 10 below)
→ Where should the new code go?
→ What patterns do adjacent blocks follow?
```

#### U.8.7: Endorsement Routing Targets

**When to use:** CR describes adding or modifying endorsement/option routing.

1. Parse the CalcOption file with `vb-parser parse`:

```
{vb_parser} parse {codebase_root}/{calcoption_file}
```

2. Extract the routing Select Case structure from parser output.

3. Claude reads the routing structure to build the dispatch map:

```
For each selectCase in calcoption_parse.functions:
  If function contains "CalcOption" routing:
    Record: category → option_code → function mapping
```

4. For new endorsements, determine insertion point from the parser's
Select Case end lines.

5. Check for duplicate option codes in the existing routing.

#### U.8.8: Vehicle Type Functions (Auto LOBs)

**When to use:** CR targets Auto LOB base rates.

1. From the parser's function roster, find per-vehicle-type functions:

```
For func in function_index:
  IF func.name matches "GetBasePrem_*" or "GetBasePremium_*":
    vehicle_type = extract_suffix(func.name)
    Record: {vehicle_type, function_name, start_line}
```

Auto LOBs have 7 vehicle types: PPV, Motorcycle, Motorhome, Trailer,
Snowmobile, ATV, Commercial. The parser identifies these by function name
pattern — Claude verifies the business meaning.

---

### Step U.9: Detect Hazards

**Action:** Scan parser structural data and Claude's code reading to detect
hazards that affect how the Change Engine should handle edits.

Hazards are detected from a combination of parser data (structural) and
Claude's code reading (semantic).

#### Parser-Detected Hazards (structural — no code reading needed):

```
HAZARD: mixed_rounding
  Trigger: Function has Array6 calls with BOTH integer-only and decimal args
  Source: parser function.calls[] where name=Array6 and parentContext=assignment
  Detection:
    has_integer = any(all(is_integer(a) for a in c.args) for c in rate_calls)
    has_decimal = any(any("." in a for a in c.args) for c in rate_calls)
    IF has_integer AND has_decimal: HAZARD

HAZARD: arithmetic_expressions
  Trigger: Any Array6 arg contains arithmetic operators (+, -, *, /)
  Source: parser function.calls[] args values
  Detection: any(has_arithmetic(arg) for call in rate_calls for arg in call.args)

HAZARD: multi_line_array6
  Trigger: Parser reports a call spanning multiple lines (endLine > startLine)
  Source: parser function.calls[] line vs endLine (if available)
  Note: Roslyn handles line continuation transparently — this is rare in
  parser output but worth flagging when detected

HAZARD: dual_use_array6
  Trigger: Function has BOTH assignment Array6 AND condition/argument Array6
  Source: parser function.calls[] — both parentContext=assignment AND
          parentContext in (argument, condition) for Array6 calls
  Detection: has_rate AND has_test calls

HAZARD: nested_depth_3plus
  Trigger: Select Case nesting depth >= 3
  Source: parser function.selectCases[] — count nested selectCases
  Detection: Walk parser selectCase structure, track depth

HAZARD: goto_labels
  Trigger: Function contains GoTo statements
  Source: parser function.controlFlow[] where kind="GoTo"
  Detection: any(cf.kind == "GoTo" for cf in function.controlFlow)

HAZARD: dead_code_nearby
  Trigger: Adjacent function has 0 call sites in Pattern Library
  Source: pattern-library.yaml functions[name].call_sites
  Detection: Check functions within ±200 lines by line distance
```

#### Claude-Detected Hazards (semantic — require code reading):

```
HAZARD: const_rate_values
  Trigger: Function-local Const declarations that look like rate values
  Source: Claude reads localConstants from parser, examines names/values
  Detection: Claude judges whether Const is a rate value vs config constant

HAZARD: duplicate_content
  Trigger: Same Array6 content appears on multiple lines in the function
  Source: parser function.calls[] — multiple calls with identical args
  Detection: Compare args arrays across all Array6 assignment calls
  Impact: Edit tool needs context_above/context_below for disambiguation

HAZARD: all_paths_must_change
  Trigger: CR says "apply to all territories" and function has N dispatch paths
  Source: Claude interprets CR scope vs parser's total_paths count
  Detection: If CR scope is "all" and total_paths > 1, flag this hazard

HAZARD: dat_file_function
  Trigger: Function uses GetPremFromResourceFile instead of inline rate values
  Source: parser function.calls[] — presence of GetPremFromResourceFile
  Detection: any(c.name == "GetPremFromResourceFile" for c in function.calls)
  Impact: CR targeting this function CANNOT be fulfilled by code edits

HAZARD: stored_field_propagation
  Trigger: A function called from the target takes a premium/subtotal parameter
           as ByVal AND stores it to an object field (e.g., obj.PREMIUMCOMP = value).
           Other functions later read that stored field to compute totals or display.
  Source: Parser on the CALLED function — look for assignments to object fields
          (pattern: {object}.{FIELD} = {parameter_or_derived_value})
  Detection:
    1. For each function call in the target that passes a premium/subtotal variable:
       a. Run parser on the called function
       b. Check if the parameter is ByVal (parser gives parameter modifiers)
       c. Read the function body — scan for obj.FIELD = assignments using the parameter
    2. If found, grep the codebase for readers of that field name
    3. If a "Totals" function or display function reads the field, FLAG this hazard
  Impact: Moving code that changes the premium BEFORE vs AFTER this call will cause
          the stored field to have a different value. The fix may be correct locally
          but break the Totals/display downstream.
  Record: {
    type: "stored_field_propagation",
    severity: "HIGH",
    storing_function: "{function that stores to field}",
    stored_field: "{field name, e.g., PREMIUMCOMP}",
    stored_from_param: "{parameter name}",
    param_is_byval: true,
    field_readers: ["{list of functions that read this field}"],
    totals_function: "{function that aggregates stored fields, if found}",
    impact: "Reordering code around this call changes what value gets stored"
  }

HAZARD: hidden_consumer
  Trigger: A function called from the target has side effects that other functions
           depend on — but the dependency is invisible from the caller's perspective.
           This is the GENERALIZED form of stored_field_propagation.
  Subtypes:
    a. stored_field — Function stores parameter to object field (see above)
    b. collection_mutation — Function adds to a shared array/collection (e.g.,
       AddToArray, AddToDiscountArray) that is later read for display or totals
    c. global_state — Function modifies a module-level variable read elsewhere
    d. byref_output — Function has ByRef output parameters that the caller
       doesn't capture (but another function in the chain does)
  Source: Parser on called functions + Claude semantic reading
  Detection: For every function call in the target that ISN'T a pure value return:
    1. Run parser on the called function
    2. Read the function body — look for:
       - Object field assignments (obj.FIELD = ...)
       - Collection additions (AddToArray, .Add, ReDim Preserve)
       - Module-level variable writes
       - ByRef output parameters
    3. If any found, trace who reads the modified state
  Impact: The plan MUST account for all consumers of the side effect, not just
          the direct return value. Reordering calls changes what consumers see.
  Record: {
    type: "hidden_consumer",
    subtype: "{stored_field|collection_mutation|global_state|byref_output}",
    severity: "HIGH",
    side_effect_function: "{function with side effects}",
    side_effect_detail: "{what it modifies}",
    consumers: ["{functions that read the modified state}"],
    impact: "{what breaks if the call order changes}"
  }
```

Record all hazards in the CR's `understanding.hazards[]` list.

---

### Step U.10: Check Caller Chain

**Action:** For each CR's target function, verify that the caller doesn't
override, discard, or transform the return value after it comes back.

**Why this matters:** A fix inside a callee function is useless if the caller
overwrites the result. This is not hypothetical — it happens with post-processing
loops and conditionals.

1. Find the immediate caller from the call_chain (Step U.3):

```
caller_name = call_chain[-2].caller  # The function that calls the target
caller_file = call_chain[-2].file
```

2. If the caller is in a different file, run parser on that file:

```
{vb_parser} function {codebase_root}/{caller_file} {caller_name}
```

3. From the caller's parser output, find where the target function is called:

```
call_site = [c for c in caller.calls if c.name == target_function_name]
result_variable = call_site[0].assignmentTarget  # What variable stores the result
```

4. Claude reads the caller's body AFTER the call site to look for competing writes:

```
READ lines {call_site.line + 1} to {caller.endLine}
→ Scan for assignments to result_variable
→ Determine: conditional or unconditional?
→ Detect ByRef parameter hazards (passing result_variable to another function)
```

5. Record caller analysis:

```yaml
caller_chain_summary: "Return value multiplied by location_factor downstream"
# Or if problems found:
caller_chain_summary: |
  WARNING: Caller overwrites result at line {L} (unconditional).
  Fix inside target function will be NULLIFIED unless caller is also fixed.
```

6. **Transitive caller check:** Walk up the call chain a maximum of 3 levels:

```
For level in 0..2:
  Check caller at this level for competing writes
  IF risk is HIGH: STOP — found the problem
  IF no more callers: STOP — reached top of chain
  Move up: caller becomes the new target
```

7. **ByRef parameter detection:** After the call site, check for function calls
that pass result_variable as an argument:

```
For each subsequent call in caller body:
  IF result_variable appears as an argument:
    Check callee's parameter list from parser
    IF parameter is ByRef: FLAG as byref_hazard
```

8. **Stored field / hidden consumer detection (CRITICAL):** For every function
call in the target that passes a premium, subtotal, or accumulator variable:

```
For each call in target function body that receives result_variable or intSubTotal:
  callee_name = call.name
  callee_file = find file containing callee (may be OUTSIDE carrier repo — trace it)

  # Parse the called function (even if in shared TBW framework)
  callee_data = {vb_parser} function {callee_file} {callee_name}

  # Check 1: Is the premium parameter ByVal?
  param = find parameter matching the passed variable
  IF param.modifier == "ByVal":
    # The caller's variable is NOT modified — but the callee may STORE the value

  # Check 2: Does the callee store to an object field?
  READ callee body — look for patterns:
    - {object}.{FIELD} = {param_or_derived}  (e.g., oVeh.PREMIUMCOMP = adjusted)
    - {object}.{FIELD} = {expression using param}
  IF found:
    stored_field = FIELD name
    # Check 3: Who reads this field?
    GREP codebase for stored_field name (e.g., "PREMIUMCOMP")
    readers = functions that access obj.{stored_field}
    # Check 4: Is there a Totals/aggregation function?
    totals_funcs = [r for r in readers if "Total" in r.name or "Sum" in r.name]

    FLAG as stored_field_propagation hazard (see Step U.9 schema)

  # Check 3: Does the callee add to a shared collection?
  READ callee body — look for:
    - AddToArray, .Add, ReDim Preserve, collection manipulations
  IF found:
    FLAG as hidden_consumer hazard, subtype: collection_mutation

  # Check 4: Does the callee modify module-level state?
  READ callee body — look for assignments to variables NOT in parameter list
    and NOT declared locally (Dim)
  IF found:
    FLAG as hidden_consumer hazard, subtype: global_state
```

**This step traces BEYOND the carrier boundary.** If the callee lives in
`Cssi.Net/Components/` or another shared module, follow it. Use the parser
on the shared file — it works on any .vb file. This is how ticket 21333's
stored field bug was found: the function was in TbwIQCommon, 3 levels deep.

8. When `risk` is HIGH or MEDIUM, surface prominently:

```
CALLER ANALYSIS WARNING (CR-{id}):
  Target function: {target_name} (fix at line {L})
  Caller function: {caller_name} (lines {start}-{end})
  PROBLEM: Caller overwrites result at line {L2} (unconditional)
  The fix inside {target_name} will be NULLIFIED unless the caller is also fixed.
  → Plan agent MUST produce an additional intent for the caller.
```

---

### Step U.11: Build FUBs (Function Understanding Blocks)

**Action:** For every CR that targets a function, build a Function Understanding
Block combining parser structure with Claude's semantic reading.

FUBs transform structural data into a "how-to guide" for downstream agents.

#### U.11.1: Build Branch Tree from Parser

Convert the parser's `selectCases[]` and `controlFlow[]` into a compressed
structural outline:

```
For each selectCase in function.selectCases:
  node = {
    type: "Select Case",
    variable: selectCase.expression,
    line: selectCase.line,
    depth: (computed from nesting),
    branches: []
  }
  For each case_entry in selectCase.cases:
    branch = {
      case: join(case_entry.labels, ", ") or "Else",
      line: case_entry.line
    }
    # Classify leaf content using parser calls within case range
    calls_in_case = [c for c in function.calls
                     if case_entry.line <= c.line <= case_entry.endLine]
    IF any(c.name == "Array6" for c in calls_in_case):
      branch.leaf = "Array6 assignment ({argCount} values)"
    ELIF any(c.parentContext == "statement" for c in calls_in_case):
      branch.leaf = "function call"
    ELSE:
      # Check assignments in this range
      assigns_in_case = [a for a in function.assignments
                         if case_entry.line <= a.line <= a.endLine]
      IF assigns_in_case:
        branch.leaf = "assignment statement"

    node.branches.append(branch)

  tree.append(node)
```

For If/ElseIf/Else blocks from `controlFlow[]`:

```
For each cf in function.controlFlow:
  IF cf.kind in ("If", "ElseIf", "Else"):
    node = {
      type: cf.kind,
      condition: cf.expression (truncated to 80 chars),
      line: cf.line,
      depth: (computed from nesting),
      children: []
    }
```

**Truncation:** Top 3 levels max. If deeper, add
`"... ({N} more branches omitted)"`.

#### U.11.2: Validate Branch Tree

After building the branch tree, sanity-check it:

```
CHECK 1: Non-trivial functions (>20 non-comment lines) should have branch nodes.
  IF no branch nodes: WARN "No branch nodes found — verify function boundaries"

CHECK 2: All line references within function range.
  IF any branch line < function.startLine or > function.endLine:
    WARN "Branch tree line {L} outside function range"
```

If warnings, include them as `branch_tree_warnings` in the FUB.

#### U.11.3: Extract Adjacent Context

Capture lines immediately surrounding the CR's target location:

```
For value-change CRs: 3 lines above + 3 lines below the first target line
For insertion CRs: 5 lines above + 5 lines below the insertion point

READ the relevant lines from the source file.
Record as: adjacent_context: {above: [{line, content}], below: [{line, content}]}
```

#### U.11.4: Collect Nearby Function Status

Provide lightweight alive/dead signals for functions near the target.

```
IF Step U.8.7 ran code pattern discovery for this CR:
  Set canonical_patterns_ref = "code_patterns" (pointer, no duplication)
ELSE:
  Query pattern-library.yaml for target function + 2 nearest by line distance
  Record: name, call_sites, status (ACTIVE/DEAD/HIGH_USE), line_start
```

#### U.11.5: Find Related Functions

Functions adjacent to the target that share the same business domain:

```
For func in function_index:
  IF func.name != target_function AND shares_keyword(func.name, target_function):
    Record as related function with relationship "same_category"
```

Keywords are extracted from the target function name:
`"GetLiabilityBundlePremiums"` → keywords = ["Liability"]

#### U.11.6: Find Peer Functions (Template References)

For downstream Change Engine — functions with similar structure that can serve
as templates:

```
For func in function_index:
  IF func shares parameter types AND similar complexity:
    Record as peer function with similarity note
```

#### U.11.7: Assemble FUB

Combine all sub-step outputs:

```yaml
fub:
  function_name: "{name}"
  file: "{source_file}"
  start_line: {parser startLine}
  end_line: {parser endLine}
  parameters: [{name, type, modifier}]   # From parser
  return_type: "{parser returnType}"
  total_lines: {parser lineCount}
  branch_tree: [...]                      # From U.11.1
  branch_tree_warnings: [...]             # From U.11.2 (only if issues)
  hazards: [...]                          # From U.9
  adjacent_context: {above, below}        # From U.11.3
  canonical_patterns_ref: "..."           # From U.11.4 (or null)
  nearby_functions: [...]                 # From U.11.4
```

#### U.11.8: FUB Deduplication

Multiple CRs targeting the SAME function share a single FUB.

```
fub_cache = {}  # key = (file, function_name) → first CR ID

For each CR:
  cache_key = (source_file, function_name)
  IF cache_key in fub_cache:
    This CR gets a lightweight pointer:
    fub_ref: "{first_cr_id}"
    adjacent_context_override: {this CR's own context around its target}
  ELSE:
    Generate full FUB
    fub_cache[cache_key] = cr_id
```

---

### Step U.12: Enrich Codebase Profile

**Action:** While function data is in memory, extract reusable knowledge and
persist to `codebase-profile.yaml`.

**Trigger:** Runs for every CR with a resolved target function. Skipped if
`codebase-profile.yaml` does not exist.

#### U.12.1: Factor Cardinality

For each CR that targets a function containing Select Case blocks, extract
cardinality metadata from the parser's selectCases[]:

```
For each selectCase in function.selectCases:
  cardinality = {
    function: function_name,
    case_variable: selectCase.expression,
    count: len(selectCase.cases),
    value_type: classify_labels(selectCase.cases),
    has_case_else: any(c.kind == "else" for c in selectCase.cases),
    provenance: "understand",
    discovered_at: timestamp
  }
```

#### U.12.2: Rule Dependency Detection

Detect function pairs with business rule relationships:

```
Pattern 1: Validate* + Get*/Set* with same domain noun
  IF function_name starts with "Validate":
    noun = function_name.replace("Validate", "")
    Search function_index for functions containing noun

Pattern 2: Direct call detection
  For each call in function.calls:
    IF call.name is in function_index:
      Record: call_dependency between function_name and call.name
```

#### U.12.3: Provenance and Merge Rules

All enriched entries get `provenance: "understand"` and `discovered_at: timestamp`.

Merge rules when writing to codebase-profile.yaml:
- Entries with `provenance: "investigation"` or `provenance: "init"` are NEVER
  overwritten (more authoritative).
- Entries with `provenance: "analyzer"` or `provenance: "understand"` are updated.
- New entries are appended.

---

## 6. SUB-AGENT DISPATCH

The Understand agent MAY spawn sub-agents for per-function analysis when the
workload exceeds safe thresholds. This is the agent's internal optimization —
the orchestrator does not control it.

### When to Use Sub-Agents

**Complexity heuristic — spawn sub-agents when ANY of these are true:**

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| Unique target functions across all CRs | >8 | Parser handles structural scan, but Claude reading still expensive |
| Any target source file exceeds | 8,000 lines | Large files strain context window |
| Total CRs | >8 | Many CRs = many function bodies to read |

**When below threshold:** Run Steps U.6-U.11 inline (single context window).

### Architecture

```
┌───────────────────────────────────────────────────────────┐
│  UNDERSTAND AGENT (coordinator)                            │
│                                                            │
│  Steps U.1-U.5: Parser Phase (always inline)               │
│  (Lightweight — subprocess calls, no code reading)         │
│                                                            │
│  Steps U.6-U.11: Claude Phase                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  IF complexity threshold MET:                        │  │
│  │    For each unique {function, source_file} pair:     │  │
│  │      Spawn "Function Reader" sub-agent               │  │
│  │      Sub-agent reads ONE function body               │  │
│  │      Sub-agent runs Steps U.7-U.11 for that function │  │
│  │      Sub-agent writes fub-{function}.yaml to disk    │  │
│  │                                                      │  │
│  │  IF complexity threshold NOT MET:                    │  │
│  │    Run Steps U.6-U.11 inline (current behavior)      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  Step U.12: Profile enrichment (always inline)             │
│  Output Phase: Write code_understanding.yaml               │
│  (Always inline — uses FUB outputs, no large reads)        │
└───────────────────────────────────────────────────────────┘
```

### Concurrency Limit

**Max 2 concurrent sub-agents** (RAM constraint — the Understand agent itself
occupies 1 agent slot, leaving 2 of the 3-agent max). Spawn sub-agents
sequentially or in pairs. Do NOT exceed 2 at a time.

### Sub-Agent Prompt Template

Each Function Reader sub-agent receives a focused prompt:

```
You are a Function Reader sub-agent for the IQ Rate Update Plugin Understand agent.

TASK: Read ONE function, identify targets, and build a FUB.

CARRIER ROOT: {root_path}
WORKSTREAM: .iq-workstreams/changes/{workstream-name}/
SOURCE FILE: {source_file_path}
FUNCTION: {function_name} (lines {start}-{end})
CR(s): {cr_ids targeting this function}
PARSER BINARY: {vb_parser_path}

PARSER DATA (pre-computed by coordinator):
  Function detail JSON: {inline the vb-parser function output}

Read the Understand agent spec sections you need:
  .iq-update/agents/understand.md — Steps U.7-U.11

For each CR targeting this function:
  1. Read the source file between lines {start} and {end}
  2. Match CRs to parser-identified targets (Step U.8)
  3. Detect hazards (Step U.9)
  4. Check caller chain (Step U.10) — coordinator provides call_chain data
  5. Build a Function Understanding Block (Step U.11)
  6. Write the FUB to: analysis/fub-{function_name}.yaml

Use this format for the FUB output file:
  function_name: "{function_name}"
  source_file: "{source_file}"
  line_range: [{start}, {end}]
  cr_targets:
    - cr_id: "cr-NNN"
      target_lines: [...]
      understanding: {...}
  fub: {from Step U.11}

CR details:
{paste each cr-NNN.yaml content for CRs targeting this function}

IMPORTANT:
  - Write ONLY to analysis/fub-{function_name}.yaml
  - Do NOT modify any source code files
  - Do NOT update manifest.yaml
  - If you encounter a question for the developer, write it to the FUB file
    as: pending_questions: ["question text"]
```

### Crash Resilience

Sub-agent results are written to disk as individual YAML files:
`analysis/fub-{function_name}.yaml`

If a sub-agent crashes or times out:
1. Check if the FUB file exists on disk
2. If file exists and is valid YAML: sub-agent succeeded (use the file)
3. If file is missing or empty: retry once with a new sub-agent
4. If retry also fails: fall back to inline processing for that function
5. Log the failure in manifest error_log

### Coordinator Collation

After all sub-agents complete (or fall back to inline):

```
1. Read all fub-{function}.yaml files from analysis/
2. Collect any pending_questions from sub-agents:
   - Present ALL pending questions to the developer in one batch
   - Record answers in developer_decisions
   - If answers change the analysis: re-run the affected sub-agent
3. Merge FUB data into the unified code_understanding.yaml
4. Continue with Output Phase
```

### What Sub-Agents Do NOT Handle

Sub-agents only handle Steps U.7-U.11 (semantic reading + FUB building).
The coordinator always handles:
- Parser Phase (Steps U.1-U.5) — needs full project context
- Source file resolution (Step U.4.1) — needs file reference map
- Reverse lookup (Output Phase) — needs province-wide .vbproj scan
- Cross-province check — needs config.yaml
- Profile enrichment (Step U.12) — needs cross-CR view
- Output writing — needs everything aggregated

---

## 7. OUTPUT PHASE

### Step U.13: Resolve Rounding Mode

**Action:** For CRs with `domain_hints.rounding_hint: "auto"`, resolve rounding
from the actual parser-reported Array6 argument values.

**Guard:** Step U.13 applies ONLY to CRs whose `extracted` include a `factor`
and `domain_hints.rounding_hint: "auto"`. Skip all other CRs.

1. For each target_line, the rounding was already classified in Step U.8.2
from parser args. Aggregate per-CR:

```
ROUNDING AGGREGATION
────────────────────────────────────────────────────────────

IF ALL target_lines have rounding = "banker":
    cr.rounding_resolved = "banker"

IF ALL target_lines have rounding = "none":
    cr.rounding_resolved = "none"

IF target_lines have a MIX of "banker" and "none":
    cr.rounding_resolved = "mixed"
    Include per-line rounding in target_lines[].rounding

IF any target_line has rounding = "review":
    cr.rounding_resolved = "review"
    Flag for developer
```

2. Cross-check against Intake's rounding_hint:

```
IF rounding_hint matches rounding_resolved: confirmed, proceed silently
IF rounding_hint disagrees:
  [Understand] Rounding cross-check MISMATCH for {cr_id}:
               Intake hint: {rounding_hint}
               Value-based analysis: {rounding_resolved}
               Using value-based result. Please confirm.
```

3. Report rounding resolution:

```
[Understand] Rounding for {cr_id} ({function_name}):
             {N} Array6 lines found:
               {M} lines with integer values → banker rounding
               {K} lines with decimal values → no rounding
               {J} lines all zeros → skip
             CR-level rounding: {rounding_resolved}
```

### Step U.14: Run Reverse Lookup for Hidden Blast Radius

**Action:** For each shared module targeted by CRs, scan ALL .vbproj files in
the province to find references NOT in the developer's target list.

**This MUST run BEFORE building files_to_copy** because the reverse lookup
discovers additional .vbproj files that need reference updates.

1. Identify shared modules with CRs:

```
shared_targets = set()
For each CR:
  IF file_reference_map[source_file].classification in ("shared_module", "cross_lob"):
    shared_targets.add(source_file)
```

2. For each shared module, use `vb-parser project` on ALL .vbproj files in
the province to find references:

```
For each vbproj file in the province (glob for Cssi.IntelliQuote.{prefix}*.vbproj):
  project_output = {vb_parser} project {vbproj}
  For each compiled_file in project_output.compiledFiles:
    IF basename(compiled_file) matches any shared_target:
      Record this vbproj as referencing the shared module
```

3. Compare against target_folders:

```
For each referencing vbproj NOT in target_folders:
  FLAG as hidden_blast_radius
```

4. Report to developer:

```
IF hidden references found:
  [Understand] REVERSE LOOKUP WARNING: {shared_module} is referenced by
               {N} projects NOT in your target list:
               {list of projects}

               Options:
                 a) Add missing projects to target list (recommended)
                 b) Acknowledge and proceed
                 c) Abort

IF all accounted for:
  [Understand] Reverse lookup: All {N} projects referencing {shared_module}
               are in the target list. No hidden blast radius.
```

### Step U.15: Check for Cross-Province Shared Files

**Action:** Verify no CR targets a cross-province shared file.

```
cross_province_files = config.cross_province_shared_files

For each CR:
  IF source_file matches any cross_province_file:
    ERROR: CR targets cross-province shared file — BLOCKED
    Cannot auto-modify files used by ALL provinces.
```

### Step U.16: Build files_to_copy List

**Action:** Assemble the list of Code/ files needing new dated copies, with
.vbproj reference updates. Includes references from the reverse lookup.

1. Collect unique source → target mappings from CRs:

```
files_to_copy = {}
For each CR with needs_copy == true:
  IF source_file not in files_to_copy:
    files_to_copy[source_file] = {
      source, target, source_hash, target_exists,
      shared_by, change_requests_in_file, vbproj_updates
    }
  files_to_copy[source_file].change_requests_in_file.append(cr_id)
```

2. For each file, find ALL .vbproj references (including reverse lookup):

```
For each source_file in files_to_copy:
  For each vbproj that references source_file (from reverse lookup):
    Compute old_include and new_include (date replacement)
    Add to vbproj_updates
```

3. Check target file existence and compute target hash:

```
For each file_to_copy entry:
  target_path = codebase_root + "/" + entry.target
  IF target_path exists on disk:
    target_hash = sha256(read_binary(target_path))
    IF target_hash == entry.source_hash:
      entry.target_exists = true   # Untouched copy already done
      entry.needs_copy = false     # No need to re-copy
    ELSE:
      entry.target_exists = true   # Modified by someone
      WARN: "Target already exists with different content"
  ELSE:
    entry.target_exists = false    # Normal case: needs copy
```

4. Extract date from filenames for source/target naming:

```
Date extraction: look for YYYYMMDD pattern before .vb extension
  mod_Common_SKHab20250901.vb → date = "20250901"
  CalcOption_SKHOME20250901.vb → date = "20250901"
```

### Step U.17: Compute Blast Radius

**Action:** Calculate the risk level and build the blast radius section.

```
RISK LEVEL CALCULATION
────────────────────────────────────────────────────────────

Start at LOW.

Upgrade to MEDIUM if ANY of:
  - 3+ CRs in a shared module
  - Any cross_lob files affected
  - Any SHARDCLASS files affected
  - Mixed rounding in any CR
  - Any CR flagged for developer review

Upgrade to HIGH if ANY of:
  - Cross-province shared file warnings
  - Hidden blast radius (reverse lookup found unaccounted projects)
  - 10+ CRs total
  - Any CR targeting a file with 3,000+ lines
  - Rule dependency warnings
```

### Step U.18: Code Pattern Discovery (for qualifying CRs)

**Action:** For CRs that involve code insertion or logic changes, discover
established code patterns so the Change Engine uses proven approaches.

**Trigger guard — when to run:**

```
TRIGGER TABLE
────────────────────────────────────────────────────────────
CR Type                        Trigger?   Reason
Value changes (Array6, factors) NO        Pure value substitution
Limit value changes             NO        Pure value substitution
New coverage type               MAYBE     Only if involves function calls
Eligibility/validation rules    YES       Accesses runtime objects
Alert messages                  YES       Calls alert functions
New endorsement/option          YES       Must follow existing file structure
New liability option            YES       Accesses liability collections
Unknown/general                 YES       Always discover when uncertain
────────────────────────────────────────────────────────────
```

If the CR does NOT match any trigger, skip Step U.18 entirely.

#### U.18.1: Check Investigation Findings

Before searching, check for saved `/iq-investigate` findings:

```
.iq-workstreams/changes/{workstream}/investigation/finding-*.yaml
```

If a finding matches the CR's access need, use it directly.

#### U.18.2: Lookup Pattern Library

For each identified access need, query `.iq-workstreams/pattern-library.yaml`:

1. `accessor_index[keyword]` → ranked accessor patterns with call counts
2. `functions[name]` → call_sites + status + file + line
3. Separate results into ACTIVE/HIGH_USE (safe) and DEAD (warn, never recommend)

**Fallback:** If pattern-library.yaml doesn't exist, grep target files directly.

#### U.18.3: Find Peer Functions

In the function index, find functions that are peers of the CR's target:

1. Similar name prefix
2. Same parameter types (from parser)
3. Keywords from CR description

Cross-reference with Pattern Library for call counts. Sort by call_sites
descending — HIGH_USE peers are the best references.

#### U.18.4: Extract Code Snippets

For active peer functions (call_sites > 0):
- Read full function body (truncate to 30 lines if longer)
- Include key access patterns

For dead-code functions (call_sites == 0):
- Include ONLY the signature + "DEAD CODE" warning
- Do NOT include body (prevents Change Engine from copying dead patterns)

#### U.18.5: Canonical Pattern Selection

```
HIGH confidence (proceed silently):
  Clear winner: 3+ call sites, no close second

MEDIUM confidence (include in Gate 1 review):
  2+ active patterns with similar call counts

LOW confidence (BLOCK — ask developer):
  Zero active patterns found
```

#### U.18.6: Write Code Patterns to CR

```yaml
code_patterns:
  peer_functions:
    - name: "{FunctionName}"
      file: "{file}"
      line_start: {N}
      call_sites: {N}
      dead_code: false
      snippet: |
        {function body or excerpt}
  canonical_access:
    - need: "{access_need}"
      pattern: "{established pattern}"
      call_sites: {N}
      confidence: "{high|medium|low}"
  warnings:
    - "{FunctionName} has 0 call sites — DEAD CODE"
  developer_confirmed: {true|false}
```

### Step U.19: Write code_understanding.yaml

**Action:** Assemble all findings into the unified output artifact.

1. Combine all data structures:
   - project_map (from U.1)
   - entry_point and call_chain (from U.2, U.3)
   - file_reference_map (from U.1)
   - files_to_copy (from U.16)
   - blast_radius (from U.17)
   - Per-CR targets, understanding, FUBs (from U.6-U.11)
   - dispatch_map (from U.8.7, if present)
   - vehicle_types (from U.8.8, if Auto)
   - peer_functions (from U.11.6)

2. Write to `analysis/code_understanding.yaml` in the workstream directory.

3. Validate the written YAML:

```
{python_cmd} -c "
import yaml, sys
try:
    with open('analysis/code_understanding.yaml') as f:
        data = yaml.safe_load(f)
    assert data.get('schema_version') == '2.0'
    assert data.get('generated_by') == 'understand'
    assert 'change_requests' in data
    print('code_understanding.yaml: VALID')
except Exception as e:
    print(f'VALIDATION FAILED: {e}')
    sys.exit(1)
"
```

### Step U.20: Update Manifest

The orchestrator handles manifest updates (not the agent). However, the agent
returns a structured completion summary that the orchestrator uses:

```
[Understand] Analysis complete:

  PROJECT MAP:
    .vbproj: {vbproj_name}
    Compiled files: {N} total, {M} Code/ files
    Parser: vb-parser {version}

  ENTRY POINT:
    {main_function} in {calcmain_path}
    Calculation flow: {N} functions traced

  FILES TO COPY: {N}
    {For each file:}
    {source} → {target_basename} ({shared_by_count} LOBs)

  CRs ANALYZED: {M} of {total}
    {For each CR:}
    {cr_id}: {function_name}() in {file_basename}
             lines {start}-{end}, {target_count} targets
             target_kind: {target_kind}
             rounding: {rounding_resolved}

  DEVELOPER CONFIRMATIONS NEEDED: {K}
    {pending confirmations, if any}

  REVERSE LOOKUP: {status}
    {All accounted / N warnings}

  BLAST RADIUS:
    Risk level: {risk_level}
    Reason: {risk_reason}

  Output: analysis/code_understanding.yaml

  Next: Plan agent will build intents and execution order.
```

---

## 8. EDGE CASES AND RULES

### Case 1: Select Case with Range Expressions

VB.NET Case syntax is richer than simple value matching:

```vb
Case 0 To 25       ' Range
Case Is > 100      ' Comparison
Case "val1", "val2" ' Multi-value
Case 5000           ' Exact value
Case "5000"         ' String-quoted numeric
```

The parser reports all case labels with their `kind` (value, range,
comparison, else). When a CR specifies `case_value: 50`, search for:
- Exact match: `Case 50`
- Range containing 50: `Case 26 To 50` (parser labels contain "26", "50")
- Multi-value containing 50: `Case 45, 50, 55`

Show all matches. Let the developer confirm.

### Case 2: Two Arrays on Adjacent Lines (Same Case Block)

```vb
Case Else
    varRates = Array6(18, 6.74, 7.04, 7.04)
    excessRates = Array6(1, 0.41, 0.44, 0.44)
```

Both are Array6 assignment calls. Parser reports them as separate entries
with different `assignmentTarget` values. The CR context determines which
to modify (or both). List both as separate target_lines.

### Case 3: Array6 with Arithmetic Expressions

```vb
varRates = Array6(30 + 10, 25.5, 40, 50)
```

Parser reports args as: `["30 + 10", "25.5", "40", "50"]`.
The argument `"30 + 10"` contains arithmetic. Flag `has_expressions: true`
and compute `evaluated_args` using safe arithmetic evaluation:

```
evaluated_args = [safe_eval("30 + 10")=40, 25.5, 40, 50]
```

If eval fails, flag for manual review.

### Case 4: Source File Already at Target Date

The .vbproj already references `mod_Common_SKHab20260101.vb`:
- `source_file = target_file` (same date)
- `needs_copy: false`
- Parse and analyze normally

### Case 5: Multiple CRs Targeting the Same Function

Two CRs target `SetDisSur_Deductible` for different Case values (5000, 2500).
The parser gives function boundaries ONCE. Each CR searches within those
boundaries for its specific target. FUB is shared via `fub_ref` (deduplication).

### Case 6: Cross-LOB File Discovery

`Option_SewerBackup_SKHome20231001.vb` is compiled by both Home and Condo
(.vbproj references from both). Parser's project command reveals this. If the
CR needs a new dated copy, vbproj_updates must include BOTH .vbproj files.

### Case 7: File Referenced by .vbproj but Missing from Disk

Parser's project output has `exists: false` for this entry. Report error.
The file may not have been copied by IQWiz yet.

### Case 8: Nova Scotia SharedClass/ Directory

NS uses "SharedClass" instead of "SHARDCLASS". Read config.yaml for the
`shardclass_folder` value. Use it in all SHARDCLASS-related classification.

### Case 9: Const Declaration Rate Values

```vb
Const ACCIDENTBASE = 200
```

Parser's file-level `constants[]` or function-level `localConstants[]`
captures these. Record as target_kind = "constant".

### Case 10: CR Targets a New File

A new endorsement requires `Option_NewEndorsement_SKHome20260101.vb`:
- `source_file: null` (no existing file)
- `needs_copy: false` (Change Engine will CREATE this file)
- `needs_new_file: true`
- Provide template reference from existing similar file:

```yaml
template_reference: "Saskatchewan/Code/Option_Bicycle_SKHome20220502.vb"
template_reason: "Similar endorsement option file in same LOB"
```

### Case 11: Partial Module Spanning Multiple Files

VB.NET `Partial Public Module` splits code across files. If a function
is not found in the specified file, the Partial Module fallback (Step U.6)
searches all files compiled by the same .vbproj using additional parser
calls.

### Case 12: Auto Base Rate Functions Use Scalar Values

Auto LOBs (mod_Algorithms) use `baseRate = 66.48` instead of Array6.
The parser's function.assignments[] captures these. When a CR targets an
Auto function and the parser finds 0 Array6 assignment calls:

```
[Understand] Function "{name}" has 0 Array6 assignments.
             Found {N} scalar assignments in Select Case blocks.
             Auto LOB base rates use scalar assignments, not Array6.
             Setting target_kind = "assignment"
```

### Case 13: DAT File Functions (Not Editable)

Parser's function.calls[] reveals `GetPremFromResourceFile` calls.
Functions using DAT file lookups cannot have their rate values edited
in source code. Flag for developer:

```
[Understand] WARNING: {function_name} uses DAT file lookups
             (GetPremFromResourceFile). Rate values are NOT in source code.
             This CR should be marked OUT_OF_SCOPE.
```

### Case 14: GoTo Labels in Function

Parser's function.controlFlow[] with kind="GoTo" and function.labels[]
reports GoTo targets. Flag as hazard `goto_labels`. The Change Engine
must be careful not to insert code between a GoTo and its label.

### Case 15: Multiple Select Case Blocks in One Function

A function can have 4+ Select Case blocks. The parser's
function.selectCases[] lists ALL of them with line ranges. Show ALL blocks
with their content classification and let the developer specify which to
modify:

```
[Understand] CR {cr_id}: {function_name} has {N} Select Case blocks:

             Block 1 (lines 870-890): Deductible factors
               4 cases, Array6 assignments
             Block 2 (lines 895-930): Purchase price groups
               12 cases, Array6 assignments + excessRates assignments

             Which block(s) should be modified?
```

### Case 16: Deferred Confirmation

When the developer defers a confirmation prompt:
- Mark: `developer_confirmed: false, status: "pending_confirmation"`
- Continue processing remaining CRs
- At completion, list ALL pending CRs
- Plan agent CANNOT proceed until all CRs are confirmed or deferred

### Case 17: SHARDCLASS Files in Blast Radius

If CRs reference SHARDCLASS files (parser classification), include in blast
radius with warning:

```
[Understand] SHARDCLASS file in scope: {file}
             Shared helper class compiled by {N} LOBs.
             Changes will affect all dependent LOBs.
```

### Case 18: Conditional Compilation Attributes

If any `<Compile>` element in the .vbproj has a `Condition` attribute (rare
but possible), the parser's project output includes this. Flag:

```
[Understand] WARNING: Conditional compilation in {vbproj}:
             {file} has Condition="{condition}"
             Verify this file is active in the current build configuration.
```

---

## 9. CRITICAL RULES

### Rule 1: Parser Gives Structure, Claude Gives Meaning

**Trust the parser alone for:**
- Function boundaries (startLine, endLine) — Roslyn is authoritative
- Call inventory (which functions called, argCount, parentContext) — exact
- Select Case structure (cases, labels, nesting depth) — exact
- Assignment targets (what variable a call result is assigned to) — exact
- Argument values (literal args of any function call) — exact
- Parse errors (is the file syntactically valid) — authoritative

**Claude MUST read actual code for:**
- Semantic meaning of Select Case expressions (what is the switch variable?)
- Whether a particular Array6 call is a base rate vs adjustment factor
- Business logic flow (what does the function RETURN and how is it USED?)
- Whether two similar calls in different branches need the same update
- Comments near code that explain business rules
- Cross-function relationships and caller chain semantics

### Rule 2: NEVER Block the Pipeline

If any step fails, continue with partial results. The output artifact includes
enough data for downstream agents to proceed with what they can.

| Failure | Impact | Recovery |
|---------|--------|----------|
| Parser fails on a file | No structural data | Read file manually, flag degraded |
| CalcMain.vb not found | No calculation_flow | CR targets still resolved via parser |
| Function not found for CR | target = unresolved | Plan agent excludes from execution |
| Parse errors in target file | Structural data partial | WARN prominently, proceed |
| Sub-agent crashes | Missing FUB | Retry once, then inline fallback |

### Rule 3: Show, Don't Guess

When multiple candidates are found (functions, case blocks, values), show ALL
to the developer and ask which to modify. Never silently pick one.

### Rule 4: Skip Commented Lines

VB.NET comments start with `'` (apostrophe) or `REM`. Both are skipped by
the parser (they don't appear in calls, assignments, or selectCases). Claude
must also skip comments when reading code.

### Rule 5: Preserve VB.NET Formatting Awareness

- Line continuation: `_` (explicit) and implicit (after operators, commas,
  open parens) — Roslyn handles both transparently
- Case syntax: `Case 5000`, `Case "5000"`, `Case 0 To 25`, `Case Is <= 3000`
- Inline Case: `Case "5000" : intPrem = 19` (colon-separated)
- Partial Public Module: functions may span multiple files
- UTF-8 BOM in Visual Studio files

### Rule 6: Cross-Province Files Are NEVER Modified

Files classified as `cross_province_shared` (3+ levels of ".." in .vbproj
include path) must NEVER be targeted by CRs. If detected, flag BLOCKED.

### Rule 7: target_kind Must Be Set

Every CR's target MUST have a `target_kind` value set during understanding.
This flows through the entire pipeline:

```
code_understanding.yaml → intent_graph.yaml → capsule → Change Engine
```

Valid values: `call`, `assignment`, `constant`, `case_label`, `code_block`

### Rule 8: File Hashes for TOCTOU Protection

Every source file gets a SHA-256 hash at parse time. If the hash changes
between understanding and execution, the Change Engine must re-verify
before writing changes.

### Rule 9: Max 3 Agent Slots

The host machine has limited RAM (VS Code crashes with >3 concurrent agents).
The Understand agent occupies 1 slot. Sub-agents occupy additional slots.
Never exceed 2 concurrent sub-agents (total 3 slots).

### Rule 10: Handle All Carrier Patterns

The agent does NOT hardcode function names. It follows a universal framework:
1. Find CalcMain → from target_folders path (any carrier)
2. Extract call graph → parser reports all calls (any TBW CalcMain)
3. Resolve files → parser project tells which Code/ file each function lives in
4. Trace and understand → parser structure + Claude reading (universal)

Different carriers have different names but the same understanding process.

---

## 10. WORKED EXAMPLES

### Example A: SK Home Base Rate Increase (Array6 Rate Values)

**Input:**

```yaml
id: "cr-001"
title: "Increase SK Home base rates by 5%"
extracted:
  factor: 1.05
  scope: "all_territories"
  target_file_hint: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  target_function_hint: "GetBasePremium_Home"
domain_hints:
  rounding_hint: "auto"
```

**Parser Phase:**

Step U.1: Run `vb-parser project` on PORTSKHOME20260101.vbproj:
- 76 compiled files, 12 Code/ files
- mod_Common_SKHab20250901.vb found in .vbproj (source date: 20250901)

Step U.2: Run `vb-parser parse` on CalcMain.vb:
- Main function: TotPrem (45 lines)
- Call flow: TotPrem → CalcHabDwelling → ... → GetBasePremium_Home

Step U.3: Call chain traced:
```
TotPrem → CalcHabDwelling → GetBasePremium_Home
  (CalcMain.vb → CalcMain.vb → mod_Common_SKHab*.vb)
```

Step U.4: Run `vb-parser parse` on mod_Common_SKHab20250901.vb:
- 4,588 lines, 56 functions, 0 parse errors
- GetBasePremium_Home: lines 3380-3920, 541 lines
- File hash: sha256:a1b2c3d4...
- needs_copy: true (source 20250901 != target 20260101)

Step U.5: Run `vb-parser function mod_Common_SKHab20250901.vb GetBasePremium_Home`:
- 15 Array6 calls with parentContext=assignment, assignmentTarget=varRates
- 2 Array6 calls with parentContext=condition (IsItemInArray — skipped)
- 1 Array6 call with all-zero args (default init — skipped)
- 2 Select Case blocks: outer on p_strClassification, inner on location_factor
- 5 outer cases: Preferred, Standard, Fire Resistive, Class I, Mobile Home
- 3 inner cases per outer: Metro 1-7, Metro 8-14, Grade

**Claude Phase:**

Step U.6: Function matched — exact name "GetBasePremium_Home" in function index.

Step U.7: Claude reads Select Case expressions:
- Outer: `p_strClassification` = dwelling classification type
- Inner: location factor territory grouping

Step U.8: Parser identified 15 rate value Array6 calls. Claude verifies each:
- Line 3401: `varRates = Array6(0, 78, 161, 189, 213, 291)`
  → Parser: parentContext=assignment, assignmentTarget=varRates
  → Parser: args = ["0", "78", "161", "189", "213", "291"]
  → Claude reads context: Case "Preferred" > Case "Metro 1-7"
  → Rounding: all integers → banker

- Lines 3405-3450: similar for other territory/classification combos

- Line 3395: `varRates = Array6(0, 0, 0, 0, 0, 0)` → SKIPPED (all zeros)

Step U.9: Hazards detected:
- mixed_rounding: 12 lines integer, 3 lines decimal
- all_paths_must_change: 15 dispatch paths, CR scope = "all"

Step U.10: Caller check:
- CalcHabDwelling calls GetBasePremium_Home
- Return value stored in dwellingPremium
- No competing writes found → risk: NONE

Step U.11: FUB built with branch tree, hazards, adjacent context.

**Output Phase:**

Step U.13: Rounding resolved → "mixed" (12 banker, 3 none)
Step U.14: Reverse lookup → all 6 hab LOBs accounted for
Step U.17: Blast radius → MEDIUM (shared module, 6 LOBs, mixed rounding)
Step U.19: code_understanding.yaml written with all CR data

**Completion summary:**

```
[Understand] Analysis complete:

  PROJECT MAP: PORTSKHOME20260101.vbproj, 76 compiled files
  ENTRY POINT: TotPrem in CalcMain.vb, 12 functions traced

  FILES TO COPY: 1
    mod_Common_SKHab20250901.vb → mod_Common_SKHab20260101.vb (6 LOBs)

  CRs ANALYZED: 1 of 1
    cr-001: GetBasePremium_Home() in mod_Common_SKHab*.vb
             lines 3380-3920, 15 targets
             target_kind: call
             rounding: mixed (12 banker, 3 none)

  REVERSE LOOKUP: All 6 hab LOBs accounted for.
  BLAST RADIUS: MEDIUM

  Output: analysis/code_understanding.yaml
```

---

### Example B: Multi-CR Auto Rate Change

**Input:**

```yaml
# CR-001
id: "cr-001"
title: "Multiply AB Auto PPV base rates by 1.05"
extracted:
  factor: 1.05
  scope: "all_territories"
  target_file_hint: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
  target_function_hint: "GetFactor_BaseRate"

# CR-002
id: "cr-002"
title: "Change AB Auto $5000 deductible factor from -0.20 to -0.22"
extracted:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22
  target_file_hint: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
  target_function_hint: "SetDisSur_Deductible"

# CR-003
id: "cr-003"
title: "Change AB Auto $2500 deductible factor from -0.15 to -0.17"
extracted:
  case_value: 2500
  old_value: -0.15
  new_value: -0.17
  target_file_hint: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
  target_function_hint: "SetDisSur_Deductible"
```

**Parser Phase:**

Step U.1: Run `vb-parser project` on PORTABAuto20260101.vbproj:
- mod_Algorithms_ABAuto20250901.vb found (source date 20250901)
- needs_copy: true

Step U.4: Run `vb-parser parse` on mod_Algorithms_ABAuto20250901.vb:
- 47 functions, GetFactor_BaseRate (lines 1201-1235), SetDisSur_Deductible (lines 2108-2227)

Step U.5: Deep dive on both functions:

For GetFactor_BaseRate:
- Parser finds 4 Array6 calls, all parentContext=assignment, all decimal args
- target_kind: "call"

For SetDisSur_Deductible:
- Parser finds selectCases with case labels including "5000" and "2500"
- Parser finds assignments (scalar) inside case blocks
- target_kind: "case_label" (for both CR-002 and CR-003)

**Claude Phase:**

Step U.6: Both functions matched exactly.

Step U.7: Claude reads Select Case in GetFactor_BaseRate:
- Switch on territory (oCurrentInscoCovItem.Fields.Item(...LOCFACTOR).Value)

Step U.8:
- CR-001: 4 Array6 territory lines, all decimal → rounding: "none"
- CR-002: Case 5000 found at line 2199. Claude reads body:
  - Farm path: `dblDedDiscount = -0.2` (line 2202, matches old_value)
  - Non-farm path: `dblDedDiscount = -0.25` (line 2205, does NOT match)
  - Show both to developer → developer selects farm path only

- CR-003: Case 2500 found at line 2178. Claude reads body:
  - 3 code paths (farm/non-farm/special)
  - Show all to developer

Step U.11: FUBs built. CR-002 and CR-003 share FUB for SetDisSur_Deductible
(deduplication: CR-003 gets `fub_ref: "cr-002"`).

**Output:**

```
[Understand] Analysis complete:

  FILES TO COPY: 1
    mod_Algorithms_ABAuto20250901.vb → mod_Algorithms_ABAuto20260101.vb

  CRs ANALYZED: 3 of 3
    cr-001: GetFactor_BaseRate() — 4 targets, target_kind: call, rounding: none
    cr-002: SetDisSur_Deductible() — Case 5000 farm path, target_kind: case_label
    cr-003: SetDisSur_Deductible() — Case 2500 (3 paths), target_kind: case_label

  BLAST RADIUS: LOW (single LOB, no shared module)
```

---

### Example C: Function Not Found — Partial Module Fallback

**Input:**

```yaml
id: "cr-006"
title: "Change Option_SewerBackup premium table"
extracted:
  target_file_hint: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  target_function_hint: "Option_SewerBackup"
```

**Parser Phase:**

Step U.4: `vb-parser parse mod_Common_SKHab20250901.vb`
- 56 functions found. "Option_SewerBackup" is NOT among them.

**Claude Phase:**

Step U.6: 0 matches in target file. Partial Module fallback:

Run `vb-parser parse` on all other Code/ files in the .vbproj:
- `Option_SewerBackup_SKHome20231001.vb`: Found! `Option_SewerBackup` at lines 5-85

```
[Understand] Function "Option_SewerBackup" not found in mod_Common_SKHab*.vb.
             Found in Option_SewerBackup_SKHome20231001.vb (Partial Module).
             Redirecting CR cr-006 to this file.
```

Update CR's source_file and proceed normally.

---

### Example D: Reverse Lookup Discovers Hidden Blast Radius

**Scenario:** Developer targets Home and Condo only, but mod_Common is shared
by 6 LOBs.

**Step U.14:**

Run `vb-parser project` on ALL Saskatchewan .vbproj files:

```
Saskatchewan/Home/20260101/*.vbproj       → references mod_Common_SKHab20250901.vb ✓
Saskatchewan/Condo/20260101/*.vbproj      → references mod_Common_SKHab20250901.vb ✓
Saskatchewan/Tenant/20260101/*.vbproj     → references mod_Common_SKHab20250901.vb ✗ NOT IN TARGET
Saskatchewan/FEC/20260101/*.vbproj        → references mod_Common_SKHab20250901.vb ✗ NOT IN TARGET
Saskatchewan/Farm/20260101/*.vbproj       → references mod_Common_SKHab20250901.vb ✗ NOT IN TARGET
Saskatchewan/Seasonal/20260101/*.vbproj   → references mod_Common_SKHab20250901.vb ✗ NOT IN TARGET
```

```
[Understand] REVERSE LOOKUP WARNING: mod_Common_SKHab is referenced by 4 projects
             NOT in your target list:

             1. Saskatchewan/Tenant/20260101/Cssi.IntelliQuote.PORTSKTENANT20260101.vbproj
             2. Saskatchewan/FEC/20260101/Cssi.IntelliQuote.PORTSKFEC20260101.vbproj
             3. Saskatchewan/Farm/20260101/Cssi.IntelliQuote.PORTSKFARM20260101.vbproj
             4. Saskatchewan/Seasonal/20260101/Cssi.IntelliQuote.PORTSKSEASONAL20260101.vbproj

             Options:
               a) Add all 4 missing projects to the target list (recommended)
               b) Acknowledge and proceed
               c) Abort
```

---

### Example E: DAT File Detection

**Input:**

```yaml
id: "cr-007"
title: "Multiply SK Home base premiums by 5%"
extracted:
  target_function_hint: "GetBasePremium_Home"
```

**Step U.5:** Parser deep dive on GetBasePremium_Home reveals:

```json
{
  "calls": [
    {"name": "GetPremFromResourceFile", "line": 3401, "parentContext": "assignment"},
    {"name": "GetPremFromResourceFile", "line": 3415, "parentContext": "assignment"},
    // ... 8 total GetPremFromResourceFile calls
    {"name": "IsItemInArray", "line": 3390, "parentContext": "condition"}
    // NO Array6 calls with parentContext=assignment
  ]
}
```

0 Array6 assignment calls, 8 GetPremFromResourceFile calls → DAT file function.

```
[Understand] WARNING: CR cr-007 targets GetBasePremium_Home, but this function
             uses DAT file lookups (GetPremFromResourceFile) for base rate values.

             Found: 0 rate-bearing Array6 assignments
             Found: 8 GetPremFromResourceFile() calls

             Rate values are NOT in VB source code. This plugin cannot edit DAT files.
             Options:
               a) Mark as OUT_OF_SCOPE (skip this CR)
               b) Override — I know the rates are in code (explain where)
```

---

### Example F: Multi-Block Select Case in Snowmobile Function

**Input:**

```yaml
id: "cr-010"
title: "Multiply snowmobile deductible factors by 1.02"
extracted:
  factor: 1.02
  target_function_hint: "GetBasePrem_Snowmobile"
```

**Step U.5:** Parser reports 4 Select Case blocks in this function:

```json
{
  "selectCases": [
    {"expression": "liabilityType", "line": 815, "endLine": 830, "cases": [...]},
    {"expression": "coverageType", "line": 835, "endLine": 865, "cases": [...]},
    {"expression": "deductible", "line": 870, "endLine": 890, "cases": [...]},
    {"expression": "purchasePrice", "line": 895, "endLine": 930, "cases": [...]}
  ]
}
```

**Step U.8:** Parser identifies Array6 calls within each block's line range:
- Block 1 (liability): 0 Array6 calls
- Block 2 (coverage): 0 Array6 calls (scalar assignments)
- Block 3 (deductible): 4 Array6 calls — these match the CR!
- Block 4 (purchase price): 12 Array6 calls + excessRates assignments

```
[Understand] CR cr-010: GetBasePrem_Snowmobile has 4 Select Case blocks:

             Block 3 (lines 870-890): deductible — 4 Array6 assignments
             Block 4 (lines 895-930): purchasePrice — 12 Array6 + excessRates

             The CR says "multiply deductible factors by 1.02".
             Recommended: Block 3 (deductible) matches.

             Which block(s) should be modified?
               a) Block 3 only (deductible factors) ← recommended
               b) Block 4 only (purchase price groups)
               c) Both blocks
               d) Let me specify exact lines
```

---

### Example G: Caller Chain Post-Processing Warning

**Input:**

```yaml
id: "cr-008"
title: "Fix driver record conviction cap"
extracted:
  target_file_hint: "Ontario/Code/mod_DC_DR_ONAuto20240601.vb"
  target_function_hint: "SetDriverRecord_MaxDR_Convictions"
```

**Parser Phase:**

Step U.5: `vb-parser function mod_DC_DR_ONAuto20240601.vb SetDriverRecord_MaxDR_Convictions`:
```json
{
  "function": {
    "name": "SetDriverRecord_MaxDR_Convictions",
    "startLine": 1420,
    "endLine": 1500,
    "returnType": "String",
    "calls": [
      {"name": "CStr", "line": 1445, "parentContext": "assignment", "assignmentTarget": "driverRecord"},
      {"name": "CInt", "line": 1460, "parentContext": "condition"}
    ]
  }
}
```

**Claude Phase:**

Step U.10: Caller chain check.

Call chain: SetDriverRecord → SetDriverRecord_MaxDR_Convictions

Run `vb-parser function` on SetDriverRecord (the caller):
```json
{
  "function": {
    "name": "SetDriverRecord",
    "startLine": 1766,
    "endLine": 1819,
    "calls": [
      {"name": "SetDriverRecord_MaxDR_Convictions", "line": 1780,
       "parentContext": "assignment", "assignmentTarget": "driverRecord"},
      {"name": "SetDriverRecord_MaxDR_YearsLicensed", "line": 1799,
       "parentContext": "assignment", "assignmentTarget": "driverRecord"},
      {"name": "SetDriverRecord_MaxDR_YearsLicensed", "line": 1800,
       "parentContext": "assignment", "assignmentTarget": "driverRecord"}
    ]
  }
}
```

Parser reveals: `driverRecord` is assigned at line 1780 (from target function)
AND again at lines 1799 and 1800 (from a different function). This is a
competing write.

Claude reads lines 1780-1810 of the caller body:
- Line 1780: `driverRecord = CStr(SetDriverRecord_MaxDR_Convictions(objDriver))`
- Line 1799: `driverRecord = CStr(SetDriverRecord_MaxDR_YearsLicensed(objDriver))`
  → UNCONDITIONAL overwrite!
- Line 1800: `driverRecord = SetDriverRecord_MaxDR_YearsLicensed(objDriver)`
  → REDUNDANT double-assignment (copy-paste artifact)

```
CALLER ANALYSIS WARNING (CR-008):
  Target function: SetDriverRecord_MaxDR_Convictions (lines 1420-1500)
  Caller function: SetDriverRecord (lines 1766-1819)
  PROBLEM: Caller overwrites result at line 1799 (unconditional)
  Code smell: Redundant double-assignment at lines 1799-1800
  The fix inside SetDriverRecord_MaxDR_Convictions will be NULLIFIED
  unless the caller is also fixed.
  → Plan agent MUST produce an additional intent for the caller.
```

Output in code_understanding.yaml:

```yaml
cr-008:
  understanding:
    caller_chain_summary: |
      WARNING: Caller SetDriverRecord overwrites result at line 1799.
      Fix inside target function will be NULLIFIED unless caller is also fixed.
    hazards:
      - type: "competing_write"
        detail: "Caller unconditionally overwrites driverRecord at line 1799"
      - type: "redundant_double_assignment"
        detail: "Lines 1799-1800 assign same variable in sequence"
```

---

### Example H: New Endorsement with Code Pattern Discovery

**Input:**

```yaml
id: "cr-009"
title: "Add Identity Fraud endorsement routing"
extracted:
  target_file_hint: "Saskatchewan/Code/CalcOption_SKHOME20260101.vb"
  target_function_hint: null  # Module-level routing change
```

**Parser Phase:**

Step U.4: `vb-parser parse CalcOption_SKHOME20250901.vb`:
- 3 functions, main routing in CalcAllOptions
- Parser finds Select Case blocks for routing

Step U.5: `vb-parser function CalcOption_SKHOME20250901.vb CalcAllOptions`:
- Select Case on TheCategory → nested Select Case on TheOptionCode
- Existing cases: 1 (Antennae), 2 (Bicycle), 3 (Boat), ...

**Claude Phase:**

Step U.8.7: Claude reads the routing structure to build dispatch_map.
Determines insertion point (after last existing Case, before End Select).
Checks for duplicate: "Identity Fraud" → NOT FOUND, safe to add.

Step U.18: Code Pattern Discovery triggers (new endorsement → YES):

Step U.18.2: Query pattern-library.yaml:
- `accessor_index["endorsement"]` → 3 patterns:
  1. `Option_Bicycle()` — 6 call sites (ACTIVE)
  2. `Option_AntennaeRadio()` — 4 call sites (ACTIVE)
  3. `Option_Legacy()` — 0 call sites (DEAD)

Step U.18.3: Peer functions found:
- Option_Bicycle (active, good template)
- Option_AntennaeRadio (active, good template)

Step U.18.5: HIGH confidence — clear winner patterns.

Output:

```yaml
cr-009:
  target:
    target_kind: "code_block"
    insertion_point:
      line: 145   # After last existing Case
      position: "before_end_select"
      context: "After Case 3 (Boat), before End Select"
  code_patterns:
    peer_functions:
      - name: "Option_Bicycle"
        file: "Saskatchewan/Code/Option_Bicycle_SKHome20220502.vb"
        call_sites: 6
        dead_code: false
        snippet: |
          Function Option_Bicycle() As Short
            ' ... premium calculation pattern
          End Function
    canonical_access:
      - need: "endorsement_routing"
        pattern: "Case {code} : dblPrem = {FunctionName}()"
        call_sites: 6
        confidence: "high"
    warnings:
      - "Option_Legacy (line 200) has 0 call sites — DEAD CODE"
```

---

## 11. GRACEFUL DEGRADATION

If any step fails, the agent continues with partial results:

| Failure | Impact | Recovery |
|---------|--------|----------|
| vb-parser project fails | No compiled file list | Use config.yaml naming patterns, file glob |
| vb-parser parse fails on CalcMain | No calculation_flow | CRs still resolved via direct function search |
| vb-parser parse fails on Code/ file | No function index for that file | Read file manually with Claude, flag degraded |
| vb-parser function fails | No deep structural data | Claude reads function body directly |
| Function not found for CR | CR has `resolved: false` | Plan agent excludes from execution |
| CalcOption not readable | No dispatch_map | Plan uses pattern matching |
| Pattern Library missing | No dead-code detection | Skip Step U.18.2, grep files directly |
| Sub-agent crashes | Missing FUB for function | Retry once, then process inline |
| codebase-profile.yaml missing | No profile enrichment | Skip Step U.12 entirely |
| YAML write fails | Partial output | Retry write, log error in manifest |
| Parser returns parse errors | Structural data may be partial | WARN prominently, proceed with caution |

**Critical rule:** NEVER block the pipeline. Downstream agents use what they
can and handle missing data gracefully.

---

## 12. BOUNDARY WITH OTHER AGENTS

The Understand agent runs AFTER Intake and BEFORE Plan.

| Responsibility | Intake | Understand | Plan | Change Engine |
|---------------|:------:|:----------:|:----:|:-------------:|
| Identify target files | Provides hint | Verifies via parser | Uses | Uses |
| Classify file types | NO | YES (parser) | Uses | Uses |
| Determine function names | Provides hint | Confirms by parser + reading | Uses | Uses |
| Determine exact lines | NO | YES (parser + Claude) | Uses | Uses |
| Set target_kind | NO | YES | Flows through | Uses for verification |
| Resolve rounding | Provides hint | Resolves from values | Uses | Uses |
| Detect cross-LOB refs | NO | YES (parser project) | Reports | N/A |
| Show candidates to dev | NO | YES (reads code) | NO | NO |
| Build FUBs | NO | YES | Uses | Uses |
| Build intent graph | NO | NO | YES | Uses |
| Determine file copies | NO | YES (files_to_copy) | Uses | Executes |
| Build blast radius | NO | YES | Includes in plan | N/A |
| Sequence changes | NO | Provides line numbers | YES (orders bottom-to-top) | Follows order |
| Build approval doc | NO | NO | YES | N/A |

---

## 13. ERROR HANDLING

### Parser Binary Not Found

```
[Understand] FATAL: vb-parser.exe not found at: {vb_parser_path}
             Run /iq-init to configure the plugin.
```

### Parser Returns Parse Errors

```
[Understand] WARNING: Parser found {N} parse error(s) in {file}:
             {For each error:}
             Line {line}: {message}

             The file has syntax errors. Structural analysis may be incomplete.
             Proceeding with available data. Fix syntax errors before executing changes.
```

### Parser Returns Empty Output

```
[Understand] ERROR: Parser returned empty output for: {command}
             File: {file}

             Possible causes:
               - File is empty or zero bytes
               - File encoding is not UTF-8 or UTF-8-BOM
               - Binary is corrupted
```

### Missing .vbproj File

```
[Understand] ERROR: .vbproj file not found:
             {path}

             Listed in change_requests.yaml target_folders but does not exist.
             Was IQWiz run to create this version folder?
```

### Source File Not Found

```
[Understand] ERROR: Cannot find source file for CR {cr_id}:
             Expected pattern: {file_pattern}
             Searched in File Reference Map ({N} Code/ files)

             No file matches. Either:
               - Intake's target_file_hint has a wrong file name
               - The .vbproj references have changed since Intake ran
               - This is a new file that needs to be created
```

### Function Not Found (After Partial Module Fallback)

```
[Understand] WARNING: Function "{hint}" not found in any file compiled by {vbproj}

             Searched {N} files, {M} total functions. Similar names:
               {ranked candidates}

             Which function should CR {cr_id} target?
```

### Hash Mismatch (TOCTOU Violation)

```
[Understand] ERROR: File hash changed between parse steps!
             File: {source_file}
             Expected: {original_hash}
             Current:  {new_hash}

             Someone modified this file while the Understand agent was running.
             Re-run /iq-plan to get fresh analysis.
```

### No Rate Values Found in Function

```
[Understand] WARNING: No rate-bearing targets found in {function_name}
             (lines {start}-{end}).

             Parser found:
               - {N} Array6 calls: {breakdown by parentContext}
               - {M} scalar assignments
               - {K} GetPremFromResourceFile calls (DAT file)

             Possible reasons:
               - Function uses DAT files (not editable)
               - Rate values are in a different function
               - CR describes a different type of change
```

### Cross-Province Shared File Violation

```
[Understand] ERROR: CR {cr_id} targets cross-province shared file:
             {source_file}

             These files are used by ALL provinces and must NEVER be
             automatically modified. This CR is BLOCKED.

             Options:
               a) Modify this file manually outside the plugin
               b) Remove this CR from the workflow
```

---

## 14. PERFORMANCE CHARACTERISTICS

### Parser Phase Cost

| Step | Parser Calls | Time | Token Cost |
|------|-------------|------|------------|
| U.1: Project mapping | 1-6 (per LOB) | ~1 sec each | 0 (subprocess) |
| U.2: Entry point analysis | 1 | ~1 sec | 0 |
| U.3: Call chain tracing | 0 (uses U.2 data) | negligible | 0 |
| U.4: Target file overview | 1-3 (per unique file) | ~1-2 sec each | 0 |
| U.5: Function deep dive | 1-8 (per unique function) | ~1 sec each | 0 |
| **Total Parser Phase** | **5-20** | **~5-20 sec** | **0 tokens** |

### Claude Phase Cost

| Step | Tool Calls | Time | Token Cost |
|------|-----------|------|------------|
| U.6: Match CRs | 0-3 (fallback searches) | ~5-10 sec | ~500-1,500 |
| U.7: Dispatch structure | 1-3 (read code chunks) | ~10-15 sec | ~1,000-3,000 |
| U.8: Target identification | 3-15 (read per-target context) | ~15-30 sec | ~2,000-6,000 |
| U.9: Hazard detection | 0 (parser data) | negligible | ~200-500 |
| U.10: Caller chain | 0-3 (read caller bodies) | ~5-10 sec | ~500-2,000 |
| U.11: Build FUBs | 0 (data already in memory) | ~5-10 sec | ~1,000-3,000 |
| U.12: Profile enrichment | 1-2 (read/write profile) | ~2-3 sec | ~200-500 |
| **Total Claude Phase** | **5-30** | **~45-90 sec** | **~5,000-16,000** |

### Output Phase Cost

| Step | Tool Calls | Time | Token Cost |
|------|-----------|------|------------|
| U.13: Rounding resolution | 0 (already computed) | negligible | ~100-300 |
| U.14: Reverse lookup | 1-6 (parser project per LOB) | ~5-10 sec | 0 |
| U.15: Cross-province check | 0 | negligible | ~50-100 |
| U.16: files_to_copy | 0 | negligible | ~200-500 |
| U.17: Blast radius | 0 | negligible | ~200-500 |
| U.18: Code patterns | 0-5 (Pattern Library + reads) | ~30-60 sec | ~1,000-3,000 |
| U.19: Write YAML | 1 (write + validate) | ~2-5 sec | ~500-1,000 |
| U.20: Summary | 0 | ~2 sec | ~200-500 |
| **Total Output Phase** | **2-12** | **~40-80 sec** | **~2,000-6,000** |

### Total

| Metric | Typical Ticket | Large Ticket |
|--------|---------------|--------------|
| Parser calls | 8-15 | 15-25 |
| Time | ~90-120 sec | ~3-5 min |
| Token cost | ~7,000-15,000 | ~15,000-25,000 |
| Developer prompts | 0-3 | 3-8 |

**Comparison to v0.3.3 (Discovery + Analyzer):**
- Time: ~8-15 min → ~2-5 min (3-4x faster)
- Context windows: 2 → 1 (50% reduction)
- Handoff artifacts: 2 → 1 (no data drift)
- Regex pseudocode: ~1,900 lines → 0

---

## 15. WHAT MAKES THIS CARRIER-AGNOSTIC

The agent does NOT hardcode function names. It follows a universal framework:

1. **Find CalcMain** → from target_folders path (works for any carrier)
2. **Parse project** → `vb-parser project` lists compiled files (any .vbproj)
3. **Parse files** → `vb-parser parse` extracts function roster (any VB.NET)
4. **Deep dive** → `vb-parser function` gives exact structure (any function)
5. **Claude reads** → semantic understanding of business logic (any domain)
6. **Match CRs** → by function names, parser structure, developer confirmation

Different carriers have different names but the same understanding process.
The parser speaks VB.NET syntax, not insurance domain. This agent interprets
parser output in the context of TBW manufactured rating.

---

## 16. CONFIGURATION REFERENCE

### paths.md Keys Used

```
vb_parser:    Path to vb-parser.exe binary
plugin_root:  Root of the .iq-update/ directory
python_cmd:   Python command for YAML validation
understand:   Path to this agent spec (for sub-agent references)
```

### config.yaml Keys Used

```
carrier_prefix:                 e.g., "PORT" for Portage Mutual
provinces.{code}.shardclass_folder:  "SHARDCLASS" or "SharedClass"
cross_province_shared_files:    List of never-modify files
```

### Manifest State Transitions

The orchestrator updates manifest.yaml after the Understand agent completes:

```yaml
understand:
  status: "completed"          # or "failed"
  completed_at: "{timestamp}"
  crs_analyzed: {N}
  files_to_copy: {N}
  blast_radius_risk: "{LOW|MEDIUM|HIGH}"
  parser_version: "1.0"
```

<!-- IMPLEMENTATION: Phase 2, Item 2.1 -->
