# Agent: Planner

## Purpose

Produce a dependency-ordered execution plan and the approval document presented at
Gate 1. The plan should be so clear and informative that the developer spends minimal
time reviewing it. Capture file hashes for TOCTOU protection.

The Planner is a FULLY AUTOMATED agent -- it has NO developer interaction. It reads
Analyzer output, computes optimal execution ordering, generates before/after previews,
and writes two output files: a human-readable plan (`plan/execution_plan.md`) and a
machine-readable execution order (`plan/execution_order.yaml`). The orchestrator
(/iq-plan) presents the human-readable plan to the developer at Gate 1.

**Core philosophy: Make the plan scannable.** A simple 5% rate increase should take
10 seconds to review. A complex multi-SRD hab workflow should clearly show phases,
dependencies, and risk areas so the developer knows exactly what will happen.

## Pipeline Position

```
[INPUT] --> Intake --> Decomposer --> Analyzer --> PLANNER --> [GATE 1] --> Modifiers --> Reviewer --> [GATE 2]
                                                  ^^^^^^^
```

- **Upstream:** Analyzer agent (provides updated `analysis/operations/op-{SRD}-{NN}.yaml` with line numbers + `analysis/blast_radius.md` + `analysis/files_to_copy.yaml` + `analysis/dependency_graph.yaml`)
- **Downstream:** Rate Modifier and Logic Modifier agents (consume `plan/execution_order.yaml`); Developer reviews `plan/execution_plan.md` at Gate 1; /iq-execute reads `execution/file_hashes.yaml`

---

## Input Schema

The Planner reads these files from the workstream directory
(`.iq-workstreams/changes/{workstream-name}/`):

### manifest.yaml (from orchestrator)

```yaml
# Key fields the Planner reads:
workflow_id: "20260101-SK-Hab-rate-update"    # Unique identifier for this workflow
province: "SK"                                 # Province code (AB, BC, MB, NB, NS, ON, PE, SK)
province_name: "Saskatchewan"                  # Full province name for display
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]  # Target LOBs
effective_date: "20260101"                     # Target effective date (YYYYMMDD)
state: "ANALYZING"                             # Current workflow state (Planner expects ANALYZING)
risk_indicators:                               # Risk flags from earlier agents
  shared_module: true                          # true if any operation targets a shared module
  cross_lob: false                             # true if cross-LOB file references detected
  cross_province_shared: false                 # true if cross-province shared files flagged
```

**Purpose:** Provides workflow-level context for plan header and risk computation.

### config.yaml (from .iq-workstreams/)

```yaml
# Key fields the Planner reads:
provinces:
  SK:
    name: "Saskatchewan"
    lobs:
      - name: "Home"
        is_hab: true
        shardclass_folder: "SHARDCLASS"        # or "SharedClass" for NS
      # ... one per LOB
    hab_code: "SKHab"                          # Used in naming patterns
naming:
  shared_module: "mod_Common_{hab_code}{date}.vb"
  calc_option: "CalcOption_{prov}{lob}{date}.vb"
  # ... other naming patterns
```

**Purpose:** Cheat sheet for classification hints and naming conventions. The Planner
uses this for display labels and naming pattern validation -- NOT for discovering
files (the Analyzer already did that).

### analysis/dependency_graph.yaml (from Decomposer, preserved by Analyzer)

```yaml
workflow_id: "20260101-SK-Hab-rate-update"
decomposer_version: "1.0"
decomposed_at: "2026-02-27T10:00:00"
total_operations: 6                            # Total operations decomposed
total_out_of_scope: 1                          # SRDs marked out of scope (DAT file, etc.)

out_of_scope:                                  # SRDs with no operations (tracked for audit)
  - srd: "srd-001"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"

shared_operations:                             # Operations targeting shared modules
  op-002-01:
    srd: "srd-002"
    description: "Change $5000 deductible factor from -0.20 to -0.22"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    agent: "rate-modifier"
    depends_on: []                             # List of op IDs this depends on
  # ... more operations

lob_operations:                                # Operations targeting LOB-specific files
  op-005-01:
    srd: "srd-005"
    description: "Add DAT IDs to ResourceID.vb"
    file: "Saskatchewan/Home/20260101/ResourceID.vb"
    file_type: "lob_specific"
    agent: "logic-modifier"
    depends_on: []
  # ... more operations

partial_approval_constraints: []               # Inter-SRD coupling for Gate 1
# Non-empty example:
#   - srd: "srd-003"
#     requires_srd: "srd-001"
#     reason: "op-003-01 depends on op-001-01"
#     blocking_operations: ["op-003-01"]
#     required_operations: ["op-001-01"]

execution_order:                               # Topological order from Decomposer
  - "op-002-01"
  - "op-003-01"
  - "op-004-01"
  - "op-004-02"
  - "op-005-01"
  - "op-005-02"
```

**Purpose:** The Planner uses `execution_order` as the starting point for phase
grouping, `depends_on` edges to build the DAG, and `partial_approval_constraints`
to carry forward into the plan for Gate 1 partial approval.

### analysis/operations/op-{SRD}-{NN}.yaml (from Analyzer)

Each operation file contains Decomposer fields + Analyzer additions. The Planner
reads ALL operation files. Key fields used by the Planner:

**Common fields (all operation types):**

| Field | Type | Purpose for Planner |
|-------|------|-------------------|
| `id` | string | Operation identifier (e.g., "op-002-01") |
| `srd` | string | Parent SRD ID (for partial approval grouping) |
| `title` | string | Human-readable title (used in phase titles) |
| `description` | string | Detailed description (included in plan) |
| `file` | string | Target file path (for file grouping) |
| `file_type` | string | shared_module, lob_specific, etc. (for risk) |
| `function` | string or null | Target function name (for display) |
| `agent` | string | "rate-modifier" or "logic-modifier" (for display) |
| `depends_on` | list | Operation IDs this depends on (for DAG) |
| `blocked_by` | list | Reverse of depends_on (for reference) |
| `pattern` | string | Change pattern type (for display) |
| `parameters` | dict | Pattern-specific parameters (for before/after) |

**Analyzer-added fields (rate-modifier operations):**

| Field | Type | Purpose for Planner |
|-------|------|-------------------|
| `source_file` | string | Current file from .vbproj (for reading current values) |
| `target_file` | string | New dated copy (for plan display) |
| `needs_copy` | bool | Whether file copy is needed (for copy phase) |
| `file_hash` | string | SHA-256 of source_file (for TOCTOU) |
| `function_line_start` | int | First line of function (for ordering) |
| `function_line_end` | int | Last line of function (for display) |
| `rounding_resolved` | string | "banker", "none", or "mixed" (for before/after calc). **Present for base_rate_increase only**; null/absent for factor_table_change and included_limits. Use `.get()` with graceful fallback. |
| `rounding_detail` | string | Explanation of rounding decision (for plan notes) |
| `target_lines` | list | Lines to modify, each with: |
| `target_lines[].line` | int | Line number (for bottom-to-top ordering) |
| `target_lines[].content` | string | Current code content (for before/after) |
| `target_lines[].context` | string | Where in the function (for display) |
| `target_lines[].rounding` | string or null | Per-line rounding (for before/after calc) |
| `target_lines[].value_count` | int | Number of values in Array6 (for impact count) |
| `target_lines[].evaluated_args` | list or null | Pre-evaluated numeric values when Array6 has arithmetic expressions (e.g., "30 + 10" -> 40). Use these instead of re-parsing. |
| `skipped_lines` | list | Lines intentionally excluded (for audit) |
| `candidates_shown` | int | How many candidates Analyzer showed developer |
| `developer_confirmed` | bool | Whether developer confirmed targets |
| `analysis_notes` | string | Analyzer's notes (included in plan) |
| `has_expressions` | bool | Whether Array6 args contain arithmetic (for risk) |

**Analyzer-added fields (logic-modifier operations):**

| Field | Type | Purpose for Planner |
|-------|------|-------------------|
| `source_file` | string | Current file from .vbproj |
| `target_file` | string | New dated copy |
| `needs_copy` | bool | Whether file copy is needed |
| `file_hash` | string | SHA-256 of source_file |
| `location` | string or null | Human-readable location (e.g., "module-level constants") |
| `insertion_point` | dict | Where to insert new code: |
| `insertion_point.line` | int | Line number (for ordering) |
| `insertion_point.position` | string | "after" or "before" (for display) |
| `insertion_point.context` | string | Human description of location |
| `insertion_point.section` | string | Section of file (for display) |
| `existing_constants` | list | Already-defined constants (for context) |
| `duplicate_check` | string | Whether constant already exists |
| `needs_new_file` | bool | Whether Logic Modifier must CREATE a file |
| `template_reference` | string or null | Path to template file (if needs_new_file) |
| `candidates_shown` | int | How many candidates shown |
| `developer_confirmed` | bool | Whether developer confirmed |

### analysis/files_to_copy.yaml (from Analyzer)

```yaml
generated_at: "2026-02-27T10:30:00"
total_files: 2                                 # Number of file copies needed

files:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "sha256:a1b2c3d4..."          # For TOCTOU cross-check
    target_exists: false                        # Whether target already on disk
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    operations_in_file: ["op-002-01", "op-003-01", "op-004-01", "op-004-02"]
    vbproj_updates:                            # .vbproj reference updates needed
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"
      # ... one per .vbproj that references this file
```

**Purpose:** The Planner includes file copies as Phase 0 (always first) in the
execution plan and the execution_order.yaml.

### analysis/blast_radius.md (from Analyzer)

Human-readable blast radius report. The Planner reads this for:
- Risk assessment details (to cross-validate its own risk computation)
- Reverse lookup results (to include in plan notes)
- Flagged items (to surface warnings in the plan)

### Actual source files (on disk)

The Planner reads the actual VB.NET source files referenced by `source_file` in each
operation to:
- Extract current code lines for before/after display
- Compute expected new values for the "after" column
- Verify that file_hash values are still fresh

---

## Output Schema

### plan/execution_plan.md

Human-readable plan for developer approval at Gate 1. Two formats depending on
complexity.

#### SIMPLE format (1-2 operations, single file, LOW or MEDIUM risk)

```markdown
EXECUTION PLAN: {province_name} {LOB(s)} {effective_date}
====================================================

Summary: {N} change(s), {N} file(s), {N} value edits, {risk} risk

FILE COPIES:
  {source_filename} -> {target_filename}
    .vbproj updates: {N} file(s)

Phase 1: {title} ({op_id}) [{agent}]
  File: {target_file}
  Function: {function_name}()
  Action: {description}

  Before -> After ({context_label}):
    {old_line}
    {new_line}
                        {per-value % change annotations}

  Impact: {N} territories x {N} values = {N total} changes
  All changes: {min%} to {max%} (rounding variation)

Approve this plan? Say "approve" to proceed or tell me what to change.
```

#### COMPLEX format (3+ operations, multiple files, or HIGH risk)

```markdown
EXECUTION PLAN: {province_name} {LOB(s)} {effective_date}
====================================================

Summary: {N} operations across {N} files, {risk} risk
LOBs affected: {comma-separated list}
Shared module: {filename} (if applicable)

OUT OF SCOPE (flagged, not executed):
  SRD-{NNN}: {title} -- {reason}

FILE COPIES:
  {source_filename} -> {target_filename}
    Shared by: {LOB list}
    .vbproj updates: {N} file(s)

  {source_filename} -> {target_filename}
    Used by: {LOB}
    .vbproj updates: {N} file(s)

Phase 1: {title} ({op_id}) [{agent}]
  File: {target_file}
  {details depending on operation type -- see below}

Phase 2: {title} ({op_id}) [{agent}, depends on Phase {N}]
  File: {target_file}
  {details}

... (all phases)

IMPACT SUMMARY:
  Total value changes: {N}
  Total files modified: {N}
  Total .vbproj updates: {N}
  Risk level: {risk} -- {reason}

CONTEXT TIERS:
  Tier 1 (value substitution):  {N} operations
  Tier 2 (logic with patterns): {N} operations
  Tier 3 (full context):        {N} operations

WARNINGS:
  {any warnings from analysis or risk computation}

PARTIAL APPROVAL CONSTRAINTS:
  {if any inter-SRD dependencies exist, show them here}
  {otherwise omit this section}

Approve this plan? Say "approve" to proceed or tell me what to change.
```

#### Phase detail formats by operation type

**rate-modifier (base_rate_increase with Array6):**
```markdown
Phase {N}: {title} ({op_id}) [rate-modifier]
  File: {target_file}
  Function: {function_name}()
  Action: Multiply all Array6 values by {factor}
  Rounding: {rounding_resolved} {rounding_detail if mixed}

  Before -> After ({context for first territory}):
    Array6({var}, {v1}, {v2}, {v3}, {v4}, {v5}, {v6})
    Array6({var}, {new_v1}, {new_v2}, {new_v3}, {new_v4}, {new_v5}, {new_v6})
                   {%chg}   {%chg}   {%chg}   {%chg}   {%chg}   {%chg}

  Before -> After ({context for second territory}):
    ...

  (showing 2 of {N} territories -- all follow same {factor}x pattern)

  Impact: {N} lines x {avg values per line} values = {total} changes
  Range: {min%} to {max%} (rounding variation)
```

