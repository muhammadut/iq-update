# Agent: Planner

## Purpose

Produce a dependency-ordered execution plan and the approval document presented at
Gate 1. The plan should be so clear and informative that the developer spends minimal
time reviewing it. Capture file hashes for TOCTOU protection.

The Planner has ONE developer interaction point: resolving open questions from the
intent graph. It reads Analyzer output, collects any open questions from intents,
presents them to the developer, records answers, then computes optimal execution
ordering, generates before/after previews, and writes two output files: a
human-readable plan (`plan/execution_plan.md`) and a machine-readable execution
order (`plan/execution_order.yaml`). The orchestrator (/iq-plan) presents the
human-readable plan to the developer at Gate 1.

**Core philosophy: Make the plan scannable.** A simple 5% rate increase should take
10 seconds to review. A complex multi-CR hab workflow should clearly show phases,
dependencies, and risk areas so the developer knows exactly what will happen.

## Pipeline Position

```
[INPUT] --> Intake --> Discovery --> Analyzer --> Decomposer --> PLANNER --> [GATE 1] --> Change Engine --> Reviewer --> [GATE 2]
                                                                ^^^^^^^
```

- **Upstream:** Decomposer agent (provides `analysis/intent_graph.yaml` with intents, dependencies, and open questions) + Analyzer agent (provides `analysis/blast_radius.md` + `analysis/files_to_copy.yaml`)
- **Downstream:** Change Engine (consumes `plan/execution_order.yaml`); Developer reviews `plan/execution_plan.md` at Gate 1; /iq-execute reads `execution/file_hashes.yaml`

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
  shared_module: true                          # true if any intent targets a shared module
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

### analysis/intent_graph.yaml (from Decomposer)

```yaml
workflow_id: "20260101-SK-Hab-rate-update"
decomposer_version: "2.0"
decomposed_at: "2026-02-27T10:00:00"
total_intents: 4                               # Total intents decomposed
total_out_of_scope: 1                          # CRs marked out of scope (DAT file, etc.)

out_of_scope:                                  # CRs with no intents (tracked for audit)
  - cr: "cr-001"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"

intents:
  - id: "intent-001"
    cr: "cr-002"
    title: "Change $5000 deductible factor from -0.20 to -0.22"
    description: "Modify the $5000 deductible discount factor"
    capability: "value_editing"                # value_editing | structure_insertion | file_creation
    strategy_hint: "factor-table"              # Optional hint for Change Engine
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    depends_on: []                             # List of intent IDs this depends on
    confidence: 0.95                           # 0.0 to 1.0
    open_questions: []                         # Questions needing developer input
    # -- Evidence traceability (carried from CR) --
    source_text: "Change $5000 deductible factor from -0.20 to -0.22"
    source_location: "ticket description item 2"
    evidence_refs: ["ticket description item 2"]
    assumptions: []
    done_when: "Case 5000 dblDedDiscount changed from -0.2 to -0.22"
    # -- Analyzer-enriched fields --
    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    needs_copy: true
    file_hash: "sha256:a1b2c3d4..."
    function_line_start: 2100
    function_line_end: 2250
    target_lines:
      - line: 2202
        content: "                Case 5000 : dblDedDiscount = -0.2"
        context: "Case 5000 deductible"
        rounding: null
        value_count: 1
    parameters:
      old_value: -0.20
      new_value: -0.22
    candidates_shown: 1
    developer_confirmed: true

  - id: "intent-002"
    cr: "cr-003"
    title: "Add $50,000 sewer backup coverage tier"
    description: "Insert new Case block for $50K sewer backup"
    capability: "structure_insertion"
    strategy_hint: null
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetSewerBackupPremium"
    depends_on: []
    confidence: 0.7
    open_questions:
      - "Ticket specifies $50K tier but no premium amount. What value?"
      - "Insert before or after existing $25K case?"
    # -- Evidence traceability (carried from CR) --
    source_text: "Add $50,000 sewer backup coverage tier"
    source_location: "ticket description item 3"
    evidence_refs: ["ticket description item 3"]
    assumptions: ["Premium amount not specified -- open question"]
    done_when: "New Case 50000 block inserted in GetSewerBackupPremium"
    # -- Analyzer-enriched fields --
    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    needs_copy: true
    file_hash: "sha256:a1b2c3d4..."
    function_line_start: 3800
    function_line_end: 3900
    insertion_point:
      line: 3850
      position: "after"
      context: "After Case 25000 block"
      section: "GetSewerBackupPremium Select Case"
    parameters:
      coverage_amount: 50000
      premium: null                            # Needs developer answer
    candidates_shown: 1
    developer_confirmed: true

  # ... more intents

partial_approval_constraints: []               # Inter-CR coupling for Gate 1
# Non-empty example:
#   - cr: "cr-003"
#     requires_cr: "cr-001"
#     reason: "intent-003 depends on intent-001"
#     blocking_intents: ["intent-003"]
#     required_intents: ["intent-001"]

execution_order:                               # Topological order from Decomposer
  - "intent-001"
  - "intent-002"
  - "intent-003"
  - "intent-004"
```

**Purpose:** The Planner uses `execution_order` as the starting point for phase
grouping, `depends_on` edges to build the DAG, `open_questions` for the Q&A step,
and `partial_approval_constraints` to carry forward into the plan for Gate 1
partial approval. The `cr` field on each intent links back to the parent change
request for partial approval grouping.

### Intent fields used by the Planner

Each intent in `intent_graph.yaml` contains Decomposer fields + Analyzer
enrichments. The Planner reads ALL intents. Key fields used by the Planner:

**Core intent fields (all intents):**

| Field | Type | Purpose for Planner |
|-------|------|-------------------|
| `id` | string | Intent identifier (e.g., "intent-001") |
| `cr` | string | Parent CR ID (for partial approval grouping) |
| `title` | string | Human-readable title (used in phase titles) |
| `description` | string | Detailed description (included in plan) |
| `capability` | string | "value_editing", "structure_insertion", or "file_creation" |
| `strategy_hint` | string or null | Optional hint for Change Engine (e.g., "array6-multiply") |
| `file` | string | Target file path (for file grouping) |
| `file_type` | string | shared_module, lob_specific, etc. (for risk) |
| `function` | string or null | Target function name (for display) |
| `depends_on` | list | Intent IDs this depends on (for DAG) |
| `confidence` | float | 0.0 to 1.0 (for risk assessment) |
| `open_questions` | list | Questions needing developer input (for Q&A step) |
| `strategy_hint` | string or null | Optional hint for Change Engine; used by Planner for before/after display |
| `parameters` | dict | Pattern-specific parameters (for before/after) |

**Evidence traceability fields (carried from CR by Decomposer):**

| Field | Type | Purpose for Planner |
|-------|------|-------------------|
| `source_text` | string | Original ticket text for this change (for evidence in plan) |
| `source_location` | string | Where in ticket this came from (for evidence in plan) |
| `evidence_refs` | list | References to screenshots/attachments (for evidence in plan) |
| `assumptions` | list | Assumptions made during decomposition (for risks section) |
| `done_when` | string | Verification criteria (for validation section in plan) |

**Analyzer-enriched fields (value_editing intents):**

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

**Analyzer-enriched fields (structure_insertion intents):**

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
| `needs_new_file` | bool | Whether Change Engine must CREATE a file |
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
    intents_in_file: ["intent-001", "intent-002", "intent-003", "intent-004"]
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

### parsed/ticket_understanding.md (from Intake -- confirmed by developer)

The Planner reads this file to build the "Understanding Journey" section of the
plan. This file has been confirmed by the developer -- it represents the agreed-upon
understanding of what the ticket is asking for.

The document has numbered sections that the Planner extracts from:
1. "What the Ticket Description Says" — raw evidence from description
2. "What the Comments Add" — how comments corrected/extended the description
3. "What the Screenshots/Images Show" — data extracted from images
4. "My Understanding (Synthesized)" — final interpretation with evidence sources
5. "Ambiguities & Open Questions"
6. "Confidence Assessment"
7. "Developer Confirmation" — timestamp and any corrections

The Planner uses this to:
- Build a condensed reasoning chain in the plan's "Understanding Journey" section
- Connect each plan phase back to the ticket evidence
- Detect if the code plan has drifted from the business intent
- Populate the Verification Strategy with CR-specific developer check items

### parsed/change_requests.yaml (from Intake)

The Planner reads this for:
- `source_text` and `source_location` per CR (evidence trail)
- `extracted` values (the concrete numbers the developer confirmed)
- `ambiguity_flag` and `ambiguity_note` (unresolved items)

### Actual source files (on disk)

The Planner reads the actual VB.NET source files referenced by `source_file` in each
intent to:
- Extract current code lines for before/after display
- Compute expected new values for the "after" column
- Verify that file_hash values are still fresh

---

## Output Schema

### plan/execution_plan.md

Human-readable plan for developer approval at Gate 1. The plan is organized by
Change Request so the developer can trace every code change back to its business
justification. Two formats depending on complexity: SIMPLE (thin wrapper) and
COMPLEX (full structure). Both use the CR-organized format below.

#### Plan structure (both formats)

```markdown
# EXECUTION PLAN: {Province} {LOB(s)} {Date}

## Understanding Journey
{Condensed reasoning chain from parsed/ticket_understanding.md.
NOT the full document -- extract the key trail that shows HOW the
final understanding was reached:

**From description:** {1-2 sentence summary of what the description said}
**From comments:** {what comments changed or added — "Comment 3 by John Smith
corrected the percentage from 5% to 3%. Comment 5 added deductible factor change."}
**From screenshots:** {what was extracted — or "None" if no images}
**Final understanding:** {2-3 sentences — the confirmed, synthesized understanding}
**What changed:** {what differs between raw description and final understanding,
or "Comments confirmed description as-is."}

Developer confirmed at {confirmation_timestamp}.}

## Decisions Applied
{List of developer decisions from manifest.yaml developer_decisions}

## Blocking Questions
{Empty if plan is approvable. Listed here if plan is DRAFT.}

## Plan By Change Request

### CR-001: {title}

**What the ticket is asking:**
{from ticket understanding, not just the CR title}

**Evidence:**
- Source: "{quoted text from ticket}"
- Location: {where in the ticket}
- Ref: {comment, screenshot, etc.}

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
- {any assumptions from intent, risk flags}

---

### CR-002: ...

## Out of Scope
{CRs marked out of scope with reasons -- omit section if none}

## Execution Order
{Phase ordering with dependency explanation}

## Verification Strategy

### What the Plugin Will Verify Automatically
{List all automated checks that run during /iq-review. For each, explain
what it proves in plain language:}
- Array6 syntax: all Array6() calls have correct parentheses and unchanged arg counts
- Completeness: all {N} territories updated, all {M} LOBs handled
- No old file modification: only target-date files were edited
- No commented code modified: no commented-out lines were changed
- Value sanity: all rate changes within expected range ({min%} to {max%})
- Cross-LOB consistency: shared module references consistent across all LOBs
- Traceability: every CR maps to at least one code change
- Vbproj integrity: every <Compile Include> path resolves to an existing file
- Semantic verification: for each value edit, verify old × factor = new within rounding

### What the Developer Must Verify
{Specific, actionable items tied to each CR:}
{For each CR:}
- **CR-001:** Build {project_name} in Visual Studio → confirm compile.
  Run a {Province} {LOB} quote → check that {specific field/section in UI}
  shows ~{expected change} (e.g., "liability premiums ~3% higher than before").
- **CR-002:** Run a quote with ${case_value} deductible → verify discount
  shows {new_value} (was {old_value}).
{Generic:}
- svn commit and record revision

## Impact Summary
- Files to copy: {N}
- Files to modify: {N}
- .vbproj updates: {N}
- Shared module blast radius: {LOBs affected}
- Value change range: {min%} to {max%}
- Risk level: {risk} -- {reasons}

## Context Tiers
  Tier 1 (value substitution):  {N} intents
  Tier 2 (logic with patterns): {N} intents
  Tier 3 (full context):        {N} intents

## Warnings
{any warnings from analysis or risk computation -- omit section if none}

## Partial Approval Constraints
{if any inter-CR dependencies exist, show them here -- omit section if none}

## Approval
Approving this plan means you agree with BOTH:
1. The business interpretation (what we're changing and why)
2. The code implementation (how we're making the changes)

Approve, reject, or ask questions.
```

#### SIMPLE format differences (1-2 intents, single file, LOW or MEDIUM risk)

For simple plans, the structure above is used but sections are condensed:
- "Confirmed Ticket Understanding" may be a single sentence
- "Decisions Applied" is omitted if no decisions were needed
- "Execution Order" is omitted (single phase needs no ordering explanation)
- All before/after entries are shown (no truncation)
- "Context Tiers" and "Warnings" are omitted if empty

#### COMPLEX format differences (3+ intents, multiple files, or HIGH risk)

For complex plans, the full structure is used with:
- Complete "Confirmed Ticket Understanding" paragraph
- All CR sections with full evidence and implementation detail
- For intents with more than 10 before/after entries, show first 2 and a
  summary: "(showing 2 of N -- all follow same pattern)"
- Full "Execution Order" with dependency graph explanation
- Full "Impact Summary" with all metrics

#### Phase detail formats by capability type

**value_editing (Array6 multiply):**
```markdown
Phase {N}: {title} ({intent_id}) [value_editing]
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

**value_editing (factor table):**
```markdown
Phase {N}: {title} ({intent_id}) [value_editing]
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

