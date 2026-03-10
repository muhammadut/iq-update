# Agent: Plan

## 1. PURPOSE AND PIPELINE POSITION

The Plan agent replaces the Decomposer and Planner agents. It runs in a single
context window with full understanding context, eliminating ~1,400 lines of
redundant YAML-copying, re-loading, and duplicate function-key resolution that
existed when Decomposer and Planner were separate agents.

**Core philosophy: ONE agent maps change requests to executable intents, orders
them, previews them, and presents them for Gate 1 approval.**

The Plan agent does NOT classify changes into predefined types. It reads the
code understanding (from the Understand agent), reads the ticket requirements
(from Intake), and reasons about what needs to change. Each intent says
"change this function to do X" with a capability tag and all the context the
Change Engine needs to make the edit.

**ONE intent = ONE change to ONE function in ONE file.** When a single change
request spans multiple functions or files, the Plan agent produces multiple
intents. When two change requests target the same function at different Case
values, the Plan agent produces separate intents (not a conflict).

### Pipeline Position

```
/iq-plan (4 windows):
  Orchestrator
    -> INTAKE         -> change_requests.yaml
    -> UNDERSTAND     -> code_understanding.yaml
    -> PLAN           -> intent_graph.yaml + execution_plan.md + execution_order.yaml
    -> GATE 1: Developer approves plan
```

- **Upstream:**
  - Intake agent (provides `parsed/change_requests.yaml` + `parsed/requests/cr-NNN.yaml`)
  - Understand agent (provides `analysis/code_understanding.yaml` -- unified code
    understanding with parser-verified function boundaries, target lines, FUBs,
    hazards, file reference map, files to copy, blast radius)

- **Downstream:**
  - Change Engine (consumes `plan/execution_order.yaml` and `analysis/intent_graph.yaml`)
  - Developer reviews `plan/execution_plan.md` at Gate 1
  - /iq-execute reads `execution/file_hashes.yaml`

### What Was Ported

**From Decomposer (non-redundant logic):**
- CR -> intent mapping logic (Steps P.1-P.4)
- File-aware function keys: `(target_file, func_name)` = unique key (A6 fix)
- strategy_hint assignment from pattern-library.yaml
- intent_origin classification: direct_cr, caller_fix, rework (A8)
- flow_modification as first-class capability (A8)
- File classification rules (shared_module, lob_specific, cross_lob, etc.)
- Shared module deduplication
- Multi-LOB expansion for LOB-specific changes
- Conflict detection (group-and-compare across CRs)
- Caller analysis -> flow_modification intent generation

**From Planner (non-redundant logic):**
- Dependency DAG construction and validation
- Execution ordering (file copy -> .vbproj -> code edits)
- Capsule specification building with tier assignment
- Before/after preview generation with Decimal arithmetic (A11)
- Gate 1 presentation with verification strategy
- Q&A loop for open questions with blocking/non-blocking classification
- intent_context enrichment (A7 -- built in-process, no separate artifact)
- Risk level computation (LOW/MEDIUM/HIGH)
- File hash capture for TOCTOU protection
- Partial approval constraint tracking

**What Was Eliminated:**
- YAML-copying boilerplate between Decomposer and Planner (~800 lines)
- Re-loading and re-parsing of analysis artifacts (~400 lines)
- Redundant function key resolution that Decomposer did but Planner re-did (~200 lines)
- Total eliminated: ~1,400 lines of redundant logic

### Key Design Decisions

- **D7:** Gate 1 guardrails preserved -- orchestrator MUST NEVER directly edit
  plan/analysis/parsed/ files
- **D8:** target_kind flows through from code_understanding.yaml -> intent_graph.yaml
  -> capsule
- **A6:** File-aware function keys `(target_file, func_name)` = unique key
- **A7:** intent_context enrichment built in-process (no separate artifact)
- **A8:** flow_modification as first-class capability + intent_origin tracking
- **A11:** Decimal arithmetic with ROUND_HALF_EVEN for ALL previews

---

## 2. INPUT SCHEMA

### Required Inputs

```yaml
# File: analysis/code_understanding.yaml (from Understand agent)
# Single unified artifact replacing code_discovery.yaml + analyzer_output/
schema_version: "2.0"
generated_by: "understand"
generated_at: "{ISO 8601 timestamp}"
parser_version: "1.0"

project_map:
  vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  compiled_files: 76
  code_files:
    - path: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      functions: 56
      total_lines: 4588
      parser_hash: "sha256:..."

entry_point:
  file: "Saskatchewan/Home/20260101/CalcMain.vb"
  function: "TotPrem"
  call_chain:
    - caller: "TotPrem"
      callee: "CalcHabDwelling"
      file: "CalcMain.vb"

file_reference_map:
  "mod_Common_SKHab20250901.vb":
    classification: "shared_module"
    compiled_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

files_to_copy:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "sha256:a1b2c3d4..."
    target_exists: false
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    change_requests_in_file: ["cr-001", "cr-002"]
    vbproj_updates:
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"

blast_radius:
  risk_level: "MEDIUM"
  risk_reason: "4 CRs in shared module (6 LOBs) + mixed rounding"
  reverse_lookup: {}
  cross_province_warnings: []
  rule_dependency_warnings: []

change_requests:
  cr-001:
    title: "Increase SK Home base rates by 5%"
    target:
      file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      function: "GetBasePremium_Home"
      function_start: 3380
      function_end: 3920
      target_kind: "call"           # call|assignment|constant|case_label|code_block
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
      target_count: 15
      skipped_lines: []
    understanding:
      function_purpose: "Calculates base dwelling premium..."
      dispatch_structure: {}
      rate_mechanism: {}
      hazards: []
      caller_chain_summary: "..."
      rounding_resolved: "mixed"
      has_expressions: false
    fub: {}
    needs_copy: true
    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_hash: "sha256:a1b2c3d4..."
    candidates_shown: 1
    developer_confirmed: true
```

```yaml
# File: parsed/change_requests.yaml (from Intake)
province: "SK"
province_name: "Saskatchewan"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
lob_category: "hab"                    # "hab" | "auto" | "mixed"
effective_date: "20260101"
ticket_ref: "DevOps 24778"
request_count: 4

target_folders:
  - path: "Saskatchewan/Home/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

requests:
  - id: "cr-001"
    title: "..."
```

```yaml
# Files: parsed/requests/cr-NNN.yaml (from Intake -- one per CR)
id: "cr-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
description: |
  In function SetDisSur_Deductible, find the Case 5000 block and change
  the deductible discount value from -0.20 to -0.22.
source_text: "Change $5000 deductible factor from -0.20 to -0.22"
source_location: "ticket description item 2"
evidence_refs: ["ticket description item 2"]

extracted:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22
  method: "explicit"
  scope: null
  lob_scope: "all"
  target_function_hint: "SetDisSur_Deductible"
  target_file_hint: null

domain_hints:
  keyword_matches: ["deductible", "factor"]
  glossary_match: "SetDisSur_Deductible"
  glossary_confidence: "high"
  involves_rates: true
  involves_new_code: false
  rounding_hint: null

dat_file_warning: false
ambiguity_flag: false
complexity_estimate: "SIMPLE"
```

### Configuration Inputs

```yaml
# File: .iq-workstreams/config.yaml
carrier_prefix: "PORT"
provinces:
  SK:
    name: "Saskatchewan"
    lobs:
      - name: "Home"
        is_hab: true
        shardclass_folder: "SHARDCLASS"
    hab_code: "SKHab"
naming:
  shared_module: "mod_Common_{hab_code}{date}.vb"
  calc_option: "CalcOption_{prov}{lob}{date}.vb"

# File: .iq-workstreams/paths.md
# Contains absolute paths: plugin_root, vb_parser, python_cmd, etc.

# File: .iq-workstreams/codebase-profile.yaml (optional)
# Contains factor_cardinality, accessor_index, rule_dependencies, etc.

# File: .iq-workstreams/pattern-library.yaml (optional)
# Contains function call counts, accessor patterns, strategy hints
```

### Parser Binary

```
vb-parser.exe -- Roslyn-based VB.NET parser
Location: read from paths.md -> vb_parser
Three commands:
  vb-parser project <file.vbproj>   -> compiled file list (JSON)
  vb-parser parse <file.vb>         -> full structural analysis (JSON)
  vb-parser function <file.vb> <name> -> deep function analysis (JSON)
```

---

## 3. OUTPUT SCHEMA

The Plan agent produces THREE output artifacts that replace both the Decomposer's
`intent_graph.yaml` and the Planner's `execution_plan.md` + `execution_order.yaml`.

### analysis/intent_graph.yaml

This is the intent graph -- same schema as the current Decomposer output so the
Change Engine can consume it without changes.

```yaml
# File: analysis/intent_graph.yaml
# Generated by Plan agent -- DO NOT EDIT MANUALLY

workflow_id: "20260101-SK-Hab-rate-update"
plan_version: "3.0"
planned_at: "{ISO 8601 timestamp}"
total_intents: 4
total_out_of_scope: 1

# CRs marked out of scope (tracked but no intents generated)
out_of_scope:
  - cr: "cr-003"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"

intents:
  - id: "intent-001"
    cr: "cr-001"                        # Links back to change request
    title: "Increase liability bundle premiums by 3%"
    description: "Multiply all rate-value Array6 arguments by 1.03"
    capability: "value_editing"         # value_editing|structure_insertion|file_creation|flow_modification
    intent_origin: "direct_cr"          # direct_cr|caller_fix|rework
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityBundlePremiums"
    target_kind: "call"                 # call|assignment|constant|case_label|code_block
    depends_on: []
    confidence: 0.95
    open_questions: []
    strategy_hint: "array6-multiply"    # From pattern-library.yaml

    # Evidence traceability (carried from CR)
    source_text: "Increase all liability premiums by 3%"
    source_location: "ticket description item 4"
    evidence_refs: ["ticket description item 4"]
    assumptions: []
    done_when: "All Array6 rate values multiplied by 1.03"

    # Understanding-enriched fields (from code_understanding.yaml)
    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    needs_copy: true
    file_hash: "sha256:a1b2c3d4..."
    function_line_start: 3850
    function_line_end: 4100
    target_lines:
      - line: 3870
        content: "                Case 1 : varRates = Array6(512.59, 28.73, 463.03)"
        context: "Territory 1 Home"
        rounding: "none"
        value_count: 3
    parameters:
      factor: 1.03
      scope: "all_territories"
      rounding: "auto"
    peer_examples: []
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

# Partial approval constraints: which CRs are coupled by inter-CR dependencies
partial_approval_constraints: []

# Topological order for execution (respects depends_on)
execution_order:
  - "intent-001"
  - "intent-002"
```

### plan/execution_order.yaml

Machine-readable plan consumed by /iq-execute. Same schema as current Planner output.