**rate-modifier (factor_table_change):**
```markdown
Phase {N}: {title} ({op_id}) [rate-modifier]
  File: {target_file}
  Function: {function_name}()
  Action: Change Case {case_value} factor

  Before: {full code line with old value}
  After:  {full code line with new value}
  Change: {old_value} -> {new_value} ({percentage or absolute change})

  (if multiple code paths exist, show each:)
  Path 1 ({context}):
    Before: {line}
    After:  {line}
  Path 2 ({context}):
    Before: {line}
    After:  {line}
```

**logic-modifier (insertion):**
```markdown
Phase {N}: {title} ({op_id}) [logic-modifier{, depends on Phase M}]
  File: {target_file}
  {Function: {function_name}() | Location: {location}}
  Action: {description}

  Insert after line {insertion_point.line} ({insertion_point.context}):
    + {new code line 1}
    + {new code line 2}
    + {new code line 3}
```

**logic-modifier (new file):**
```markdown
Phase {N}: {title} ({op_id}) [logic-modifier]
  CREATE NEW FILE: {target_file}
  Template: {template_reference}
  Action: {description}
```

### plan/execution_order.yaml

Machine-readable plan consumed by /iq-execute.

```yaml
# File: plan/execution_order.yaml
# Generated by Planner agent
# Consumed by /iq-execute orchestrator and modifier agents

planner_version: "1.0"
generated_at: "2026-02-27T11:00:00"            # ISO 8601 timestamp
workflow_id: "20260101-SK-Hab-rate-update"      # From manifest.yaml

# Summary metrics
total_phases: 5                                 # Number of execution phases
total_operations: 6                             # Number of operations across all phases
total_value_changes: 107                        # Sum of all value edits
total_file_copies: 2                            # Number of file copies
total_vbproj_updates: 7                         # Number of .vbproj reference updates
risk_level: "MEDIUM"                            # LOW | MEDIUM | HIGH
risk_reasons:                                   # List of reasons for the risk level
  - "4 operations in shared module (6 LOBs)"
  - "Mixed rounding in GetLiabilityBundlePremiums"
tier_distribution:                               # From Step 9.5
  tier_1: 4                                      # Value substitution (thin capsule)
  tier_2: 2                                      # Logic with patterns (FUB + canonical)
  tier_3: 0                                      # Full context (FUB + peers + cross-file)

# File copy phase (always Phase 0, always first)
file_copies:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "sha256:a1b2c3d4..."           # From files_to_copy.yaml
    target_exists: false                         # Whether target already on disk
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    vbproj_updates:
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"
      # ... all .vbproj updates for this file copy

  - source: "Saskatchewan/Code/CalcOption_SKHOME20250901.vb"
    target: "Saskatchewan/Code/CalcOption_SKHOME20260101.vb"
    source_hash: "sha256:e5f6g7h8..."
    target_exists: false
    shared_by: []
    vbproj_updates:
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\CalcOption_SKHOME20250901.vb"
        new_include: "..\\Code\\CalcOption_SKHOME20260101.vb"

# Execution phases (dependency-ordered)
# Operations within the same phase can execute in parallel ONLY if they target
# different files. Same-file operations are NEVER in the same phase.
phases:
  - phase: 1
    title: "Add ELITECOMP constant"             # Human-readable phase title
    operations: ["op-003-01"]                   # List of operation IDs in this phase
    agent: "logic-modifier"                     # Primary agent (or "mixed" if both)
    rationale: "Must define constant before referencing it"
    depends_on_phases: []                       # Phase numbers this phase depends on

  - phase: 2
    title: "Add rate table selection"
    operations: ["op-003-02"]
    agent: "logic-modifier"
    rationale: "Depends on Phase 1 (ELITECOMP constant)"
    depends_on_phases: [1]

  - phase: 3
    title: "Base rate increase"
    operations: ["op-004-01"]
    agent: "rate-modifier"
    rationale: "Independent of Phases 1-2"
    depends_on_phases: []

  - phase: 4
    title: "Deductible factor changes + Liability extension premiums"
    operations: ["op-002-01", "op-004-02"]
    agent: "mixed"
    rationale: "op-002-01 and op-004-02 target different functions, sequenced after op-004-01 for same-file bottom-to-top"
    depends_on_phases: [3]

  - phase: 5
    title: "Add DAT IDs to ResourceID.vb"
    operations: ["op-005-01", "op-005-02", "op-005-03", "op-005-04", "op-005-05", "op-005-06"]
    agent: "logic-modifier"
    rationale: "LOB-specific changes, all independent, different files"
    depends_on_phases: []

# Within each file, operations are ordered highest line number first
# to prevent line-number drift from insertions/deletions above.
# The modifier agents MUST follow this order exactly.
file_operation_order:
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    - op_id: "op-004-02"                       # line 4106 (highest)
      line_ref: 4106                            # Reference line for ordering
      tier: 2                                   # From Step 9.5
    - op_id: "op-004-01"                       # line 4012
      line_ref: 4012
      tier: 2
    - op_id: "op-002-01"                       # line 2108
      line_ref: 2108
      tier: 1
    - op_id: "op-003-02"                       # line ~435
      line_ref: 435
      tier: 2
    - op_id: "op-003-01"                       # line ~23 (lowest)
      line_ref: 23
      tier: 1

# Flat execution sequence combining topological sort + bottom-to-top.
# /iq-execute processes operations in EXACTLY this order.
# This is the authoritative execution order.
execution_sequence:
  - op_id: "op-005-01"                         # Phase 5 - independent, different file
    phase: 5
    file: "Saskatchewan/Home/20260101/ResourceID.vb"
    agent: "logic-modifier"
    tier: 1                                     # From Step 9.5
  - op_id: "op-005-02"                         # Phase 5 - independent, different file
    phase: 5
    file: "Saskatchewan/Condo/20260101/ResourceID.vb"
    agent: "logic-modifier"
    tier: 1
  # ... (remaining op-005-* for other LOBs)
  - op_id: "op-004-02"                         # Phase 4 - bottom-to-top (line 4106)
    phase: 4
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "rate-modifier"
    tier: 2
  - op_id: "op-004-01"                         # Phase 3 - bottom-to-top (line 4012)
    phase: 3
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "rate-modifier"
    tier: 2
  - op_id: "op-002-01"                         # Phase 4 - bottom-to-top (line 2108)
    phase: 4
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "rate-modifier"
    tier: 1
  - op_id: "op-003-02"                         # Phase 2 - bottom-to-top (line ~435)
    phase: 2
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "logic-modifier"
    tier: 2
  - op_id: "op-003-01"                         # Phase 1 - bottom-to-top (line ~23)
    phase: 1
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    agent: "logic-modifier"
    tier: 1

# Partial approval constraints (carried from dependency_graph.yaml)
partial_approval_constraints: []
# Non-empty example:
#   - srd: "srd-003"
#     requires_srd: "srd-001"
#     reason: "op-003-01 depends on op-001-01"
```

### execution/file_hashes.yaml

```yaml
# File: execution/file_hashes.yaml
# Captured by Planner at plan generation time
# Used by /iq-execute for TOCTOU protection before each file write

planner_version: "1.0"
captured_at: "2026-02-27T11:00:00"             # ISO 8601 timestamp
workflow_id: "20260101-SK-Hab-rate-update"

files:
  "Saskatchewan/Code/mod_Common_SKHab20250901.vb":
    hash: "sha256:a1b2c3d4e5f6..."             # SHA-256 of file at plan time
    size: 45230                                 # File size in bytes
    role: "source"                              # source = will be copied
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    hash: null                                  # null = file does not exist yet (will be created by copy)
    size: null
    role: "target"                              # target = will be created/modified
  "Saskatchewan/Code/CalcOption_SKHOME20250901.vb":
    hash: "sha256:e5f6g7h8i9j0..."
    size: 12450
    role: "source"
  "Saskatchewan/Code/CalcOption_SKHOME20260101.vb":
    hash: null
    size: null
    role: "target"
  "Saskatchewan/Home/20260101/ResourceID.vb":
    hash: "sha256:7b1d4e..."
    size: 3210
    role: "target"                              # Already exists, will be modified in place
  # ... one entry per file that will be read, copied, or modified
```

**File hash handoff from Analyzer:** The Analyzer writes `file_hash` in each operation
file. The Planner collects these hashes and writes `execution/file_hashes.yaml` at
plan generation time. If a file's hash has changed between the Analyzer run and the
Planner run, the Planner MUST abort with a stale hash error (see Step 3).

---

## EXECUTION STEPS

These are the step-by-step instructions for generating the execution plan. Follow
them in order. Each step has clear inputs, actions, and outputs.

### Prerequisites

Before starting, confirm the following exist and are readable:

1. The workflow directory at `.iq-workstreams/changes/{workstream-name}/`
2. The `manifest.yaml` inside that directory
3. The `analysis/dependency_graph.yaml` (from Decomposer, preserved by Analyzer)
4. The `analysis/operations/` directory with individual op-{SRD}-{NN}.yaml files
5. The `analysis/files_to_copy.yaml` (from Analyzer)
6. The `analysis/blast_radius.md` (from Analyzer)
7. The `.iq-workstreams/config.yaml` (for naming patterns and hab flags)

If any of these are missing, STOP and report:
```
[Planner] Cannot proceed -- missing required file: {path}
          Was the Analyzer completed? Check manifest.yaml for analyzer.status = "completed".
```

### Step 1: Load Context

**Action:** Read manifest.yaml and config.yaml to build the workflow context.