**structure_insertion (code insertion):**
```markdown
Phase {N}: {title} ({intent_id}) [structure_insertion{, depends on Phase M}]
  File: {target_file}
  {Function: {function_name}() | Location: {location}}
  Action: {description}

  Insert after line {insertion_point.line} ({insertion_point.context}):
    + {new code line 1}
    + {new code line 2}
    + {new code line 3}
```

**file_creation (new file):**
```markdown
Phase {N}: {title} ({intent_id}) [file_creation]
  CREATE NEW FILE: {target_file}
  Template: {template_reference}
  Action: {description}
```

### plan/execution_order.yaml

Machine-readable plan consumed by /iq-execute.

```yaml
# File: plan/execution_order.yaml
# Generated by Planner agent
# Consumed by /iq-execute orchestrator and Change Engine

planner_version: "2.0"
generated_at: "2026-02-27T11:00:00"            # ISO 8601 timestamp
workflow_id: "20260101-SK-Hab-rate-update"      # From manifest.yaml
plan_status: "approved"                         # "approved" | "draft" (draft = blocking questions remain)

# Summary metrics
total_phases: 5                                 # Number of execution phases
total_intents: 4                                # Number of intents across all phases
total_value_changes: 107                        # Sum of all value edits
total_file_copies: 2                            # Number of file copies
total_vbproj_updates: 7                         # Number of .vbproj reference updates
risk_level: "MEDIUM"                            # LOW | MEDIUM | HIGH
risk_reasons:                                   # List of reasons for the risk level
  - "3 intents in shared module (6 LOBs)"
  - "Mixed rounding in GetLiabilityBundlePremiums"
tier_distribution:                               # From Step 9.5
  tier_1: 2                                      # Value substitution (thin capsule)
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
# Intents within the same phase can run in parallel ONLY if they target
# different files. Same-file intents are NEVER in the same phase.
phases:
  - phase: 1
    title: "Change $5000 deductible factor"     # Human-readable phase title
    intents: ["intent-001"]                     # List of intent IDs in this phase
    rationale: "Independent, no dependencies"
    depends_on_phases: []                       # Phase numbers this phase depends on

  - phase: 2
    title: "Add $50K sewer backup tier"
    intents: ["intent-002"]
    rationale: "Independent of Phase 1"
    depends_on_phases: []

  - phase: 3
    title: "Multiply liability bundle premiums by 1.03"
    intents: ["intent-003"]
    rationale: "Independent"
    depends_on_phases: []

  - phase: 4
    title: "Multiply liability extension premiums by 1.03"
    intents: ["intent-004"]
    rationale: "Same file as Phase 3, sequenced for bottom-to-top"
    depends_on_phases: [3]

# Within each file, intents are ordered highest line number first
# to prevent line-number drift from insertions/deletions above.
# The Change Engine MUST follow this order exactly.
file_operation_order:
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    - intent_id: "intent-004"                  # line 4106 (highest)
      line_ref: 4106                            # Reference line for ordering
      tier: 2                                   # From Step 9.5
    - intent_id: "intent-003"                  # line 4012
      line_ref: 4012
      tier: 2
    - intent_id: "intent-002"                  # line 3850
      line_ref: 3850
      tier: 2
    - intent_id: "intent-001"                  # line 2202 (lowest in this file)
      line_ref: 2202
      tier: 1

# Flat execution sequence combining topological sort + bottom-to-top.
# /iq-execute processes intents in EXACTLY this order.
# This is the authoritative execution order.
execution_sequence:
  - intent_id: "intent-004"                    # Phase 4 - bottom-to-top (line 4106)
    phase: 4
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    capability: "value_editing"
    strategy_hint: "array6-multiply"            # Optional
    tier: 2                                     # From Step 9.5
  - intent_id: "intent-003"                    # Phase 3 - bottom-to-top (line 4012)
    phase: 3
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    capability: "value_editing"
    strategy_hint: "array6-multiply"
    tier: 2
  - intent_id: "intent-002"                    # Phase 2 - bottom-to-top (line 3850)
    phase: 2
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    capability: "structure_insertion"
    strategy_hint: null
    tier: 2
  - intent_id: "intent-001"                    # Phase 1 - bottom-to-top (line 2202)
    phase: 1
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    capability: "value_editing"
    strategy_hint: "factor-table"
    tier: 1

# Partial approval constraints (carried from intent_graph.yaml)
partial_approval_constraints: []
# Non-empty example:
#   - cr: "cr-003"
#     requires_cr: "cr-001"
#     reason: "intent-003 depends on intent-001"
```

### execution/file_hashes.yaml

```yaml
# File: execution/file_hashes.yaml
# Captured by Planner at plan generation time
# Used by /iq-execute for TOCTOU protection before each file write

planner_version: "2.0"
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

**File hash handoff from Analyzer:** The Analyzer writes `file_hash` in each intent
entry. The Planner collects these hashes and writes `execution/file_hashes.yaml` at
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
3. The `analysis/intent_graph.yaml` (from Decomposer, with Analyzer enrichments)
4. The `analysis/files_to_copy.yaml` (from Analyzer)
5. The `analysis/blast_radius.md` (from Analyzer)
6. The `.iq-workstreams/config.yaml` (for naming patterns and hab flags)
7. The `parsed/ticket_understanding.md` (from Intake -- confirmed by developer)
8. The `parsed/change_requests.yaml` (from Intake -- CR evidence and extracted values)

If items 1-6 are missing, STOP and report:
```
[Planner] Cannot proceed -- missing required file: {path}
          Was the Decomposer completed? Check manifest.yaml for decomposer.status = "completed".
```

If items 7-8 are missing, log a warning and proceed -- the plan will omit business
context sections but can still generate the code-level execution plan:
```
[Planner] WARNING: Missing {path} -- plan will not include business context sections.
          The Intake agent should have produced these files. Check manifest.yaml for intake.status.
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

1.3. Read `analysis/intent_graph.yaml`. Extract:
   - `total_intents` (int)
   - `total_out_of_scope` (int)
   - `out_of_scope` (list -- for inclusion in plan header)
   - `intents` (list -- each intent with id, cr, title, capability, etc.)
   - `partial_approval_constraints` (list -- for inclusion in plan)
   - `execution_order` (list -- topological order from Decomposer)

1.4. Read `analysis/files_to_copy.yaml`. Extract:
   - `total_files` (int)
   - `files` (list -- each with source, target, source_hash, target_exists,
     shared_by, intents_in_file, vbproj_updates)

1.5. Read `parsed/ticket_understanding.md` (if it exists). Store the full text
   as `ticket_understanding`. This is the developer-confirmed business context.
   Extract:
   - The one-paragraph summary of what the ticket is asking for
   - Any non-goals or scope limitations
   - Any corrections the developer made during Intake confirmation

1.6. Read `parsed/change_requests.yaml` (if it exists). Build a CR lookup map:

```python
cr_map = {}
for cr in change_requests.get("requests", []):
    cr_map[cr["id"]] = {
        "title": cr.get("title", ""),
        "source_text": cr.get("source_text", ""),
        "source_location": cr.get("source_location", ""),
        "evidence_refs": cr.get("evidence_refs", []),
        "extracted": cr.get("extracted", {}),
        "ambiguity_flag": cr.get("ambiguity_flag", False),
        "ambiguity_note": cr.get("ambiguity_note", ""),
    }
```

1.7. Build the **plan context** object:

```
PLAN CONTEXT
---------------------------------------------------------
Workflow:       {workflow_id}
Province:       {province_name} ({province})
LOBs:           {comma-separated lobs}
Effective Date: {effective_date}
Intents:        {total_intents} in scope, {total_out_of_scope} out of scope
File Copies:    {total_files} files to copy
Risk Indicators: shared_module={Y/N}, cross_lob={Y/N}, cross_province={Y/N}
```

If `total_intents == 0`:
```
[Planner] No in-scope intents to plan. All CRs were out of scope.
          Out of scope: {list of out_of_scope CR titles}
          Writing empty plan and exiting.
```
Write an empty execution_plan.md (with the out-of-scope list) and an empty
execution_order.yaml (total_phases: 0, total_intents: 0), then exit.

### Step 2: Load and Validate Intents

**Action:** Read all intents from intent_graph.yaml and build the intent lookup map.

2.1. Read the `intents` list from `analysis/intent_graph.yaml`.

2.2. For each intent, validate required fields:

**For ALL intents:**
- `id` (string, must match pattern intent-NNN)
- `cr` (string, must start with "cr-")
- `title` (string, non-empty)
- `capability` (string, one of: "value_editing", "structure_insertion", "file_creation", "flow_modification")
- `file` (string, non-empty path)
- `file_type` (string, one of: shared_module, lob_specific, cross_lob, local)
- `depends_on` (list, may be empty)
- `confidence` (float, 0.0 to 1.0)
- `open_questions` (list, may be empty)
- `source_file` (string, path to existing source file)
- `target_file` (string, path to target file)
- `needs_copy` (bool)
- `file_hash` (string, "sha256:...")

**Additional for value_editing intents:**
- `function_line_start` (int, > 0)
- `function_line_end` (int, > function_line_start)
- `target_lines` (list, non-empty, each with line, content, context, rounding)

**Additional for structure_insertion intents:**
- `insertion_point` (dict with line, position, context) OR `needs_new_file: true`

If any required field is missing or invalid:
```
[Planner] ERROR: Intent {intent_id} is missing required field: {field_name}
          Was the Decomposer/Analyzer completed? This field should be present.
```

2.3. Build the **intent lookup map**: `intent_id -> full intent data`

```python
# Pseudocode
intent_map = {}
for intent in intent_graph['intents']:
    intent_map[intent['id']] = intent
```

2.4. Count intents by capability:

```
INTENT COUNTS
---------------------------------------------------------
value_editing intents:        {N}
structure_insertion intents:  {N}
file_creation intents:        {N}
Total:                        {N}
```

2.5. Validate that all intent IDs referenced in `execution_order` from
intent_graph.yaml exist in the intent_map:

```python
for intent_id in intent_graph['execution_order']:
    if intent_id not in intent_map:
        STOP("Intent {intent_id} in execution_order not found in intents list")
```

2.6. Validate that all `depends_on` references point to existing intents:

```python
for intent_id, intent in intent_map.items():
    for dep_id in intent.get('depends_on', []):
        if dep_id not in intent_map:
            STOP("Intent {intent_id} depends on {dep_id} which does not exist")
```

### Step 3: Verify File Hashes (Freshness Check)

**Action:** Verify that no source files have changed since the Analyzer ran.

3.1. Collect all unique `source_file` paths across all intents:

```python
source_files = {}
for intent_id, intent in intent_map.items():
    src = intent['source_file']
    if src not in source_files:
        source_files[src] = {
            'expected_hash': intent['file_hash'],
            'intents': [intent_id]
        }
    else:
        source_files[src]['intents'].append(intent_id)
        # Verify consistency: all intents on the same file should have the same hash
        if source_files[src]['expected_hash'] != intent['file_hash']:
            STOP("Hash inconsistency for {src}: intent {intent_id} has different hash than others")
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
          Affected intents: {', '.join(info['intents'])}

          Someone modified this file between the Analyzer and Planner runs.
          Re-run from /iq-plan to get fresh analysis.
""")
```

3.3. If ALL hashes match, proceed. Log:
```
[Planner] File hash verification: {N} source files checked, all current.
```

### Step 3.5: Resolve Open Questions (Q&A Flow)

**Action:** Collect open questions from intents, present them to the developer,
record answers, and update intents with resolved values.

3.5.1. Scan all intents for `open_questions`:

```python
questions_by_intent = {}
for intent_id, intent in intent_map.items():
    if intent.get('open_questions'):
        questions_by_intent[intent_id] = {
            'title': intent['title'],
            'questions': intent['open_questions'],
            'confidence': intent['confidence'],
        }
```

3.5.2. If no intents have open questions, skip this step entirely:

```python
if not questions_by_intent:
    # Log and skip
    print("[Planner] No open questions -- skipping Q&A step.")
    # Proceed directly to Step 4
```

3.5.3. Present questions to the developer, grouped by intent:

```
Questions requiring your input:

Intent intent-002: "Add $50,000 sewer backup coverage tier"
  Q1: Ticket specifies $50K tier but no premium amount. What value?
  Q2: Insert before or after existing $25K case?

Intent intent-003: "Increase extension premiums by 3%"
  Q3: GetLiabilityExtensionPremiums found in same category as bundle.
      Should extension premiums also get the 3% increase? (Y/N)
```

Number questions sequentially across all intents (Q1, Q2, Q3...) for easy
reference. Include the intent title for context.

3.5.4. Record answers in `plan/developer_decisions.yaml`:

```yaml
# File: plan/developer_decisions.yaml
decisions:
  - question: "Ticket specifies $50K tier but no premium amount. What value?"
    answer: "125.00"
    intent: "intent-002"
    question_index: 1
    answered_at: "2026-03-03T10:00:00"
  - question: "Insert before or after existing $25K case?"
    answer: "After the $25K case"
    intent: "intent-002"
    question_index: 2
    answered_at: "2026-03-03T10:00:30"
  - question: "Should extension premiums also get the 3% increase?"
    answer: "Yes"
    intent: "intent-003"
    question_index: 3
    answered_at: "2026-03-03T10:01:00"
```

3.5.5. Update intents based on answers:

```python
for decision in decisions:
    intent_id = decision['intent']
    intent = intent_map[intent_id]

    # Fill in missing values from answers
    # (implementation depends on question type -- e.g., premium amount fills
    #  intent['parameters']['premium'])
    apply_answer_to_intent(intent, decision)

    # Remove the answered question from open_questions
    if decision['question'] in intent['open_questions']:
        intent['open_questions'].remove(decision['question'])

    # Bump confidence on resolved intents
    if not intent['open_questions']:
        # All questions answered -- raise confidence
        intent['confidence'] = min(intent['confidence'] + 0.2, 1.0)
```

3.5.6. Classify remaining open questions as BLOCKING or NON-BLOCKING:

```python
BLOCKING_CATEGORIES = {
    "missing_value",        # Missing values required for code changes (e.g., "what premium for $50K tier?")
    "ambiguous_scope",      # Ambiguous scope (e.g., "which territories?")
    "conflicting_reqs",     # Conflicting requirements between CRs
    "missing_insertion",    # Missing insertion points for new code
}

NON_BLOCKING_CATEGORIES = {
    "style_preference",     # Style preferences (e.g., variable naming)
    "optimization_choice",  # Optimization choices
    "optional_enhancement", # Optional enhancements beyond the CR scope
}

def classify_question(question_text, intent):
    """Classify an open question as blocking or non-blocking.

    BLOCKING questions (must be resolved before Gate 1):
    - Missing values required for code changes (e.g., "what premium for $50K tier?")
    - Ambiguous scope (e.g., "which territories?")
    - Conflicting requirements
    - Missing insertion points for new code

    NON-BLOCKING questions (noted but don't stop the plan):
    - Style preferences
    - Optimization choices
    - Optional enhancements
    """
    q_lower = question_text.lower()

    # Missing value indicators
    if any(kw in q_lower for kw in ["what value", "what premium", "what amount",
                                     "not specified", "no premium", "missing"]):
        return "blocking", "missing_value"

    # Ambiguous scope indicators
    if any(kw in q_lower for kw in ["which territories", "which lobs",
                                     "which function", "which version"]):
        return "blocking", "ambiguous_scope"

    # Conflict indicators
    if any(kw in q_lower for kw in ["conflict", "contradicts", "both"]):
        return "blocking", "conflicting_reqs"

    # Missing insertion point
    if any(kw in q_lower for kw in ["where to insert", "insert before or after",
                                     "insertion point"]):
        return "blocking", "missing_insertion"

    # If intent has null required parameters, it's blocking
    params = intent.get("parameters", {})
    if intent["capability"] == "structure_insertion":
        if params.get("premium") is None and "premium" in q_lower:
            return "blocking", "missing_value"

    # Default: non-blocking (style/preference questions)
    return "non-blocking", "style_preference"


remaining = {
    intent_id: info
    for intent_id, info in questions_by_intent.items()
    if intent_map[intent_id].get('open_questions')
}

blocking_questions = []
non_blocking_questions = []

for intent_id, info in remaining.items():
    intent = intent_map[intent_id]
    for q in intent.get('open_questions', []):
        classification, category = classify_question(q, intent)
        entry = {
            "intent_id": intent_id,
            "intent_title": intent["title"],
            "question": q,
            "category": category,
        }
        if classification == "blocking":
            blocking_questions.append(entry)
        else:
            non_blocking_questions.append(entry)

if blocking_questions:
    print(f"[Planner] BLOCKING: {len(blocking_questions)} question(s) must be resolved before Gate 1.")
    for bq in blocking_questions:
        print(f"          - [{bq['category']}] {bq['intent_title']}: {bq['question']}")
if non_blocking_questions:
    print(f"[Planner] NON-BLOCKING: {len(non_blocking_questions)} question(s) noted (will not stop plan).")
if not remaining:
    print("[Planner] All open questions resolved. Proceeding with plan generation.")
```

3.5.7. **BLOCKING QUESTION GATE:** If ANY blocking questions remain unresolved
after the Q&A step, the Planner MUST:

1. Mark the plan as `DRAFT - DECISIONS REQUIRED`
2. List all blocking questions at the TOP of execution_plan.md
3. Set a field `plan_status: "draft"` in execution_order.yaml
4. The orchestrator in /iq-plan MUST NOT present a draft plan as approvable at Gate 1

```python
plan_is_draft = len(blocking_questions) > 0

if plan_is_draft:
    print("[Planner] Plan will be generated as DRAFT -- blocking questions prevent approval.")
    print("          Developer must answer blocking questions, then re-run /iq-plan.")
```

3.5.8. Log completion:
```
[Planner] Q&A step complete: {N} questions answered across {M} intents.
          Blocking questions remaining: {len(blocking_questions)}
          Non-blocking questions noted: {len(non_blocking_questions)}
          Developer decisions saved to plan/developer_decisions.yaml
          Plan status: {"DRAFT - DECISIONS REQUIRED" if plan_is_draft else "READY"}
```

### Step 4: Build Dependency DAG

**Action:** Parse dependency edges into a directed acyclic graph and validate it.

4.1. Build adjacency lists from intent `depends_on` fields:

```python
# Forward edges: intent -> list of intents that depend on it
dependents = {intent_id: [] for intent_id in intent_map}
# Reverse edges: intent -> list of intents it depends on
dependencies = {intent_id: [] for intent_id in intent_map}

for intent_id, intent in intent_map.items():
    for dep_id in intent.get('depends_on', []):
        dependents[dep_id].append(intent_id)
        dependencies[intent_id].append(dep_id)
```

4.2. Validate: no self-loops.

```python
for intent_id, intent in intent_map.items():
    if intent_id in intent.get('depends_on', []):
        STOP("[Planner] ERROR: Self-loop detected: {intent_id} depends on itself")
```

4.3. Validate: all referenced nodes exist (already done in Step 2.6).

4.4. Detect cycles using DFS with 3-color marking:

```python
WHITE, GRAY, BLACK = 0, 1, 2
color = {intent_id: WHITE for intent_id in intent_map}
parent = {intent_id: None for intent_id in intent_map}
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

for intent_id in intent_map:
    if color[intent_id] == WHITE:
        cycle = dfs(intent_id)
        if cycle:
            cycle_str = ' -> '.join(cycle)
            STOP(f"""
[Planner] ERROR: Circular dependency detected!
          Cycle: {cycle_str}

          This should have been caught by the Decomposer. The dependency
          graph has a cycle that makes it impossible to determine execution
          order. Please review the depends_on fields in these intents
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

in_degree = {intent_id: len(dependencies[intent_id]) for intent_id in intent_map}
```

5.2. Initialize queue with all nodes having in-degree 0:

```python
# Tie-breaking: sort by intent_id for deterministic output
queue = deque(sorted(
    [intent_id for intent_id, deg in in_degree.items() if deg == 0],
    key=lambda x: x
))
```

5.3. Process queue using Kahn's algorithm:

```python
topo_order = []
topo_level = {}  # intent_id -> topological level (for phase grouping)

current_level = {intent_id: 0 for intent_id in queue}

while queue:
    intent_id = queue.popleft()
    topo_order.append(intent_id)
    topo_level[intent_id] = current_level[intent_id]

    for dep_intent in sorted(dependents[intent_id]):
        in_degree[dep_intent] -= 1
        # Level of dependent = max level of all its dependencies + 1
        current_level.setdefault(dep_intent, 0)
        current_level[dep_intent] = max(
            current_level[dep_intent],
            current_level[intent_id] + 1
        )
        if in_degree[dep_intent] == 0:
            queue.append(dep_intent)
    # Re-sort queue for deterministic tie-breaking
    queue = deque(sorted(queue, key=lambda x: x))
```

5.4. Verify completeness:

```python
if len(topo_order) != len(intent_map):
    processed = set(topo_order)
    stuck = [intent_id for intent_id in intent_map if intent_id not in processed]
    STOP(f"""
[Planner] ERROR: Topological sort incomplete!
          Processed: {len(topo_order)} of {len(intent_map)} intents
          Stuck intents: {', '.join(stuck)}

          This indicates a cycle that DFS missed (should not happen).
          Re-run from /iq-plan to re-analyze.
""")
```

5.5. Log the topological order:
```
[Planner] Topological sort complete: {N} intents in {max_level + 1} levels.
          Order: {', '.join(topo_order)}
```

### Step 6: Group into Phases

**Action:** Group intents into execution phases based on topological level and
file conflicts.

6.1. Start with topological levels as initial phase grouping:

```python
# Group by topological level
level_groups = {}
for intent_id in topo_order:
    level = topo_level[intent_id]
    level_groups.setdefault(level, [])
    level_groups[level].append(intent_id)
```

6.2. Within each level, split intents on the SAME file into separate phases.
Intents on different files at the same topological level can stay together
(they execute on different files, so no line-drift conflict):

```python
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

    # Determine how many sub-phases needed (max intents on any single file)
    max_per_file = max(len(intents) for intents in file_groups.values())

    for sub_phase_idx in range(max_per_file):
        phase_num += 1
        phase_intents = []
        for target_file, intents in file_groups.items():
            if sub_phase_idx < len(intents):
                phase_intents.append(intents[sub_phase_idx])

        if phase_intents:
            phases.append({
                'phase': phase_num,
                'intents': phase_intents,
                'topo_level': level,
            })
```

6.3. Assign titles and metadata to each phase:

```python
for phase in phases:
    intents = phase['intents']

    # Determine title
    if len(intents) == 1:
        phase['title'] = intent_map[intents[0]]['title']
    else:
        # Check if all intents share the same capability
        capabilities = set(intent_map[intent_id]['capability'] for intent_id in intents)
        if len(capabilities) == 1:
            cap = capabilities.pop()
            phase['title'] = f"{len(intents)} {cap.replace('_', ' ')} changes"
        else:
            phase['title'] = f"Mixed changes ({len(intents)} intents)"

    # Determine rationale
    if phase.get('topo_level', 0) == 0 and not any(
        intent_map[intent_id].get('depends_on') for intent_id in intents
    ):
        phase['rationale'] = "Independent, no dependencies"
    else:
        # Find which phases this depends on
        dep_phases = set()
        for intent_id in intents:
            for dep_id in intent_map[intent_id].get('depends_on', []):
                for prev_phase in phases:
                    if dep_id in prev_phase['intents']:
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
          Phase 1: {title} ({N} intents)
          Phase 2: {title} ({N} intents)
          ...
```

### Step 7: Within-File Bottom-to-Top Ordering

**Action:** For each file that has multiple intents across different phases,
sort them by line number DESCENDING (highest line first).

7.1. Build the file-to-intents map:

```python
file_intents = {}  # target_file -> list of (line_ref, intent_id)

for intent_id, intent in intent_map.items():
    target = intent['target_file']
    file_intents.setdefault(target, [])

    # Determine the reference line number for ordering
    if intent['capability'] == 'value_editing':
        # Use the HIGHEST target_line for ordering
        if intent.get('target_lines'):
            max_line = max(tl['line'] for tl in intent['target_lines'])
            line_ref = max_line
        else:
            line_ref = intent.get('function_line_start', 0)
    elif intent['capability'] == 'structure_insertion':
        # Use insertion_point.line for ordering
        if intent.get('insertion_point'):
            line_ref = intent['insertion_point']['line']
        elif intent.get('function_line_start'):
            line_ref = intent['function_line_start']
        else:
            line_ref = 0  # New files go last
    else:
        line_ref = intent.get('function_line_start', 0)

    file_intents[target].append((line_ref, intent_id))
```

7.2. Sort each file's intents DESCENDING by line number:

```python
file_operation_order = {}

for target_file, intents_with_lines in file_intents.items():
    # Sort descending by line number (highest first = bottom-to-top)
    sorted_intents = sorted(intents_with_lines, key=lambda x: x[0], reverse=True)
    file_operation_order[target_file] = [
        {'intent_id': intent_id, 'line_ref': line_ref}
        for line_ref, intent_id in sorted_intents
    ]
```

7.3. Log the bottom-to-top ordering for files with multiple intents:

```
[Planner] Bottom-to-top ordering:
          {target_file}: {intent_id1} (line {N}) -> {intent_id2} (line {M}) -> ...
```

**Why bottom-to-top matters:** When the Change Engine adds or removes lines in
a file, all line numbers BELOW the edit stay the same, but all line numbers
ABOVE the edit shift. By starting from the bottom (highest line numbers first),
each edit only affects lines that have already been processed, so line-number
references for remaining intents stay valid.

### Step 8: Extract Before/After Values

**Action:** Read actual source files and compute expected before/after for each
intent. This is the core of what makes the plan useful for developer review.

8.1. Read each unique source file once:

```python
file_contents = {}
for intent_id, intent in intent_map.items():
    src = intent['source_file']
    if src not in file_contents:
        with open(src, 'r') as f:
            file_contents[src] = f.readlines()
```

8.2. For each **value_editing** intent with `target_lines`:

```python
for intent_id, intent in intent_map.items():
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

            intent['before_after'].append({
                'line': line_num,
                'context': tl['context'],
                'before': content.strip(),
                'after': new_content.strip(),
                'pct_changes': pct_changes,
                'value_count': tl.get('value_count', len(values)),
            })

        elif strategy == 'factor-table' or params.get('case_value'):
            old_val = params['old_value']
            new_val = params['new_value']
            new_content = content.replace(str(old_val), str(new_val))

            if old_val != 0:
                pct = ((new_val - old_val) / abs(old_val)) * 100
            else:
                pct = None

            intent['before_after'].append({
                'line': line_num,
                'context': tl['context'],
                'before': content.strip(),
                'after': new_content.strip(),
                'change': f"{old_val} -> {new_val}",
                'pct_change': pct,
            })

        else:
            # Generic explicit value replacement
            old_val = params.get('old_value')
            new_val = params.get('new_value')
            if old_val is not None and new_val is not None:
                new_content = content.replace(str(old_val), str(new_val))
            else:
                new_content = content  # No computation possible

            intent['before_after'].append({
                'line': line_num,
                'context': tl['context'],
                'before': content.strip(),
                'after': new_content.strip(),
                'change': f"{old_val} -> {new_val}" if old_val is not None else "",
            })
```