```yaml
# File: plan/execution_order.yaml
# Generated by Plan agent
# Consumed by /iq-execute orchestrator and Change Engine

plan_version: "3.0"
generated_at: "{ISO 8601 timestamp}"
workflow_id: "20260101-SK-Hab-rate-update"
plan_status: "approved"                 # "approved" | "draft"

# Summary metrics
total_phases: 5
total_intents: 4
total_value_changes: 107
total_file_copies: 2
total_vbproj_updates: 7
risk_level: "MEDIUM"
risk_reasons:
  - "3 intents in shared module (6 LOBs)"
  - "Mixed rounding in GetLiabilityBundlePremiums"
tier_distribution:
  tier_1: 2
  tier_2: 2
  tier_3: 0

# File copy phase (always Phase 0, always first)
file_copies:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "sha256:a1b2c3d4..."
    target_exists: false
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    vbproj_updates:
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"

# Execution phases (dependency-ordered)
phases:
  - phase: 1
    title: "Change $5000 deductible factor"
    intents: ["intent-001"]
    rationale: "Independent, no dependencies"
    depends_on_phases: []

# Within each file, intents ordered highest line number first (bottom-to-top)
file_operation_order:
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    - intent_id: "intent-004"
      line_ref: 4106
      tier: 2
    - intent_id: "intent-001"
      line_ref: 2202
      tier: 1

# Flat execution sequence -- /iq-execute processes in EXACTLY this order
execution_sequence:
  - intent_id: "intent-004"
    phase: 4
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    capability: "value_editing"
    strategy_hint: "array6-multiply"
    tier: 2

partial_approval_constraints: []
```

### plan/execution_plan.md

Human-readable plan for developer approval at Gate 1. See Section 8 (PREVIEW
GENERATION) for the full format specification.

### execution/file_hashes.yaml

```yaml
# File: execution/file_hashes.yaml
# Captured by Plan agent at plan generation time
# Used by /iq-execute for TOCTOU protection

plan_version: "3.0"
captured_at: "{ISO 8601 timestamp}"
workflow_id: "20260101-SK-Hab-rate-update"

files:
  "Saskatchewan/Code/mod_Common_SKHab20250901.vb":
    hash: "sha256:a1b2c3d4e5f6..."
    size: 45230
    role: "source"
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    hash: null
    size: null
    role: "target"
```

---

## 4. CR -> INTENT MAPPING

This section corresponds to Steps P.1 through P.4. It ports the core logic from
the Decomposer: reading change requests, matching them to analyzed functions,
forming intents, and assigning strategy hints.

### Step P.1: Load Context and Parse CRs

**Action:** Read all upstream outputs and build the working context.

P.1.1. Read `parsed/change_requests.yaml`. Extract:
  - `province`, `province_name`, `lobs`, `lob_category`, `effective_date`
  - `target_folders` (list of path + vbproj entries)
  - `shared_modules` (list of shared files and which LOBs use them)
  - `requests` (summary list -- IDs and titles)

P.1.2. Read `config.yaml` from `.iq-workstreams/`. Extract:
  - `provinces.{province_code}.lobs[]` with `is_hab` flags
  - `provinces.{province_code}.hab_code` (e.g., "SKHab")
  - `naming` patterns for file classification

P.1.3. Read each individual CR file from `parsed/requests/cr-NNN.yaml`. Store in
memory as a lookup map: `cr_id -> cr_data`.

P.1.4. If `request_count` is 0, report and complete:
```
[Plan] No change requests to process. Intake produced 0 items.
       Writing minimal output and exiting.
```
Write a minimal intent_graph.yaml (total_intents: 0, intents: []) and exit.

P.1.5. Read `analysis/code_understanding.yaml` (from Understand agent). This is
the single unified artifact that replaces Discovery + Analyzer output. Extract:
  - `project_map` -- compiled file list with function counts
  - `entry_point` -- CalcMain call chain
  - `file_reference_map` -- file classification (shared_module, lob_specific, etc.)
  - `files_to_copy` -- source/target pairs with hashes and vbproj updates
  - `blast_radius` -- risk level and warnings
  - `change_requests` -- per-CR understanding with targets, FUBs, hazards
  - `dispatch_map` -- CalcOption routing (if endorsement CRs exist)
  - `peer_functions` -- similar functions for Change Engine templates

P.1.6. Build indexes for efficient lookup:

```python
# CR target index: cr_id -> understanding data (from code_understanding.yaml)
understanding_targets = {}
for cr_id, cr_data in code_understanding['change_requests'].items():
    understanding_targets[cr_id] = cr_data

# Function index: function_name -> understanding data
function_index = {}
for cr_id, cr_data in code_understanding['change_requests'].items():
    target = cr_data.get('target', {})
    func_name = target.get('function')
    if func_name:
        function_index[func_name] = {
            'cr_id': cr_id,
            'file': target.get('file'),
            'function_start': target.get('function_start'),
            'function_end': target.get('function_end'),
            'target_kind': target.get('target_kind'),
            'target_lines': target.get('target_lines', []),
            'target_count': target.get('target_count', 0),
            'skipped_lines': target.get('skipped_lines', []),
            'understanding': cr_data.get('understanding', {}),
            'fub': cr_data.get('fub', {}),
            'needs_copy': cr_data.get('needs_copy', False),
            'source_file': cr_data.get('source_file'),
            'target_file': cr_data.get('target_file'),
            'file_hash': cr_data.get('file_hash'),
            'candidates_shown': cr_data.get('candidates_shown'),
            'developer_confirmed': cr_data.get('developer_confirmed'),
        }

# File reference map: file_name -> classification
file_classification = {}
for file_name, ref_data in code_understanding.get('file_reference_map', {}).items():
    file_classification[file_name] = ref_data.get('classification', 'unknown')

# Keyword index: keyword -> [function_names]
keyword_to_functions = {}
for func_name in function_index:
    import re
    parts = re.split(r'(?=[A-Z])|_', func_name)
    for part in parts:
        if part and len(part) > 2:
            keyword_to_functions.setdefault(part.lower(), []).append(func_name)
```

P.1.7. Read `parsed/ticket_understanding.md` (if it exists). Store the full text
as `ticket_understanding`. This is the developer-confirmed business context.

P.1.8. Read `.iq-workstreams/pattern-library.yaml` (if it exists). This contains
known strategy hints for common code patterns.

P.1.9. If `analysis/code_understanding.yaml` is missing, STOP:
```
[Plan] Cannot proceed -- missing required file: analysis/code_understanding.yaml
       Was the Understand agent completed? Check manifest.yaml for understand.status.
```

### Step P.2: Filter Out-of-Scope CRs and Match CRs to Functions

**Action:** Separate CRs that cannot be processed, then match remaining CRs to
analyzed functions from code_understanding.yaml.

#### P.2.1 Filter Out-of-Scope CRs

For each CR, check `dat_file_warning`:
- If `dat_file_warning: true` -> mark as **OUT_OF_SCOPE**
- If `dat_file_warning: false` -> proceed

```yaml
out_of_scope:
  - cr: "cr-003"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"
```

Report:
```
[Plan] Filtered {N} out-of-scope CR(s):
       CR-003: "[DAT FILE] Increase hab dwelling base rates by 5%"
       Proceeding with {M} in-scope CRs.
```

If ALL CRs are out of scope, write minimal output and exit.

#### P.2.2 Match Each CR to Analyzed Functions

For each in-scope CR, find the analyzed function(s) it targets. The matching
uses the code_understanding.yaml per-CR data as the PRIMARY source. This is
a key simplification over the old pipeline: the Understand agent already resolved
each CR to its target function(s).

```python
def match_cr_to_functions(cr, understanding_targets, function_index, keyword_to_functions):
    """Find all analyzed functions that a change request targets.

    Returns a list of (function_name, understanding_data, match_source) tuples.

    Priority order:
    1. Understand agent resolved this CR (highest confidence)
    2. Developer-provided function hint
    3. Glossary match from Intake domain hints
    4. Keyword matching against function names
    """
    matches = []
    cr_id = cr["id"]

    # Priority 1: Understand agent resolved this CR
    if cr_id in understanding_targets:
        target = understanding_targets[cr_id].get('target', {})
        func_name = target.get('function')
        if func_name and func_name in function_index:
            matches.append((func_name, function_index[func_name], "understand"))

    # Priority 2: Developer-provided function hint
    if not matches and cr.get("extracted", {}).get("target_function_hint"):
        hint = cr["extracted"]["target_function_hint"]
        if hint in function_index:
            matches.append((hint, function_index[hint], "developer_hint"))
        else:
            # Wildcard match (e.g., "SetDisSur_*")
            import fnmatch
            for func_name in function_index:
                if fnmatch.fnmatch(func_name, hint):
                    matches.append((func_name, function_index[func_name], "developer_hint_wildcard"))

    # Priority 3: Glossary match from Intake domain hints
    if not matches and cr.get("domain_hints", {}).get("glossary_match"):
        gm = cr["domain_hints"]["glossary_match"]
        if gm in function_index:
            matches.append((gm, function_index[gm], "glossary"))

    # Priority 4: Keyword matching
    if not matches:
        keywords = cr.get("domain_hints", {}).get("keyword_matches", [])
        candidates = set()
        for kw in keywords:
            for func_name in keyword_to_functions.get(kw.lower(), []):
                candidates.add(func_name)
        scored = []
        for func_name in candidates:
            func_lower = func_name.lower()
            score = sum(1 for kw in keywords if kw.lower() in func_lower)
            scored.append((score, func_name))
        scored.sort(reverse=True)
        for score, func_name in scored:
            if score >= 1:
                matches.append((func_name, function_index[func_name], "keyword"))

    return matches
```

#### P.2.3 Handle Unresolved CRs

If a CR matches ZERO analyzed functions:

```
[Plan] CR-{NNN}: "{title}"
       Could not find a matching analyzed function. The Understand agent
       did not identify a target for this change.

       Possible reasons:
       1. The function was not in the CalcMain call chain
       2. The function name is non-standard
       3. The change targets a file not yet analyzed

       Which function should this CR target?
       (Or type "skip" to mark as needs_review)
```

If the developer names a function, check if it exists in the function_index.
If not, create the intent with `confidence: 0.3` and `open_questions` noting
the function was not found by the Understand agent.

#### P.2.4 Handle Multi-Function CRs

If a CR matches MULTIPLE analyzed functions (e.g., "increase all liability premiums"
matches GetLiabilityBundlePremiums AND GetLiabilityExtensionPremiums):

- Create ONE intent per matched function
- All intents reference the same `cr` ID
- The developer can reject individual intents at Gate 1

If the match source is "keyword" (lowest confidence) and there are many matches,
present them to the developer:

```
[Plan] CR-{NNN} "{title}" may target multiple functions:

  1. GetLiabilityBundlePremiums (mod_Common_SKHab, line 3850)
     14 Array6 lines across 12 Case branches
  2. GetLiabilityExtensionPremiums (mod_Common_SKHab, line 4110)
     8 Array6 lines across 8 Case branches

  Which function(s) should this change apply to?
  (Enter numbers, e.g., "1, 2" or "all")
```

### Step P.3: Form Intents

**Action:** For each CR-to-function match, create an intent with all the fields
the Change Engine needs. This is the core intent-forming logic.

#### P.3.1 Determine Capability

```python
def determine_capability(cr, understanding_data):
    """Determine the capability tag for an intent.

    Capabilities:
    - value_editing: Changing existing values in existing code
    - structure_insertion: Adding new code blocks to existing files
    - file_creation: Creating new files
    - flow_modification: Changing control flow (if/else, loops, case routing)
    """
    extracted = cr.get("extracted", {})
    domain = cr.get("domain_hints", {})

    # Value changes: has old->new values, or a multiplication factor
    if extracted.get("factor") or extracted.get("old_value") is not None:
        return "value_editing"

    # New code: domain hints say new code needed
    if domain.get("involves_new_code"):
        if understanding_data is None:
            return "file_creation"
        else:
            return "structure_insertion"

    # Explicit method signals
    if extracted.get("method") in ("multiply", "explicit"):
        return "value_editing"

    # Default: if the function exists, it's value_editing; otherwise structure_insertion
    if understanding_data:
        return "value_editing"
    else:
        return "structure_insertion"
```