1.1. Read `manifest.yaml`. Extract:
   - `workflow_id` (string -- used as identifier in output files)
   - `province` (string -- e.g., "SK")
   - `province_name` (string -- e.g., "Saskatchewan")
   - `lobs` (list -- e.g., ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"])
   - `effective_date` (string -- e.g., "20260101")
   - `risk_indicators` (dict -- shared_module, cross_lob, cross_province_shared flags)

1.2. Read `config.yaml` from `.iq-workstreams/`. Extract:
   - `provinces.{province}.lobs[]` with `is_hab` flags
   - `provinces.{province}.hab_code` (e.g., "SKHab")
   - `naming` patterns (for display and validation)

1.3. Read `analysis/dependency_graph.yaml`. Extract:
   - `total_operations` (int)
   - `total_out_of_scope` (int)
   - `out_of_scope` (list -- for inclusion in plan header)
   - `shared_operations` (dict -- op_id -> operation summary)
   - `lob_operations` (dict -- op_id -> operation summary)
   - `partial_approval_constraints` (list -- for inclusion in plan)
   - `execution_order` (list -- topological order from Decomposer)

1.4. Read `analysis/files_to_copy.yaml`. Extract:
   - `total_files` (int)
   - `files` (list -- each with source, target, source_hash, target_exists,
     shared_by, operations_in_file, vbproj_updates)

1.5. Build the **plan context** object:

```
PLAN CONTEXT
---------------------------------------------------------
Workflow:       {workflow_id}
Province:       {province_name} ({province})
LOBs:           {comma-separated lobs}
Effective Date: {effective_date}
Operations:     {total_operations} in scope, {total_out_of_scope} out of scope
File Copies:    {total_files} files to copy
Risk Indicators: shared_module={Y/N}, cross_lob={Y/N}, cross_province={Y/N}
```

If `total_operations == 0`:
```
[Planner] No in-scope operations to plan. All SRDs were out of scope.
          Out of scope: {list of out_of_scope SRD titles}
          Writing empty plan and exiting.
```
Write an empty execution_plan.md (with the out-of-scope list) and an empty
execution_order.yaml (total_phases: 0, total_operations: 0), then exit.

### Step 2: Load and Validate Operations

**Action:** Read all operation files and build the operation lookup map.

2.1. List all files in `analysis/operations/` matching pattern `op-*.yaml`.

2.2. For each operation file, read and validate required fields:

**For ALL operations:**
- `id` (string, must match filename pattern op-{SRD}-{NN})
- `srd` (string, must start with "srd-")
- `title` (string, non-empty)
- `file` (string, non-empty path)
- `file_type` (string, one of: shared_module, lob_specific, cross_lob, local)
- `agent` (string, one of: "rate-modifier", "logic-modifier")
- `depends_on` (list, may be empty)
- `source_file` (string, path to existing source file)
- `target_file` (string, path to target file)
- `needs_copy` (bool)
- `file_hash` (string, "sha256:...")

**Additional for rate-modifier operations:**
- `function_line_start` (int, > 0)
- `function_line_end` (int, > function_line_start)
- `target_lines` (list, non-empty, each with line, content, context, rounding)

**Additional for logic-modifier operations:**
- `insertion_point` (dict with line, position, context) OR `needs_new_file: true`

If any required field is missing or invalid:
```
[Planner] ERROR: Operation {op_id} is missing required field: {field_name}
          File: analysis/operations/{op_id}.yaml
          Was the Analyzer completed? This field should have been added by the Analyzer.
```

2.3. Build the **operation lookup map**: `op_id -> full operation data`

```python
# Pseudocode
op_map = {}
for op_file in operation_files:
    op = read_yaml(op_file)
    op_map[op['id']] = op
```

2.4. Count operations by agent type:

```
OPERATION COUNTS
---------------------------------------------------------
Rate-modifier operations:  {N}
Logic-modifier operations: {N}
Total:                     {N}
```

2.5. Validate that all operation IDs referenced in `execution_order` from
dependency_graph.yaml exist in the op_map:

```python
for op_id in dependency_graph['execution_order']:
    if op_id not in op_map:
        STOP("Operation {op_id} in execution_order not found in analysis/operations/")
```

2.6. Validate that all `depends_on` references point to existing operations:

```python
for op_id, op in op_map.items():
    for dep_id in op.get('depends_on', []):
        if dep_id not in op_map:
            STOP("Operation {op_id} depends on {dep_id} which does not exist")
```

### Step 3: Verify File Hashes (Freshness Check)

**Action:** Verify that no source files have changed since the Analyzer ran.

3.1. Collect all unique `source_file` paths across all operations:

```python
source_files = {}
for op_id, op in op_map.items():
    src = op['source_file']
    if src not in source_files:
        source_files[src] = {
            'expected_hash': op['file_hash'],
            'operations': [op_id]
        }
    else:
        source_files[src]['operations'].append(op_id)
        # Verify consistency: all ops on the same file should have the same hash
        if source_files[src]['expected_hash'] != op['file_hash']:
            STOP("Hash inconsistency for {src}: op {op_id} has different hash than others")
```

3.2. For each unique source file, compute the current SHA-256:

```python
import hashlib

for filepath, info in source_files.items():
    with open(filepath, 'rb') as f:
        current_hash = 'sha256:' + hashlib.sha256(f.read()).hexdigest()
    if current_hash != info['expected_hash']:
        STOP("""
[Planner] ERROR: Source file changed since Analyzer ran!
          File: {filepath}
          Expected hash: {info['expected_hash']}
          Current hash:  {current_hash}
          Affected operations: {', '.join(info['operations'])}

          Someone modified this file between the Analyzer and Planner runs.
          Re-run from /iq-plan to get fresh analysis.
""")
```

3.3. If ALL hashes match, proceed. Log:
```
[Planner] File hash verification: {N} source files checked, all current.
```

### Step 4: Build Dependency DAG

**Action:** Parse dependency edges into a directed acyclic graph and validate it.

4.1. Build adjacency lists from operation `depends_on` fields:

```python
# Forward edges: op -> list of ops that depend on it
dependents = {op_id: [] for op_id in op_map}
# Reverse edges: op -> list of ops it depends on
dependencies = {op_id: [] for op_id in op_map}

for op_id, op in op_map.items():
    for dep_id in op.get('depends_on', []):
        dependents[dep_id].append(op_id)
        dependencies[op_id].append(dep_id)
```

4.2. Validate: no self-loops.

```python
for op_id, op in op_map.items():
    if op_id in op.get('depends_on', []):
        STOP("[Planner] ERROR: Self-loop detected: {op_id} depends on itself")
```

4.3. Validate: all referenced nodes exist (already done in Step 2.6).

4.4. Detect cycles using DFS with 3-color marking:

```python
WHITE, GRAY, BLACK = 0, 1, 2
color = {op_id: WHITE for op_id in op_map}
parent = {op_id: None for op_id in op_map}
cycle_path = []

def dfs(node):
    color[node] = GRAY
    for neighbor in dependents[node]:
        if color[neighbor] == GRAY:
            # Found cycle -- reconstruct path
            path = [neighbor, node]
            current = node
            while current != neighbor and parent[current] is not None:
                current = parent[current]
                path.append(current)
            path.reverse()
            return path
        if color[neighbor] == WHITE:
            parent[neighbor] = node
            result = dfs(neighbor)
            if result:
                return result
    color[node] = BLACK
    return None

for op_id in op_map:
    if color[op_id] == WHITE:
        cycle = dfs(op_id)
        if cycle:
            cycle_str = ' -> '.join(cycle)
            STOP(f"""
[Planner] ERROR: Circular dependency detected!
          Cycle: {cycle_str}

          This should have been caught by the Decomposer. The dependency
          graph has a cycle that makes it impossible to determine execution
          order. Please review the depends_on fields in these operations
          and break the cycle.
""")
```

4.5. Log the validated DAG:
```
[Planner] Dependency DAG validated: {N} nodes, {E} edges, no cycles.
```

### Step 5: Topological Sort (Kahn's Algorithm)

**Action:** Compute a dependency-respecting execution order.

5.1. Compute in-degree for each node:

```python
from collections import deque

in_degree = {op_id: len(dependencies[op_id]) for op_id in op_map}
```

5.2. Initialize queue with all nodes having in-degree 0:

```python
# Tie-breaking: sort by op_id for deterministic output
queue = deque(sorted(
    [op_id for op_id, deg in in_degree.items() if deg == 0],
    key=lambda x: x
))
```

5.3. Process queue using Kahn's algorithm:

```python
topo_order = []
topo_level = {}  # op_id -> topological level (for phase grouping)

current_level = {op_id: 0 for op_id in queue}

while queue:
    op_id = queue.popleft()
    topo_order.append(op_id)
    topo_level[op_id] = current_level[op_id]

    for dep_op in sorted(dependents[op_id]):
        in_degree[dep_op] -= 1
        # Level of dependent = max level of all its dependencies + 1
        current_level.setdefault(dep_op, 0)
        current_level[dep_op] = max(
            current_level[dep_op],
            current_level[op_id] + 1
        )
        if in_degree[dep_op] == 0:
            queue.append(dep_op)
    # Re-sort queue for deterministic tie-breaking
    queue = deque(sorted(queue, key=lambda x: x))
```

5.4. Verify completeness:

```python
if len(topo_order) != len(op_map):
    processed = set(topo_order)
    stuck = [op_id for op_id in op_map if op_id not in processed]
    STOP(f"""
[Planner] ERROR: Topological sort incomplete!
          Processed: {len(topo_order)} of {len(op_map)} operations
          Stuck operations: {', '.join(stuck)}

          This indicates a cycle that DFS missed (should not happen).
          Re-run from /iq-plan to re-analyze.
""")
```

5.5. Log the topological order:
```
[Planner] Topological sort complete: {N} operations in {max_level + 1} levels.
          Order: {', '.join(topo_order)}
```

### Step 6: Group into Phases

**Action:** Group operations into execution phases based on topological level and
file conflicts.

6.1. Start with topological levels as initial phase grouping:

```python
# Group by topological level
level_groups = {}
for op_id in topo_order:
    level = topo_level[op_id]
    level_groups.setdefault(level, [])
    level_groups[level].append(op_id)
```

6.2. Within each level, split operations on the SAME file into separate phases.
Operations on different files at the same topological level can stay together
(they execute on different files, so no line-drift conflict):

```python
phases = []
phase_num = 0

for level in sorted(level_groups.keys()):
    ops_at_level = level_groups[level]

    # Group by target file
    file_groups = {}
    for op_id in ops_at_level:
        target = op_map[op_id]['target_file']
        file_groups.setdefault(target, [])
        file_groups[target].append(op_id)

    # Determine how many sub-phases needed (max ops on any single file)
    max_per_file = max(len(ops) for ops in file_groups.values())

    for sub_phase_idx in range(max_per_file):
        phase_num += 1
        phase_ops = []
        for target_file, ops in file_groups.items():
            if sub_phase_idx < len(ops):
                phase_ops.append(ops[sub_phase_idx])

        if phase_ops:
            phases.append({
                'phase': phase_num,
                'operations': phase_ops,
                'topo_level': level,
            })
```

6.3. Assign titles and metadata to each phase:

```python
for phase in phases:
    ops = phase['operations']

    # Determine title
    if len(ops) == 1:
        phase['title'] = op_map[ops[0]]['title']
    else:
        # Check if all ops share the same pattern
        patterns = set(op_map[op_id]['pattern'] for op_id in ops)
        if len(patterns) == 1:
            pattern = patterns.pop()
            phase['title'] = f"{len(ops)} {pattern.replace('_', ' ')} changes"
        else:
            phase['title'] = f"Mixed changes ({len(ops)} operations)"

    # Determine agent
    agents = set(op_map[op_id]['agent'] for op_id in ops)
    phase['agent'] = agents.pop() if len(agents) == 1 else "mixed"

    # Determine rationale
    if phase.get('topo_level', 0) == 0 and not any(
        op_map[op_id].get('depends_on') for op_id in ops
    ):
        phase['rationale'] = "Independent, no dependencies"
    else:
        # Find which phases this depends on
        dep_phases = set()
        for op_id in ops:
            for dep_id in op_map[op_id].get('depends_on', []):
                for prev_phase in phases:
                    if dep_id in prev_phase['operations']:
                        dep_phases.add(prev_phase['phase'])
        if dep_phases:
            phase['rationale'] = f"Depends on Phase(s) {', '.join(str(p) for p in sorted(dep_phases))}"
            phase['depends_on_phases'] = sorted(dep_phases)
        else:
            phase['rationale'] = "Same topological level, different file from adjacent phase"

    if 'depends_on_phases' not in phase:
        phase['depends_on_phases'] = []
```

6.4. Log the phase structure:
```
[Planner] Grouped into {N} phases:
          Phase 1: {title} ({N} ops)
          Phase 2: {title} ({N} ops)
          ...
```

### Step 7: Within-File Bottom-to-Top Ordering

**Action:** For each file that has multiple operations across different phases,
sort them by line number DESCENDING (highest line first).

7.1. Build the file-to-operations map:

```python
file_ops = {}  # target_file -> list of (line_ref, op_id)

for op_id, op in op_map.items():
    target = op['target_file']
    file_ops.setdefault(target, [])

    # Determine the reference line number for ordering
    if op['agent'] == 'rate-modifier':
        # Use the HIGHEST target_line for ordering
        if op.get('target_lines'):
            max_line = max(tl['line'] for tl in op['target_lines'])
            line_ref = max_line
        else:
            line_ref = op.get('function_line_start', 0)
    elif op['agent'] == 'logic-modifier':
        # Use insertion_point.line for ordering
        if op.get('insertion_point'):
            line_ref = op['insertion_point']['line']
        elif op.get('function_line_start'):
            line_ref = op['function_line_start']
        else:
            line_ref = 0  # New files go last

    file_ops[target].append((line_ref, op_id))
```

7.2. Sort each file's operations DESCENDING by line number:

```python
file_operation_order = {}

for target_file, ops_with_lines in file_ops.items():
    # Sort descending by line number (highest first = bottom-to-top)
    sorted_ops = sorted(ops_with_lines, key=lambda x: x[0], reverse=True)
    file_operation_order[target_file] = [
        {'op_id': op_id, 'line_ref': line_ref}
        for line_ref, op_id in sorted_ops
    ]
```

7.3. Log the bottom-to-top ordering for files with multiple operations:

```
[Planner] Bottom-to-top ordering:
          {target_file}: {op_id1} (line {N}) -> {op_id2} (line {M}) -> ...
```

**Why bottom-to-top matters:** When the Rate Modifier or Logic Modifier adds or
removes lines in a file, all line numbers BELOW the edit stay the same, but all
line numbers ABOVE the edit shift. By starting from the bottom (highest line
numbers first), each edit only affects lines that have already been processed,
so line-number references for remaining operations stay valid.

### Step 8: Extract Before/After Values

**Action:** Read actual source files and compute expected before/after for each
operation. This is the core of what makes the plan useful for developer review.

8.1. Read each unique source file once:

```python
file_contents = {}
for op_id, op in op_map.items():
    src = op['source_file']
    if src not in file_contents:
        with open(src, 'r') as f:
            file_contents[src] = f.readlines()
```

8.2. For each **rate-modifier** operation with `target_lines`:

```python
for op_id, op in op_map.items():
    if op['agent'] != 'rate-modifier':
        continue

    op['before_after'] = []
    pattern = op['pattern']
    params = op['parameters']

    for tl in op.get('target_lines', []):
        content = tl['content']
        line_num = tl['line']
        rounding = tl.get('rounding')

        if pattern == 'base_rate_increase':
            factor = params['factor']
            # Parse Array6 values from content (or use pre-evaluated args if available)
            # e.g., "Array6(basePremium, 233, 274, 319, 372, 432, 502)"
            values = parse_array6_values(content, tl.get('evaluated_args'))
            new_values = []
            pct_changes = []
            for val in values:
                if isinstance(val, str):
                    # Variable name (e.g., "basePremium") -- keep as-is
                    new_values.append(val)
                    pct_changes.append(None)
                else:
                    new_val = val * factor
                    if rounding == 'banker':
                        new_val = banker_round(new_val)
                    elif rounding == 'none':
                        new_val = round(new_val, 2)  # Keep 2 decimal places
                    # else rounding is null (explicit value, no rounding)
                    new_values.append(new_val)
                    if val != 0:
                        pct = ((new_val - val) / abs(val)) * 100
                        pct_changes.append(pct)
                    else:
                        pct_changes.append(0.0)

            new_content = rebuild_array6_line(content, new_values)

            op['before_after'].append({
                'line': line_num,
                'context': tl['context'],
                'before': content.strip(),
                'after': new_content.strip(),
                'pct_changes': pct_changes,
                'value_count': tl.get('value_count', len(values)),
            })

        elif pattern == 'factor_table_change':
            old_val = params['old_value']
            new_val = params['new_value']
            new_content = content.replace(str(old_val), str(new_val))

            if old_val != 0:
                pct = ((new_val - old_val) / abs(old_val)) * 100
            else:
                pct = None

            op['before_after'].append({
                'line': line_num,
                'context': tl['context'],
                'before': content.strip(),
                'after': new_content.strip(),
                'change': f"{old_val} -> {new_val}",
                'pct_change': pct,
            })

        elif pattern == 'included_limits':
            old_val = params.get('old_value')
            new_val = params.get('new_value')
            new_content = content.replace(str(old_val), str(new_val))

            op['before_after'].append({
                'line': line_num,
                'context': tl['context'],
                'before': content.strip(),
                'after': new_content.strip(),
                'change': f"{old_val} -> {new_val}",
            })
```

8.3. For each **logic-modifier** operation:

```python
for op_id, op in op_map.items():
    if op['agent'] != 'logic-modifier':
        continue

    if op.get('insertion_point'):
        ip = op['insertion_point']
        src_lines = file_contents[op['source_file']]

        # Extract context lines around insertion point
        line_idx = ip['line'] - 1  # 0-indexed
        context_before = src_lines[max(0, line_idx - 2):line_idx + 1]
        context_after = src_lines[line_idx + 1:min(len(src_lines), line_idx + 3)]

        op['insertion_context'] = {
            'lines_before': [l.rstrip() for l in context_before],
            'lines_after': [l.rstrip() for l in context_after],
            'insert_after_line': ip['line'],
            'insert_after_content': ip['context'],
        }

    elif op.get('needs_new_file'):
        op['new_file_info'] = {
            'target_path': op['target_file'],
            'template': op.get('template_reference', 'none'),
        }
```

8.4. Compute aggregate statistics:

```python
total_value_changes = 0
all_pct_changes = []

for op_id, op in op_map.items():
    if op['agent'] == 'rate-modifier':
        for ba in op.get('before_after', []):
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

**`parse_array6_values` helper:** Extract numeric values from an Array6 call.
The first argument may be a variable name (e.g., `basePremium`); subsequent
arguments are numeric. Handle integers and decimals. If the target_line entry
has `evaluated_args` (pre-computed by the Analyzer), use those values directly
instead of parsing expressions from the raw content. Otherwise, if an argument
contains arithmetic (e.g., `30 + 10`), evaluate it and flag `has_expressions: true`.

**`banker_round` helper:** Round to nearest integer using banker's rounding
(round half to even). Python's built-in `round()` uses banker's rounding by
default for integers: `round(0.5) = 0`, `round(1.5) = 2`, `round(2.5) = 2`.

**`rebuild_array6_line` helper:** Reconstruct the Array6 line with new values,
preserving exact whitespace and formatting from the original line. Replace only
the numeric values inside the parentheses, keeping variable names and commas in
their original positions.

### Step 9: Compute Risk Level

**Action:** Determine the overall risk level for the plan.

9.1. Start with LOW:

```python
risk_level = "LOW"
risk_reasons = []
```

9.2. Check for MEDIUM conditions:

```python
# Multiple files
unique_files = set(op['target_file'] for op in op_map.values())
if len(unique_files) > 1:
    risk_level = "MEDIUM"
    risk_reasons.append(f"Multiple target files ({len(unique_files)})")

# Shared module involved
if any(op['file_type'] == 'shared_module' for op in op_map.values()):
    risk_level = "MEDIUM"
    shared_count = sum(1 for op in op_map.values() if op['file_type'] == 'shared_module')
    risk_reasons.append(f"{shared_count} operations in shared module")

# More than 100 value changes
if total_value_changes > 100:
    risk_level = "MEDIUM"
    risk_reasons.append(f"{total_value_changes} value changes (>100)")

# Any MEDIUM-complexity operations (mixed rounding)
if any(op.get('rounding_resolved') == 'mixed' for op in op_map.values()):
    risk_level = "MEDIUM"
    risk_reasons.append("Mixed rounding detected (per-line handling required)")
```

9.3. Check for HIGH conditions:

```python
# Cross-file dependencies (operation depends on op in a different file)
for op_id, op in op_map.items():
    for dep_id in op.get('depends_on', []):
        if op['target_file'] != op_map[dep_id]['target_file']:
            risk_level = "HIGH"
            risk_reasons.append(f"Cross-file dependency: {op_id} -> {dep_id}")

# Cross-LOB shared module with LOBs outside target list
if manifest_risk_indicators.get('cross_lob'):
    risk_level = "HIGH"
    risk_reasons.append("Cross-LOB file references detected")

# Any logic-modifier operations with complexity
logic_ops = [op for op in op_map.values() if op['agent'] == 'logic-modifier']
if len(logic_ops) > 2:
    risk_level = "HIGH"
    risk_reasons.append(f"{len(logic_ops)} logic-modifier operations")

# has_expressions in any operation
if any(op.get('has_expressions') for op in op_map.values()):
    risk_level = "HIGH"
    risk_reasons.append("Array6 arguments contain arithmetic expressions")

# developer_confirmed: false on any operation
unconfirmed = [op['id'] for op in op_map.values() if not op.get('developer_confirmed', True)]
if unconfirmed:
    risk_level = "HIGH"
    risk_reasons.append(f"Unconfirmed operations: {', '.join(unconfirmed)}")

# needs_new_file: true
if any(op.get('needs_new_file') for op in op_map.values()):
    risk_level = max_risk(risk_level, "MEDIUM")
    risk_reasons.append("New file creation required")

# skipped_lines present (may indicate unexpected code patterns)
if any(op.get('skipped_lines') for op in op_map.values()):
    risk_reasons.append("Analyzer skipped some lines (see operation details)")

# Rule dependency warnings from codebase profile
profile_path = ".iq-workstreams/codebase-profile.yaml"
rule_deps = load_yaml_section(profile_path, "rule_dependencies")
if rule_deps:
    target_functions = set(op.get('function') for op in op_map.values() if op.get('function'))
    for dep in rule_deps:
        dep_functions = set(dep.get("functions", []))
        if dep_functions & target_functions:  # overlap exists
            missing = dep_functions - target_functions
            if missing:
                risk_level = max_risk(risk_level, "HIGH")
                risk_reasons.append(
                    f"Business rule dependency: {dep['name']} — "
                    f"{', '.join(missing)} linked but not in target list"
                )
```

9.4. Log the risk assessment:
```
[Planner] Risk level: {risk_level}
          Reasons: {risk_reasons}
```

### Step 9.5: Assign Operation Tiers

After computing risk_level in Step 9, assign a `tier` (1, 2, or 3) to each operation.
The tier determines how much context the capsule builder (/iq-execute) includes for
that operation's worker. Tier 1 = thin capsule (current format, no FUB). Tier 2 =
adds Function Understanding Block + canonical patterns. Tier 3 = adds peer function
bodies + cross-file context.

**This step is fully automated — no developer interaction.**

```
TIER ASSIGNMENT TABLE
─────────────────────────────────────────────────────────────────────
Condition                                                    Tier
─────────────────────────────────────────────────────────────────────
rate-modifier, simple pattern, no mixed rounding,             1
  no expressions

rate-modifier with mixed rounding OR has_expressions          2

logic-modifier, simple constant insertion, no code_patterns   1

logic-modifier with code_patterns OR fub present              2

logic-modifier with needs_new_file                            2

logic-modifier with pattern == "UNKNOWN"                      3

Any op with cross-file dependency (depends_on in diff file)   3

Any op with developer_confirmed == false                      3

Any op where function_line_end - function_line_start > 100    2
  (large functions benefit from FUB even for simple patterns)

DEFAULT (no match)                                            1
  (surfaces gaps via logging rather than silently adding context)
─────────────────────────────────────────────────────────────────────
Highest tier wins when multiple conditions match.
```

```python
def assign_tier(op, op_map):
    """Assign a context tier (1, 2, or 3) to an operation.

    Tier determines capsule richness:
      1 = thin (value substitution, no FUB)
      2 = standard (FUB + canonical patterns)
      3 = full (FUB + peer bodies + cross-file context)

    Highest matching tier wins.
    """
    tier = 0  # Will take max of all matching conditions
    agent = op.get("agent", "rate-modifier")
    pattern = op.get("pattern", "")

    if agent == "rate-modifier":
        # Simple rate-modifier: no mixed rounding, no expressions
        has_mixed = op.get("rounding_resolved") == "mixed"
        has_expr = op.get("has_expressions", False)
        if not has_mixed and not has_expr:
            tier = max(tier, 1)
        else:
            tier = max(tier, 2)

    elif agent == "logic-modifier":
        # Simple constant insertion without code_patterns
        is_simple_const = (
            pattern == "new_coverage_type"
            and op.get("parameters", {}).get("constant_name")
            and not op.get("parameters", {}).get("case_block_type")
            and not op.get("code_patterns")
        )
        if is_simple_const:
            tier = max(tier, 1)

        # Has code_patterns or FUB
        if op.get("code_patterns") or op.get("fub"):
            tier = max(tier, 2)

        # Needs new file creation
        if op.get("needs_new_file"):
            tier = max(tier, 2)

        # Unknown pattern → maximum context
        if pattern == "UNKNOWN":
            tier = max(tier, 3)

    # Cross-file dependency: depends_on an op in a different file
    for dep_id in op.get("depends_on", []):
        dep_op = op_map.get(dep_id)
        if dep_op and op.get("target_file") != dep_op.get("target_file"):
            tier = max(tier, 3)

    # Unconfirmed targets → maximum context for safety
    if not op.get("developer_confirmed", True):
        tier = max(tier, 3)

    # Large functions (>100 lines) benefit from FUB even for simple patterns
    func_start = op.get("function_line_start", 0)
    func_end = op.get("function_line_end", 0)
    if func_start and func_end and (func_end - func_start) > 100:
        tier = max(tier, 2)

    # Default: if nothing matched above, use Tier 1 (surfaces assignment gaps
    # via logging rather than silently consuming extra tokens)
    if tier == 0:
        tier = 1
        # Log: "No tier condition matched for op {op_id} — defaulting to Tier 1.
        #        Review tier assignment table if this operation needs richer context."

    return tier


# Apply tiers to all operations
for op_id, op in op_map.items():
    op["tier"] = assign_tier(op, op_map)
```

9.5.1. Add `tier` to `execution_sequence` and `file_operation_order` entries:

```python
# In execution_sequence:
for entry in execution_sequence:
    entry["tier"] = op_map[entry["op_id"]]["tier"]

# In file_operation_order:
for file_path, ops in file_operation_order.items():
    for entry in ops:
        entry["tier"] = op_map[entry["op_id"]]["tier"]
```

9.5.2. Compute tier distribution summary:

```python
tier_counts = {1: 0, 2: 0, 3: 0}
for op in op_map.values():
    tier_counts[op["tier"]] += 1

tier_distribution = {
    "tier_1": tier_counts[1],
    "tier_2": tier_counts[2],
    "tier_3": tier_counts[3],
}
```

9.5.3. Log tier assignments:

```
[Planner] Tier assignments:
          Tier 1 (value substitution):   {N} operations
          Tier 2 (logic with patterns):  {N} operations
          Tier 3 (full context):         {N} operations
```

### Step 10: Generate execution_plan.md

**Action:** Write the human-readable plan for developer approval at Gate 1.

10.1. Determine format: SIMPLE or COMPLEX.

SIMPLE criteria: few operations, single file, and risk no higher than MEDIUM.
A single shared-module change is common (e.g., 5% rate increase) and should
still get a scannable SIMPLE plan. COMPLEX kicks in at 3+ operations, multiple
files, or HIGH risk.

```python
use_simple = (
    total_operations <= 2
    and len(unique_files) <= 1
    and risk_level in ("LOW", "MEDIUM")
)
```

10.2. Write the plan header:

```python
plan_lines = []

# Title
if use_simple:
    lob_str = lobs[0] if len(lobs) == 1 else f"{lobs[0]} (+ {len(lobs) - 1} LOBs)"
else:
    lob_str = "Habitational" if all(is_hab(l) for l in lobs) else ", ".join(lobs)

plan_lines.append(f"EXECUTION PLAN: {province_name} {lob_str} {effective_date}")
plan_lines.append("=" * len(plan_lines[0]))
plan_lines.append("")

# Summary line
if use_simple:
    plan_lines.append(
        f"Summary: {total_operations} change(s), {len(unique_files)} file(s), "
        f"{total_value_changes} value edits, {risk_level} risk"
    )
else:
    plan_lines.append(
        f"Summary: {total_operations} operations across {len(unique_files)} files, "
        f"{risk_level} risk"
    )
    plan_lines.append(f"LOBs affected: {', '.join(lobs)}")
    shared_modules = [f for f in unique_files
                      if any(op['file_type'] == 'shared_module'
                             for op in op_map.values() if op['target_file'] == f)]
    if shared_modules:
        for sm in shared_modules:
            plan_lines.append(f"Shared module: {sm.split('/')[-1]}")
```

10.3. Write the OUT OF SCOPE section (if any):

```python
if out_of_scope:
    plan_lines.append("")
    plan_lines.append("OUT OF SCOPE (flagged, not executed):")
    for oos in out_of_scope:
        plan_lines.append(f"  {oos['srd'].upper()}: {oos['title']}")
        plan_lines.append(f"    Reason: {oos['reason']}")
```

10.4. Write the FILE COPIES section:

```python
if files_to_copy:
    plan_lines.append("")
    plan_lines.append("FILE COPIES:")
    for fc in files_to_copy:
        src_name = fc['source'].split('/')[-1]
        tgt_name = fc['target'].split('/')[-1]
        plan_lines.append(f"  {src_name} -> {tgt_name}")
        if fc.get('shared_by'):
            plan_lines.append(f"    Shared by: {', '.join(fc['shared_by'])}")
        else:
            plan_lines.append(f"    Used by: {fc.get('used_by', 'single LOB')}")
        plan_lines.append(f"    .vbproj updates: {len(fc['vbproj_updates'])} file(s)")
else:
    plan_lines.append("")
    plan_lines.append("FILE COPIES: None (target files already exist)")
```

10.5. Write each phase with before/after details:

For SIMPLE plans, show ALL before/after entries.
For COMPLEX plans with more than 10 entries per operation, show the first 2
entries and a summary line "(showing 2 of N -- all follow same pattern)".

```python
for phase in phases:
    plan_lines.append("")
    dep_str = ""
    if phase['depends_on_phases']:
        deps = ', '.join(str(p) for p in phase['depends_on_phases'])
        dep_str = f", depends on Phase {deps}"

    ops_str = ', '.join(phase['operations'])
    plan_lines.append(
        f"Phase {phase['phase']}: {phase['title']} ({ops_str}) "
        f"[{phase['agent']}{dep_str}]"
    )

    for op_id in phase['operations']:
        op = op_map[op_id]

        plan_lines.append(f"  File: {op['target_file']}")
        if op.get('function'):
            plan_lines.append(f"  Function: {op['function']}()")

        if op['agent'] == 'rate-modifier':
            write_rate_modifier_details(plan_lines, op, use_simple)
        elif op['agent'] == 'logic-modifier':
            write_logic_modifier_details(plan_lines, op)

        # Show warnings for this operation
        if not op.get('developer_confirmed', True):
            plan_lines.append("")
            plan_lines.append(f"  *** WARNING: Targets NOT confirmed by developer ***")
            plan_lines.append(f"  *** Review before approving ***")

        if op.get('has_expressions'):
            plan_lines.append("")
            plan_lines.append(f"  *** NOTE: Array6 arguments contain arithmetic expressions ***")
            plan_lines.append(f"  *** Expressions will be evaluated before modification ***")
```

10.6. Write the impact summary and footer (COMPLEX format):

```python
if not use_simple:
    plan_lines.append("")
    plan_lines.append("IMPACT SUMMARY:")
    plan_lines.append(f"  Total value changes: {total_value_changes}")
    plan_lines.append(f"  Total files modified: {len(unique_files)}")
    plan_lines.append(f"  Total file copies: {len(files_to_copy)}")
    plan_lines.append(f"  Total .vbproj updates: {total_vbproj_updates}")
    plan_lines.append(f"  Risk level: {risk_level}")
    for reason in risk_reasons:
        plan_lines.append(f"    - {reason}")
    if all_pct_changes:
        plan_lines.append(f"  Value change range: {min_pct:+.1f}% to {max_pct:+.1f}%")

    # Context tiers (from Step 9.5)
    plan_lines.append("")
    plan_lines.append("CONTEXT TIERS:")
    plan_lines.append(f"  Tier 1 (value substitution):  {tier_distribution['tier_1']} operations")
    plan_lines.append(f"  Tier 2 (logic with patterns): {tier_distribution['tier_2']} operations")
    plan_lines.append(f"  Tier 3 (full context):        {tier_distribution['tier_3']} operations")

    # Warnings section
    warnings = collect_warnings(op_map)
    if warnings:
        plan_lines.append("")
        plan_lines.append("WARNINGS:")
        for w in warnings:
            plan_lines.append(f"  {w}")

    # Partial approval constraints
    if partial_approval_constraints:
        plan_lines.append("")
        plan_lines.append("PARTIAL APPROVAL CONSTRAINTS:")
        plan_lines.append("  The following SRDs are coupled by dependencies:")
        for pac in partial_approval_constraints:
            plan_lines.append(
                f"  - {pac['srd'].upper()} requires {pac['requires_srd'].upper()}: "
                f"{pac['reason']}"
            )
        plan_lines.append("  Rejecting a required SRD will also block the dependent SRD.")

plan_lines.append("")
plan_lines.append("Approve this plan? Say \"approve\" to proceed or tell me what to change.")
```

10.7. Write to `plan/execution_plan.md`:

```python
plan_dir = f"{workstream_path}/plan"
os.makedirs(plan_dir, exist_ok=True)

with open(f"{plan_dir}/execution_plan.md", 'w') as f:
    f.write('\n'.join(plan_lines))
```

**`write_rate_modifier_details` helper:**

```python
def write_rate_modifier_details(lines, op, use_simple):
    params = op['parameters']
    ba_list = op.get('before_after', [])

    if op['pattern'] == 'base_rate_increase':
        lines.append(f"  Action: Multiply all Array6 values by {params['factor']}")
        if op.get('rounding_resolved'):
            lines.append(f"  Rounding: {op['rounding_resolved']}")
            if op.get('rounding_detail'):
                lines.append(f"    {op['rounding_detail'].strip()}")
        lines.append("")

        # Show before/after entries
        max_show = len(ba_list) if use_simple else min(2, len(ba_list))
        for i, ba in enumerate(ba_list[:max_show]):
            lines.append(f"  Before -> After ({ba['context']}):")
            lines.append(f"    {ba['before']}")
            lines.append(f"    {ba['after']}")
            # Show per-value percentage changes
            if ba.get('pct_changes'):
                pct_strs = []
                for pct in ba['pct_changes']:
                    if pct is None:
                        pct_strs.append("    ")
                    else:
                        pct_strs.append(f"{pct:+.1f}%")
                lines.append(f"    {'  '.join(pct_strs)}")
            lines.append("")

        if not use_simple and len(ba_list) > max_show:
            lines.append(
                f"  (showing {max_show} of {len(ba_list)} -- "
                f"all follow same {params['factor']}x pattern)"
            )

        total_vals = sum(ba.get('value_count', 1) for ba in ba_list)
        lines.append(f"  Impact: {len(ba_list)} lines x ~{total_vals // max(len(ba_list), 1)} values = {total_vals} changes")

    elif op['pattern'] == 'factor_table_change':
        lines.append(f"  Action: Change Case {params.get('case_value')} factor")
        lines.append("")
        for ba in ba_list:
            if len(ba_list) > 1:
                lines.append(f"  Path ({ba['context']}):")
            lines.append(f"  Before: {ba['before']}")
            lines.append(f"  After:  {ba['after']}")
            lines.append(f"  Change: {ba.get('change', '')}")
            lines.append("")

    elif op['pattern'] == 'included_limits':
        lines.append(f"  Action: Change included limit value")
        lines.append("")
        for ba in ba_list:
            lines.append(f"  Before: {ba['before']}")
            lines.append(f"  After:  {ba['after']}")
            lines.append("")
```

**`write_logic_modifier_details` helper:**

```python
def write_logic_modifier_details(lines, op):
    params = op['parameters']

    if op.get('insertion_point'):
        ip = op['insertion_point']
        lines.append(f"  Action: {op['description']}")
        lines.append(f"  Insert {ip['position']} line {ip['line']} ({ip['context']}):")

        # Show the new code to be added (from parameters)
        if op['pattern'] == 'new_coverage_type':
            lines.append(f"    + Public Const {params['constant_name']} As String = \"{params['coverage_type_name']}\"")
        elif 'code_to_add' in params:
            for code_line in params['code_to_add']:
                lines.append(f"    + {code_line}")
        else:
            lines.append(f"    (code will be generated by Logic Modifier per pattern: {op['pattern']})")

    elif op.get('needs_new_file'):
        lines.append(f"  Action: CREATE NEW FILE")
        lines.append(f"  Target: {op['target_file']}")
        if op.get('template_reference'):
            lines.append(f"  Template: {op['template_reference']}")
        lines.append(f"  Description: {op['description']}")
```

### Step 11: Generate execution_order.yaml

**Action:** Write the machine-readable plan for /iq-execute consumption.

11.1. Build the flat execution sequence. This combines:
- Topological order (dependency-respecting)
- Bottom-to-top within each file (highest line first)

The execution_sequence is the AUTHORITATIVE order that /iq-execute follows.
It interleaves cross-file operations and within-file operations correctly:

```python
execution_sequence = []

# Process phases in order
for phase in phases:
    # Within each phase, process files in deterministic order
    phase_ops_by_file = {}
    for op_id in phase['operations']:
        target = op_map[op_id]['target_file']
        phase_ops_by_file.setdefault(target, [])
        phase_ops_by_file[target].append(op_id)

    for target_file in sorted(phase_ops_by_file.keys()):
        ops = phase_ops_by_file[target_file]
        # Within same file in same phase, use bottom-to-top order
        if target_file in file_operation_order:
            full_order = [entry['op_id'] for entry in file_operation_order[target_file]]
            ops_sorted = [op_id for op_id in full_order if op_id in ops]
        else:
            ops_sorted = ops

        for op_id in ops_sorted:
            execution_sequence.append({
                'op_id': op_id,
                'phase': phase['phase'],
                'file': op_map[op_id]['target_file'],
                'agent': op_map[op_id]['agent'],
            })
```

11.2. Assemble the complete YAML structure and write:

```python
execution_order = {
    'planner_version': '1.0',
    'generated_at': now_iso8601(),
    'workflow_id': workflow_id,
    'total_phases': len(phases),
    'total_operations': len(op_map),
    'total_value_changes': total_value_changes,
    'total_file_copies': len(files_to_copy),
    'total_vbproj_updates': total_vbproj_updates,
    'risk_level': risk_level,
    'risk_reasons': risk_reasons,
    'file_copies': files_to_copy,  # Pass through from files_to_copy.yaml
    'phases': [
        {
            'phase': p['phase'],
            'title': p['title'],
            'operations': p['operations'],
            'agent': p['agent'],
            'rationale': p['rationale'],
            'depends_on_phases': p['depends_on_phases'],
        }
        for p in phases
    ],
    'file_operation_order': file_operation_order,
    'execution_sequence': execution_sequence,
    'partial_approval_constraints': partial_approval_constraints,
}

with open(f"{plan_dir}/execution_order.yaml", 'w') as f:
    yaml.dump(execution_order, f, default_flow_style=False)
```

### Step 12: Collect Hashes and Write file_hashes.yaml

**Action:** Capture SHA-256 hashes of all files that will be read, copied, or
modified during execution.

12.1. Collect all file paths and their roles:

```python
file_hash_entries = {}

# Source files (will be read and copied)
for fc in files_to_copy:
    file_hash_entries[fc['source']] = {
        'hash': fc['source_hash'],
        'size': os.path.getsize(fc['source']),
        'role': 'source',
    }
    # Target files (will be created -- hash is null until copy)
    file_hash_entries[fc['target']] = {
        'hash': None,
        'size': None,
        'role': 'target',
    }

# Files that already exist and will be modified in place
for op_id, op in op_map.items():
    target = op['target_file']
    if target not in file_hash_entries:
        # This file already exists (not being created by a copy)
        if os.path.exists(target):
            with open(target, 'rb') as f:
                h = 'sha256:' + hashlib.sha256(f.read()).hexdigest()
            file_hash_entries[target] = {
                'hash': h,
                'size': os.path.getsize(target),
                'role': 'target',
            }
        else:
            # File will be created by copy step -- already in entries as target
            pass

# .vbproj files (will be modified)
for fc in files_to_copy:
    for vbu in fc['vbproj_updates']:
        vbproj = vbu['vbproj']
        if vbproj not in file_hash_entries:
            with open(vbproj, 'rb') as f:
                h = 'sha256:' + hashlib.sha256(f.read()).hexdigest()
            file_hash_entries[vbproj] = {
                'hash': h,
                'size': os.path.getsize(vbproj),
                'role': 'vbproj',
            }
```

12.2. Write execution/file_hashes.yaml:

```python
exec_dir = f"{workstream_path}/execution"
os.makedirs(exec_dir, exist_ok=True)

file_hashes = {
    'planner_version': '1.0',
    'captured_at': now_iso8601(),
    'workflow_id': workflow_id,
    'files': file_hash_entries,
}

with open(f"{exec_dir}/file_hashes.yaml", 'w') as f:
    yaml.dump(file_hashes, f, default_flow_style=False)
```

12.3. Log completion:
```
[Planner] Wrote execution/file_hashes.yaml: {N} files tracked.
[Planner] Plan generation complete.
          Output: plan/execution_plan.md ({N} lines)
          Output: plan/execution_order.yaml ({N} phases, {N} operations)
          Output: execution/file_hashes.yaml ({N} files)
```

---

## WORKED EXAMPLES

These examples demonstrate the full Planner flow for common scenarios.

### Example A: Simple -- Single file, 1 SRD, 5% rate multiply

**Scenario:** New Brunswick Home, effective 2026-07-01. Single SRD: increase
GetBasePremium_Home Array6 values by 5%.

**Input from Analyzer:**

```yaml
# analysis/operations/op-001-01.yaml
id: "op-001-01"
srd: "srd-001"
title: "Increase home base premiums by 5%"
file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
file_type: "shared_module"
function: "GetBasePremium_Home"
agent: "rate-modifier"
depends_on: []
pattern: "base_rate_increase"
parameters:
  factor: 1.05
  scope: "all_territories"
  rounding: "auto"

# -- Added by Analyzer --
source_file: "New Brunswick/Code/mod_Common_NBHab20260401.vb"
target_file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
needs_copy: true
file_hash: "sha256:abc123..."
function_line_start: 312
function_line_end: 418
rounding_resolved: "banker"
rounding_detail: "All Array6 values are integers -- banker rounding applied."
target_lines:
  - line: 322
    content: "                Case 1 : varRates = Array6(basePremium, 233, 274, 319, 372, 432, 502)"
    context: "Territory 1"
    rounding: "banker"
    value_count: 6
  - line: 324
    content: "                Case 2 : varRates = Array6(basePremium, 198, 233, 271, 316, 367, 427)"
    context: "Territory 2"
    rounding: "banker"
    value_count: 6
  # ... 13 more territories
candidates_shown: 1
developer_confirmed: true
```

```yaml
# analysis/dependency_graph.yaml
workflow_id: "20260701-NB-Home-base-rates"
total_operations: 1
total_out_of_scope: 0
out_of_scope: []
shared_operations:
  op-001-01:
    srd: "srd-001"
    description: "Increase home base premiums by 5%"
    file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
    file_type: "shared_module"
    function: "GetBasePremium_Home"
    agent: "rate-modifier"
    depends_on: []
lob_operations: {}
partial_approval_constraints: []
execution_order:
  - "op-001-01"
```

```yaml
# analysis/files_to_copy.yaml
total_files: 1
files:
  - source: "New Brunswick/Code/mod_Common_NBHab20260401.vb"
    target: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
    source_hash: "sha256:abc123..."
    target_exists: false
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    operations_in_file: ["op-001-01"]
    vbproj_updates:
      - vbproj: "New Brunswick/Home/20260701/Cssi.IntelliQuote.PORTNBHOME20260701.vbproj"
        old_include: "..\\Code\\mod_Common_NBHab20260401.vb"
        new_include: "..\\Code\\mod_Common_NBHab20260701.vb"
      # ... 5 more (one per hab LOB)
```

**Step 3 -- Hash check:** 1 source file, hash matches. Proceed.

**Step 4 -- DAG:** 1 node, 0 edges. Trivially valid.

**Step 5 -- Topo sort:** 1 node at level 0. Order: ["op-001-01"].

**Step 6 -- Phase grouping:** 1 phase.

```
Phase 1: "Increase home base premiums by 5%" (op-001-01) [rate-modifier]
```

**Step 7 -- Bottom-to-top:** 1 operation, trivially ordered.

**Step 8 -- Before/after (first 2 territories):**

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

**Step 9 -- Risk:** MEDIUM (shared module involved, but only 1 operation so LOW
would apply if not for shared module).

Actually: 1 file, 1 operation, shared_module = true, < 100 value changes (90).
Risk = MEDIUM (shared module criterion).

Wait -- re-examine: this is a single-SRD simple change. The shared module flag
makes it MEDIUM, not LOW. Risk reasons: ["1 operation in shared module (6 LOBs)"].

**Step 10 -- execution_plan.md output:**

```markdown
EXECUTION PLAN: New Brunswick Home 2026-07-01
==============================================

Summary: 1 change, 1 file, 90 value edits, MEDIUM risk

FILE COPIES:
  mod_Common_NBHab20260401.vb -> mod_Common_NBHab20260701.vb
    Shared by: Home, Condo, Tenant, FEC, Farm, Seasonal
    .vbproj updates: 6 file(s)

Phase 1: Increase home base premiums by 5% (op-001-01) [rate-modifier]
  File: New Brunswick/Code/mod_Common_NBHab20260701.vb
  Function: GetBasePremium_Home()
  Action: Multiply all Array6 values by 1.05
  Rounding: banker (all values are integers)

  Before -> After (Territory 1):
    Array6(basePremium, 233, 274, 319, 372, 432, 502)
    Array6(basePremium, 245, 288, 335, 391, 454, 527)
                        +5.2%  +5.1%  +5.0%  +5.1%  +5.1%  +5.0%

  Before -> After (Territory 2):
    Array6(basePremium, 198, 233, 271, 316, 367, 427)
    Array6(basePremium, 208, 245, 285, 332, 385, 448)
                        +5.1%  +5.2%  +5.2%  +5.1%  +4.9%  +4.9%

  (showing 2 of 15 -- all follow same 1.05x pattern)

  Impact: 15 lines x 6 values = 90 changes
  Range: +4.9% to +5.2% (rounding variation)

Approve this plan? Say "approve" to proceed or tell me what to change.
```

**Step 11 -- execution_order.yaml output:**

```yaml
planner_version: "1.0"
generated_at: "2026-02-27T11:00:00"
workflow_id: "20260701-NB-Home-base-rates"
total_phases: 1
total_operations: 1
total_value_changes: 90
total_file_copies: 1
total_vbproj_updates: 6
risk_level: "MEDIUM"
risk_reasons:
  - "1 operation in shared module (6 LOBs)"
file_copies:
  - source: "New Brunswick/Code/mod_Common_NBHab20260401.vb"
    target: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
    source_hash: "sha256:abc123..."
    target_exists: false
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    vbproj_updates:
      - vbproj: "New Brunswick/Home/20260701/Cssi.IntelliQuote.PORTNBHOME20260701.vbproj"
        old_include: "..\\Code\\mod_Common_NBHab20260401.vb"
        new_include: "..\\Code\\mod_Common_NBHab20260701.vb"
      # ... 5 more
phases:
  - phase: 1
    title: "Increase home base premiums by 5%"
    operations: ["op-001-01"]
    agent: "rate-modifier"
    rationale: "Independent, no dependencies"
    depends_on_phases: []
file_operation_order:
  "New Brunswick/Code/mod_Common_NBHab20260701.vb":
    - op_id: "op-001-01"
      line_ref: 350                              # max(target_lines[].line), NOT function_line_end
execution_sequence:
  - op_id: "op-001-01"
    phase: 1
    file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
    agent: "rate-modifier"
partial_approval_constraints: []
```

---

### Example B: Medium -- Shared module, 3 SRDs, mixed agents

**Scenario:** Saskatchewan Habitational, effective 2026-01-01.
- SRD-002: Deductible factor change ($5000: -0.20 to -0.22) -- rate-modifier
- SRD-003: Deductible factor change ($2500: -0.15 to -0.17) -- rate-modifier
- SRD-004: Liability premium increase (bundle + extension, 1.03x) -- rate-modifier (2 ops)
- SRD-005: Add ELITECOMP constant + Case block -- logic-modifier (2 ops)
  - op-005-01: Add constant (line ~23)
  - op-005-02: Add Case block in GetRateTableID (line ~435), depends on op-005-01

**Dependency graph edges:**
- op-005-02 depends on op-005-01 (Case block references ELITECOMP constant)
- All others are independent

**Step 4 -- DAG:** 6 nodes, 1 edge. Valid, no cycles.

**Step 5 -- Topo sort:**
- Level 0: op-002-01, op-003-01, op-004-01, op-004-02, op-005-01 (in-degree 0)
- Level 1: op-005-02 (depends on op-005-01)
- Order: [op-002-01, op-003-01, op-004-01, op-004-02, op-005-01, op-005-02]

**Step 6 -- Phase grouping:**
- Level 0 has 5 operations. But op-002-01, op-003-01, op-004-01, op-004-02 are ALL
  on the same file (mod_Common_SKHab20260101.vb). Only op-005-01 is on a different
  file but is ALSO on mod_Common_SKHab20260101.vb (module-level constants).
- So all 5 level-0 ops are on the same file -> max_per_file = 5 -> 5 sub-phases.
- Level 1 has 1 op (op-005-02, same file) -> 1 sub-phase.
- Total: 6 phases.

**Step 7 -- Bottom-to-top for mod_Common_SKHab20260101.vb:**

```
file_operation_order["Saskatchewan/Code/mod_Common_SKHab20260101.vb"]:
  - op-004-02  (line 4106, GetLiabilityExtensionPremiums)
  - op-004-01  (line 4012, GetLiabilityBundlePremiums)
  - op-002-01  (line 2202, SetDisSur_Deductible Case 5000)
  - op-003-01  (line 2180, SetDisSur_Deductible Case 2500)
  - op-005-02  (line ~435, GetRateTableID insertion)
  - op-005-01  (line ~23, module-level constant insertion)
```

**Step 9 -- Risk:** MEDIUM.
Reasons: ["4 operations in shared module (6 LOBs)", "Mixed rounding in GetLiabilityBundlePremiums"]

**Step 10 -- execution_plan.md (abbreviated):**

Phase numbers follow the code's assignment order (topo-level + alphabetical
tie-breaking within each level). The code assigns:
- Level 0, 5 ops on same file -> sub-phases 1-5 in topo_order:
  Phase 1: op-002-01, Phase 2: op-003-01, Phase 3: op-004-01,
  Phase 4: op-004-02, Phase 5: op-005-01
- Level 1, 1 op -> Phase 6: op-005-02

Phase 6 (op-005-02) depends on Phase 5 (op-005-01) -- this is a valid forward
dependency (later phase depends on earlier phase).

The plan document shows phases in this numbered order. The execution_sequence
in execution_order.yaml then reorders within the file to bottom-to-top for
correct execution (line 4106 first, line 23 last). The two orderings serve
different purposes: plan = human readability, execution_sequence = machine
correctness.

```markdown
EXECUTION PLAN: Saskatchewan Habitational 2026-01-01
====================================================

Summary: 6 operations across 1 file, MEDIUM risk
LOBs affected: Home, Condo, Tenant, FEC, Farm, Seasonal
Shared module: mod_Common_SKHab20260101.vb

FILE COPIES:
  mod_Common_SKHab20250901.vb -> mod_Common_SKHab20260101.vb
    Shared by: Home, Condo, Tenant, FEC, Farm, Seasonal
    .vbproj updates: 6 file(s)

Phase 1: Change $5000 deductible factor (op-002-01) [rate-modifier]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  Before: dblDedDiscount = -0.2
  After:  dblDedDiscount = -0.22
  ...

Phase 2: Change $2500 deductible factor (op-003-01) [rate-modifier]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  Before: dblDedDiscount = -0.15
  After:  dblDedDiscount = -0.17
  ...

Phase 3: Multiply liability bundle premiums by 1.03 (op-004-01) [rate-modifier]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: GetLiabilityBundlePremiums()
  Action: Multiply all Array6 values by 1.03
  Rounding: mixed (42 lines banker, 6 lines none -- per-line detail below)
  ...

Phase 4: Multiply liability extension premiums by 1.03 (op-004-02) [rate-modifier]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: GetLiabilityExtensionPremiums()
  Action: Multiply all Array6 values by 1.03
  Rounding: banker (all values are integers)

  Before -> After (first entry):
    Array6(0, 78, 106, 161, 189, 216, 291)
    Array6(0, 80, 109, 166, 195, 222, 300)
  ...

Phase 5: Add ELITECOMP constant (op-005-01) [logic-modifier]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Location: module-level constants
  Action: Add line after existing constants
    + Public Const ELITECOMP As String = "Elite Comp."

Phase 6: Add Case block for ELITECOMP (op-005-02) [logic-modifier, depends on Phase 5]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: GetRateTableID()
  Action: Add Case block after existing coverage types
    + Case ELITECOMP
    +     Select Case strClassification
    +         Case STANDARD : intFileID = DAT_Home_EliteComp_Standard
    +         Case PREFERRED : intFileID = DAT_Home_EliteComp_Preferred
    +     End Select

IMPACT SUMMARY:
  Total value changes: 62
  Total files modified: 1
  Total file copies: 1
  Total .vbproj updates: 6
  Risk level: MEDIUM
    - 4 operations in shared module (6 LOBs)
    - Mixed rounding in GetLiabilityBundlePremiums

Approve this plan? Say "approve" to proceed or tell me what to change.
```

Note: The execution_sequence in execution_order.yaml reorders these phases
for bottom-to-top execution within the file: op-004-02 (line 4106) executes
first, down to op-005-01 (line ~23) last. Phase numbers in the plan document
serve human readability; the execution_sequence is the authoritative machine
execution order.

---

### Example C: Complex -- Cross-file deps, 5+ SRDs, partial approval

**Scenario:** Saskatchewan Habitational, effective 2026-01-01. 5 SRDs with
inter-SRD dependencies:

- SRD-001: Define ELITECOMP constant (logic-modifier) -- op-001-01
- SRD-002: Add rate table routing in GetRateTableID (logic-modifier) -- op-002-01, depends on op-001-01
- SRD-003: Add base rate Array6 for ELITECOMP in GetBasePremium_Home (rate-modifier) -- op-003-01, depends on op-001-01
- SRD-004: Add DAT IDs to ResourceID.vb in each LOB (logic-modifier) -- op-004-01..06, depends on op-002-01
- SRD-005: Add eligibility rule in CalcOption (logic-modifier) -- op-005-01, depends on op-001-01 and op-004-01

**Dependency graph:**
```
op-001-01 (ELITECOMP constant)
  |
  +---> op-002-01 (rate table routing)
  |       |
  |       +---> op-004-01 (DAT ID in Home ResourceID)
  |       +---> op-004-02 (DAT ID in Condo ResourceID)
  |       +---> op-004-03 (DAT ID in Tenant ResourceID)
  |       +---> op-004-04 (DAT ID in FEC ResourceID)
  |       +---> op-004-05 (DAT ID in Farm ResourceID)
  |       +---> op-004-06 (DAT ID in Seasonal ResourceID)
  |                 |
  +---> op-003-01 (base rate Array6)
  |
  +---> op-005-01 (eligibility rule) -- also depends on op-004-01
```

**Step 5 -- Topo sort:**
- Level 0: op-001-01
- Level 1: op-002-01, op-003-01
- Level 2: op-004-01..06
- Level 3: op-005-01

**Step 6 -- Phases:** 6 phases (level 0: 1 phase, level 1: 2 ops on same file
= 2 phases, level 2: 6 ops on 6 different files = 1 phase, level 3: 1 phase).

Total: 5 phases.

**Step 9 -- Risk:** HIGH.
Reasons: ["Cross-file dependency: op-005-01 -> op-004-01", "5 logic-modifier operations", "Inter-SRD dependencies"]

**Partial approval scenario:** Developer says "Approve SRD-001 and SRD-002, reject SRD-003, SRD-004, SRD-005."

Dependency validation:
- SRD-003 (rejected): depends on SRD-001 (approved). OK to reject.
- SRD-004 (rejected): depends on SRD-002 (approved). OK to reject.
- SRD-005 (rejected): depends on SRD-001 (approved) and SRD-004 (rejected). OK to reject.
- No approved SRD depends on a rejected SRD. Partial approval is valid.

If developer instead says "Approve SRD-004, reject SRD-001":
```
Cannot approve SRD-004 without SRD-001.
SRD-004 (Add DAT IDs) depends on SRD-002 (rate table routing),
which depends on SRD-001 (ELITECOMP constant).

Options:
  1. Approve SRD-001, SRD-002, and SRD-004 together
  2. Reject all three
  3. Show me the dependency graph
```

---

### Example D: Edge -- All operations on one file

**Scenario:** 6 operations all targeting mod_Common_SKHab20260101.vb at different
line numbers. No dependencies between operations (all independent).

**Operations:**
- op-001-01: GetBasePremium_Home (lines 312-418)
- op-002-01: SetDisSur_Deductible Case 5000 (line 2202)
- op-003-01: SetDisSur_Deductible Case 2500 (line 2180)
- op-004-01: GetLiabilityBundlePremiums (lines 4012-4104)
- op-004-02: GetLiabilityExtensionPremiums (lines 4106-4156)
- op-005-01: Add constant at line ~23

**Step 6 -- Phase grouping:** All at topo level 0, all same file. 6 sub-phases
needed (max 1 operation per file per phase).

**Step 7 -- Bottom-to-top ordering is CRITICAL:**

```yaml
file_operation_order:
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    - op_id: "op-004-02"    # line 4106 (highest -- executed first)
      line_ref: 4106
    - op_id: "op-004-01"    # line 4012
      line_ref: 4012
    - op_id: "op-002-01"    # line 2202
      line_ref: 2202
    - op_id: "op-003-01"    # line 2180
      line_ref: 2180
    - op_id: "op-001-01"    # line 312
      line_ref: 312
    - op_id: "op-005-01"    # line 23 (lowest -- executed last)
      line_ref: 23
```

The execution_sequence follows this order exactly. If op-005-01 (insertion at
line 23) were executed first, it would shift ALL subsequent line numbers by 1+
lines, making the line references for op-001-01 through op-004-02 incorrect.
Bottom-to-top prevents this drift.

**Plan display:** The plan document can show phases in any readable order (e.g.,
logical grouping), but the execution_sequence MUST follow bottom-to-top.

---

### Example E: Edge -- File already has target-date copy

**Scenario:** Developer already ran a previous workflow that created
mod_Common_SKHab20260101.vb. Now a new workflow has additional changes to the
same file.

**Analyzer output for operations:**
```yaml
source_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"  # Same as target!
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: false                                              # Already exists
file_hash: "sha256:xyz789..."                                  # Hash of existing file
```

**files_to_copy.yaml:**
```yaml
total_files: 0
files: []
```

**Plan output:**
```markdown
EXECUTION PLAN: Saskatchewan Habitational 2026-01-01
====================================================

Summary: 2 operations across 1 file, LOW risk

FILE COPIES: None (target files already exist)

Phase 1: Change $5000 deductible factor (op-001-01) [rate-modifier]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  ...

Phase 2: Change $2500 deductible factor (op-002-01) [rate-modifier]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  ...

Approve this plan? Say "approve" to proceed or tell me what to change.
```

The file_hashes.yaml still captures the hash of the existing file for TOCTOU
protection -- /iq-execute will verify it hasn't changed since the plan was built.

---

### Example F: Edge -- Zero operations (values already match)

**Scenario:** The Analyzer found that all current values in the source file already
equal the requested target values. Perhaps the rate change was already applied in
a previous workflow.

**dependency_graph.yaml:**
```yaml
total_operations: 0
total_out_of_scope: 0
out_of_scope: []
shared_operations: {}
lob_operations: {}
execution_order: []
```

**Planner behavior at Step 1.5:**

```
[Planner] No in-scope operations to plan.
          The Analyzer found 0 operations requiring changes.
          This may mean all values already match the requested targets.
          Writing empty plan and exiting.
```

**execution_plan.md:**
```markdown
EXECUTION PLAN: Saskatchewan Habitational 2026-01-01
====================================================

Summary: No changes needed -- all values already match requested targets.

The Analyzer verified that current values in the source files already equal
the requested values. No modifications are required.

SRDs processed:
  SRD-001: "Increase deductible factors" -- values already match
  SRD-002: "Increase liability premiums" -- values already match

No approval needed. The workflow will be marked as COMPLETED with no changes.
```

**execution_order.yaml:**
```yaml
planner_version: "1.0"
generated_at: "2026-02-27T11:00:00"
workflow_id: "20260101-SK-Hab-match"
total_phases: 0
total_operations: 0
total_value_changes: 0
total_file_copies: 0
total_vbproj_updates: 0
risk_level: "LOW"
risk_reasons: []
file_copies: []
phases: []
file_operation_order: {}
execution_sequence: []
partial_approval_constraints: []
```

---

## SPECIAL CASES

### 1. Mixed Rounding Within Same Function

**Pattern:** GetLiabilityBundlePremiums has BOTH integer Array6 and decimal Array6
in different Case branches. The Analyzer sets `rounding_resolved: "mixed"` and
provides per-line rounding in `target_lines[].rounding`.

**Planner behavior:** When computing before/after values in Step 8, the Planner
MUST check `target_lines[].rounding` for EACH line independently:

```python
for tl in op['target_lines']:
    if tl['rounding'] == 'banker':
        new_values = [banker_round(v * factor) for v in values]
    elif tl['rounding'] == 'none':
        new_values = [round(v * factor, 2) for v in values]
    elif tl['rounding'] is None:
        # Explicit value change, no rounding
        new_values = [v * factor for v in values]
```

**Plan display:** Show rounding mode per entry:

```markdown
  Before -> After (Farm > PRIMARYITEM > Enhanced Comp) [banker]:
    Array6(0, 78, 161, 189, 213, 291)
    Array6(0, 80, 166, 195, 219, 300)

  Before -> After (Farm > PRIMARYITEM > ELITECOMP) [no rounding]:
    Array6(0, 0, 0, 0, 324.29, 462.32)
    Array6(0, 0, 0, 0, 334.02, 476.19)
```

### 2. Array6 Dual Use in Same Function

**Pattern:** `varRates = Array6(...)` is a rate assignment (MODIFY), while
`IsItemInArray(x, Array6(...))` is a membership test (NEVER MODIFY). Both can
appear in the same function.

**Planner behavior:** The Analyzer already separates these into `target_lines`
(modify) and `skipped_lines` (don't modify). The Planner:
- Shows only `target_lines` entries in the before/after section
- Notes the skipped lines in the plan if `skipped_lines` is non-empty:

```markdown
  Note: {N} Array6 lines skipped (membership tests, not rate values).
  See analysis notes for details.
```

### 3. Developer-Confirmed: false

**Pattern:** The Analyzer couldn't auto-confirm targets (e.g., multiple candidate
functions, ambiguous match). The operation has `developer_confirmed: false`.

**Planner behavior:** Flag prominently in the plan:

```markdown
Phase {N}: {title} ({op_id}) [rate-modifier]
  *** WARNING: Targets NOT confirmed by developer ***
  *** The Analyzer found multiple candidates. Review carefully. ***
  File: {target_file}
  Function: {function_name}() -- UNCONFIRMED
  ...
```

Risk level is automatically elevated to HIGH (Step 9).

### 4. Circular Dependency Detected

**Pattern:** The dependency graph has a cycle (should not happen -- Decomposer
checks for this, but the Planner double-checks).

**Planner behavior:** STOP immediately at Step 4.4 with:

```
[Planner] ERROR: Circular dependency detected!
          Cycle: op-001-01 -> op-003-01 -> op-002-01 -> op-001-01

          This should have been caught by the Decomposer. The dependency
          graph has a cycle that makes it impossible to determine execution
          order. Please review the depends_on fields in these operations
          and break the cycle.
```

Write no output files. The orchestrator must re-run from the Decomposer.

### 5. Very Large Plan (100+ operations)

**Pattern:** A massive rate update with many SRDs affecting many functions.

**Planner behavior:** In the execution_plan.md, summarize phases with counts and
show abbreviated details:

```markdown
EXECUTION PLAN: Saskatchewan Habitational 2026-01-01
====================================================

Summary: 127 operations across 14 files, HIGH risk
LOBs affected: Home, Condo, Tenant, FEC, Farm, Seasonal

... (FILE COPIES section as normal) ...

Phase 1: Base rate increases (42 operations) [rate-modifier]
  Files: mod_Common_SKHab20260101.vb (36 ops), CalcOption_SKHOME20260101.vb (6 ops)

  Showing first 3 of 42:

    op-001-01: GetBasePremium_Home - multiply by 1.05
      Before: Array6(basePremium, 233, 274, 319, 372, 432, 502)
      After:  Array6(basePremium, 245, 288, 335, 391, 454, 527)

    op-001-02: GetBasePremium_Condo - multiply by 1.05
      Before: Array6(basePremium, 189, 222, 259, 301, 350, 407)
      After:  Array6(basePremium, 198, 233, 272, 316, 368, 427)

    op-001-03: GetBasePremium_Tenant - multiply by 1.05
      Before: Array6(basePremium, 145, 170, 198, 231, 268, 312)
      After:  Array6(basePremium, 152, 179, 208, 243, 281, 328)

  ... (39 more operations following same 1.05x pattern)

Phase 2: Factor table changes (18 operations) [rate-modifier]
  ... (abbreviated similarly)

... (remaining phases)

FULL DETAIL: See plan/execution_order.yaml for complete operation list.
```

The execution_order.yaml always contains ALL operations regardless of plan size.

### 6. Partial Approval with Diamond Dependencies

**Pattern:** SRD-A -> SRD-B, SRD-A -> SRD-C, SRD-B + SRD-C -> SRD-D. This
creates a diamond dependency pattern.

```
    SRD-A
   /     \
SRD-B   SRD-C
   \     /
    SRD-D
```

**Planner behavior:** The partial_approval_constraints surface all inter-SRD
couplings. Rejecting SRD-A blocks SRD-B, SRD-C, AND SRD-D. Rejecting SRD-B
blocks SRD-D (but not SRD-C). Rejecting SRD-C blocks SRD-D (but not SRD-B).

The plan shows:
```markdown
PARTIAL APPROVAL CONSTRAINTS:
  The following SRDs are coupled by dependencies:
  - SRD-B requires SRD-A: op-002-01 depends on op-001-01
  - SRD-C requires SRD-A: op-003-01 depends on op-001-01
  - SRD-D requires SRD-B: op-004-01 depends on op-002-01
  - SRD-D requires SRD-C: op-004-01 depends on op-003-01
  Rejecting a required SRD will also block the dependent SRD.
```

### 7. Cross-Province Shared File Flagged

**Pattern:** An operation references `Code/PORTCommonHeat.vb` -- a cross-province
shared file that the plugin MUST NOT modify.

**Planner behavior:** The Analyzer should have flagged this. If the operation
still appears, the Planner includes a prominent WARNING:

```markdown
Phase {N}: {title} ({op_id}) [WARNING: CROSS-PROVINCE SHARED FILE]
  *** THIS OPERATION WILL NOT BE EXECUTED ***
  File: Code/PORTCommonHeat.vb
  Reason: Cross-province shared file. Modifying this file would affect
          ALL provinces, not just {province}. This change must be made
          manually by the developer after careful review.

  The developer must:
    1. Review PORTCommonHeat.vb manually
    2. Make the change in a separate commit
    3. Test all affected provinces
```

The operation is included in the plan for visibility but excluded from
execution_sequence in execution_order.yaml.

### 8. File needs_new_file: true

**Pattern:** The Logic Modifier must CREATE a file from scratch (e.g., a new
Option_*.vb file for a new endorsement type).

**Planner behavior:**

```markdown
Phase {N}: Create Option_EliteComp_SKHOME20260101.vb ({op_id}) [logic-modifier]
  CREATE NEW FILE: Saskatchewan/Code/Option_EliteComp_SKHOME20260101.vb
  Template: Saskatchewan/Code/Option_Comprehensive_SKHOME20250901.vb
  Description: New endorsement option file for Elite Comp coverage.
               Logic Modifier will use the template as a structural reference
               and generate the new file with ELITECOMP-specific logic.

  *** New file -- no before/after comparison available ***
  *** Template will guide structure; values come from SRD parameters ***
```

In execution_order.yaml, the operation appears normally. In file_hashes.yaml,
the target file has `hash: null` (does not exist yet).

### 9. has_expressions: true in Array6

**Pattern:** Some Array6 arguments contain arithmetic expressions like `30 + 10`
instead of simple numeric values.

**Planner behavior:** Elevate risk to HIGH and annotate:

```markdown
Phase {N}: {title} ({op_id}) [rate-modifier]
  File: {target_file}
  Function: {function_name}()
  Action: Multiply all Array6 values by {factor}

  *** NOTE: Some Array6 arguments contain arithmetic expressions ***
  *** These will be evaluated before modification ***

  Before -> After ({context}):
    Array6(basePremium, 30 + 10, 50 + 15, 100)
    Array6(basePremium, 42, 68, 105)
                        ^^ evaluated: (30+10)*1.05=42

  The Rate Modifier will:
    1. Evaluate each expression to get the numeric value
    2. Apply the multiplication factor
    3. Replace the expression with the computed result
    4. The original expression form is NOT preserved
```

### 10. Stale Hash Detected

**Pattern:** A source file's hash has changed between the Analyzer run and the
Planner run. Someone edited a Code/ file while the pipeline was in progress.

**Planner behavior:** STOP at Step 3.2 with:

```
[Planner] ERROR: Source file changed since Analyzer ran!
          File: Saskatchewan/Code/mod_Common_SKHab20250901.vb
          Expected hash: sha256:a1b2c3d4...
          Current hash:  sha256:x9y8z7w6...
          Affected operations: op-002-01, op-003-01, op-004-01, op-004-02

          Someone modified this file between the Analyzer and Planner runs.
          The Analyzer's line numbers and target_lines content may be stale.
          Re-run from /iq-plan to get fresh analysis.
```

Write no output files. The orchestrator must re-run the full pipeline.

---

## KEY RESPONSIBILITIES (Summary)

1. **Load all Analyzer output:** Read manifest, config, dependency graph, operation
   files, files_to_copy, and blast radius report.
2. **Validate operation completeness:** Every operation must have required Analyzer
   fields (source_file, target_file, file_hash, function_line_start/end or
   insertion_point, target_lines or equivalent).
3. **Verify file hashes:** Compute current SHA-256 of every source file and compare
   against Analyzer's recorded hashes. STOP if any mismatch.
4. **Build and validate the dependency DAG:** Parse depends_on edges, check for
   self-loops and cycles using DFS 3-color marking.
5. **Compute topological sort:** Use Kahn's algorithm with deterministic tie-breaking
   (alphabetical op_id). Track topological levels for phase grouping.
6. **Group operations into phases:** Same topological level + different files = same
   phase. Same file = different phases. Assign titles, agents, rationales.
7. **Order within-file operations bottom-to-top:** Highest line number first within
   each file to prevent line-number drift during execution.
8. **Extract before/after values:** Read actual source files, compute expected new
   values applying factors and rounding, generate side-by-side comparisons.
9. **Compute risk level:** LOW -> MEDIUM -> HIGH based on file count, shared modules,
   cross-file dependencies, expression complexity, unconfirmed operations.
10. **Generate execution_plan.md:** Human-readable plan with scannable format, before/
    after previews, impact metrics, warnings, and partial approval constraints.
11. **Generate execution_order.yaml:** Machine-readable plan with phases, file operation
    order (bottom-to-top), flat execution sequence, and file copy instructions.
12. **Write file_hashes.yaml:** Capture SHA-256 of all source, target, and .vbproj
    files for TOCTOU protection during /iq-execute.
13. **Handle zero-operation case:** When Analyzer found nothing to change, write an
    empty plan explaining why and exit cleanly.
14. **Surface cross-province shared file warnings:** Include in plan but exclude from
    execution sequence.
15. **Carry forward partial approval constraints:** Copy from dependency_graph.yaml
    into execution_order.yaml and show in execution_plan.md.

---

## Boundary Table

| Responsibility | Planner | Orchestrator (/iq-plan) | /iq-execute |
|---|---|---|---|
| Order operations (topo sort) | YES | NO | Follows order |
| Bottom-to-top within file | YES | NO | Follows order |
| Present plan to developer | Writes files | Shows to developer | NO |
| Handle Gate 1 approval/rejection | NO | YES | Requires approved |
| Handle partial approval | Writes constraints | Processes approval | Executes approved only |
| File hash capture | YES (writes file_hashes.yaml) | NO | Reads + verifies |
| TOCTOU check at execution | NO | NO | YES |
| File copies | Lists in plan | NO | Executes copies |
| Before/after computation | YES | Shows to developer | Executes changes |
| Risk level computation | YES | Displays to developer | NO |
| Developer interaction | NONE (fully automated) | YES (Gate 1) | YES (if issues) |
| Phase grouping | YES | Displays to developer | Follows phases |
| Cross-province file warning | Includes in plan | Shows warning | Skips execution |
| .vbproj update instructions | Passes through from Analyzer | NO | Executes updates |

---

## Partial Approval

When the developer partially approves the plan at Gate 1, the orchestrator
(/iq-plan) handles the interaction. The Planner's role is to provide the data
that enables partial approval:

### What the Planner provides

1. **partial_approval_constraints** in execution_order.yaml -- lists inter-SRD
   couplings so the orchestrator can validate the developer's choices.

2. **SRD grouping** -- every operation has an `srd` field, so the orchestrator
   can filter by SRD.

3. **Dependency chain tracking** -- the `depends_on` edges in each operation
   allow the orchestrator to compute transitive dependencies:

```python
def get_blocked_srds(rejected_srds, op_map):
    """Given rejected SRDs, find all transitively blocked SRDs."""
    rejected_ops = set()
    for op in op_map.values():
        if op['srd'] in rejected_srds:
            rejected_ops.add(op['id'])

    blocked_srds = set()
    changed = True
    while changed:
        changed = False
        for op in op_map.values():
            if op['srd'] in rejected_srds or op['srd'] in blocked_srds:
                continue
            for dep_id in op.get('depends_on', []):
                if dep_id in rejected_ops:
                    blocked_srds.add(op['srd'])
                    rejected_ops.add(op['id'])
                    changed = True
                    break

    return blocked_srds
```

### What the orchestrator does with it

1. Parses developer's "approve X, reject Y" response
2. Calls dependency validation using partial_approval_constraints
3. If blocked: reports to developer with options
4. If valid: filters execution_order.yaml to approved-only and proceeds

---

## Plan Revision

When the developer rejects the plan or requests changes at Gate 1, the
orchestrator (/iq-plan) handles the interaction. The Planner may be re-run
with updated inputs.

### Revision scenarios

**Scenario 1: Developer corrects a specific value.**
"Change the factor for Territory 1 from 1.05 to 1.03."

The orchestrator updates the operation file (op-*.yaml) and re-runs the Planner.
The Planner re-reads all inputs and regenerates the plan. No special handling
needed -- the Planner always reads from disk.

**Scenario 2: Developer rejects the approach.**
"Don't modify GetBasePremium_Home. Use GetBasePrem_HomeNew instead."

The orchestrator must re-run from the Analyzer (or possibly the Decomposer)
to get new line numbers. The Planner is not involved until the Analyzer produces
updated operation files.

**Scenario 3: Developer requests additional changes.**
"Also change the $2500 deductible factor."

The orchestrator must re-run from the Intake agent to parse the new SRD.
The Planner is not involved until the full pipeline produces updated inputs.

### Planner's role in revision

The Planner does NOT maintain state between runs. Each invocation:
1. Reads all inputs fresh from disk
2. Validates everything from scratch (including hash checks)
3. Generates fresh output files

This stateless design means the Planner can be re-run at any time without
risk of stale state. The orchestrator is responsible for ensuring the inputs
are up-to-date before invoking the Planner.

---

## Error Handling

### Missing Operation Files

```
[Planner] ERROR: Expected {N} operation files (from dependency_graph.yaml)
          but found {M} in analysis/operations/.
          Missing: {list of missing op IDs}

          The Analyzer may not have completed successfully.
          Check manifest.yaml for analyzer.status.
```

### Invalid Operation Schema

```
[Planner] ERROR: Operation {op_id} has invalid schema.
          File: analysis/operations/{op_id}.yaml
          Issue: {specific validation failure}

          Expected fields for {agent} operation:
            {list of required fields}

          Missing: {list of missing fields}
```

### Source File Not Found

```
[Planner] ERROR: Source file not found for operation {op_id}:
          Path: {source_file}

          This file should exist on disk. Either:
            - The file was deleted after the Analyzer ran
            - The path in the operation file is incorrect
          Re-run from /iq-plan to re-analyze.
```

### Hash Mismatch (Stale File)

```
[Planner] ERROR: Source file changed since Analyzer ran!
          File: {filepath}
          Expected hash: {expected}
          Current hash:  {actual}
          Affected operations: {op_ids}

          Someone modified this file between the Analyzer and Planner runs.
          Re-run from /iq-plan to get fresh analysis.
```

### Cycle Detected

```
[Planner] ERROR: Circular dependency detected!
          Cycle: {cycle_path}

          This should have been caught by the Decomposer.
          Please review the depends_on fields in these operations
          and break the cycle.
```

### No Output Directory

```
[Planner] ERROR: Cannot create output directory:
          Path: {path}
          Error: {os_error}

          Check file system permissions for the workstream directory.
```

### Topological Sort Incomplete

```
[Planner] ERROR: Topological sort processed {N} of {M} operations.
          Stuck operations: {list}

          This indicates a hidden cycle in the dependency graph.
          Re-run from the Decomposer to rebuild the dependency graph.
```

---

## NOT YET IMPLEMENTED (Future Enhancements)

- **Interactive plan builder:** Allow the developer to reorder phases or merge
  operations interactively before approving. Currently the Planner generates a
  fixed plan that the developer approves or rejects as-is.

- **Dry-run execution:** Run the Rate Modifier and Logic Modifier in dry-run mode
  to validate that all changes CAN be applied before presenting the plan. This
  would catch issues like "function not found at expected line" before Gate 1.

- **Plan diffing:** When the Planner is re-run after a revision, show what changed
  compared to the previous plan. Currently each plan is generated independently.

- **Confidence scores:** Assign per-operation confidence based on how precisely the
  Analyzer matched targets. High confidence = exact content match, low confidence =
  pattern-based guess. Show in the plan to help developers focus review.

- **Parallel execution hints:** Currently all same-file operations are sequential.
  Future versions could analyze whether two operations in the same file but in
  different functions could safely execute in parallel (if their line ranges don't
  overlap and neither adds/removes lines).

- **Plan templates:** For common change patterns (e.g., "5% across-the-board rate
  increase"), use a template that pre-fills the plan structure, reducing generation
  time and improving consistency.

<!-- IMPLEMENTATION: Phase 06 -->