8.3. For each **structure_insertion** intent:

```python
for intent_id, intent in intent_map.items():
    if intent['capability'] != 'structure_insertion':
        continue

    if intent.get('insertion_point'):
        ip = intent['insertion_point']
        src_lines = file_contents[intent['source_file']]

        # Extract context lines around insertion point
        line_idx = ip['line'] - 1  # 0-indexed
        context_before = src_lines[max(0, line_idx - 2):line_idx + 1]
        context_after = src_lines[line_idx + 1:min(len(src_lines), line_idx + 3)]

        intent['insertion_context'] = {
            'lines_before': [l.rstrip() for l in context_before],
            'lines_after': [l.rstrip() for l in context_after],
            'insert_after_line': ip['line'],
            'insert_after_content': ip['context'],
        }

    elif intent.get('needs_new_file'):
        intent['new_file_info'] = {
            'target_path': intent['target_file'],
            'template': intent.get('template_reference', 'none'),
        }
```

8.4. Compute aggregate statistics:

```python
total_value_changes = 0
all_pct_changes = []

for intent_id, intent in intent_map.items():
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

> **Note:** Before/after previews are **approximate**. The Planner computes preview
> values using standard floating-point arithmetic. The Change Engine may produce
> slightly different results due to its use of `Decimal` precision and
> `ROUND_HALF_EVEN` (banker's rounding). Small discrepancies (< 0.01) between
> previews and actual results are expected and not indicative of errors.

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
unique_files = set(intent['target_file'] for intent in intent_map.values())
if len(unique_files) > 1:
    risk_level = "MEDIUM"
    risk_reasons.append(f"Multiple target files ({len(unique_files)})")

# Shared module involved
if any(intent['file_type'] == 'shared_module' for intent in intent_map.values()):
    risk_level = "MEDIUM"
    shared_count = sum(1 for intent in intent_map.values() if intent['file_type'] == 'shared_module')
    risk_reasons.append(f"{shared_count} intents in shared module")

# More than 100 value changes
if total_value_changes > 100:
    risk_level = "MEDIUM"
    risk_reasons.append(f"{total_value_changes} value changes (>100)")

# Any MEDIUM-complexity intents (mixed rounding)
if any(intent.get('rounding_resolved') == 'mixed' for intent in intent_map.values()):
    risk_level = "MEDIUM"
    risk_reasons.append("Mixed rounding detected (per-line handling required)")
```

9.3. Check for HIGH conditions:

```python
# Cross-file dependencies (intent depends on intent in a different file)
for intent_id, intent in intent_map.items():
    for dep_id in intent.get('depends_on', []):
        if intent['target_file'] != intent_map[dep_id]['target_file']:
            risk_level = "HIGH"
            risk_reasons.append(f"Cross-file dependency: {intent_id} -> {dep_id}")

# Cross-LOB shared module with LOBs outside target list
if manifest_risk_indicators.get('cross_lob'):
    risk_level = "HIGH"
    risk_reasons.append("Cross-LOB file references detected")

# Many structure_insertion intents indicate complexity
insertion_intents = [i for i in intent_map.values() if i['capability'] == 'structure_insertion']
if len(insertion_intents) > 2:
    risk_level = "HIGH"
    risk_reasons.append(f"{len(insertion_intents)} structure_insertion intents")

# has_expressions in any intent
if any(intent.get('has_expressions') for intent in intent_map.values()):
    risk_level = "HIGH"
    risk_reasons.append("Array6 arguments contain arithmetic expressions")

# developer_confirmed: false on any intent
unconfirmed = [intent['id'] for intent in intent_map.values() if not intent.get('developer_confirmed', True)]
if unconfirmed:
    risk_level = "HIGH"
    risk_reasons.append(f"Unconfirmed intents: {', '.join(unconfirmed)}")

# needs_new_file: true
if any(intent.get('needs_new_file') for intent in intent_map.values()):
    risk_level = max_risk(risk_level, "MEDIUM")
    risk_reasons.append("New file creation required")

# skipped_lines present (may indicate unexpected code patterns)
if any(intent.get('skipped_lines') for intent in intent_map.values()):
    risk_reasons.append("Analyzer skipped some lines (see intent details)")

# Rule dependency warnings from codebase profile
profile_path = ".iq-workstreams/codebase-profile.yaml"
rule_deps = load_yaml_section(profile_path, "rule_dependencies")
if rule_deps:
    target_functions = set(intent.get('function') for intent in intent_map.values() if intent.get('function'))
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

### Step 9.5: Assign Intent Tiers

After computing risk_level in Step 9, assign a `tier` (1, 2, or 3) to each intent.
The tier determines how much context the capsule builder (/iq-execute) includes for
that intent's worker. Tier 1 = thin capsule (current format, no FUB). Tier 2 =
adds Function Understanding Block + canonical patterns. Tier 3 = adds peer function
bodies + cross-file context.

**This step is fully automated -- no developer interaction.**

```
TIER ASSIGNMENT TABLE
─────────────────────────────────────────────────────────────────────
Condition                                                    Tier
─────────────────────────────────────────────────────────────────────
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
  100 (large functions benefit from FUB even for simple
  strategies)

DEFAULT (no match)                                            1
  (surfaces gaps via logging rather than silently adding context)
─────────────────────────────────────────────────────────────────────
Highest tier wins when multiple conditions match.
```

```python
def assign_tier(intent, intent_map):
    """Assign a context tier (1, 2, or 3) to an intent.

    Tier determines capsule richness:
      1 = thin (value substitution, no FUB)
      2 = standard (FUB + canonical patterns)
      3 = full (FUB + peer bodies + cross-file context)

    Highest matching tier wins.
    """
    tier = 0  # Will take max of all matching conditions
    capability = intent.get("capability", "value_editing")
    strategy = intent.get("strategy_hint", "")

    if capability == "value_editing":
        # Simple value editing: no mixed rounding, no expressions
        has_mixed = intent.get("rounding_resolved") == "mixed"
        has_expr = intent.get("has_expressions", False)
        if not has_mixed and not has_expr:
            tier = max(tier, 1)
        else:
            tier = max(tier, 2)

    elif capability == "structure_insertion":
        # Simple constant insertion without code_patterns
        is_simple_const = (
            intent.get("parameters", {}).get("constant_name")
            and not intent.get("parameters", {}).get("case_block_type")
            and not intent.get("code_patterns")
        )
        if is_simple_const:
            tier = max(tier, 1)

        # Has code_patterns or FUB
        if intent.get("code_patterns") or intent.get("fub"):
            tier = max(tier, 2)

    elif capability == "file_creation":
        # New file creation always needs patterns
        tier = max(tier, 2)

    # Low confidence without strategy hint → maximum context
    if not intent.get("strategy_hint") and intent.get("confidence", 1.0) < 0.8:
        tier = max(tier, 3)

    # Cross-file dependency: depends_on an intent in a different file
    for dep_id in intent.get("depends_on", []):
        dep_intent = intent_map.get(dep_id)
        if dep_intent and intent.get("target_file") != dep_intent.get("target_file"):
            tier = max(tier, 3)

    # Unconfirmed targets → maximum context for safety
    if not intent.get("developer_confirmed", True):
        tier = max(tier, 3)

    # Large functions (>100 lines) benefit from FUB even for simple strategies
    func_start = intent.get("function_line_start", 0)
    func_end = intent.get("function_line_end", 0)
    if func_start and func_end and (func_end - func_start) > 100:
        tier = max(tier, 2)

    # Default: if nothing matched above, use Tier 1 (surfaces assignment gaps
    # via logging rather than silently consuming extra tokens)
    if tier == 0:
        tier = 1
        # Log: "No tier condition matched for intent {intent_id} — defaulting to Tier 1.
        #        Review tier assignment table if this intent needs richer context."

    return tier


# Apply tiers to all intents
for intent_id, intent in intent_map.items():
    intent["tier"] = assign_tier(intent, intent_map)
```

9.5.1. Add `tier` to `execution_sequence` and `file_operation_order` entries:

```python
# In execution_sequence:
for entry in execution_sequence:
    entry["tier"] = intent_map[entry["intent_id"]]["tier"]

# In file_operation_order:
for file_path, intents in file_operation_order.items():
    for entry in intents:
        entry["tier"] = intent_map[entry["intent_id"]]["tier"]
```

9.5.2. Compute tier distribution summary:

```python
tier_counts = {1: 0, 2: 0, 3: 0}
for intent in intent_map.values():
    tier_counts[intent["tier"]] += 1

tier_distribution = {
    "tier_1": tier_counts[1],
    "tier_2": tier_counts[2],
    "tier_3": tier_counts[3],
}
```

9.5.3. Log tier assignments:

```
[Planner] Tier assignments:
          Tier 1 (value substitution):   {N} intents
          Tier 2 (logic with patterns):  {N} intents
          Tier 3 (full context):         {N} intents
```

### Step 9.7: End-to-End Value Flow Verification

**Action:** For each value_editing intent, verify that the changed value actually
reaches the final output. This catches cases where:
- A caller overwrites the return value (detected by Analyzer's caller_analysis)
- A flow_modification intent was auto-generated by the Decomposer (Step 8.5)
- The value flows through multiple functions before reaching the output

This is a verification step, NOT a discovery step — it uses data already produced
by Discovery and Analyzer.

9.7.1. For each value_editing intent, check if a companion caller-fix intent exists:

```python
def verify_value_flow(intents):
    """Verify that each value change actually reaches the output.

    For intents with caller_analysis warnings, confirm a companion
    flow_modification intent exists. If not, flag as HIGH risk.
    """
    flow_warnings = []

    for intent in intents:
        if intent["capability"] != "value_editing":
            continue

        # Check if this intent has a caller fix companion
        caller_fix_id = intent.get("has_caller_fix")
        if caller_fix_id:
            companion = next(
                (i for i in intents if i["id"] == caller_fix_id), None
            )
            if not companion:
                flow_warnings.append({
                    "intent": intent["id"],
                    "warning": f"Intent {intent['id']} has caller_analysis "
                               f"warning but no companion fix intent "
                               f"(expected {caller_fix_id}). The value change "
                               f"may have NO EFFECT at runtime.",
                    "severity": "CRITICAL",
                })

        # Check if Analyzer flagged caller_analysis but Decomposer didn't
        # create a fix (belt-and-suspenders check).
        # The Decomposer propagates caller_analysis onto the original intent
        # as "caller_analysis_risk" in Step 8.5.3.
        caller_risk = intent.get("caller_analysis_risk")
        if caller_risk == "HIGH" and not caller_fix_id:
            flow_warnings.append({
                "intent": intent["id"],
                "warning": f"Analyzer detected HIGH caller risk for "
                           f"{intent['function']} but no caller fix intent "
                           f"was generated. Value may be overwritten.",
                "severity": "CRITICAL",
            })
        elif caller_risk == "MEDIUM" and not caller_fix_id:
            flow_warnings.append({
                "intent": intent["id"],
                "warning": f"Analyzer detected MEDIUM caller risk for "
                           f"{intent['function']}. Caller may conditionally "
                           f"overwrite the return value.",
                "severity": "WARNING",
            })

    return flow_warnings
```

9.7.2. If any CRITICAL flow warnings exist:
- Set `risk_level = "HIGH"` (override)
- Add each warning to `risk_reasons`
- Add a prominent banner to the execution plan (Step 10)

```python
flow_warnings = verify_value_flow(intents)
critical_warnings = [w for w in flow_warnings if w["severity"] == "CRITICAL"]

if critical_warnings:
    risk_level = "HIGH"
    for w in critical_warnings:
        risk_reasons.append(f"VALUE FLOW: {w['warning']}")
```

9.7.3. Log:
```
[Planner] Value flow verification: {len(flow_warnings)} warning(s)
          {len(critical_warnings)} CRITICAL (value may not reach output)
```

### Step 10: Generate execution_plan.md

**Action:** Write the human-readable plan for developer approval at Gate 1.

10.1. Determine format: SIMPLE or COMPLEX.

SIMPLE criteria: few intents, single file, and risk no higher than MEDIUM.
A single shared-module change is common (e.g., 5% rate increase) and should
still get a scannable SIMPLE plan. COMPLEX kicks in at 3+ intents, multiple
files, or HIGH risk.

```python
use_simple = (
    total_intents <= 2
    and len(unique_files) <= 1
    and risk_level in ("LOW", "MEDIUM")
)
```

10.2. Write the plan title and draft banner (if applicable):

```python
plan_lines = []

# Title
lob_str = "Habitational" if all(is_hab(l) for l in lobs) else ", ".join(lobs)
plan_lines.append(f"# EXECUTION PLAN: {province_name} {lob_str} {effective_date}")
plan_lines.append("")