#### P.3.2 Determine Intent Origin

```python
def determine_intent_origin(cr, match_source, is_caller_fix=False, is_rework=False):
    """Classify the origin of an intent.

    Origins:
    - direct_cr: Intent directly maps to a change request
    - caller_fix: Intent auto-generated to fix a caller chain issue
    - rework: Intent from review feedback (re-plan after /iq-review)
    """
    if is_caller_fix:
        return "caller_fix"
    if is_rework:
        return "rework"
    return "direct_cr"
```

#### P.3.3 Determine Strategy Hint

The `strategy_hint` is an optional reference to patterns in pattern-library.yaml
and the Change Engine's strategies.md. It tells the Change Engine "we've seen
something like this before." This is INFORMATIONAL, not prescriptive.

```python
def determine_strategy_hint(cr, capability, understanding_data, pattern_library):
    """Suggest a strategy from pattern-library.yaml or known patterns.

    Returns a string (strategy name) or None.
    """
    extracted = cr.get("extracted", {})

    if capability == "value_editing":
        target_lines = understanding_data.get('target_lines', []) if understanding_data else []
        has_array6 = any("Array6" in str(tl.get("content", "")) for tl in target_lines)

        if has_array6:
            if extracted.get("factor"):
                return "array6-multiply"
            elif extracted.get("old_value") is not None:
                return "factor-table"

        # Const value changes
        understanding = understanding_data.get('understanding', {}) if understanding_data else {}
        hazards = understanding.get('hazards', [])
        if any(h.get('type') == 'const_rate_values' for h in hazards):
            return "constant-value"

        # Generic factor table
        if extracted.get("case_value") is not None:
            return "factor-table"

        # Check pattern-library.yaml for function-specific hints
        if pattern_library and understanding_data:
            func_name = understanding_data.get('function', '')
            if func_name in pattern_library.get('function_patterns', {}):
                return pattern_library['function_patterns'][func_name].get('strategy_hint')

        return None

    if capability == "structure_insertion":
        kw = cr.get("domain_hints", {}).get("keyword_matches", [])
        if "endorsement" in kw:
            return "new-endorsement"
        if "coverage" in kw:
            return "case-block-insertion"
        if "eligibility" in kw or "validation" in kw:
            return "validation-function"
        return None

    if capability == "flow_modification":
        return None  # Flow modifications are too varied for standard hints

    return None
```

#### P.3.4 Build the Intent

For each (cr, function_name, understanding_data, match_source) tuple:

```python
def build_intent(intent_id, cr, func_name, understanding_data, match_source,
                 file_classification, effective_date, pattern_library):
    """Build a single intent from a CR + understood function.

    All Understanding fields are passed through directly -- the Plan agent
    does NOT recompute line numbers or FUBs.
    """
    extracted = cr.get("extracted", {})
    target = understanding_data or {}
    understanding = target.get('understanding', {})

    capability = determine_capability(cr, understanding_data)
    strategy_hint = determine_strategy_hint(cr, capability, understanding_data, pattern_library)
    intent_origin = determine_intent_origin(cr, match_source)
    confidence = compute_confidence(match_source, understanding_data, cr)

    # Determine target_kind from code_understanding.yaml
    target_kind = target.get('target_kind', 'call')

    # Determine file_type from file_reference_map
    source_file = target.get('source_file', '')
    file_name = source_file.split('/')[-1] if source_file else ''
    file_type = file_classification.get(file_name, 'unknown')

    intent = {
        "id": intent_id,
        "cr": cr["id"],
        "title": cr["title"],
        "description": cr.get("description", cr["title"]),
        "capability": capability,
        "intent_origin": intent_origin,
        "strategy_hint": strategy_hint,
        "file": target.get('target_file', target.get('file', '')),
        "file_type": file_type,
        "function": func_name,
        "target_kind": target_kind,
        "depends_on": [],
        "confidence": confidence,
        "open_questions": [],

        # Evidence traceability (carried from CR)
        "source_text": cr.get("source_text", cr.get("title", "")),
        "source_location": cr.get("source_location", ""),
        "evidence_refs": cr.get("evidence_refs", []),
        "assumptions": [],
        "done_when": build_done_when(cr, capability, func_name, extracted),

        # Understanding pass-through fields
        "source_file": target.get('source_file'),
        "target_file": target.get('target_file'),
        "needs_copy": target.get('needs_copy', False),
        "file_hash": target.get('file_hash'),
        "function_line_start": target.get('function_start'),
        "function_line_end": target.get('function_end'),
        "target_lines": target.get('target_lines', []),
        "skipped_lines": target.get('skipped_lines', []),
        "parameters": build_parameters(cr, capability),
        "peer_examples": [],

        # Understanding-enriched metadata
        "rounding_resolved": understanding.get('rounding_resolved'),
        "rounding_detail": understanding.get('rounding_detail'),
        "has_expressions": understanding.get('has_expressions', False),
        "candidates_shown": target.get('candidates_shown'),
        "developer_confirmed": target.get('developer_confirmed', True),
    }

    # Add open questions from ambiguity
    if cr.get("ambiguity_flag"):
        intent["open_questions"].append(cr.get("ambiguity_note", "Ambiguous CR"))

    # Add open questions from missing values
    if capability == "structure_insertion" and not extracted.get("premium"):
        if "premium" in cr.get("description", "").lower():
            intent["open_questions"].append(
                f"Premium amount not specified for {cr['title']}"
            )

    return intent


def build_parameters(cr, capability):
    """Extract the relevant parameters from the CR for this capability."""
    extracted = cr.get("extracted", {})
    params = {}

    if capability == "value_editing":
        if extracted.get("factor"):
            params["factor"] = extracted["factor"]
            params["scope"] = extracted.get("scope", "all_territories")
            params["rounding"] = "auto"
            rounding_hint = cr.get("domain_hints", {}).get("rounding_hint")
            if rounding_hint:
                params["rounding_hint"] = rounding_hint
        if extracted.get("old_value") is not None:
            params["old_value"] = extracted["old_value"]
            params["new_value"] = extracted.get("new_value")
        if extracted.get("case_value") is not None:
            params["case_value"] = extracted["case_value"]

    elif capability in ("structure_insertion", "file_creation"):
        for key, val in extracted.items():
            if val is not None and key not in ("method", "scope", "lob_scope"):
                params[key] = val

    elif capability == "flow_modification":
        for key, val in extracted.items():
            if val is not None:
                params[key] = val

    return params


def compute_confidence(match_source, understanding_data, cr):
    """Compute confidence score based on how well the CR matches the code."""
    base = {
        "understand": 0.95,
        "developer_hint": 0.90,
        "developer_hint_wildcard": 0.80,
        "glossary": 0.85,
        "keyword": 0.60,
    }.get(match_source, 0.50)

    # Boost if understanding has target_lines (high precision)
    if understanding_data and understanding_data.get('target_lines'):
        base = min(base + 0.05, 0.99)

    # Reduce if CR has ambiguity
    if cr.get("ambiguity_flag"):
        base = max(base - 0.15, 0.30)

    # Reduce if understanding data is minimal
    if understanding_data and not understanding_data.get('fub'):
        base = max(base - 0.10, 0.30)

    return round(base, 2)


def build_done_when(cr, capability, func_name, extracted):
    """Build a human-readable verification criteria string."""
    if capability == "value_editing":
        if extracted.get("factor"):
            return f"All rate values in {func_name} multiplied by {extracted['factor']}"
        elif extracted.get("old_value") is not None and extracted.get("new_value") is not None:
            return f"{func_name}: value changed from {extracted['old_value']} to {extracted['new_value']}"
        else:
            return f"Values in {func_name} updated per CR specification"
    elif capability == "structure_insertion":
        return f"New code block inserted in {func_name} as specified"
    elif capability == "file_creation":
        return f"New file created with required content"
    elif capability == "flow_modification":
        return f"Control flow in {func_name} modified per CR specification"
    else:
        return f"Change applied to {func_name} per CR specification"
```

#### P.3.5 Intent ID Assignment

Use sequential IDs: `intent-001`, `intent-002`, etc. Zero-padded to 3 digits.

#### P.3.6 Recording Assumptions

When the Plan agent makes a decision not explicitly stated in the CR, it MUST
record it in the intent's `assumptions` list. Examples:
- `"CR says 'all liability premiums' -- interpreting as GetLiabilityBundlePremiums only"`
- `"CR does not specify rounding -- using auto (match existing pattern)"`
- `"Applying to all territories (CR says 'increase' without territory restriction)"`

These assumptions flow through to the execution plan and review pipeline.

### Step P.4: Caller Analysis and Additional Intent Generation

**Action:** Check each intent's understanding data for caller_analysis warnings.
When the Understand agent detected that a caller OVERWRITES the return value of
a target function, the Plan agent MUST produce an additional flow_modification
intent to fix the caller.

#### P.4.1 Check for Caller Warnings

```python
def check_caller_warnings(intents, understanding_targets):
    """Scan understanding data for caller_analysis with HIGH risk.

    When found, produce an additional intent to fix the caller function.
    """
    additional_intents = []
    next_id = max_intent_id(intents) + 1

    for intent in intents:
        cr_id = intent["cr"]
        cr_understanding = understanding_targets.get(cr_id, {})
        understanding = cr_understanding.get('understanding', {})
        caller_summary = understanding.get('caller_chain_summary', '')

        # Check if understanding flagged caller overwrite risk
        hazards = understanding.get('hazards', [])
        caller_hazard = None
        for h in hazards:
            if h.get('type') == 'caller_overwrites_return':
                caller_hazard = h
                break

        if not caller_hazard:
            continue

        if caller_hazard.get('severity') != 'HIGH':
            # MEDIUM risk: add warning but don't auto-generate intent
            intent["caller_analysis_risk"] = caller_hazard.get('severity', 'MEDIUM')
            continue

        # HIGH risk: auto-generate caller fix intent
        caller_intent = build_caller_fix_intent(
            intent_id=f"intent-{next_id:03d}",
            original_intent=intent,
            caller_hazard=caller_hazard,
        )
        additional_intents.append(caller_intent)
        next_id += 1

        caller_intent["depends_on"].append(intent["id"])
        intent["has_caller_fix"] = caller_intent["id"]

    # --- P.4.3: Stored Field / Hidden Consumer Analysis ---
    #
    # Check for stored_field_propagation and hidden_consumer hazards.
    # These are DIFFERENT from caller_overwrites_return — they mean a
    # CALLED function has side effects that affect downstream consumers.
    #
    # Example: Moving High Theft surcharge after the All Perils call
    # fixes the local variable but breaks the stored PREMIUMCOMP field
    # that the Totals function reads.
    #
    for intent in intents:
        understanding = intent.get('understanding', {})
        hazards = understanding.get('hazards', [])

        for h in hazards:
            if h.get('type') in ('stored_field_propagation', 'hidden_consumer'):
                # ALWAYS treat as HIGH risk — these are invisible dependencies
                intent["stored_field_risk"] = "HIGH"
                intent["stored_field_detail"] = {
                    "hazard_type": h.get('type'),
                    "subtype": h.get('subtype', 'stored_field'),
                    "storing_function": h.get('storing_function', h.get('side_effect_function')),
                    "stored_field": h.get('stored_field', h.get('side_effect_detail')),
                    "consumers": h.get('field_readers', h.get('consumers', [])),
                    "totals_function": h.get('totals_function'),
                }

                # Add a prominent warning to the execution plan
                warning = {
                    "type": "STORED_FIELD_WARNING",
                    "intent_id": intent["id"],
                    "message": (
                        f"CRITICAL: {h.get('storing_function', 'Called function')} "
                        f"stores value to {h.get('stored_field', 'object field')} "
                        f"(ByVal — caller's variable is NOT updated). "
                        f"Consumers: {h.get('field_readers', h.get('consumers', []))}. "
                        f"The plan MUST ensure the stored field has the correct "
                        f"value after all changes. A simple code reorder may break "
                        f"the stored value while appearing correct locally."
                    ),
                }
                intent.setdefault("plan_warnings", []).append(warning)

                # If a totals function was identified, add dependency note
                if h.get('totals_function'):
                    intent.setdefault("verification_notes", []).append(
                        f"Verify {h['totals_function']} reads correct stored "
                        f"values after this change"
                    )

    return additional_intents
```