# Draft banner (from Step 3.5.7 -- blocking questions prevent approval)
if plan_is_draft:
    plan_lines.append("> **DRAFT - DECISIONS REQUIRED**")
    plan_lines.append("> This plan cannot be approved until all blocking questions are resolved.")
    plan_lines.append("> Answer the questions in the Blocking Questions section below, then re-run /iq-plan.")
    plan_lines.append("")
```

10.2.1. If Step 9.7 produced CRITICAL flow warnings, add a caller-fix banner:

```python
# Value flow warning banner (from Step 9.7)
caller_fix_intents = [i for i in intent_map.values()
                       if i.get("caller_analysis_source")]
if caller_fix_intents:
    plan_lines.append("> **⚠ CALLER FIX REQUIRED**")
    for cfi in caller_fix_intents:
        orig_func = cfi["parameters"]["original_function"]
        caller_func = cfi["function"]
        plan_lines.append(
            f"> The return value of `{orig_func}` is overwritten by caller "
            f"`{caller_func}`. An additional intent ({cfi['id']}) has been "
            f"generated to fix the caller. Without this fix, the value change "
            f"has **no effect** at runtime."
        )
    plan_lines.append("")
```

10.3. Write the "Understanding Journey" section:

The plan should show the condensed reasoning chain — not dump the full
ticket_understanding.md, but extract the key evidence trail so the developer
sees HOW the understanding was built and can spot errors at the source level.

```python
plan_lines.append("## Understanding Journey")
if ticket_understanding:
    # ticket_understanding is the full text from parsed/ticket_understanding.md
    # Extract key sections to build the condensed reasoning chain.
    # The ticket understanding document has numbered sections:
    #   1. What the Ticket Description Says
    #   2. What the Comments Add
    #   3. What the Screenshots/Images Show
    #   4. My Understanding (Synthesized)
    #   5. Ambiguities & Open Questions
    #   6. Confidence Assessment

    desc_summary = extract_section_summary(ticket_understanding, "What the Ticket Description Says")
    comments_summary = extract_section_summary(ticket_understanding, "What the Comments Add")
    images_summary = extract_section_summary(ticket_understanding, "What the Screenshots")
    synthesis = extract_section_summary(ticket_understanding, "My Understanding")
    what_changed = extract_subsection(ticket_understanding, "What changed from description")
    confidence = extract_section_summary(ticket_understanding, "Confidence Assessment")

    plan_lines.append(f"**From description:** {desc_summary or '(not available)'}")
    plan_lines.append(f"**From comments:** {comments_summary or 'No comments.'}")
    plan_lines.append(f"**From screenshots:** {images_summary or 'None.'}")
    plan_lines.append(f"**Final understanding:** {synthesis or '(not available)'}")
    plan_lines.append(f"**What changed:** {what_changed or 'Comments confirmed description as-is.'}")
    plan_lines.append(f"**Confidence:** {confidence or 'N/A'}")

    # Include developer confirmation timestamp if present
    confirmation = extract_section_summary(ticket_understanding, "Developer Confirmation")
    if confirmation:
        plan_lines.append(f"**Developer confirmed:** {confirmation}")
else:
    plan_lines.append("*(ticket_understanding.md not available)*")

# Include developer corrections from manifest if any
developer_decisions = manifest.get("developer_decisions", [])
if developer_decisions:
    plan_lines.append("")
    plan_lines.append(f"Latest clarifications: {len(developer_decisions)} decision(s) applied (see Decisions Applied below)")

# Non-goals from ticket understanding (if parsed)
non_goals = extract_non_goals(ticket_understanding) if ticket_understanding else None
if non_goals:
    plan_lines.append(f"Non-goals: {non_goals}")
plan_lines.append("")
```

**`extract_section_summary` helper:** Find the section header matching the given
prefix (case-insensitive), extract its content, and return a condensed version
(first 2-3 non-empty lines, or the full section if short). If the section has
sub-items (comment-by-comment evidence), summarize the key findings rather than
repeating every comment. The goal is a 1-3 sentence summary per evidence source.

**`extract_subsection` helper:** Find a specific subsection within a section
(e.g., "What changed from description" within section 4). Return its content
as a single string.

10.4. Write the "Decisions Applied" section:

```python
if developer_decisions or decisions_from_qa:
    plan_lines.append("## Decisions Applied")
    for dd in developer_decisions:
        plan_lines.append(f"- **Q:** {dd.get('question', 'N/A')} **A:** {dd.get('answer', 'N/A')}")
    for dd in decisions_from_qa:
        plan_lines.append(f"- **Q:** {dd['question']} **A:** {dd['answer']} (intent: {dd['intent']})")
    plan_lines.append("")
elif not use_simple:
    plan_lines.append("## Decisions Applied")
    plan_lines.append("No decisions required -- all values were explicit in the ticket.")
    plan_lines.append("")
```

10.5. Write the "Blocking Questions" section:

```python
plan_lines.append("## Blocking Questions")
if blocking_questions:
    for bq in blocking_questions:
        plan_lines.append(
            f"- **[{bq['category']}]** {bq['intent_title']} ({bq['intent_id']}): "
            f"{bq['question']}"
        )
else:
    plan_lines.append("None -- plan is ready for approval.")
plan_lines.append("")
```

10.6. Write the "Plan By Change Request" section:

This is the core of the new plan format. Group intents by their parent CR and
present each CR with its business context, evidence, implementation details,
and validation criteria.

```python
plan_lines.append("## Plan By Change Request")
plan_lines.append("")

# Group intents by CR
intents_by_cr = {}
for intent_id, intent in intent_map.items():
    cr_id = intent['cr']
    intents_by_cr.setdefault(cr_id, []).append(intent)

# Sort CRs by ID for consistent ordering
for cr_id in sorted(intents_by_cr.keys()):
    cr_intents = intents_by_cr[cr_id]
    cr_info = cr_map.get(cr_id, {})
    cr_title = cr_intents[0]['title']  # Use first intent's title as fallback

    plan_lines.append(f"### {cr_id.upper()}: {cr_info.get('title', cr_title)}")
    plan_lines.append("")

    # What the ticket is asking (from ticket understanding + CR context)
    plan_lines.append(f"**What the ticket is asking:**")
    plan_lines.append(f"{cr_info.get('source_text', cr_title)}")
    plan_lines.append("")

    # Evidence trail -- each piece on its own line for readability
    plan_lines.append("**Evidence:**")
    if cr_info.get('source_text'):
        plan_lines.append(f"- Source: \"{cr_info['source_text']}\"")
    if cr_info.get('source_location'):
        plan_lines.append(f"- Location: {cr_info['source_location']}")
    # Also check intent-level evidence_refs (carried from Decomposer)
    all_refs = set()
    for intent in cr_intents:
        for ref in intent.get('evidence_refs', []):
            all_refs.add(ref)
    if all_refs:
        for ref in sorted(all_refs):
            plan_lines.append(f"- Ref: {ref}")
    if not cr_info.get('source_text') and not cr_info.get('source_location') and not all_refs:
        plan_lines.append("- *(no evidence trail available)*")
    plan_lines.append("")

    # Implementation details -- each intent as a phase, with clear visual separation
    plan_lines.append("**Implementation:**")
    plan_lines.append("")
    for intent in cr_intents:
        intent_id = intent['id']
        # Find which phase this intent belongs to
        intent_phase = None
        for phase in phases:
            if intent_id in phase['intents']:
                intent_phase = phase['phase']
                break

        dep_str = ""
        if intent.get('depends_on'):
            dep_str = f" (depends on {', '.join(intent['depends_on'])})"

        plan_lines.append(f"> **Phase {intent_phase}: {intent['title']}** ({intent_id}) `[{intent['capability']}{dep_str}]`")
        plan_lines.append(f">")
        plan_lines.append(f"> - File: `{intent['target_file']}`")
        if intent.get('function'):
            plan_lines.append(f"> - Function: `{intent['function']}()`")

        # Delegate to capability-specific detail writers
        if intent['capability'] == 'value_editing':
            write_value_editing_details(plan_lines, intent, use_simple)
        elif intent['capability'] in ('structure_insertion', 'file_creation'):
            write_insertion_details(plan_lines, intent)

        # Show warnings for this intent
        if not intent.get('developer_confirmed', True):
            plan_lines.append(f"> - ⚠ WARNING: Targets NOT confirmed by developer")
        if intent.get('has_expressions'):
            plan_lines.append(f"> - ℹ NOTE: Array6 arguments contain arithmetic expressions")
        plan_lines.append("")

    # Validation criteria (done_when from intents)
    done_whens = [intent.get('done_when', '') for intent in cr_intents if intent.get('done_when')]
    plan_lines.append("**Validation:**")
    if done_whens:
        for dw in done_whens:
            plan_lines.append(f"- {dw}")
    else:
        plan_lines.append("- Verify values match before/after previews above")
    plan_lines.append("")

    # Risks and assumptions
    all_assumptions = []
    for intent in cr_intents:
        all_assumptions.extend(intent.get('assumptions', []))
    risk_notes = []
    if any(not intent.get('developer_confirmed', True) for intent in cr_intents):
        risk_notes.append("Targets not confirmed by developer")
    if any(intent.get('has_expressions') for intent in cr_intents):
        risk_notes.append("Array6 arguments contain arithmetic expressions")
    if cr_info.get('ambiguity_flag'):
        risk_notes.append(f"Ambiguity: {cr_info.get('ambiguity_note', 'flagged')}")

    combined = all_assumptions + risk_notes
    plan_lines.append("**Risks/Assumptions:**")
    if combined:
        for item in combined:
            plan_lines.append(f"- {item}")
    else:
        plan_lines.append("- None identified")
    plan_lines.append("")
    plan_lines.append("---")
    plan_lines.append("")
```

10.7. Write the "Out of Scope" section (if any):

```python
if out_of_scope:
    plan_lines.append("## Out of Scope")
    for oos in out_of_scope:
        plan_lines.append(f"- **{oos['cr'].upper()}:** {oos['title']}")
        plan_lines.append(f"  Reason: {oos['reason']}")
    plan_lines.append("")
```

10.8. Write the "Execution Order" section (COMPLEX only or when dependencies exist):

```python
has_dependencies = any(
    intent.get('depends_on') for intent in intent_map.values()
)

if not use_simple or has_dependencies:
    plan_lines.append("## Execution Order")

    # File copies always first
    if files_to_copy:
        plan_lines.append("**Phase 0: File Copies**")
        for fc in files_to_copy:
            src_name = fc['source'].split('/')[-1]
            tgt_name = fc['target'].split('/')[-1]
            plan_lines.append(f"  {src_name} -> {tgt_name}")
            if fc.get('shared_by'):
                plan_lines.append(f"    Shared by: {', '.join(fc['shared_by'])}")
            plan_lines.append(f"    .vbproj updates: {len(fc['vbproj_updates'])} file(s)")

    # Phase ordering with rationale
    for phase in phases:
        intents_str = ', '.join(phase['intents'])
        dep_str = ""
        if phase.get('depends_on_phases'):
            dep_str = f" -- depends on Phase(s) {', '.join(str(p) for p in phase['depends_on_phases'])}"
        plan_lines.append(
            f"**Phase {phase['phase']}:** {phase['title']} ({intents_str}){dep_str}"
        )
        plan_lines.append(f"  Rationale: {phase.get('rationale', 'N/A')}")
    plan_lines.append("")
elif files_to_copy:
    # SIMPLE format: still show file copies compactly
    plan_lines.append("## File Copies")
    for fc in files_to_copy:
        src_name = fc['source'].split('/')[-1]
        tgt_name = fc['target'].split('/')[-1]
        plan_lines.append(f"  {src_name} -> {tgt_name}")
        if fc.get('shared_by'):
            plan_lines.append(f"    Shared by: {', '.join(fc['shared_by'])}")
        plan_lines.append(f"    .vbproj updates: {len(fc['vbproj_updates'])} file(s)")
    plan_lines.append("")
```

10.9. Write the "Impact Summary" section:

```python
plan_lines.append("## Impact Summary")
plan_lines.append(f"- Files to copy: {len(files_to_copy)}")
plan_lines.append(f"- Files to modify: {len(unique_files)}")
plan_lines.append(f"- .vbproj updates: {total_vbproj_updates}")
shared_lobs = set()
for fc in files_to_copy:
    shared_lobs.update(fc.get('shared_by', []))
if shared_lobs:
    plan_lines.append(f"- Shared module blast radius: {', '.join(sorted(shared_lobs))}")
if all_pct_changes:
    plan_lines.append(f"- Value change range: {min_pct:+.1f}% to {max_pct:+.1f}%")
plan_lines.append(f"- Risk level: {risk_level}")
for reason in risk_reasons:
    plan_lines.append(f"  - {reason}")
plan_lines.append("")
```

10.10. Write the "Context Tiers" section (COMPLEX format only):

```python
if not use_simple:
    plan_lines.append("## Context Tiers")
    plan_lines.append(f"  Tier 1 (value substitution):  {tier_distribution['tier_1']} intents")
    plan_lines.append(f"  Tier 2 (logic with patterns): {tier_distribution['tier_2']} intents")
    plan_lines.append(f"  Tier 3 (full context):        {tier_distribution['tier_3']} intents")
    plan_lines.append("")
```

10.11. Write the "Warnings" section (if any):

```python
warnings = collect_warnings(intent_map)
if warnings:
    plan_lines.append("## Warnings")
    for w in warnings:
        plan_lines.append(f"- {w}")
    plan_lines.append("")