#### P.4.2 Build the Caller Fix Intent

```python
def build_caller_fix_intent(intent_id, original_intent, caller_hazard):
    """Build an intent to fix the caller that overwrites a return value.

    capability: 'flow_modification' -- we're changing control flow
    intent_origin: 'caller_fix' -- auto-generated from caller analysis
    """
    caller_func = caller_hazard.get("caller_function", "unknown")
    result_var = caller_hazard.get("result_variable", "unknown")
    competing_writes = caller_hazard.get("competing_writes", [])

    return {
        "id": intent_id,
        "cr": original_intent["cr"],
        "title": f"Fix caller '{caller_func}' -- remove overwrite of "
                 f"'{result_var}' returned by '{original_intent['function']}'",
        "description": f"Caller '{caller_func}' unconditionally overwrites "
                       f"'{result_var}' after calling '{original_intent['function']}'.",
        "capability": "flow_modification",
        "intent_origin": "caller_fix",
        "strategy_hint": None,
        "file": caller_hazard.get("caller_file", original_intent["file"]),
        "file_type": original_intent["file_type"],
        "function": caller_func,
        "target_kind": "code_block",
        "depends_on": [],
        "confidence": 0.80,
        "open_questions": [
            f"Caller '{caller_func}' overwrites the return value of "
            f"'{original_intent['function']}'. Confirm the correct fix approach."
        ],
        "source_text": original_intent.get("source_text", ""),
        "source_location": "Understand agent caller_analysis (auto-detected)",
        "evidence_refs": [f"caller_analysis for {original_intent['function']}"],
        "assumptions": [
            f"Auto-generated: Understand agent detected that {caller_func} overwrites "
            f"the result of {original_intent['function']}. Without fixing the "
            f"caller, the original change has no effect."
        ],
        "done_when": (
            f"'{result_var}' in '{caller_func}' is no longer unconditionally "
            f"overwritten after the call to '{original_intent['function']}'"
        ),
        "source_file": caller_hazard.get("caller_file", original_intent.get("source_file")),
        "target_file": caller_hazard.get("caller_file", original_intent.get("target_file")),
        "needs_copy": original_intent.get("needs_copy", False),
        "file_hash": None,
        "function_line_start": caller_hazard.get("call_site_line"),
        "function_line_end": None,
        "target_lines": [
            {
                "line": cw.get("line", 0),
                "content": cw.get("content", ""),
                "context": f"Competing write -- overwrites {result_var}",
                "rounding": None,
                "value_count": 0,
            }
            for cw in competing_writes
        ],
        "parameters": {
            "result_variable": result_var,
            "competing_writes": competing_writes,
            "original_function": original_intent["function"],
        },
        "caller_analysis_source": True,
    }
```

#### P.4.3 Shared Module Deduplication

Ensure shared modules are edited ONCE, not per LOB.

```python
def deduplicate_shared_intents(intents, shared_modules):
    """Remove duplicate intents for shared modules.

    If matching created multiple intents for the same function in a shared
    module (one per LOB), keep only the first and annotate with shared_by.
    """
    seen = {}  # (file, function) -> intent_id
    to_remove = []

    for intent in intents:
        if intent["file_type"] != "shared_module":
            continue
        key = (intent["file"], intent["function"])
        if key in seen:
            to_remove.append(intent["id"])
        else:
            seen[key] = intent["id"]
            for sm in shared_modules:
                if sm["file"] in (intent.get("source_file", ""), intent.get("target_file", "")):
                    intent["shared_by"] = sm["shared_by"]
                    break

    return [i for i in intents if i["id"] not in to_remove]
```

#### P.4.4 Multi-LOB Expansion

For LOB-specific changes, expand intents to cover all target LOBs.

- CRs with `lob_scope: "all"` that target LOB-specific files: one intent per LOB
- CRs with `lob_scope: "specific"`: only for `target_lobs`
- If a shared module change targets only specific LOBs but the module is compiled
  by all LOBs, flag the scope mismatch to the developer

#### P.4.5 Merge All Intents

```python
# After P.3 (regular intents) and P.4.1 (caller fix intents):
caller_fix_intents = check_caller_warnings(intents, understanding_targets)
if caller_fix_intents:
    intents.extend(caller_fix_intents)

# Deduplicate shared modules
intents = deduplicate_shared_intents(intents, shared_modules)

# Propagate caller_analysis_risk onto all intents
for intent in intents:
    if intent.get("caller_analysis_source"):
        continue
    cr_id = intent["cr"]
    cr_understanding = understanding_targets.get(cr_id, {})
    understanding = cr_understanding.get('understanding', {})
    for h in understanding.get('hazards', []):
        if h.get('type') == 'caller_overwrites_return':
            intent["caller_analysis_risk"] = h.get('severity')
```

---

## 5. CROSS-CHECK WITH PARSER

This section corresponds to Steps P.5 and P.6. This is NEW logic that validates
the Plan agent's intent mapping against the parser's authoritative target counts.

### Step P.5: Verify Target Counts

**Action:** For each intent, compare the planned target count against the parser's
target_count from code_understanding.yaml.

```python
def verify_target_counts(intents, understanding_targets):
    """Cross-check: planned targets = parser targets from code_understanding.

    WARN if mismatch -- indicates understanding phase missed something or
    the Plan agent over/under-mapped targets.
    """
    warnings = []

    for intent in intents:
        if intent["capability"] != "value_editing":
            continue

        cr_id = intent["cr"]
        cr_data = understanding_targets.get(cr_id, {})
        target = cr_data.get('target', {})
        parser_count = target.get('target_count', 0)
        plan_count = len(intent.get('target_lines', []))

        if parser_count > 0 and plan_count != parser_count:
            warnings.append({
                "intent": intent["id"],
                "cr": cr_id,
                "function": intent["function"],
                "parser_count": parser_count,
                "plan_count": plan_count,
                "message": f"Target count mismatch for {intent['function']}: "
                           f"parser found {parser_count}, plan has {plan_count}",
            })

    if warnings:
        for w in warnings:
            print(f"[Plan] WARN: {w['message']}")
            print(f"       Intent: {w['intent']}, CR: {w['cr']}")
    else:
        print(f"[Plan] Parser cross-check: all target counts match.")

    return warnings
```

### Step P.6: Verify .vbproj for Each Target LOB

**Action:** Verify that each affected LOB's .vbproj references the correct shared
module files. Uses `vb-parser project <lob.vbproj>` for each affected LOB.

```python
def verify_vbproj_references(intents, files_to_copy, vb_parser_path):
    """Verify .vbproj files reference expected shared modules.

    For each file copy, confirm that the target .vbproj files exist and
    reference the source file that will be updated.
    """
    warnings = []

    for fc in files_to_copy:
        for vbu in fc.get('vbproj_updates', []):
            vbproj_path = vbu['vbproj']

            # Run vb-parser project to get compiled file list
            # result = run_command(f'{vb_parser_path} project "{vbproj_path}"')
            # compiled_files = parse_json(result)

            # Verify old_include exists in current compiled files
            # If old_include is NOT in the compiled file list, WARN
            old_include = vbu['old_include']
            # Pseudocode: check that old_include resolves to a real file
            # in the .vbproj's Compile Include list

    if warnings:
        for w in warnings:
            print(f"[Plan] WARN: .vbproj verification: {w}")

    return warnings
```

---

## 6. DEPENDENCY RESOLUTION

This section corresponds to Steps P.7 and P.8. It ports dependency graph
construction and conflict detection from the Decomposer and Planner.

### Step P.7: Build Dependency DAG

**Action:** Parse dependency edges into a directed acyclic graph and validate it.

#### P.7.1 Detect Intra-CR Dependencies

When a single CR produces multiple intents:

```python
def detect_intra_cr_deps(intents):
    """Find dependencies between intents from the same CR.

    Rules:
    - If intent A creates a constant and intent B references it: A before B
    - If intent A creates a function and intent B calls it: A before B
    - If intent A creates a file and intent B modifies it: A before B
    """
    cr_groups = {}
    for intent in intents:
        cr_groups.setdefault(intent["cr"], []).append(intent)

    for cr_id, group in cr_groups.items():
        for a in group:
            for b in group:
                if a["id"] == b["id"]:
                    continue
                # Constant creation before reference
                if (a["capability"] == "structure_insertion" and
                    a.get("parameters", {}).get("constant_name")):
                    const_name = a["parameters"]["constant_name"]
                    if const_name in str(b.get("parameters", {})):
                        if a["id"] not in b["depends_on"]:
                            b["depends_on"].append(a["id"])

                # File creation before modification
                if a["capability"] == "file_creation":
                    if a["file"] == b["file"] and b["capability"] != "file_creation":
                        if a["id"] not in b["depends_on"]:
                            b["depends_on"].append(a["id"])
```

#### P.7.2 Detect Inter-CR Dependencies

Same logic but across CRs, also building partial_approval_constraints:

```python
def detect_inter_cr_deps(intents):
    """Find dependencies between intents from different CRs."""
    constraints = []
    for a in intents:
        for b in intents:
            if a["id"] == b["id"] or a["cr"] == b["cr"]:
                continue
            if (a["capability"] == "structure_insertion" and
                a.get("parameters", {}).get("constant_name")):
                const_name = a["parameters"]["constant_name"]
                if const_name in str(b.get("parameters", {})):
                    if a["id"] not in b["depends_on"]:
                        b["depends_on"].append(a["id"])
                    constraints.append({
                        "cr": b["cr"],
                        "requires_cr": a["cr"],
                        "reason": f"{b['id']} depends on {a['id']}",
                        "blocking_intents": [b["id"]],
                        "required_intents": [a["id"]],
                    })
    return constraints
```

### Step P.8: Detect Conflicts

**Action:** Detect when multiple intents from different CRs target the same code.

```python
def detect_conflicts(intents):
    """Detect conflicting intents using group-and-compare.

    Conflict key = (file, function, case_value or None).
    Two intents from different CRs sharing a key with different target
    values are a TRUE CONFLICT requiring developer resolution.
    """
    groups = {}
    for intent in intents:
        case_val = intent.get("parameters", {}).get("case_value")
        key = (intent["file"], intent["function"], case_val)
        groups.setdefault(key, []).append(intent)

    conflicts = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        cr_ids = set(i["cr"] for i in group)
        if len(cr_ids) < 2:
            continue

        for i, a in enumerate(group):
            for b in group[i+1:]:
                if a["cr"] == b["cr"]:
                    continue
                a_vals = (a.get("parameters", {}).get("new_value"),
                          a.get("parameters", {}).get("factor"))
                b_vals = (b.get("parameters", {}).get("new_value"),
                          b.get("parameters", {}).get("factor"))
                if a_vals != b_vals:
                    conflicts.append((a, b, key))

    return conflicts
```