```

10.12. Write the "Partial Approval Constraints" section (if any):

```python
if partial_approval_constraints:
    plan_lines.append("## Partial Approval Constraints")
    plan_lines.append("The following CRs are coupled by dependencies:")
    for pac in partial_approval_constraints:
        plan_lines.append(
            f"- {pac['cr'].upper()} requires {pac['requires_cr'].upper()}: "
            f"{pac['reason']}"
        )
    plan_lines.append("Rejecting a required CR will also block the dependent CR.")
    plan_lines.append("")
```

10.13. Write the "Verification Strategy" section:

This section explicitly separates what the plugin will verify automatically from
what the developer must verify manually. This closes the loop — the developer
knows upfront what they're still on the hook for after execution.

```python
plan_lines.append("## Verification Strategy")
plan_lines.append("")
plan_lines.append("### What the Plugin Will Verify Automatically")
plan_lines.append("After `/iq-execute`, running `/iq-review` will check:")
plan_lines.append("- **Array6 syntax:** all Array6() calls have correct parentheses and unchanged arg counts")
plan_lines.append("- **Completeness:** all territories updated, all LOBs handled")
plan_lines.append("- **No old file modification:** only target-date files were edited")
plan_lines.append("- **No commented code modified:** no commented-out lines were changed")
if all_pct_changes:
    plan_lines.append(f"- **Value sanity:** all rate changes within expected range ({min_pct:+.1f}% to {max_pct:+.1f}%)")
else:
    plan_lines.append("- **Value sanity:** all rate changes within expected range")
plan_lines.append("- **Cross-LOB consistency:** shared module references consistent across all LOBs")
plan_lines.append("- **Traceability:** every CR maps to at least one code change")
plan_lines.append("- **Vbproj integrity:** every Compile Include path resolves to an existing file")
plan_lines.append("- **Semantic verification:** for each value edit, verify old x factor = new within rounding tolerance")
plan_lines.append("")

plan_lines.append("### What the Developer Must Verify")
plan_lines.append("These checks require recompiling the DLL and testing in TBW:")

# Build per-CR developer verification items
for cr_id in sorted(intents_by_cr.keys()):
    cr_intents = intents_by_cr[cr_id]
    cr_info = cr_map.get(cr_id, {})
    cr_title = cr_info.get('title', cr_intents[0]['title'])

    # Determine what to check based on capability and parameters
    capabilities = set(intent['capability'] for intent in cr_intents)
    params = cr_intents[0].get('parameters', {})

    plan_lines.append(f"- **{cr_id.upper()}: {cr_title}**")

    # Build project names from target folders
    target_files = set(intent['target_file'] for intent in cr_intents)
    plan_lines.append(f"  1. Build affected project(s) in Visual Studio -- confirm compile")

    if 'value_editing' in capabilities:
        factor = params.get('factor')
        if factor:
            pct_str = f"{(factor - 1) * 100:+.1f}%" if factor else ""
            plan_lines.append(
                f"  2. Run a {province_name} {', '.join(lobs[:2])} quote in TBW -- "
                f"verify affected premiums show ~{pct_str} change"
            )
        elif params.get('case_value') is not None:
            plan_lines.append(
                f"  2. Run a quote with ${params['case_value']} deductible -- "
                f"verify factor is {params.get('new_value')} (was {params.get('old_value')})"
            )
        else:
            plan_lines.append(
                f"  2. Run a quote and verify the changed values appear correctly in TBW"
            )
    elif 'structure_insertion' in capabilities:
        plan_lines.append(
            f"  2. Run a quote that exercises the new code path -- verify it behaves as expected"
        )
    elif 'file_creation' in capabilities:
        plan_lines.append(
            f"  2. Run a quote that uses the new file -- verify it loads and produces correct results"
        )

plan_lines.append(f"- **General:** svn commit and record revision number")
plan_lines.append("")
```

10.14. Write the "Approval" footer:

```python
plan_lines.append("## Approval")
if plan_is_draft:
    plan_lines.append("**This plan is a DRAFT.** Blocking questions must be resolved before approval.")
    plan_lines.append("Answer the blocking questions above, then re-run /iq-plan.")
else:
    plan_lines.append("Approving this plan means you agree with BOTH:")
    plan_lines.append("1. The business interpretation (what we're changing and why)")
    plan_lines.append("2. The code implementation (how we're making the changes)")
    plan_lines.append("")
    plan_lines.append("Approve, reject, or ask questions.")
```

10.15. Write to `plan/execution_plan.md`:

```python
plan_dir = f"{workstream_path}/plan"
os.makedirs(plan_dir, exist_ok=True)

with open(f"{plan_dir}/execution_plan.md", 'w') as f:
    f.write('\n'.join(plan_lines))
```

**`write_value_editing_details` helper:**

```python
def write_value_editing_details(lines, intent, use_simple):
    params = intent['parameters']
    ba_list = intent.get('before_after', [])
    strategy = intent.get('strategy_hint', '')

    if strategy in ('array6-multiply', None) and params.get('factor'):
        lines.append(f"> - Action: Multiply all Array6 values by {params['factor']}")
        if intent.get('rounding_resolved'):
            lines.append(f"> - Rounding: {intent['rounding_resolved']}")
            if intent.get('rounding_detail'):
                lines.append(f">   {intent['rounding_detail'].strip()}")
        lines.append(f">")

        # Show before/after entries
        max_show = len(ba_list) if use_simple else min(2, len(ba_list))
        for i, ba in enumerate(ba_list[:max_show]):
            lines.append(f"> Before → After ({ba['context']}):")
            lines.append(f"> ```")
            lines.append(f"> {ba['before']}")
            lines.append(f"> {ba['after']}")
            # Show per-value percentage changes
            if ba.get('pct_changes'):
                pct_strs = []
                for pct in ba['pct_changes']:
                    if pct is None:
                        pct_strs.append("    ")
                    else:
                        pct_strs.append(f"{pct:+.1f}%")
                lines.append(f"> {'  '.join(pct_strs)}")
            lines.append(f"> ```")
            lines.append(f">")

        if not use_simple and len(ba_list) > max_show:
            lines.append(
                f"> *(showing {max_show} of {len(ba_list)} — "
                f"all follow same {params['factor']}x pattern)*"
            )

        total_vals = sum(ba.get('value_count', 1) for ba in ba_list)
        lines.append(f"> - Impact: {len(ba_list)} lines × ~{total_vals // max(len(ba_list), 1)} values = {total_vals} changes")

    elif strategy == 'factor-table' or params.get('case_value'):
        lines.append(f"> - Action: Change Case {params.get('case_value')} factor")
        lines.append(f">")
        for ba in ba_list:
            if len(ba_list) > 1:
                lines.append(f"> Path ({ba['context']}):")
            lines.append(f"> ```")
            lines.append(f"> Before: {ba['before']}")
            lines.append(f"> After:  {ba['after']}")
            lines.append(f"> Change: {ba.get('change', '')}")
            lines.append(f"> ```")
            lines.append(f">")

    else:
        # Generic value editing -- show before/after pairs
        lines.append(f"> - Action: {intent['description']}")
        lines.append(f">")
        for ba in ba_list:
            lines.append(f"> ```")
            lines.append(f"> Before: {ba['before']}")
            lines.append(f"> After:  {ba['after']}")
            lines.append(f"> ```")
            lines.append(f">")
```

**`write_insertion_details` helper:**

```python
def write_insertion_details(lines, intent):
    params = intent['parameters']

    if intent.get('insertion_point'):
        ip = intent['insertion_point']
        lines.append(f"> - Action: {intent['description']}")
        lines.append(f"> - Insert {ip['position']} line {ip['line']} ({ip['context']}):")
        lines.append(f"> ```vb")

        # Show the new code to be added (from parameters)
        if params.get('constant_name'):
            lines.append(f"> + Public Const {params['constant_name']} As String = \"{params.get('coverage_type_name', 'VALUE')}\"")
        elif 'code_to_add' in params:
            for code_line in params['code_to_add']:
                lines.append(f"> + {code_line}")
        else:
            lines.append(f"> (code will be generated by Change Engine)")
        lines.append(f"> ```")

    elif intent.get('needs_new_file'):
        lines.append(f"  Action: CREATE NEW FILE")
        lines.append(f"  Target: {intent['target_file']}")
        if intent.get('template_reference'):
            lines.append(f"  Template: {intent['template_reference']}")
        lines.append(f"  Description: {intent['description']}")
```

### Step 11: Generate execution_order.yaml

**Action:** Write the machine-readable plan for /iq-execute consumption.

11.1. Build the flat execution sequence. This combines:
- Topological order (dependency-respecting)
- Bottom-to-top within each file (highest line first)

The execution_sequence is the AUTHORITATIVE order that /iq-execute follows.
It interleaves cross-file intents and within-file intents correctly:

```python
execution_sequence = []

# Process phases in order
for phase in phases:
    # Within each phase, process files in deterministic order
    phase_intents_by_file = {}
    for intent_id in phase['intents']:
        target = intent_map[intent_id]['target_file']
        phase_intents_by_file.setdefault(target, [])
        phase_intents_by_file[target].append(intent_id)

    for target_file in sorted(phase_intents_by_file.keys()):
        intents = phase_intents_by_file[target_file]
        # Within same file in same phase, use bottom-to-top order
        if target_file in file_operation_order:
            full_order = [entry['intent_id'] for entry in file_operation_order[target_file]]
            intents_sorted = [iid for iid in full_order if iid in intents]
        else:
            intents_sorted = intents

        for intent_id in intents_sorted:
            execution_sequence.append({
                'intent_id': intent_id,
                'phase': phase['phase'],
                'file': intent_map[intent_id]['target_file'],
                'capability': intent_map[intent_id]['capability'],
                'strategy_hint': intent_map[intent_id].get('strategy_hint'),
            })