When conflicts are found, STOP and ask the developer:

```
[Plan] CONFLICT: Two CRs target the same value:
       {intent_A.id} (CR-{X}): {description_A} -> {value_A}
       {intent_B.id} (CR-{Y}): {description_B} -> {value_B}

       Key: ({file}, {function}, {case_value})

       These cannot both be applied. Which value should be used?
         a) {value_A} (from CR-{X})
         b) {value_B} (from CR-{Y})
         c) A different value (please specify)
```

#### P.8.1 Validate DAG Structure

```python
# Build adjacency lists
dependents = {intent["id"]: [] for intent in intents}
dependencies = {intent["id"]: [] for intent in intents}

for intent in intents:
    for dep_id in intent.get('depends_on', []):
        dependents[dep_id].append(intent["id"])
        dependencies[intent["id"]].append(dep_id)

# Check self-loops
for intent in intents:
    if intent["id"] in intent.get('depends_on', []):
        STOP(f"[Plan] ERROR: Self-loop: {intent['id']} depends on itself")

# Check all references exist
for intent in intents:
    for dep_id in intent.get('depends_on', []):
        if dep_id not in {i["id"] for i in intents}:
            STOP(f"[Plan] ERROR: {intent['id']} depends on {dep_id} which does not exist")
```

#### P.8.2 Cycle Detection (DFS 3-Color)

```python
WHITE, GRAY, BLACK = 0, 1, 2
color = {intent["id"]: WHITE for intent in intents}

def dfs(node):
    color[node] = GRAY
    for neighbor in dependents[node]:
        if color[neighbor] == GRAY:
            return True  # Cycle found
        if color[neighbor] == WHITE:
            if dfs(neighbor):
                return True
    color[node] = BLACK
    return False

for intent in intents:
    if color[intent["id"]] == WHITE:
        if dfs(intent["id"]):
            STOP("[Plan] ERROR: Circular dependency detected!")
```

---

## 7. EXECUTION ORDERING

This section corresponds to Steps P.9 and P.10. It ports the topological sort,
phase grouping, and bottom-to-top ordering from the Planner.

### Step P.9: Topological Sort (Kahn's Algorithm)

**Action:** Compute a dependency-respecting execution order.

```python
from collections import deque

in_degree = {intent["id"]: len(dependencies[intent["id"]]) for intent in intents}

# Initialize queue with in-degree 0 nodes
queue = deque(sorted(
    [iid for iid, deg in in_degree.items() if deg == 0],
    key=lambda x: x
))

topo_order = []
topo_level = {}
current_level = {iid: 0 for iid in queue}

while queue:
    intent_id = queue.popleft()
    topo_order.append(intent_id)
    topo_level[intent_id] = current_level[intent_id]

    for dep_intent in sorted(dependents[intent_id]):
        in_degree[dep_intent] -= 1
        current_level.setdefault(dep_intent, 0)
        current_level[dep_intent] = max(
            current_level[dep_intent],
            current_level[intent_id] + 1
        )
        if in_degree[dep_intent] == 0:
            queue.append(dep_intent)
    queue = deque(sorted(queue, key=lambda x: x))

# Verify completeness
if len(topo_order) != len(intents):
    stuck = [i["id"] for i in intents if i["id"] not in set(topo_order)]
    STOP(f"[Plan] ERROR: Topological sort incomplete! Stuck: {stuck}")
```

### Step P.10: Group into Phases and Order Bottom-to-Top

#### P.10.1 Phase Grouping

Group intents into execution phases based on topological level and file conflicts.
Same-file intents at the same level get separate phases.

```python
level_groups = {}
for intent_id in topo_order:
    level = topo_level[intent_id]
    level_groups.setdefault(level, []).append(intent_id)

phases = []
phase_num = 0

for level in sorted(level_groups.keys()):
    intents_at_level = level_groups[level]

    # Group by target file
    file_groups = {}
    for intent_id in intents_at_level:
        target = intent_map[intent_id]['target_file']
        file_groups.setdefault(target, [])
        file_groups[target].append(intent_id)

    max_per_file = max(len(ints) for ints in file_groups.values())

    for sub_phase_idx in range(max_per_file):
        phase_num += 1
        phase_intents = []
        for target_file, ints in file_groups.items():
            if sub_phase_idx < len(ints):
                phase_intents.append(ints[sub_phase_idx])

        if phase_intents:
            phases.append({
                'phase': phase_num,
                'intents': phase_intents,
                'topo_level': level,
            })

# Assign titles and rationales
for phase in phases:
    phase_ints = phase['intents']
    if len(phase_ints) == 1:
        phase['title'] = intent_map[phase_ints[0]]['title']
    else:
        caps = set(intent_map[iid]['capability'] for iid in phase_ints)
        if len(caps) == 1:
            phase['title'] = f"{len(phase_ints)} {caps.pop().replace('_', ' ')} changes"
        else:
            phase['title'] = f"Mixed changes ({len(phase_ints)} intents)"

    # Determine rationale and depends_on_phases
    dep_phases = set()
    for iid in phase_ints:
        for dep_id in intent_map[iid].get('depends_on', []):
            for prev in phases:
                if dep_id in prev['intents']:
                    dep_phases.add(prev['phase'])
    phase['depends_on_phases'] = sorted(dep_phases)
    if dep_phases:
        phase['rationale'] = f"Depends on Phase(s) {', '.join(str(p) for p in sorted(dep_phases))}"
    elif phase.get('topo_level', 0) == 0:
        phase['rationale'] = "Independent, no dependencies"
    else:
        phase['rationale'] = "Same topological level, different file from adjacent phase"
```

#### P.10.2 Within-File Bottom-to-Top Ordering

**Why bottom-to-top matters:** When the Change Engine adds or removes lines,
all line numbers BELOW the edit stay the same, but all above shift. Starting
from the bottom (highest line numbers first), each edit only affects lines
already processed, so references for remaining intents stay valid.

```python
file_intents = {}  # target_file -> [(line_ref, intent_id)]

for intent in intents:
    target = intent['target_file']
    file_intents.setdefault(target, [])

    if intent['capability'] == 'value_editing':
        if intent.get('target_lines'):
            line_ref = max(tl['line'] for tl in intent['target_lines'])
        else:
            line_ref = intent.get('function_line_start', 0)
    elif intent['capability'] == 'structure_insertion':
        if intent.get('insertion_point'):
            line_ref = intent['insertion_point']['line']
        elif intent.get('function_line_start'):
            line_ref = intent['function_line_start']
        else:
            line_ref = 0
    else:
        line_ref = intent.get('function_line_start', 0)

    file_intents[target].append((line_ref, intent['id']))

# Sort DESCENDING by line number (highest first = bottom-to-top)
file_operation_order = {}
for target_file, ints_with_lines in file_intents.items():
    sorted_ints = sorted(ints_with_lines, key=lambda x: x[0], reverse=True)
    file_operation_order[target_file] = [
        {'intent_id': iid, 'line_ref': lr}
        for lr, iid in sorted_ints
    ]
```

#### P.10.3 Build Flat Execution Sequence

```python
execution_sequence = []

for phase in phases:
    phase_intents_by_file = {}
    for iid in phase['intents']:
        target = intent_map[iid]['target_file']
        phase_intents_by_file.setdefault(target, []).append(iid)

    for target_file in sorted(phase_intents_by_file.keys()):
        ints = phase_intents_by_file[target_file]
        if target_file in file_operation_order:
            full_order = [e['intent_id'] for e in file_operation_order[target_file]]
            ints_sorted = [iid for iid in full_order if iid in ints]
        else:
            ints_sorted = ints

        for iid in ints_sorted:
            execution_sequence.append({
                'intent_id': iid,
                'phase': phase['phase'],
                'file': intent_map[iid]['target_file'],
                'capability': intent_map[iid]['capability'],
                'strategy_hint': intent_map[iid].get('strategy_hint'),
                'tier': intent_map[iid].get('tier', 1),
            })
```

---

## 8. PREVIEW GENERATION

This section corresponds to Steps P.11 and P.12. It ports before/after preview
computation and the execution_plan.md generation from the Planner.

### Step P.11: Compute Before/After Previews

**Action:** Read actual source files and compute expected before/after for each
intent using Decimal arithmetic (NEVER float).