```

11.2. Assemble the complete YAML structure and write:

```python
execution_order = {
    'planner_version': '2.0',
    'generated_at': now_iso8601(),
    'workflow_id': workflow_id,
    'plan_status': 'draft' if plan_is_draft else 'approved',  # "draft" blocks Gate 1 approval
    'total_phases': len(phases),
    'total_intents': len(intent_map),
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
            'intents': p['intents'],
            'capability': p['capability'],
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
for intent_id, intent in intent_map.items():
    target = intent['target_file']
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
    'planner_version': '2.0',
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
          Output: plan/execution_order.yaml ({N} phases, {N} intents)
          Output: execution/file_hashes.yaml ({N} files)
```

---

## WORKED EXAMPLES

These examples demonstrate the full Planner flow for common scenarios.

### Example A: Simple -- Single file, 1 CR, 5% rate multiply

**Scenario:** New Brunswick Home, effective 2026-07-01. Single CR: increase
GetBasePremium_Home Array6 values by 5%.

**Input from Decomposer + Analyzer (intent_graph.yaml):**

```yaml
# analysis/intent_graph.yaml (abbreviated -- single intent)
workflow_id: "20260701-NB-Home-base-rates"
total_intents: 1
total_out_of_scope: 0
out_of_scope: []

intents:
  - id: "intent-001"
    cr: "cr-001"
    title: "Increase home base premiums by 5%"
    capability: "value_editing"
    strategy_hint: "array6-multiply"
    file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
    file_type: "shared_module"
    function: "GetBasePremium_Home"
    depends_on: []
    confidence: 0.95
    open_questions: []
    parameters:
      factor: 1.05
      scope: "all_territories"
    # -- Analyzer-enriched --
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

partial_approval_constraints: []
execution_order:
  - "intent-001"
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
    intents_in_file: ["intent-001"]
    vbproj_updates:
      - vbproj: "New Brunswick/Home/20260701/Cssi.IntelliQuote.PORTNBHOME20260701.vbproj"
        old_include: "..\\Code\\mod_Common_NBHab20260401.vb"
        new_include: "..\\Code\\mod_Common_NBHab20260701.vb"
      # ... 5 more (one per hab LOB)
```

**Step 3 -- Hash check:** 1 source file, hash matches. Proceed.

**Step 3.5 -- Q&A:** No open questions. Skipped.

**Step 4 -- DAG:** 1 node, 0 edges. Trivially valid.

**Step 5 -- Topo sort:** 1 node at level 0. Order: ["intent-001"].

**Step 6 -- Phase grouping:** 1 phase.

```
Phase 1: "Increase home base premiums by 5%" (intent-001) [value_editing]
```

**Step 7 -- Bottom-to-top:** 1 intent, trivially ordered.

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

**Step 9 -- Risk:** MEDIUM (shared module involved, but only 1 intent so LOW
would apply if not for shared module).

Actually: 1 file, 1 intent, shared_module = true, < 100 value changes (90).
Risk = MEDIUM (shared module criterion).

Wait -- re-examine: this is a single-CR simple change. The shared module flag
makes it MEDIUM, not LOW. Risk reasons: ["1 intent in shared module (6 LOBs)"].

**Step 10 -- execution_plan.md output:**

```markdown
EXECUTION PLAN: New Brunswick Home 2026-07-01
==============================================

Summary: 1 change, 1 file, 90 value edits, MEDIUM risk

FILE COPIES:
  mod_Common_NBHab20260401.vb -> mod_Common_NBHab20260701.vb
    Shared by: Home, Condo, Tenant, FEC, Farm, Seasonal
    .vbproj updates: 6 file(s)

Phase 1: Increase home base premiums by 5% (intent-001) [value_editing]
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
planner_version: "2.0"
generated_at: "2026-02-27T11:00:00"
workflow_id: "20260701-NB-Home-base-rates"
total_phases: 1
total_intents: 1
total_value_changes: 90
total_file_copies: 1
total_vbproj_updates: 6
risk_level: "MEDIUM"
risk_reasons:
  - "1 intent in shared module (6 LOBs)"
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
    intents: ["intent-001"]
    capability: "value_editing"
    rationale: "Independent, no dependencies"
    depends_on_phases: []
file_operation_order:
  "New Brunswick/Code/mod_Common_NBHab20260701.vb":
    - intent_id: "intent-001"
      line_ref: 350                              # max(target_lines[].line), NOT function_line_end
execution_sequence:
  - intent_id: "intent-001"
    phase: 1
    file: "New Brunswick/Code/mod_Common_NBHab20260701.vb"
    capability: "value_editing"
    strategy_hint: "array6-multiply"
partial_approval_constraints: []
```

---

### Example B: Medium -- Shared module, 3 CRs, mixed capabilities

**Scenario:** Saskatchewan Habitational, effective 2026-01-01.
- CR-002: Deductible factor change ($5000: -0.20 to -0.22) -- value_editing
- CR-003: Deductible factor change ($2500: -0.15 to -0.17) -- value_editing
- CR-004: Liability premium increase (bundle + extension, 1.03x) -- value_editing (2 intents)
- CR-005: Add ELITECOMP constant + Case block -- structure_insertion (2 intents)
  - intent-005: Add constant (line ~23)
  - intent-006: Add Case block in GetRateTableID (line ~435), depends on intent-005

**Dependency graph edges:**
- intent-006 depends on intent-005 (Case block references ELITECOMP constant)
- All others are independent

**Step 4 -- DAG:** 6 nodes, 1 edge. Valid, no cycles.

**Step 5 -- Topo sort:**
- Level 0: intent-001, intent-002, intent-003, intent-004, intent-005 (in-degree 0)
- Level 1: intent-006 (depends on intent-005)
- Order: [intent-001, intent-002, intent-003, intent-004, intent-005, intent-006]

**Step 6 -- Phase grouping:**
- Level 0 has 5 intents. But intent-001 through intent-004 are ALL
  on the same file (mod_Common_SKHab20260101.vb). intent-005 is ALSO on
  mod_Common_SKHab20260101.vb (module-level constants).
- So all 5 level-0 intents are on the same file -> max_per_file = 5 -> 5 sub-phases.
- Level 1 has 1 intent (intent-006, same file) -> 1 sub-phase.
- Total: 6 phases.

**Step 7 -- Bottom-to-top for mod_Common_SKHab20260101.vb:**

```
file_operation_order["Saskatchewan/Code/mod_Common_SKHab20260101.vb"]:
  - intent-004  (line 4106, GetLiabilityExtensionPremiums)
  - intent-003  (line 4012, GetLiabilityBundlePremiums)
  - intent-001  (line 2202, SetDisSur_Deductible Case 5000)
  - intent-002  (line 2180, SetDisSur_Deductible Case 2500)
  - intent-006  (line ~435, GetRateTableID insertion)
  - intent-005  (line ~23, module-level constant insertion)
```

**Step 9 -- Risk:** MEDIUM.
Reasons: ["4 intents in shared module (6 LOBs)", "Mixed rounding in GetLiabilityBundlePremiums"]

**Step 10 -- execution_plan.md (abbreviated):**

Phase numbers follow the code's assignment order (topo-level + alphabetical
tie-breaking within each level). The code assigns:
- Level 0, 5 intents on same file -> sub-phases 1-5 in topo_order:
  Phase 1: intent-001, Phase 2: intent-002, Phase 3: intent-003,
  Phase 4: intent-004, Phase 5: intent-005
- Level 1, 1 intent -> Phase 6: intent-006

Phase 6 (intent-006) depends on Phase 5 (intent-005) -- this is a valid forward
dependency (later phase depends on earlier phase).

The plan document shows phases in this numbered order. The execution_sequence
in execution_order.yaml then reorders within the file to bottom-to-top for
correct execution (line 4106 first, line 23 last). The two orderings serve
different purposes: plan = human readability, execution_sequence = machine
correctness.

```markdown
EXECUTION PLAN: Saskatchewan Habitational 2026-01-01
====================================================

Summary: 6 intents across 1 file, MEDIUM risk
LOBs affected: Home, Condo, Tenant, FEC, Farm, Seasonal
Shared module: mod_Common_SKHab20260101.vb

FILE COPIES:
  mod_Common_SKHab20250901.vb -> mod_Common_SKHab20260101.vb
    Shared by: Home, Condo, Tenant, FEC, Farm, Seasonal
    .vbproj updates: 6 file(s)

Phase 1: Change $5000 deductible factor (intent-001) [value_editing]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  Before: dblDedDiscount = -0.2
  After:  dblDedDiscount = -0.22
  ...

Phase 2: Change $2500 deductible factor (intent-002) [value_editing]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  Before: dblDedDiscount = -0.15
  After:  dblDedDiscount = -0.17
  ...

Phase 3: Multiply liability bundle premiums by 1.03 (intent-003) [value_editing]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: GetLiabilityBundlePremiums()
  Action: Multiply all Array6 values by 1.03
  Rounding: mixed (42 lines banker, 6 lines none -- per-line detail below)
  ...

Phase 4: Multiply liability extension premiums by 1.03 (intent-004) [value_editing]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: GetLiabilityExtensionPremiums()
  Action: Multiply all Array6 values by 1.03
  Rounding: banker (all values are integers)

  Before -> After (first entry):
    Array6(0, 78, 106, 161, 189, 216, 291)
    Array6(0, 80, 109, 166, 195, 222, 300)
  ...

Phase 5: Add ELITECOMP constant (intent-005) [structure_insertion]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Location: module-level constants
  Action: Add line after existing constants
    + Public Const ELITECOMP As String = "Elite Comp."

Phase 6: Add Case block for ELITECOMP (intent-006) [structure_insertion, depends on Phase 5]
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
    - 4 intents in shared module (6 LOBs)
    - Mixed rounding in GetLiabilityBundlePremiums

Approve this plan? Say "approve" to proceed or tell me what to change.
```

Note: The execution_sequence in execution_order.yaml reorders these phases
for bottom-to-top execution within the file: intent-004 (line 4106) executes
first, down to intent-005 (line ~23) last. Phase numbers in the plan document
serve human readability; the execution_sequence is the authoritative machine
execution order.

---

### Example C: Complex -- Cross-file deps, 5+ CRs, partial approval

**Scenario:** Saskatchewan Habitational, effective 2026-01-01. 5 CRs with
inter-CR dependencies:

- CR-001: Define ELITECOMP constant (structure_insertion) -- intent-001
- CR-002: Add rate table routing in GetRateTableID (structure_insertion) -- intent-002, depends on intent-001
- CR-003: Add base rate Array6 for ELITECOMP in GetBasePremium_Home (value_editing) -- intent-003, depends on intent-001
- CR-004: Add DAT IDs to ResourceID.vb in each LOB (structure_insertion) -- intent-004..009, depends on intent-002
- CR-005: Add eligibility rule in CalcOption (structure_insertion) -- intent-010, depends on intent-001 and intent-004

**Dependency graph:**
```
intent-001 (ELITECOMP constant)
  |
  +---> intent-002 (rate table routing)
  |       |
  |       +---> intent-004 (DAT ID in Home ResourceID)
  |       +---> intent-005 (DAT ID in Condo ResourceID)
  |       +---> intent-006 (DAT ID in Tenant ResourceID)
  |       +---> intent-007 (DAT ID in FEC ResourceID)
  |       +---> intent-008 (DAT ID in Farm ResourceID)
  |       +---> intent-009 (DAT ID in Seasonal ResourceID)
  |                 |
  +---> intent-003 (base rate Array6)
  |
  +---> intent-010 (eligibility rule) -- also depends on intent-004
```

**Step 5 -- Topo sort:**
- Level 0: intent-001
- Level 1: intent-002, intent-003
- Level 2: intent-004..009
- Level 3: intent-010

**Step 6 -- Phases:** 6 phases (level 0: 1 phase, level 1: 2 intents on same file
= 2 phases, level 2: 6 intents on 6 different files = 1 phase, level 3: 1 phase).

Total: 5 phases.

**Step 9 -- Risk:** HIGH.
Reasons: ["Cross-file dependency: intent-010 -> intent-004", "5 structure_insertion intents", "Inter-CR dependencies"]

**Partial approval scenario:** Developer says "Approve CR-001 and CR-002, reject CR-003, CR-004, CR-005."

Dependency validation:
- CR-003 (rejected): depends on CR-001 (approved). OK to reject.
- CR-004 (rejected): depends on CR-002 (approved). OK to reject.
- CR-005 (rejected): depends on CR-001 (approved) and CR-004 (rejected). OK to reject.
- No approved CR depends on a rejected CR. Partial approval is valid.

If developer instead says "Approve CR-004, reject CR-001":
```
Cannot approve CR-004 without CR-001.
CR-004 (Add DAT IDs) depends on CR-002 (rate table routing),
which depends on CR-001 (ELITECOMP constant).

Options:
  1. Approve CR-001, CR-002, and CR-004 together
  2. Reject all three
  3. Show me the dependency graph
```

---

### Example D: Edge -- All intents on one file

**Scenario:** 6 intents all targeting mod_Common_SKHab20260101.vb at different
line numbers. No dependencies between intents (all independent).

**Intents:**
- intent-001: GetBasePremium_Home (lines 312-418)
- intent-002: SetDisSur_Deductible Case 5000 (line 2202)
- intent-003: SetDisSur_Deductible Case 2500 (line 2180)
- intent-004: GetLiabilityBundlePremiums (lines 4012-4104)
- intent-005: GetLiabilityExtensionPremiums (lines 4106-4156)
- intent-006: Add constant at line ~23

**Step 6 -- Phase grouping:** All at topo level 0, all same file. 6 sub-phases
needed (max 1 intent per file per phase).

**Step 7 -- Bottom-to-top ordering is CRITICAL:**

```yaml
file_operation_order:
  "Saskatchewan/Code/mod_Common_SKHab20260101.vb":
    - intent_id: "intent-005"  # line 4106 (highest -- executed first)
      line_ref: 4106
    - intent_id: "intent-004"  # line 4012
      line_ref: 4012
    - intent_id: "intent-002"  # line 2202
      line_ref: 2202
    - intent_id: "intent-003"  # line 2180
      line_ref: 2180
    - intent_id: "intent-001"  # line 312
      line_ref: 312
    - intent_id: "intent-006"  # line 23 (lowest -- executed last)
      line_ref: 23
```

The execution_sequence follows this order exactly. If intent-006 (insertion at
line 23) were executed first, it would shift ALL subsequent line numbers by 1+
lines, making the line references for intent-001 through intent-005 incorrect.
Bottom-to-top prevents this drift.

**Plan display:** The plan document can show phases in any readable order (e.g.,
logical grouping), but the execution_sequence MUST follow bottom-to-top.

---

### Example E: Edge -- File already has target-date copy

**Scenario:** Developer already ran a previous workflow that created
mod_Common_SKHab20260101.vb. Now a new workflow has additional changes to the
same file.

**Analyzer output for intents:**
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

Summary: 2 intents across 1 file, LOW risk

FILE COPIES: None (target files already exist)

Phase 1: Change $5000 deductible factor (intent-001) [value_editing]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  ...

Phase 2: Change $2500 deductible factor (intent-002) [value_editing]
  File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
  Function: SetDisSur_Deductible()
  ...

Approve this plan? Say "approve" to proceed or tell me what to change.
```

The file_hashes.yaml still captures the hash of the existing file for TOCTOU
protection -- /iq-execute will verify it hasn't changed since the plan was built.

---

### Example F: Edge -- Zero intents (values already match)

**Scenario:** The Decomposer + Analyzer found that all current values in the source
file already equal the requested target values. Perhaps the rate change was already
applied in a previous workflow.

**intent_graph.yaml:**
```yaml
total_intents: 0
total_out_of_scope: 0
out_of_scope: []
intents: []
execution_order: []
```

**Planner behavior at Step 1.5:**

```
[Planner] No in-scope intents to plan.
          The Decomposer found 0 intents requiring changes.
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

CRs processed:
  CR-001: "Increase deductible factors" -- values already match
  CR-002: "Increase liability premiums" -- values already match

No approval needed. The workflow will be marked as COMPLETED with no changes.
```

**execution_order.yaml:**
```yaml
planner_version: "2.0"
generated_at: "2026-02-27T11:00:00"
workflow_id: "20260101-SK-Hab-match"
total_phases: 0
total_intents: 0
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
- Notes the skipped lines in the plan if `skipped_lines` is non-empty on the intent:

```markdown
  Note: {N} Array6 lines skipped (membership tests, not rate values).
  See analysis notes for details.
```

### 3. Developer-Confirmed: false

**Pattern:** The Analyzer couldn't auto-confirm targets (e.g., multiple candidate
functions, ambiguous match). The intent has `developer_confirmed: false`.

**Planner behavior:** Flag prominently in the plan:

```markdown
Phase {N}: {title} ({intent_id}) [{capability}]
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
          Cycle: intent-001 -> intent-003 -> intent-002 -> intent-001

          This should have been caught by the Decomposer. The dependency
          graph has a cycle that makes it impossible to determine execution
          order. Please review the depends_on fields in these intents
          and break the cycle.
```

Write no output files. The orchestrator must re-run from the Decomposer.

### 5. Very Large Plan (100+ intents)

**Pattern:** A massive rate update with many CRs affecting many functions.

**Planner behavior:** In the execution_plan.md, summarize phases with counts and
show abbreviated details:

```markdown
EXECUTION PLAN: Saskatchewan Habitational 2026-01-01
====================================================

Summary: 127 intents across 14 files, HIGH risk
LOBs affected: Home, Condo, Tenant, FEC, Farm, Seasonal

... (FILE COPIES section as normal) ...

Phase 1: Base rate increases (42 intents) [value_editing]
  Files: mod_Common_SKHab20260101.vb (36 intents), CalcOption_SKHOME20260101.vb (6 intents)

  Showing first 3 of 42:

    intent-001: GetBasePremium_Home - multiply by 1.05
      Before: Array6(basePremium, 233, 274, 319, 372, 432, 502)
      After:  Array6(basePremium, 245, 288, 335, 391, 454, 527)

    intent-002: GetBasePremium_Condo - multiply by 1.05
      Before: Array6(basePremium, 189, 222, 259, 301, 350, 407)
      After:  Array6(basePremium, 198, 233, 272, 316, 368, 427)

    intent-003: GetBasePremium_Tenant - multiply by 1.05
      Before: Array6(basePremium, 145, 170, 198, 231, 268, 312)
      After:  Array6(basePremium, 152, 179, 208, 243, 281, 328)

  ... (39 more intents following same 1.05x pattern)

Phase 2: Factor table changes (18 intents) [value_editing]
  ... (abbreviated similarly)

... (remaining phases)

FULL DETAIL: See plan/execution_order.yaml for complete intent list.
```

The execution_order.yaml always contains ALL intents regardless of plan size.

### 6. Partial Approval with Diamond Dependencies

**Pattern:** CR-A -> CR-B, CR-A -> CR-C, CR-B + CR-C -> CR-D. This
creates a diamond dependency pattern.

```
    CR-A
   /     \
CR-B    CR-C
   \     /
    CR-D
```

**Planner behavior:** The partial_approval_constraints surface all inter-CR
couplings. Rejecting CR-A blocks CR-B, CR-C, AND CR-D. Rejecting CR-B
blocks CR-D (but not CR-C). Rejecting CR-C blocks CR-D (but not CR-B).

The plan shows:
```markdown
PARTIAL APPROVAL CONSTRAINTS:
  The following CRs are coupled by dependencies:
  - CR-B requires CR-A: intent-002 depends on intent-001
  - CR-C requires CR-A: intent-003 depends on intent-001
  - CR-D requires CR-B: intent-004 depends on intent-002
  - CR-D requires CR-C: intent-004 depends on intent-003
  Rejecting a required CR will also block the dependent CR.
```

### 7. Cross-Province Shared File Flagged

**Pattern:** An intent references `Code/PORTCommonHeat.vb` -- a cross-province
shared file that the plugin MUST NOT modify.

**Planner behavior:** The Analyzer should have flagged this. If the intent
still appears, the Planner includes a prominent WARNING:

```markdown
Phase {N}: {title} ({intent_id}) [WARNING: CROSS-PROVINCE SHARED FILE]
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

The intent is included in the plan for visibility but excluded from
execution_sequence in execution_order.yaml.

### 8. File needs_new_file: true

**Pattern:** The Change Engine must CREATE a file from scratch (e.g., a new
Option_*.vb file for a new endorsement type).

**Planner behavior:**

```markdown
Phase {N}: Create Option_EliteComp_SKHOME20260101.vb ({intent_id}) [file_creation]
  CREATE NEW FILE: Saskatchewan/Code/Option_EliteComp_SKHOME20260101.vb
  Template: Saskatchewan/Code/Option_Comprehensive_SKHOME20250901.vb
  Description: New endorsement option file for Elite Comp coverage.
               The Change Engine will use the template as a structural reference
               and generate the new file with ELITECOMP-specific logic.

  *** New file -- no before/after comparison available ***
  *** Template will guide structure; values come from CR parameters ***
```

In execution_order.yaml, the intent appears normally. In file_hashes.yaml,
the target file has `hash: null` (does not exist yet).

### 9. has_expressions: true in Array6

**Pattern:** Some Array6 arguments contain arithmetic expressions like `30 + 10`
instead of simple numeric values.

**Planner behavior:** Elevate risk to HIGH and annotate:

```markdown
Phase {N}: {title} ({intent_id}) [value_editing]
  File: {target_file}
  Function: {function_name}()
  Action: Multiply all Array6 values by {factor}

  *** NOTE: Some Array6 arguments contain arithmetic expressions ***
  *** These will be evaluated before modification ***

  Before -> After ({context}):
    Array6(basePremium, 30 + 10, 50 + 15, 100)
    Array6(basePremium, 42, 68, 105)
                        ^^ evaluated: (30+10)*1.05=42

  The Change Engine will:
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
          Affected intents: intent-001, intent-002, intent-003, intent-004

          Someone modified this file between the Analyzer and Planner runs.
          The Analyzer's line numbers and target_lines content may be stale.
          Re-run from /iq-plan to get fresh analysis.
```

Write no output files. The orchestrator must re-run the full pipeline.

---

## KEY RESPONSIBILITIES (Summary)

1. **Load all upstream output:** Read manifest, config, intent_graph.yaml,
   files_to_copy, and blast radius report.
2. **Validate intent completeness:** Every intent must have required Analyzer-enriched
   fields (source_file, target_file, file_hash, function_line_start/end or
   insertion_point, target_lines or equivalent).
3. **Verify file hashes:** Compute current SHA-256 of every source file and compare
   against Analyzer's recorded hashes. STOP if any mismatch.
4. **Resolve open questions:** Collect open_questions from intents, present to
   developer with code context, record answers, update intent parameters and confidence.
5. **Build and validate the dependency DAG:** Parse depends_on edges, check for
   self-loops and cycles using DFS 3-color marking.
6. **Compute topological sort:** Use Kahn's algorithm with deterministic tie-breaking
   (alphabetical intent_id). Track topological levels for phase grouping.
7. **Group intents into phases:** Same topological level + different files = same
   phase. Same file = different phases. Assign titles, capabilities, rationales.
8. **Order within-file intents bottom-to-top:** Highest line number first within
   each file to prevent line-number drift during execution.
9. **Extract before/after values:** Read actual source files, compute expected new
   values applying factors and rounding, generate side-by-side comparisons.
10. **Compute risk level:** LOW -> MEDIUM -> HIGH based on file count, shared modules,
    cross-file dependencies, expression complexity, unconfirmed intents.
11. **Generate execution_plan.md:** Human-readable plan with scannable format, before/
    after previews, impact metrics, warnings, and partial approval constraints.
12. **Generate execution_order.yaml:** Machine-readable plan with phases, file operation
    order (bottom-to-top), flat execution sequence, and file copy instructions.
13. **Write file_hashes.yaml:** Capture SHA-256 of all source, target, and .vbproj
    files for TOCTOU protection during /iq-execute.
14. **Handle zero-intent case:** When Decomposer found nothing to change, write an
    empty plan explaining why and exit cleanly.
15. **Surface cross-province shared file warnings:** Include in plan but exclude from
    execution sequence.
16. **Carry forward partial approval constraints:** Copy from intent_graph.yaml
    into execution_order.yaml and show in execution_plan.md.
17. **NEVER invent API references.** Every function call, constant, enum value,
    and `Cssi.ResourcesConstants.*` reference in plan output (action descriptions,
    code snippets, before/after previews) MUST trace back to one of:
    - An existing line in the source file (copy from discovered code)
    - An explicit instruction from the intent/decomposer
    - A value the developer provided in `developer_decisions`

    If the Planner observes a pattern in the file (e.g., every `AddToArray` is
    paired with `AddToDiscountArray`) and wants to replicate it for new code,
    it MUST flag this as an `open_question` for the developer to confirm at
    Gate 1 — NOT silently add it. Pattern extrapolation is a hallucination risk.

    **Caller vs library responsibility:** When a library function is called
    (e.g., `oIQCommon.AddPolicyTermToPPVCoverageArray`), do NOT assume the
    caller needs to replicate behavior that the library handles internally.
    If the original code did not have a matching caller-side call, the plan
    should not add one.

---

## Boundary Table

| Responsibility | Planner | Orchestrator (/iq-plan) | /iq-execute |
|---|---|---|---|
| Order intents (topo sort) | YES | NO | Follows order |
| Bottom-to-top within file | YES | NO | Follows order |
| Resolve open questions (Q&A) | YES | NO | NO |
| Present plan to developer | Writes files | Shows to developer | NO |
| Handle Gate 1 approval/rejection | NO | YES | Requires approved |
| Handle partial approval | Writes constraints | Processes approval | Executes approved only |
| File hash capture | YES (writes file_hashes.yaml) | NO | Reads + verifies |
| TOCTOU check at execution | NO | NO | YES |
| File copies | Lists in plan | NO | Executes copies |
| Before/after computation | YES | Shows to developer | Executes changes |
| Risk level computation | YES | Displays to developer | NO |
| Developer interaction | Q&A step only (Step 3.5) | YES (Gate 1) | YES (if issues) |
| Phase grouping | YES | Displays to developer | Follows phases |
| Cross-province file warning | Includes in plan | Shows warning | Skips execution |
| .vbproj update instructions | Passes through from Analyzer | NO | Executes updates |

---

## Partial Approval

When the developer partially approves the plan at Gate 1, the orchestrator
(/iq-plan) handles the interaction. The Planner's role is to provide the data
that enables partial approval:

### What the Planner provides

1. **partial_approval_constraints** in execution_order.yaml -- lists inter-CR
   couplings so the orchestrator can validate the developer's choices.

2. **CR grouping** -- every intent has a `cr` field, so the orchestrator
   can filter by CR.

3. **Dependency chain tracking** -- the `depends_on` edges in each intent
   allow the orchestrator to compute transitive dependencies:

```python
def get_blocked_crs(rejected_crs, intent_map):
    """Given rejected CRs, find all transitively blocked CRs."""
    rejected_intents = set()
    for intent in intent_map.values():
        if intent['cr'] in rejected_crs:
            rejected_intents.add(intent['id'])

    blocked_crs = set()
    changed = True
    while changed:
        changed = False
        for intent in intent_map.values():
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

The orchestrator updates the intent in intent_graph.yaml and re-runs the Planner.
The Planner re-reads all inputs and regenerates the plan. No special handling
needed -- the Planner always reads from disk.

**Scenario 2: Developer rejects the approach.**
"Don't modify GetBasePremium_Home. Use GetBasePrem_HomeNew instead."

The orchestrator must re-run from the Analyzer (or possibly the Decomposer)
to get new line numbers. The Planner is not involved until the Analyzer produces
an updated intent_graph.yaml.

**Scenario 3: Developer requests additional changes.**
"Also change the $2500 deductible factor."

The orchestrator must re-run from the Intake agent to parse the new CR.
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

### Missing Intents

```
[Planner] ERROR: Expected {N} intents (from intent_graph.yaml)
          but found {M} in the intents list.
          Missing: {list of missing intent IDs}

          The Decomposer/Analyzer may not have completed successfully.
          Check manifest.yaml for decomposer.status.
```

### Invalid Intent Schema

```
[Planner] ERROR: Intent {intent_id} has invalid schema.
          File: analysis/intent_graph.yaml
          Issue: {specific validation failure}

          Expected fields for {capability} intent:
            {list of required fields}

          Missing: {list of missing fields}
```

### Source File Not Found

```
[Planner] ERROR: Source file not found for intent {intent_id}:
          Path: {source_file}

          This file should exist on disk. Either:
            - The file was deleted after the Analyzer ran
            - The path in the intent_graph.yaml is incorrect
          Re-run from /iq-plan to re-analyze.
```

### Hash Mismatch (Stale File)

```
[Planner] ERROR: Source file changed since Analyzer ran!
          File: {filepath}
          Expected hash: {expected}
          Current hash:  {actual}
          Affected intents: {intent_ids}

          Someone modified this file between the Analyzer and Planner runs.
          Re-run from /iq-plan to get fresh analysis.
```

### Cycle Detected

```
[Planner] ERROR: Circular dependency detected!
          Cycle: {cycle_path}

          This should have been caught by the Decomposer.
          Please review the depends_on fields in these intents
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
[Planner] ERROR: Topological sort processed {N} of {M} intents.
          Stuck intents: {list}

          This indicates a hidden cycle in the dependency graph.
          Re-run from the Decomposer to rebuild the dependency graph.
```

---

## NOT YET IMPLEMENTED (Future Enhancements)

- **Interactive plan builder:** Allow the developer to reorder phases or merge
  intents interactively before approving. Currently the Planner generates a
  fixed plan that the developer approves or rejects as-is.

- **Dry-run execution:** Run the Change Engine in dry-run mode to validate that
  all changes CAN be applied before presenting the plan. This would catch issues
  like "function not found at expected line" before Gate 1.

- **Plan diffing:** When the Planner is re-run after a revision, show what changed
  compared to the previous plan. Currently each plan is generated independently.

- **Parallel execution hints:** Currently all same-file intents are sequential.
  Future versions could analyze whether two intents in the same file but in
  different functions could safely execute in parallel (if their line ranges don't
  overlap and neither adds/removes lines).

- **Plan templates:** For common change patterns (e.g., "5% across-the-board rate
  increase"), use a template that pre-fills the plan structure, reducing generation
  time and improving consistency.

<!-- IMPLEMENTATION: Phase 06 -->