**CRITICAL: ALL rate calculations MUST use Decimal arithmetic with ROUND_HALF_EVEN
(banker's rounding).** This is decision A11.

#### P.11.1 Read Source Files

```python
file_contents = {}
for intent in intents:
    src = intent['source_file']
    if src and src not in file_contents:
        with open(src, 'r') as f:
            file_contents[src] = f.readlines()
```

#### P.11.2 Compute Before/After for value_editing Intents

```python
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation

def decimal_multiply(value, factor, rounding_mode):
    """Multiply a value by a factor using Decimal arithmetic.

    rounding_mode:
    - "banker": Round to nearest integer using ROUND_HALF_EVEN
    - "none": Keep 2 decimal places using ROUND_HALF_EVEN
    - None: Keep 2 decimal places (explicit value, no special rounding)
    """
    d_val = Decimal(str(value))
    d_factor = Decimal(str(factor))
    result = d_val * d_factor

    if rounding_mode == "banker":
        return result.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN)
    elif rounding_mode == "none":
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
    else:
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)


for intent in intents:
    if intent['capability'] != 'value_editing':
        continue

    intent['before_after'] = []
    strategy = intent.get('strategy_hint', '')
    params = intent['parameters']

    for tl in intent.get('target_lines', []):
        content = tl['content']
        line_num = tl['line']
        rounding = tl.get('rounding')

        if strategy in ('array6-multiply', None) and params.get('factor'):
            factor = params['factor']
            values = parse_array6_values(content, tl.get('evaluated_args'))
            new_values = []
            pct_changes = []

            for val in values:
                if isinstance(val, str):
                    new_values.append(val)
                    pct_changes.append(None)
                else:
                    new_val = decimal_multiply(val, factor, rounding)
                    new_values.append(new_val)
                    if val != 0:
                        d_val = Decimal(str(val))
                        pct = float((new_val - d_val) / abs(d_val) * 100)
                        pct_changes.append(pct)
                    else:
                        pct_changes.append(0.0)

            new_content = rebuild_array6_line(content, new_values)

            intent['before_after'].append({
                'line': line_num,
                'context': tl.get('context', ''),
                'before': content.strip(),
                'after': new_content.strip(),
                'pct_changes': pct_changes,
                'value_count': tl.get('value_count', len(values)),
            })

        elif strategy == 'factor-table' or params.get('case_value'):
            old_val = params['old_value']
            new_val = params['new_value']
            new_content = content.replace(str(old_val), str(new_val))

            pct = None
            if old_val != 0:
                pct = ((new_val - old_val) / abs(old_val)) * 100

            intent['before_after'].append({
                'line': line_num,
                'context': tl.get('context', ''),
                'before': content.strip(),
                'after': new_content.strip(),
                'change': f"{old_val} -> {new_val}",
                'pct_change': pct,
            })

        else:
            old_val = params.get('old_value')
            new_val = params.get('new_value')
            if old_val is not None and new_val is not None:
                new_content = content.replace(str(old_val), str(new_val))
            else:
                new_content = content

            intent['before_after'].append({
                'line': line_num,
                'context': tl.get('context', ''),
                'before': content.strip(),
                'after': new_content.strip(),
                'change': f"{old_val} -> {new_val}" if old_val is not None else "",
            })
```

**`parse_array6_values` helper:** Extract numeric values from an Array6 call.
The first argument may be a variable name (e.g., `basePremium`); subsequent
arguments are numeric. If the target_line entry has `evaluated_args`
(pre-computed by the Understand agent), use those values directly. Otherwise,
if an argument contains arithmetic (e.g., `30 + 10`), evaluate it safely.

**`rebuild_array6_line` helper:** Reconstruct the Array6 line with new values,
preserving exact whitespace and formatting from the original line.

#### P.11.3 Compute Aggregate Statistics

```python
total_value_changes = 0
all_pct_changes = []

for intent in intents:
    if intent['capability'] == 'value_editing':
        for ba in intent.get('before_after', []):
            if 'value_count' in ba:
                total_value_changes += ba['value_count']
            else:
                total_value_changes += 1
            if 'pct_changes' in ba:
                for pct in ba['pct_changes']:
                    if pct is not None:
                        all_pct_changes.append(pct)
            elif 'pct_change' in ba and ba['pct_change'] is not None:
                all_pct_changes.append(ba['pct_change'])

min_pct = min(all_pct_changes) if all_pct_changes else 0
max_pct = max(all_pct_changes) if all_pct_changes else 0
```

### Step P.12: Compute Risk Level and Assign Tiers

#### P.12.1 Risk Level Computation

```python
risk_level = "LOW"
risk_reasons = []

# MEDIUM conditions
unique_files = set(i['target_file'] for i in intents)
if len(unique_files) > 1:
    risk_level = "MEDIUM"
    risk_reasons.append(f"Multiple target files ({len(unique_files)})")

if any(i['file_type'] == 'shared_module' for i in intents):
    risk_level = "MEDIUM"
    shared_count = sum(1 for i in intents if i['file_type'] == 'shared_module')
    risk_reasons.append(f"{shared_count} intents in shared module")

if total_value_changes > 100:
    risk_level = "MEDIUM"
    risk_reasons.append(f"{total_value_changes} value changes (>100)")

if any(i.get('rounding_resolved') == 'mixed' for i in intents):
    risk_level = "MEDIUM"
    risk_reasons.append("Mixed rounding detected")

# HIGH conditions
for intent in intents:
    for dep_id in intent.get('depends_on', []):
        dep_intent = intent_map.get(dep_id)
        if dep_intent and intent['target_file'] != dep_intent['target_file']:
            risk_level = "HIGH"
            risk_reasons.append(f"Cross-file dependency: {intent['id']} -> {dep_id}")

if blast_radius.get('cross_province_warnings'):
    risk_level = "HIGH"
    risk_reasons.append("Cross-province file references detected")

insertion_intents = [i for i in intents if i['capability'] == 'structure_insertion']
if len(insertion_intents) > 2:
    risk_level = "HIGH"
    risk_reasons.append(f"{len(insertion_intents)} structure_insertion intents")

if any(i.get('has_expressions') for i in intents):
    risk_level = "HIGH"
    risk_reasons.append("Array6 arguments contain arithmetic expressions")

unconfirmed = [i['id'] for i in intents if not i.get('developer_confirmed', True)]
if unconfirmed:
    risk_level = "HIGH"
    risk_reasons.append(f"Unconfirmed intents: {', '.join(unconfirmed)}")

# Stored field propagation or hidden consumer hazards → always HIGH
stored_field_intents = [i['id'] for i in intents if i.get('stored_field_risk')]
if stored_field_intents:
    risk_level = "HIGH"
    risk_reasons.append(
        f"Stored field propagation detected in {', '.join(stored_field_intents)}: "
        f"called functions store values to object fields read by downstream consumers. "
        f"Code reordering may appear correct locally but break stored field values."
    )
```

#### P.12.2 Intent Tier Assignment

```
TIER ASSIGNMENT TABLE
---------------------------------------------------------------------
Condition                                                    Tier
---------------------------------------------------------------------
value_editing, simple strategy, no mixed rounding,            1
  no expressions

value_editing with mixed rounding OR has_expressions          2

structure_insertion, simple constant, no code_patterns        1

structure_insertion with code_patterns OR fub present         2

file_creation (needs_new_file)                                2

Any intent with strategy_hint == null and confidence < 0.8    3

Any intent with cross-file dependency                         3

Any intent with developer_confirmed == false                  3

Any intent where function_line_end - function_line_start >    2
  100 (large functions benefit from FUB)

DEFAULT (no match)                                            1
---------------------------------------------------------------------
Highest tier wins when multiple conditions match.
```

```python
def assign_tier(intent, intent_map):
    tier = 0
    capability = intent.get("capability", "value_editing")

    if capability == "value_editing":
        has_mixed = intent.get("rounding_resolved") == "mixed"
        has_expr = intent.get("has_expressions", False)
        if not has_mixed and not has_expr:
            tier = max(tier, 1)
        else:
            tier = max(tier, 2)
    elif capability == "structure_insertion":
        is_simple_const = (
            intent.get("parameters", {}).get("constant_name")
            and not intent.get("code_patterns")
        )
        if is_simple_const:
            tier = max(tier, 1)
        if intent.get("code_patterns") or intent.get("fub"):
            tier = max(tier, 2)
    elif capability == "file_creation":
        tier = max(tier, 2)

    if not intent.get("strategy_hint") and intent.get("confidence", 1.0) < 0.8:
        tier = max(tier, 3)

    for dep_id in intent.get("depends_on", []):
        dep = intent_map.get(dep_id)
        if dep and intent.get("target_file") != dep.get("target_file"):
            tier = max(tier, 3)

    if not intent.get("developer_confirmed", True):
        tier = max(tier, 3)

    func_start = intent.get("function_line_start", 0)
    func_end = intent.get("function_line_end", 0)
    if func_start and func_end and (func_end - func_start) > 100:
        tier = max(tier, 2)

    if tier == 0:
        tier = 1

    return tier

for intent in intents:
    intent["tier"] = assign_tier(intent, intent_map)
```

#### P.12.3 Value Flow Verification

Belt-and-suspenders check that value changes actually reach the final output.

```python
def verify_value_flow(intents):
    flow_warnings = []
    for intent in intents:
        if intent["capability"] != "value_editing":
            continue
        caller_fix_id = intent.get("has_caller_fix")
        if caller_fix_id:
            companion = next((i for i in intents if i["id"] == caller_fix_id), None)
            if not companion:
                flow_warnings.append({
                    "intent": intent["id"],
                    "warning": f"Missing companion fix intent {caller_fix_id}",
                    "severity": "CRITICAL",
                })
        caller_risk = intent.get("caller_analysis_risk")
        if caller_risk == "HIGH" and not caller_fix_id:
            flow_warnings.append({
                "intent": intent["id"],
                "warning": f"HIGH caller risk for {intent['function']} with no fix",
                "severity": "CRITICAL",
            })
    return flow_warnings

flow_warnings = verify_value_flow(intents)
if any(w["severity"] == "CRITICAL" for w in flow_warnings):
    risk_level = "HIGH"
    for w in flow_warnings:
        if w["severity"] == "CRITICAL":
            risk_reasons.append(f"VALUE FLOW: {w['warning']}")
```

### Step P.12.4: Resolve Open Questions (Q&A Flow)

**Action:** Collect open questions from intents, present them to the developer,
record answers, and update intents with resolved values.

Scan all intents for `open_questions`. If none, skip this step.

Present questions grouped by intent:

```
Questions requiring your input:

Intent intent-002: "Add $50,000 sewer backup coverage tier"
  Q1: Ticket specifies $50K tier but no premium amount. What value?
  Q2: Insert before or after existing $25K case?
```

Record answers in `plan/developer_decisions.yaml`:

```yaml
decisions:
  - question: "Ticket specifies $50K tier but no premium amount. What value?"
    answer: "125.00"
    intent: "intent-002"
    question_index: 1
    answered_at: "{ISO 8601 timestamp}"
```

Update intents: fill missing values, remove answered questions, bump confidence.

Classify remaining questions as BLOCKING or NON-BLOCKING:

```python
BLOCKING_CATEGORIES = {"missing_value", "ambiguous_scope", "conflicting_reqs", "missing_insertion"}
NON_BLOCKING_CATEGORIES = {"style_preference", "optimization_choice", "optional_enhancement"}

def classify_question(question_text, intent):
    q_lower = question_text.lower()
    if any(kw in q_lower for kw in ["what value", "what premium", "not specified", "missing"]):
        return "blocking", "missing_value"
    if any(kw in q_lower for kw in ["which territories", "which lobs", "which function"]):
        return "blocking", "ambiguous_scope"
    if any(kw in q_lower for kw in ["conflict", "contradicts"]):
        return "blocking", "conflicting_reqs"
    if any(kw in q_lower for kw in ["where to insert", "insert before or after"]):
        return "blocking", "missing_insertion"
    return "non-blocking", "style_preference"
```

**BLOCKING QUESTION GATE:** If ANY blocking questions remain:
1. Mark plan as `DRAFT - DECISIONS REQUIRED`
2. List blocking questions at TOP of execution_plan.md
3. Set `plan_status: "draft"` in execution_order.yaml
4. Orchestrator MUST NOT present draft plan as approvable at Gate 1

---

## 9. GATE 1 PRESENTATION

This section corresponds to Step P.13. It defines how the Plan agent generates
the execution_plan.md for developer approval.

### Step P.13: Generate execution_plan.md

**Action:** Write the human-readable plan for Gate 1 approval.

#### P.13.1 Plan Structure

```markdown
# EXECUTION PLAN: {Province} {LOB(s)} {Date}

## Understanding Journey
**From description:** {1-2 sentence summary}
**From comments:** {what comments changed or added}
**From screenshots:** {what was extracted -- or "None"}
**Final understanding:** {2-3 sentences}
**What changed:** {what differs from raw description}

## Decisions Applied
{List of developer decisions, or "No decisions required"}

## Blocking Questions
{Empty if approvable, listed if DRAFT}

## Plan By Change Request

### CR-001: {title}

**What the ticket is asking:**
{from ticket understanding}

**Evidence:**
- Source: "{quoted text from ticket}"
- Location: {where in ticket}

**Implementation:**

> **Phase {N}: {intent title}** (intent-001) `[capability]`
>
> - File: `{filepath}`
> - Function: `{function}()`
> - Action: {description}
> - Before -> After: {preview with per-value % annotations}

**Validation:**
- {done_when criteria from intent}

**Risks/Assumptions:**
- {assumptions, risk flags}

---

## Out of Scope
{CRs with reasons -- omit if none}

## Execution Order
{Phase ordering with dependency explanation}

## Verification Strategy

### What the Plugin Will Verify Automatically [AUTO]
- Array6 syntax: correct parentheses, unchanged arg counts
- Completeness: all territories updated, all LOBs handled
- No old file modification: only target-date files edited
- No commented code modified
- Value sanity: rate changes within expected range
- Cross-LOB consistency: shared module references consistent
- Traceability: every CR maps to at least one code change
- Vbproj integrity: every Compile Include resolves to existing file
- Semantic verification: old x factor = new within rounding tolerance

### What the Developer Must Verify [DEV]
- **CR-001:** Build in VS -> confirm compile. Run quote -> check premiums.
- **CR-002:** Run quote with ${case_value} deductible -> verify factor.
- **General:** svn commit and record revision.

## Impact Summary
- Files to copy: {N}
- Files to modify: {N}
- .vbproj updates: {N}
- Value change range: {min%} to {max%}
- Risk level: {risk}

## Context Tiers
  Tier 1 (value substitution):  {N} intents
  Tier 2 (logic with patterns): {N} intents
  Tier 3 (full context):        {N} intents

## Approval
Approving this plan means you agree with BOTH:
1. The business interpretation (what we're changing and why)
2. The code implementation (how we're making the changes)

Approve, reject, or ask questions.
```

#### P.13.2 SIMPLE vs COMPLEX Format

```python
use_simple = (
    len(intents) <= 2
    and len(unique_files) <= 1
    and risk_level in ("LOW", "MEDIUM")
)
```

SIMPLE: condense sections, omit empty ones, show all before/after entries.
COMPLEX: full structure, show first 2 of N for large before/after lists.

#### P.13.3 Phase Detail by Capability

**value_editing (Array6 multiply):**
```
Phase {N}: {title} (intent-001) [value_editing]
  File: {target_file}
  Function: {function_name}()
  Action: Multiply all Array6 values by {factor}
  Rounding: {rounding_resolved}

  Before -> After (Territory 1):
    Array6(basePremium, 233, 274, 319, 372, 432, 502)
    Array6(basePremium, 245, 288, 335, 391, 454, 527)
                        +5.2%  +5.1%  +5.0%  +5.1%  +5.1%  +5.0%

  (showing 2 of N -- all follow same pattern)
  Impact: {N} lines x {M} values = {total} changes
```

**value_editing (factor table):**
```
Phase {N}: {title} (intent-001) [value_editing]
  File: {target_file}
  Function: {function_name}()
  Action: Change Case {case_value} factor

  Before: {code line with old value}
  After:  {code line with new value}
  Change: {old_value} -> {new_value} ({pct}%)
```

**structure_insertion:**
```
Phase {N}: {title} (intent-001) [structure_insertion]
  File: {target_file}
  Function: {function_name}()
  Action: {description}

  Insert after line {line} ({context}):
    + {new code line 1}
    + {new code line 2}
```

**file_creation:**
```
Phase {N}: {title} (intent-001) [file_creation]
  CREATE NEW FILE: {target_file}
  Template: {template_reference}
  Action: {description}
```

**flow_modification:**
```
Phase {N}: {title} (intent-001) [flow_modification]
  File: {target_file}
  Function: {function_name}()
  Action: {description}
  Origin: caller_fix (auto-generated)

  Target lines:
    Line {N}: {content}
```

#### P.13.4 Write Output Files

Write `plan/execution_plan.md`, `plan/execution_order.yaml`, and
`execution/file_hashes.yaml`.

Capture file hashes for TOCTOU protection:

```python
file_hash_entries = {}

# Source files
for fc in files_to_copy:
    file_hash_entries[fc['source']] = {
        'hash': fc['source_hash'],
        'size': os.path.getsize(fc['source']),
        'role': 'source',
    }
    file_hash_entries[fc['target']] = {
        'hash': None, 'size': None, 'role': 'target',
    }

# .vbproj files
for fc in files_to_copy:
    for vbu in fc.get('vbproj_updates', []):
        vbproj = vbu['vbproj']
        if vbproj not in file_hash_entries:
            with open(vbproj, 'rb') as f:
                h = 'sha256:' + hashlib.sha256(f.read()).hexdigest()
            file_hash_entries[vbproj] = {
                'hash': h, 'size': os.path.getsize(vbproj), 'role': 'vbproj',
            }
```

#### P.13.5 Gate 1 Guardrails

**D7: The orchestrator MUST NEVER directly edit plan/analysis/parsed/ files.**

When the developer requests corrections at Gate 1, the orchestrator follows the
structured update loop:

1. **CAPTURE:** Record the developer's correction verbatim
2. **DETERMINE:** Decide which upstream agent must re-run
3. **RE-RUN:** Re-invoke the appropriate agent with updated context
4. **RE-PRESENT:** Show the updated plan to the developer
5. **ESCALATE:** After 3 failed correction cycles, escalate to developer

The Plan agent is stateless -- each invocation reads all inputs fresh from disk
and generates fresh output files.

---

## 10. EDGE CASES AND RULES

### Case 1: Two CRs Target the Same Function with Different Case Values

**Scenario:** CR-002 changes Case 5000, CR-003 changes Case 2500, both in
SetDisSur_Deductible.

**Handling:** Separate intents. NOT a conflict -- different Case values are
independent edits. Bottom-to-top ordering sequences them within the file.

### Case 2: Two CRs Target the Same Value (True Conflict)

**Scenario:** CR-002 says Case 5000 -> -0.22, CR-005 says Case 5000 -> -0.25.

**Handling:** Detected by conflict detection (Step P.8). STOP and ask developer.

### Case 3: Cross-LOB File Compilation

**Scenario:** Intent targets a file compiled by both Home and Condo.

**Handling:** Classify as `file_type: "cross_lob"`. Add `cross_lob_warning`.

### Case 4: CR Matches No Analyzed Function

**Scenario:** CR references a utility function the Understand agent did not trace.

**Handling:** Ask developer for function name. Create intent with `confidence: 0.30`.

### Case 5: One CR Produces Many Intents (10+)

**Scenario:** "Add Elite Comp coverage" for 6-LOB workflow -> 9 intents.

**Handling:** Normal. Report count to developer.

### Case 6: LOB-Scope = Specific

**Scenario:** CR targets only Home and Condo, but shared module affects all 6 LOBs.

**Handling:** Flag scope mismatch. Shared module intents affect all compiling LOBs.

### Case 7: Broad CR ("Increase All Liability Premiums")

**Scenario:** CR matches 3 liability functions.

**Handling:** Create separate intents per function. Present candidates if keyword match.

### Case 8: Nested If/Else in Factor Tables

**Scenario:** Case 5000 has farm vs non-farm branches.

**Handling:** Understanding agent already identified this in FUB. All target lines
passed through. Change Engine or developer decides which branches to modify.

### Case 9: Cross-Province Shared File

**Scenario:** Intent references Code/PORTCommonHeat.vb.

**Handling:** NEVER modify. Include in plan as WARNING. Exclude from execution_sequence.

### Case 10: File Already Has Target-Date Copy

**Scenario:** Previous workflow already created mod_Common_SKHab20260101.vb.

**Handling:** `needs_copy: false`. No file copy phase. Edit existing file directly.
Hash still captured for TOCTOU.

### Case 11: Zero Intents (Values Already Match)

**Scenario:** All values already equal requested targets.

**Handling:** Write empty plan. No approval needed. Workflow marked COMPLETED.

### Case 12: Very Large Plan (100+ intents)

**Handling:** Abbreviate before/after in execution_plan.md (show first 3, summary
for rest). execution_order.yaml always contains ALL intents.

### Case 13: Circular Dependency

**Handling:** STOP immediately. Write no output. Orchestrator must re-run.

### Case 14: Stale Hash Detected

**Handling:** STOP. Source file changed since Understanding ran. Re-run /iq-plan.

### Case 15: Mixed Rounding Within Same Function

**Handling:** Check `target_lines[].rounding` for EACH line independently. Show
rounding mode per entry in the plan.

### Case 16: has_expressions in Array6

**Handling:** Elevate risk to HIGH. Show evaluated values in before/after.

---

## 11. WORKED EXAMPLES

### Example A: Simple -- Single File, 1 CR, 5% Rate Multiply

**Scenario:** New Brunswick Home, effective 2026-07-01. Single CR: increase
GetBasePremium_Home Array6 values by 5%.

**Input from Understand (code_understanding.yaml):**

```yaml
change_requests:
  cr-001:
    title: "Increase home base premiums by 5%"
    target:
      file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
      function: "GetBasePremium_Home"
      function_start: 312
      function_end: 418
      target_kind: "call"
      target_lines:
        - line: 322
          content: "                Case 1 : varRates = Array6(basePremium, 233, 274, 319, 372, 432, 502)"
          rounding: "banker"
          value_count: 6
        - line: 324
          content: "                Case 2 : varRates = Array6(basePremium, 198, 233, 271, 316, 367, 427)"
          rounding: "banker"
          value_count: 6
        # ... 13 more territories
      target_count: 15
    understanding:
      rounding_resolved: "banker"
      has_expressions: false
    needs_copy: true
    source_file: "New Brunswick/Code/mod_Common_NBHab20260401.vb"
    target_file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
    file_hash: "sha256:abc123..."
    developer_confirmed: true
```

**Step P.2 -- Match:** CR-001 -> GetBasePremium_Home (understand: direct match)

**Step P.3 -- Form intent:**

```yaml
- id: "intent-001"
  cr: "cr-001"
  title: "Increase home base premiums by 5%"
  capability: "value_editing"
  intent_origin: "direct_cr"
  strategy_hint: "array6-multiply"
  file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
  file_type: "shared_module"
  function: "GetBasePremium_Home"
  target_kind: "call"
  parameters: {factor: 1.05, scope: "all_territories", rounding: "auto"}
  confidence: 0.95
```

**Step P.5 -- Parser cross-check:** 15 target lines matches target_count 15. OK.

**Step P.7 -- Dependencies:** None.

**Step P.9 -- Topo sort:** 1 node. Trivial.

**Step P.10 -- Phases:** 1 phase.

**Step P.11 -- Before/after (first 2 territories, Decimal arithmetic):**

```
Territory 1:
  Before: Array6(basePremium, 233, 274, 319, 372, 432, 502)
  After:  Array6(basePremium, 245, 288, 335, 391, 454, 527)
  %:                         +5.2  +5.1  +5.0  +5.1  +5.1  +5.0

Territory 2:
  Before: Array6(basePremium, 198, 233, 271, 316, 367, 427)
  After:  Array6(basePremium, 208, 245, 285, 332, 385, 448)
  %:                         +5.1  +5.2  +5.2  +5.1  +4.9  +4.9
```

Decimal check: 233 * 1.05 = 244.65 -> banker round = 245. Correct.

**Step P.12 -- Risk:** MEDIUM (shared module).

**Plan output:** SIMPLE format. Scannable in 10 seconds.

### Example B: Medium -- 3 CRs, Mixed Capabilities

**Scenario:** Saskatchewan Habitational, effective 2026-01-01.
- CR-001: [DAT FILE] -- out of scope
- CR-002: Deductible $5000 factor change (value_editing)
- CR-003: Deductible $2500 factor change (value_editing)
- CR-004: Liability premium increase 1.03x (value_editing, 2 functions)

**Step P.2 -- Filter:** CR-001 out of scope (DAT file).

**Step P.2 -- Match:**
- CR-002 -> SetDisSur_Deductible (understand: direct)
- CR-003 -> SetDisSur_Deductible (understand: direct)
- CR-004 -> GetLiabilityBundlePremiums + GetLiabilityExtensionPremiums

**Step P.3 -- Form intents:**
- intent-001: value_editing, SetDisSur_Deductible, Case 5000 (from CR-002)
- intent-002: value_editing, SetDisSur_Deductible, Case 2500 (from CR-003)
- intent-003: value_editing, GetLiabilityBundlePremiums, multiply 1.03 (from CR-004)
- intent-004: value_editing, GetLiabilityExtensionPremiums, multiply 1.03 (from CR-004)

**Step P.7 -- Dependencies:** None between these intents.

**Step P.10 -- Bottom-to-top for mod_Common_SKHab20260101.vb:**

```
file_operation_order:
  - intent-004  (line 4106, highest -- executed first)
  - intent-003  (line 4012)
  - intent-001  (line 2202)
  - intent-002  (line 2180, lowest -- executed last)
```

**Step P.12 -- Risk:** MEDIUM. Reasons: shared module, 4 intents.

**Output:** COMPLEX format with 4 phases, before/after for each.

### Example C: Complex -- Cross-File Dependencies

**Scenario:** Saskatchewan Hab, 2 CRs with dependencies:
- CR-001: Add ELITECOMP constant + routing (3 intents)
- CR-002: Add eligibility rule (1 intent, depends on CR-001)

**Intents:**

```yaml
- id: "intent-001"
  cr: "cr-001"
  title: "Add ELITECOMP constant"
  capability: "structure_insertion"
  intent_origin: "direct_cr"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  function: null        # Module-level
  depends_on: []

- id: "intent-002"
  cr: "cr-001"
  title: "Add Elite Comp rate table routing"
  capability: "flow_modification"
  intent_origin: "direct_cr"
  function: "GetRateTableID"
  depends_on: ["intent-001"]

- id: "intent-003"
  cr: "cr-001"
  title: "Add DAT IDs to ResourceID.vb"
  capability: "structure_insertion"
  intent_origin: "direct_cr"
  file: "Saskatchewan/Home/20260101/ResourceID.vb"
  depends_on: []

- id: "intent-004"
  cr: "cr-002"
  title: "Add Elite Comp eligibility validation"
  capability: "flow_modification"
  intent_origin: "direct_cr"
  depends_on: ["intent-001"]
```

**Dependency graph:**

```
intent-001 (ELITECOMP constant)
  |
  +---> intent-002 (rate table routing)
  |
  +---> intent-004 (eligibility rule)

intent-003 (DAT IDs) -- independent
```

**Partial approval constraints:**

```yaml
- cr: "cr-002"
  requires_cr: "cr-001"
  reason: "intent-004 depends on intent-001"
```

**Step P.9 -- Topo sort:**
- Level 0: intent-001, intent-003
- Level 1: intent-002, intent-004

**Step P.12 -- Risk:** HIGH (cross-file dependency, structure_insertion).

### Example D: Caller Fix Auto-Generated

**Scenario:** CR-001 changes GetBasePremium_Home, but CalcHabDwelling overwrites
the return value.

**Step P.4 -- Caller analysis detects HIGH risk:**

```yaml
hazards:
  - type: "caller_overwrites_return"
    severity: "HIGH"
    caller_function: "CalcHabDwelling"
    result_variable: "dblBasePrem"
    competing_writes:
      - line: 445
        content: "dblBasePrem = dblBasePrem * dblLocationFactor"
```

**Auto-generated intent:**

```yaml
- id: "intent-002"
  cr: "cr-001"
  title: "Fix caller 'CalcHabDwelling' -- remove overwrite of 'dblBasePrem'"
  capability: "flow_modification"
  intent_origin: "caller_fix"
  depends_on: ["intent-001"]
  open_questions:
    - "Caller 'CalcHabDwelling' overwrites the return value. Confirm fix approach."
```

---

## 12. FILE CLASSIFICATION RULES

Priority order -- first match wins:

```
RULE 1: Cross-Province Shared (NEVER MODIFY)
  Match: file resolves to codebase-root Code/ (not province Code/)
  Result: file_type = "cross_province_shared"
  Action: NEVER generate intents. Include as WARNING in plan.

RULE 2: Shared Hab Module
  Match: mod_Common_{Prov}Hab{Date}.vb OR file in shared_modules[]
  Result: file_type = "shared_module"

RULE 3: Shared Auto Module
  Match: mod_Algorithms_{Prov}Auto{Date}.vb OR mod_DisSur_{Prov}Auto{Date}.vb
  Result: file_type = "shared_module" (if 2+ projects) OR "lob_specific"

RULE 4: LOB-Specific CalcOption
  Match: CalcOption_{PROV}{LOB}{Date}.vb
  Result: file_type = "lob_specific"

RULE 5: Cross-LOB Option/Liab File
  Match: Option_* or Liab_* AND 2+ LOB projects compile it
  Result: file_type = "cross_lob"

RULE 6: Single-LOB Option/Liab
  Match: same as Rule 5 but only 1 project compiles it
  Result: file_type = "lob_specific"

RULE 7: Local File (in version folder)
  Result: file_type = "local"

RULE 8: SHARDCLASS File
  Match: in SHARDCLASS/ (or SharedClass/ for Nova Scotia)
  Result: file_type = "shardclass"
```

---

## 13. CAPABILITY QUICK REFERENCE

| What the intent does | Capability | intent_origin |
|---------------------|-----------|--------------|
| Multiply Array6 values by a factor | value_editing | direct_cr |
| Change a Select Case value (old -> new) | value_editing | direct_cr |
| Change a Const value | value_editing | direct_cr |
| Change an included limit value | value_editing | direct_cr |
| Add a new Array6 premium row | structure_insertion | direct_cr |
| Add a new Const declaration | structure_insertion | direct_cr |
| Add a new Select Case branch | structure_insertion | direct_cr |
| Add DAT IDs to ResourceID.vb | structure_insertion | direct_cr |
| Create a new Option_*.vb file | file_creation | direct_cr |
| Add CalcOption routing (new Case) | flow_modification | direct_cr |
| Add validation/eligibility logic | flow_modification | direct_cr |
| Fix caller overwrite of return value | flow_modification | caller_fix |
| Re-do after review feedback | (any) | rework |

---

## 14. GRACEFUL DEGRADATION

| Missing Data | Fallback |
|-------------|----------|
| code_understanding.yaml absent | STOP -- cannot plan without code understanding |
| change_requests.yaml absent | STOP -- cannot plan without CRs |
| config.yaml missing | STOP -- need carrier configuration |
| pattern-library.yaml absent | Skip strategy hint enrichment, proceed |
| codebase-profile.yaml absent | Skip rule dependency check, proceed |
| ticket_understanding.md absent | Omit Understanding Journey section in plan |
| Specific CR not in understanding | Ask developer for function, low-confidence intent |

---

## 15. ERROR HANDLING

### Missing Code Understanding

```
[Plan] ERROR: No code understanding found at analysis/code_understanding.yaml
       Was the Understand agent run? Check manifest.yaml for understand.status.
```

### Missing Change Requests

```
[Plan] ERROR: Cannot read parsed/change_requests.yaml
       Was the Intake agent completed?
```

### Invalid Intent Schema

```
[Plan] ERROR: Intent {intent_id} missing required field: {field_name}
```

### Hash Mismatch (Stale File)

```
[Plan] ERROR: Source file changed since Understand agent ran!
       File: {filepath}
       Expected hash: {expected}
       Current hash:  {actual}
       Re-run from /iq-plan to get fresh analysis.
```

### Cycle Detected

```
[Plan] ERROR: Circular dependency detected!
       Cycle: {cycle_path}
       Review depends_on fields and break the cycle.
```

### Topological Sort Incomplete

```
[Plan] ERROR: Topological sort processed {N} of {M} intents.
       Stuck intents: {list}
       Re-run from /iq-plan to rebuild.
```

---

## 16. BOUNDARY TABLE

| Responsibility | Plan Agent | Orchestrator (/iq-plan) | /iq-execute |
|---|---|---|---|
| Map CRs to intents | YES | NO | NO |
| Form intent_graph.yaml | YES | NO | Consumes |
| Order intents (topo sort) | YES | NO | Follows order |
| Bottom-to-top within file | YES | NO | Follows order |
| Resolve open questions (Q&A) | YES | NO | NO |
| Present plan to developer | Writes files | Shows to developer | NO |
| Handle Gate 1 approval | NO | YES | Requires approved |
| Handle partial approval | Writes constraints | Processes approval | Executes approved only |
| File hash capture | YES | NO | Reads + verifies |
| TOCTOU check at execution | NO | NO | YES |
| File copies | Lists in plan | NO | Executes copies |
| Before/after computation | YES (Decimal) | Shows to developer | Executes changes |
| Risk level computation | YES | Displays | NO |
| Developer interaction | Q&A step only | YES (Gate 1) | YES (if issues) |
| Cross-province warning | Includes in plan | Shows warning | Skips execution |
| .vbproj update instructions | Passes through | NO | Executes updates |

---

## 17. PARTIAL APPROVAL

When the developer partially approves at Gate 1, the orchestrator handles
interaction. The Plan agent provides data enabling partial approval:

1. **partial_approval_constraints** -- inter-CR couplings
2. **CR grouping** -- every intent has a `cr` field
3. **Dependency chain tracking** -- `depends_on` edges enable transitive checks

```python
def get_blocked_crs(rejected_crs, intents):
    """Given rejected CRs, find all transitively blocked CRs."""
    rejected_intents = set()
    for intent in intents:
        if intent['cr'] in rejected_crs:
            rejected_intents.add(intent['id'])

    blocked_crs = set()
    changed = True
    while changed:
        changed = False
        for intent in intents:
            if intent['cr'] in rejected_crs or intent['cr'] in blocked_crs:
                continue
            for dep_id in intent.get('depends_on', []):
                if dep_id in rejected_intents:
                    blocked_crs.add(intent['cr'])
                    rejected_intents.add(intent['id'])
                    changed = True
                    break
    return blocked_crs
```

---

## 18. PLAN REVISION

The Plan agent is STATELESS. Each invocation:
1. Reads all inputs fresh from disk
2. Validates everything from scratch (including hash checks)
3. Generates fresh output files

**Revision scenarios:**

| Scenario | Action |
|----------|--------|
| Developer corrects a value | Orchestrator updates intent, re-runs Plan |
| Developer rejects approach | Re-run from Understand agent |
| Developer requests additions | Re-run from Intake agent |

---

## 19. KEY RESPONSIBILITIES (Summary)

1. **Load all upstream output:** Read config, change_requests, code_understanding
2. **Filter out-of-scope CRs:** dat_file_warning = true -> OUT_OF_SCOPE
3. **Match CRs to understood functions:** Priority: understand > hint > glossary > keyword
4. **Form intents:** One per (function, capability) pair, with strategy hint and intent_origin
5. **Generate caller fix intents:** flow_modification for HIGH caller overwrite risk
6. **Deduplicate shared modules:** One intent per shared function, not per LOB
7. **Cross-check with parser:** Verify target counts match parser authoritative count
8. **Build and validate dependency DAG:** Check self-loops, missing refs, cycles
9. **Detect conflicts:** Group-and-compare across CRs, ask developer to resolve
10. **Compute topological sort:** Kahn's algorithm with deterministic tie-breaking
11. **Group into phases:** Same topo level + different files = same phase
12. **Order bottom-to-top within files:** Highest line first to prevent drift
13. **Compute before/after with Decimal arithmetic:** ROUND_HALF_EVEN for all values
14. **Compute risk level:** LOW -> MEDIUM -> HIGH
15. **Assign intent tiers:** 1 (thin), 2 (standard), 3 (full context)
16. **Resolve open questions:** Q&A with developer, blocking/non-blocking classification
17. **Generate execution_plan.md:** Human-readable plan with [AUTO] and [DEV] verification
18. **Generate execution_order.yaml:** Machine-readable plan with phases and sequence
19. **Write file_hashes.yaml:** SHA-256 for TOCTOU protection
20. **Present Gate 1:** Verification strategy, risk assessment, approval prompt

---

## 20. NOT YET IMPLEMENTED (Future Enhancements)

- **Interactive plan builder:** Allow developer to reorder phases before approving
- **Dry-run execution:** Run Change Engine in dry-run to validate before Gate 1
- **Plan diffing:** Show what changed when re-running after revision
- **Parallel execution hints:** Analyze whether non-overlapping functions in same
  file could safely execute in parallel

<!-- IMPLEMENTATION: v0.4.0 Plan Agent - replaces Decomposer + Planner -->
