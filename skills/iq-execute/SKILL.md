---
name: iq-execute
description: Execute the approved plan using the capsule pattern. Spawns per-file worker agents with fresh context, coordinated via checkpoint file for crash recovery.
user-invocable: true
---

# Skill: /iq-execute

## 1. Purpose & Trigger

Execute the approved rate change plan. Picks up after /iq-plan has produced an
approved execution plan (state: PLANNED, gate_1: approved) and applies the actual
file modifications: copy Code/ files, update .vbproj references, take snapshots,
and make rate value / logic changes.

**Architecture:** The orchestrator is a **crash-only stateless coordinator**. It
builds operation capsules (self-contained worker briefs), spawns short-lived worker
agents (one per file), and tracks progress via `checkpoint.yaml`. If the orchestrator
loses context or the session is interrupted, it re-reads the checkpoint and resumes
from the next incomplete capsule. No state lives only in memory.

**Trigger:** Slash command `/iq-execute`

**Context switch:** The developer runs /iq-plan, approves at Gate 1, then does
`/clear` and runs `/iq-execute` in a fresh context window. This skill reads ALL
context from workstream files — zero knowledge of what happened during /iq-plan.

---

## 2. Precondition Checks

Execute IN ORDER. If any fails, STOP.

### Check 1: Plugin Installed

Verify `.iq-update/CLAUDE.md` exists. If missing:
```
ERROR: The .iq-update/ plugin is not installed in this folder.
```

### Check 2: Config Exists

Verify `.iq-workstreams/config.yaml` exists. If missing:
```
ERROR: No config.yaml found. Please run /iq-init first.
```

### Check 3: Find Executable Workflow

Scan `.iq-workstreams/changes/` for manifest.yaml where state is PLANNED or
EXECUTING.

- **None found:** STOP with error listing all workflows and their states.
  Suggest /iq-plan (not planned yet), /iq-review (already executed), etc.
- **One found:** Display summary (workflow_id, province, LOBs, date, SRD
  count) and proceed.
- **Multiple found:** Present list, ask developer to choose by number.

### Check 4: Validate Workflow State

Read the selected manifest.yaml fully:

1. **State must be PLANNED or EXECUTING.** Any other state: STOP.
2. **Gate 1 must be approved:** `phase_status.gate_1.status == "approved"`.
   If not: STOP, tell developer to run /iq-plan to approve first.
3. **Required files must exist:**
   - `plan/execution_order.yaml`
   - `analysis/files_to_copy.yaml`
   - `analysis/operations/` (at least one op-*.yaml)
   - `execution/file_hashes.yaml`
   If any missing: STOP, tell developer to run /iq-plan to regenerate.

If all pass, proceed to Section 3.

---

## 3. Checkpoint Rehydration

The orchestrator ALWAYS starts by reading checkpoint state. This makes it
crash-safe — the orchestrator can lose context at any point and resume.

### Step 3.1: Read or Create Checkpoint

Check if `execution/checkpoint.yaml` exists in the workstream directory.

**If checkpoint exists (EXECUTING state — resume):**
```
1. Read execution/checkpoint.yaml
2. RECONCILE DANGLING RESULTS: Check if current_capsule has a result file
   on disk that wasn't acknowledged in the checkpoint (crash between worker
   finish and checkpoint update):
   - If result file exists AND validates: treat capsule as completed,
     update checkpoint, advance to next capsule
   - If result file exists but INVALID: delete it, will re-spawn worker
   - If no result file: normal resume, will spawn worker
3. Identify: total capsules, completed capsules, current capsule, next action
4. Report to developer:
   "Resuming execution. {N} of {M} file groups complete.
    Next: {next_action}"
5. Skip to the appropriate phase (Section 5 for file copy, Section 6 for
   modifications, Section 7 for review)
```

**If no checkpoint (PLANNED state — fresh start):**
```
1. Proceed to Section 4 (Pre-Execution) to build capsules
```

### Step 3.2: Dirty File Detection (on resume only)

For each file in `execution/file_hashes.yaml`, compute current SHA256 and
compare against stored hash.

- **ALL match:** Safe to resume.
- **ANY mismatch:**
  ```
  WARNING: {N} file(s) changed since last execution session:
    {filename}: expected {hash}, got {hash}

  Options:
    1. Show diff between snapshot and current state
    2. Re-hash and continue from current state (RISKY)
    3. Restore from snapshots and retry
    4. Abort execution
  ```

---

## 4. Pre-Execution: Build Capsules

This is where the orchestrator does its heavy work — reading the full execution
plan and building self-contained capsules for each worker. After this section,
the orchestrator NEVER needs to re-read the full plan.

### Step 4.1: Pre-Execution Validation

```
1. Read execution/file_hashes.yaml for baseline hashes
2. Compute current hashes for ALL target files
3. Compare current vs baseline
   - ALL MATCH: safe to proceed
   - ANY DIFFER: warn developer. Options:
     a. Show diff
     b. Update hashes and proceed
     c. Abort, return to /iq-plan
```

### Step 4.2: Group Operations by File

```
1. Read plan/execution_order.yaml (full operation sequence)
2. Read analysis/operations/op-*.yaml for each operation
3. Group operations by target file:
   - file_groups = {}
   - For each op in execution_order:
       file = op.target_file
       file_groups[file].append(op)
   - Operations within each group retain their bottom-to-top order
4. Determine agent type per group:
   - If ALL ops in group use "rate-modifier": agent_type = "rate-modifier"
   - If ALL ops use "logic-modifier": agent_type = "logic-modifier"
   - If MIXED: split into sub-groups by agent type (same file, different capsules)
     Capsule IDs for split groups: "mod-{filename}-rate", "mod-{filename}-logic"
     Ordering: rate capsule BEFORE logic capsule for same file (rate does value
     replacement; logic does line insertions which shift line numbers)

5. **MAX OPERATIONS PER CAPSULE: 20.**
   If a file group has more than 20 operations (e.g., 48 territory Array6 changes),
   split into sub-capsules of at most 20 operations each. Maintain bottom-to-top
   order WITHIN each sub-capsule. Sub-capsules for the same file are chained:
   capsule B waits for capsule A to complete, then re-hashes the file before starting.
   Capsule IDs: "mod-{filename}-part1", "mod-{filename}-part2", etc.

   WHY: A worker with 48 operations + the full file + the spec modules approaches
   context window limits. Splitting at 20 ensures each worker has comfortable headroom
   (~120K of 200K context). The hash-chain between sub-capsules preserves TOCTOU safety.

   Token budget per capsule:
     Spec overhead:  ~35-43K tokens
     VB file:        ~85K tokens (worst case, mod_Common_SKHab)
     20 operations:  ~10K tokens (20 * ~500 tokens per op)
     Conversation:   ~15K tokens
     TOTAL:          ~145-153K tokens -- fits in 200K with headroom
```

### Step 4.2b: Cross-File Dependency Resolution

After grouping operations into capsules, resolve cross-file dependencies to
determine capsule execution order.

```
1. Build capsule dependency graph:
   - For each capsule, collect all depends_on from its operations
   - If any op in capsule B depends on an op in capsule A (different file):
     capsule B depends on capsule A
   - Same-file split capsules: rate capsule always before logic capsule

2. Topological sort:
   - Start with file-copy capsule (always first, no dependencies)
   - Then modifier capsules in topological order:
     a. Shared modules (mod_Common_*) before LOB-specific files
        (LOB files may reference constants/functions defined in shared modules)
     b. Within same dependency level: sort by filename for determinism
   - End with internal-review capsule (always last)

3. If dependency cycle detected: ABORT with error showing the cycle.
   This should never happen -- the Planner should have caught it.

4. Write resolved capsule_order to checkpoint (Step 4.7)
```

**Default ordering when no explicit dependencies exist:**
```
file-copy > shared modules (mod_Common_*) > LOB-specific Code/ files > Option/Liab files > internal-review
```

This matches the natural data flow: shared modules define constants and functions
that LOB-specific and endorsement files reference.

### Step 4.3: Determine Spec Modules Per Capsule

For each file group, determine which progressive spec modules the worker needs.
This is DETERMINISTIC — based on operation fields, not agent intuition.

**Rate modifier dispatch:**

| Condition | Modules to Load |
|-----------|----------------|
| pattern = base_rate_increase | core.md + modules/array6-multiply.md |
| + rounding_resolved = "mixed" (any op in group) | + modules/mixed-rounding.md |
| + has_expressions = true (any op in group) | + modules/expressions.md |
| pattern = factor_table_change OR included_limits | core.md + modules/factor-table.md |
| Any op has edge case flags | + edge-cases.md |

**Logic modifier dispatch:**

| Condition | Modules to Load |
|-----------|----------------|
| pattern = new_coverage_type + constant_name | core.md + modules/constant-insertion.md |
| pattern = new_coverage_type + case_block_type | core.md + modules/case-block-insertion.md |
| target = ResourceID.vb | core.md + modules/dat-constants.md |
| pattern = new_endorsement_flat OR new_liability_option | core.md + modules/new-endorsement-file.md |
| pattern = eligibility_rules | core.md + modules/validation-function.md |
| pattern = alert_message | core.md + modules/alert-message.md |

**Always include:** `dispatch.md` is always loaded (it's only ~100 lines).

### Step 4.3b: Resolve FUBs for Tier 2/3 Capsules

For each file group containing Tier 2 or Tier 3 operations, resolve Function
Understanding Blocks (FUBs) from the Analyzer's operation YAML files. FUBs provide
workers with structural understanding of the target function (branch tree, hazards,
adjacent context) so they can modify code accurately.

**This step is fully automated — no developer interaction.**

```python
def resolve_fubs_for_capsule(operations, workstream_path, all_op_yamls):
    """Resolve FUBs for operations that need enriched context.

    For Tier 1: skip (no FUB needed)
    For Tier 2/3: read FUB from operation YAML (direct `fub:` or resolve `fub_ref:`)
    For Tier 3: also collect peer function bodies and cross-file context

    Args:
        operations: list of operations in this capsule's file group
        workstream_path: path to workstream directory
        all_op_yamls: dict of op_id -> loaded operation YAML

    Returns: dict of op_id -> {fub, canonical_patterns, peer_function_bodies, cross_file_context}

    IMPORTANT: The returned dict is used to INJECT these fields into per-operation
    entries within the capsule YAML. Workers read enriched fields from their
    capsule operation entry, NOT from the Analyzer's op-*.yaml files. The capsule
    builder (Step 4.5) must merge these fields into each operation's capsule entry.
    """
    fub_data = {}

    for op in operations:
        tier = op.get("tier", 2)  # Default to Tier 2 if absent (backward compat)

        if tier == 1:
            continue  # Tier 1: thin capsule, no FUB

        op_id = op["id"]
        op_yaml = all_op_yamls.get(op_id, {})

        # Resolve FUB (direct or via reference)
        fub = op_yaml.get("fub")
        if not fub and op_yaml.get("fub_ref"):
            # Resolve reference: read FUB from the referenced operation
            # NOTE: all_op_yamls must include ALL operations across ALL capsules
            # (loaded from analysis/operations/*.yaml before capsule building)
            ref_op_yaml = all_op_yamls.get(op_yaml["fub_ref"], {})
            fub = ref_op_yaml.get("fub")
            # Apply adjacent_context_override if this op has its own target line
            if fub and op_yaml.get("adjacent_context_override"):
                fub = dict(fub)  # Shallow copy to avoid mutating shared FUB
                fub["adjacent_context"] = op_yaml["adjacent_context_override"]

        # Extract canonical patterns from code_patterns (if present)
        code_patterns = op_yaml.get("code_patterns", {})
        canonical_patterns = []
        for access in code_patterns.get("canonical_access", []):
            canonical_patterns.append({
                "need": access["need"],
                "pattern": access["pattern"],
                "confidence": access["confidence"],
            })

        result = {"fub": fub, "canonical_patterns": canonical_patterns}

        # Tier 3: additional context
        if tier == 3:
            result["peer_function_bodies"] = collect_peer_bodies(
                fub, op_yaml, workstream_path, codebase_root
            )
            result["cross_file_context"] = collect_cross_file_context(
                op_yaml, all_op_yamls
            )

        fub_data[op_id] = result

    return fub_data


def extract_function_lines(file_path, start_line, max_lines=50):
    """Read lines from a VB.NET source file starting at start_line.

    Reads from start_line until End Function/End Sub or max_lines,
    whichever comes first.

    Args:
        file_path: absolute path to the .vb file
        start_line: 1-based line number of the function declaration
        max_lines: maximum number of lines to return

    Returns: list of strings (lines), or [] if file/line not found
    """
    import re
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            all_lines = f.readlines()
    except (FileNotFoundError, PermissionError):
        return []

    if start_line < 1 or start_line > len(all_lines):
        return []

    end_pattern = re.compile(r'^\s*End\s+(Sub|Function)', re.IGNORECASE)
    result = []
    for i in range(start_line - 1, min(start_line - 1 + max_lines, len(all_lines))):
        line = all_lines[i].rstrip("\n\r")
        result.append(line)
        if end_pattern.match(line) and i > start_line - 1:
            break  # Found End Sub/Function

    return result


def collect_peer_bodies(fub, op_yaml, workstream_path, codebase_root):
    """Collect peer function bodies for Tier 3 capsules.

    Reads up to 3 peer functions (max 50 lines each) from source files,
    sorted by call_sites (highest first). Only includes ACTIVE/HIGH_USE peers.

    Sources checked (in order):
    1. fub["nearby_functions"] — lightweight entries from Analyzer Step 5.10.5
    2. code_patterns["peer_functions"] — richer entries from Analyzer Step 5.9
       (FALLBACK when nearby_functions is empty, which happens when Step 5.9 ran
       and set canonical_patterns_ref instead of populating nearby_functions)

    Args:
        fub: the Function Understanding Block (or None)
        op_yaml: the full operation YAML from the Analyzer
        workstream_path: path to workstream directory
        codebase_root: absolute path to carrier root (from manifest.yaml)

    Returns: list of {name, call_sites, body}
    """
    peers = []
    target_file = fub.get("file") if fub else op_yaml.get("source_file", op_yaml.get("target_file"))

    # Source 1: FUB nearby_functions
    candidates = []
    if fub and fub.get("nearby_functions"):
        candidates = [
            nf for nf in fub["nearby_functions"]
            if nf.get("status") != "DEAD" and nf.get("call_sites", 0) > 0
        ]

    # Source 2: code_patterns peer_functions (fallback)
    if not candidates:
        code_patterns = op_yaml.get("code_patterns", {})
        for peer in code_patterns.get("peer_functions", []):
            if not peer.get("dead_code", False) and peer.get("call_sites", 0) > 0:
                candidates.append({
                    "name": peer["name"],
                    "call_sites": peer.get("call_sites", 0),
                    "status": "HIGH_USE" if peer.get("call_sites", 0) >= 3 else "ACTIVE",
                    "line_start": peer.get("line_start", 0),
                })

    candidates.sort(key=lambda x: x.get("call_sites", 0), reverse=True)

    for nf in candidates[:3]:  # Max 3 peers
        full_path = os.path.join(codebase_root, target_file)
        body_lines = extract_function_lines(full_path, nf.get("line_start", 0), max_lines=50)
        if body_lines:
            peers.append({
                "name": nf["name"],
                "call_sites": nf.get("call_sites", 0),
                "body": "\n".join(body_lines),
            })

    return peers


def collect_cross_file_context(op_yaml, all_op_yamls):
    """Collect cross-file dependency context for Tier 3 capsules.

    For operations with depends_on pointing to a different file, include
    the dependent operation's FUB summary.

    Returns: list of {dep_op, dep_summary}
    """
    cross_ctx = []
    target_file = op_yaml.get("target_file")

    for dep_id in op_yaml.get("depends_on", []):
        dep_yaml = all_op_yamls.get(dep_id, {})
        if dep_yaml.get("target_file") != target_file:
            cross_ctx.append({
                "dep_op": dep_id,
                "dep_summary": dep_yaml.get("title", f"Operation {dep_id}"),
            })

    return cross_ctx
```

**Capsule injection protocol:** After `resolve_fubs_for_capsule` returns, the capsule
builder (Step 4.5) MUST merge the resolved fields into each operation's entry within
the capsule YAML:

```python
# In Step 4.5, when building each capsule's operations list:
for op_entry in capsule["operations"]:
    enrichment = fub_data.get(op_entry["id"])
    if enrichment:
        op_entry["fub"] = enrichment["fub"]
        op_entry["canonical_patterns"] = enrichment["canonical_patterns"]
        if enrichment.get("peer_function_bodies"):
            op_entry["peer_function_bodies"] = enrichment["peer_function_bodies"]
        if enrichment.get("cross_file_context"):
            op_entry["cross_file_context"] = enrichment["cross_file_context"]
```

This ensures workers read ALL enriched fields from the capsule operation entry —
they never need to look outside their capsule for FUB/peer/cross-file data.

**Backward compatibility:** If `tier` is absent from operation YAML (pre-enhancement
planner output), the capsule builder defaults to Tier 2. If `fub` is absent, the
capsule is built without FUB data (equivalent to current behavior).

### Step 4.4: Build File Copy Capsule

If `analysis/files_to_copy.yaml` has entries, create a file-copy capsule:

```yaml
# execution/capsules/capsule-file-copy.yaml
capsule_id: "file-copy"
capsule_type: "file-copy"
phase: "file_copy"
files_to_copy:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "{from file_hashes.yaml}"
  # ... one per file
vbproj_updates:
  - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
    old_ref: "mod_Common_SKHab20250901.vb"
    new_ref: "mod_Common_SKHab20260101.vb"
  # ... one per vbproj per file
shared_modules:
  - file: "mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
output_file: "execution/results/result-file-copy.yaml"
```

### Step 4.5: Build Modifier Capsules (Tiered)

For each file group from Step 4.2, build a capsule with context depth matching the
highest tier among its operations. FUB data comes from Step 4.3b.

**Token budget by tier:**

| Tier | Capsule Overhead | When |
|------|-----------------|------|
| 1 | ~300 tokens | Simple rate changes, constant insertions |
| 2 | ~1,700 tokens | Logic changes with known patterns |
| 3 | ~5,000 tokens | Novel logic, cross-file, unconfirmed targets |

#### Tier 1 Capsule (identical to current format — no FUB, no extra context)

```yaml
# execution/capsules/capsule-{sanitized-filename}.yaml
capsule_id: "mod-{sanitized-filename}"
capsule_type: "modifier"
phase: "modifications"
agent_type: "rate-modifier"                    # or "logic-modifier"
spec_modules:                                  # from Step 4.3
  - "rate-modifier/core.md"
  - "rate-modifier/dispatch.md"
  - "rate-modifier/modules/array6-multiply.md"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_hash: "{current hash from file_hashes.yaml}"
depends_on_capsules: []                          # capsule IDs that must complete first
load_edge_cases: false                           # true if any op has sentinel/-999/edge flags
config_snapshot:                                 # carrier-specific safety constraints
  carrier_prefix: "PORT"
  cross_province_shared_files:                   # files worker must NEVER modify
    - "Code/PORTCommonHeat.vb"
operations:
  - id: "op-002-01"
    op_file: "analysis/operations/op-002-01.yaml"
    pattern: "base_rate_increase"
    function: "GetBasePremium_Home"
    anchor: "Case 1 : varRates = Array6(512.59, 28.73"
    summary: "Multiply base rates by 1.05, banker round"
    tier: 1
  - id: "op-002-02"
    op_file: "analysis/operations/op-002-02.yaml"
    pattern: "base_rate_increase"
    function: "GetBasePremium_Home"
    anchor: "Case 2 : varRates = Array6(489.22"
    summary: "Multiply base rates by 1.05, banker round"
    tier: 1
  # ... operations in bottom-to-top order
output_file: "execution/results/result-{capsule-id}.yaml"
success_criteria:
  - "All operations applied"
  - "Array6 arg counts unchanged"
  - "File hash updated in output"
```

#### Tier 2 Capsule (adds FUB + canonical patterns from code_patterns)

```yaml
capsule_id: "mod-{sanitized-filename}"
capsule_type: "modifier"
phase: "modifications"
agent_type: "logic-modifier"
spec_modules:
  - "logic-modifier/core.md"
  - "logic-modifier/dispatch.md"
  - "logic-modifier/modules/case-block-insertion.md"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_hash: "{current hash from file_hashes.yaml}"
depends_on_capsules: []
load_edge_cases: false
config_snapshot:
  carrier_prefix: "PORT"
  cross_province_shared_files:
    - "Code/PORTCommonHeat.vb"
operations:
  - id: "op-003-02"
    op_file: "analysis/operations/op-003-02.yaml"
    pattern: "new_coverage_type"
    function: "GetRateTableID"
    anchor: "Inside: Select Case strCoverageType"
    summary: "Add Elite Comp Case block"
    tier: 2
    fub:                                        # From Analyzer Step 5.10 (via Step 4.3b)
      function: "GetRateTableID"
      file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      line_start: 405
      line_end: 486
      total_lines: 81
      param_types:
        - {name: "strCoverageType", type: "String"}
      return_type: "Integer"
      branch_tree:
        - type: "Select Case"
          variable: "strCoverageType"
          line: 410
          depth: 1
          branches:
            - case: "\"STANDARD\""
              line: 411
              leaf: "assignment statement"
            - case: "\"PREFERRED\""
              line: 413
              leaf: "assignment statement"
            # ...
      hazards: ["nested_depth_3plus"]
      adjacent_context:
        above: [{line: 438, content: "            Case \"COMPREHENSIVE\""}]
        below: [{line: 440, content: "            Case Else"}]
      canonical_patterns_ref: "code_patterns"
      nearby_functions:
        - {name: "GetCoverageTypeID", call_sites: 8, status: "HIGH_USE", line_start: 350}
    canonical_patterns:                         # From code_patterns (via Step 4.3b)
      - need: "rate_table_routing"
        pattern: "Select Case strCoverageType -> intRateTableID = {N}"
        confidence: "high"
output_file: "execution/results/result-{capsule-id}.yaml"
success_criteria:
  - "All operations applied"
  - "Generated code compiles structurally"
  - "File hash updated in output"
```

#### Tier 3 Capsule (adds peer function bodies + cross-file context)

```yaml
# Same base as Tier 2, plus:
operations:
  - id: "op-006-01"
    op_file: "analysis/operations/op-006-01.yaml"
    pattern: "UNKNOWN"
    function: "GetLiabilityBundlePremiums"
    anchor: "Inside: Select Case strCoverageType"
    summary: "Add new coverage type premium calculation"
    tier: 3
    fub: { ... }                                # Same as Tier 2
    canonical_patterns: [...]                   # Same as Tier 2
    peer_function_bodies:                       # Tier 3 only (via Step 4.3b)
      - name: "GetLiabilityExtensionPremiums"
        call_sites: 12
        body: |
          Public Function GetLiabilityExtensionPremiums(ByVal covItem As ICoverageItem, ...) As Short
              Dim varRates As Object
              Select Case strCoverageType
                  Case "STANDARD"
                      Select Case territory
                          Case 1 : varRates = Array6(78, 106, 161, 189, 216, 291)
                          ...
                      End Select
                  Case Else
                      ...
              End Select
          End Function
    cross_file_context:                         # Tier 3 with cross-file deps (via Step 4.3b)
      - dep_op: "op-003-01"
        dep_summary: "Adds ELITECOMP constant at line 23"
```

#### Worker Prompt Enhancement

When spawning a worker agent for a Tier 2 or Tier 3 capsule, append these
instructions to the worker prompt (in addition to the standard spec module content):

```
--- FUNCTION UNDERSTANDING BLOCK ---

Before modifying the target function, READ the FUB provided in the capsule:

1. READ `branch_tree` to understand the function's nesting structure.
   Know WHERE Select Case blocks, If/ElseIf branches exist BEFORE editing.

2. USE `adjacent_context` to validate that the insertion/anchor point hasn't
   drifted. If adjacent lines don't match, ABORT — the file may have changed.

3. CHECK `hazards` before applying changes:
   - "mixed_rounding": resolve rounding PER LINE, not per function
   - "dual_use_array6": only modify `varRates = Array6(...)`, NEVER
     `IsItemInArray(Array6(...))`
   - "dead_code_nearby": avoid copying patterns from functions with
     call_sites == 0 (check `nearby_functions`)
   - "nested_depth_3plus": count actual spaces from adjacent_context,
     do NOT assume 4-space nesting at deep levels
   - "arithmetic_expressions": if Array6 arg is `30 + 10`, multiply
     the evaluated value `40 * factor` and write `41.2`, NOT
     `(30 + 10) * 1.03` — keep the result as a simple literal
   - "const_rate_values": rate values are in `Const` declarations
     (e.g., `Const ACCIDENTBASE = 200`), NOT inline Array6 calls.
     Modify the Const value, not an Array6 line
   - "multi_line_array6": Array6 call spans multiple lines with
     ` _` line continuation. Treat all continuation lines as a
     single logical Array6 — preserve the ` _` continuations and
     match the same line-break structure in the output

4. For Tier 3 capsules with `peer_function_bodies`:
   - Read ALL peer bodies BEFORE writing any code
   - Copy structure from the peer with the HIGHEST call_sites
   - Match indentation, variable naming, comment style from peers
   - If inserting a new Case block, model it after the same Case structure
     in the peer with most call_sites

5. For Tier 3 capsules with `cross_file_context`:
   - Verify that cross-file dependencies have already been applied
   - Reference the dependency's summary to understand what was added

6. If `branch_tree_warnings` is present, the tree may be unreliable —
   rely more on `adjacent_context` and less on branch_tree structure.

--- WORKED EXAMPLE: Using FUB for Case Block Insertion ---

Given capsule operation with FUB:
  function: "GetRateTableID"
  branch_tree:
    - type: "Select Case"
      variable: "strCoverageType"
      line: 410, depth: 1
      branches:
        - case: "STANDARD", line: 411, leaf: "assignment statement"
        - case: "PREFERRED", line: 413, leaf: "assignment statement"
        - case: "COMPREHENSIVE", line: 438, leaf: "assignment statement"
        - case: "Else", line: 440, leaf: "assignment statement"
  adjacent_context:
    above: [{line: 438, content: "            Case \"COMPREHENSIVE\""}]
    below: [{line: 440, content: "            Case Else"}]

Task: Insert Case "ELITECOMP" block.

Worker reasoning:
  1. branch_tree shows Select Case on strCoverageType at depth 1
     with 3 named Cases + Case Else
  2. New Case goes BEFORE Case Else (line 440), AFTER last named
     Case "COMPREHENSIVE" (line 438)
  3. adjacent_context confirms: line 438 has "COMPREHENSIVE",
     line 440 has "Case Else" — file has NOT shifted since analysis
  4. Measure indent from adjacent: "            Case" = 12 spaces
  5. Generate new lines with 12-space indent:
       + '            Case "ELITECOMP"'
       + '                intRateTableID = 99'
  6. Insert AFTER the COMPREHENSIVE Case block body, BEFORE Case Else

This example shows the complete reasoning chain. Workers should follow
this pattern: READ tree → VALIDATE adjacent → MEASURE indent → GENERATE.
```

### Step 4.6: Build Review Capsule

```yaml
# execution/capsules/capsule-internal-review.yaml
capsule_id: "internal-review"
capsule_type: "internal-review"
phase: "internal_review"
modifier_results:                              # populated after modifiers complete
  - "execution/results/result-mod-*.yaml"
snapshot_dir: "execution/snapshots/"
output_file: "execution/results/result-internal-review.yaml"
```

### Step 4.7: Write Initial Checkpoint

```yaml
# execution/checkpoint.yaml
run_id: "exec-{workstream-name}-{timestamp}"
workstream: "{workstream-name}"
phase: "file_copy"                             # file_copy | modifications | internal_review | completed
capsule_order:
  - "file-copy"                                # always first (if files to copy)
  - "mod-mod_Common_SKHab20260101"             # grouped by file
  - "mod-CalcOption_SKHome20260101"
  - "mod-Option_EliteComp_NB20260701"
  - "internal-review"                          # always last
completed: []
current_capsule: "file-copy"
current_status: "prepared"                     # prepared | spawned | completed | failed
next_action: "spawn file-copy worker"
retry_count: 0
updated_at: "{timestamp}"
```

### Step 4.8: Update Manifest

```yaml
state: "EXECUTING"
updated_at: "{now}"
phase_status:
  file_copy: {status: "pending"}
  modifications: {status: "pending"}
  internal_review: {status: "pending"}
```

Tell developer:
```
EXECUTING: {Province} {LOB(s)} {effective_date}
============================================================
Workflow:    {workflow_id}
Operations:  {N} across {M} file(s)
Capsules:    {K} worker agents will be spawned
============================================================
```

---

## 5. Phase 1: File Copy

### Step 5.1: Read Checkpoint (Crash-Safe Entry)

```
RULE: Re-read execution/checkpoint.yaml BEFORE every action.
```

If checkpoint shows file-copy already completed: skip to Section 6.

### Step 5.2: Spawn File-Copy Worker

Read `execution/capsules/capsule-file-copy.yaml`.

**Worker prompt:**
```
You are the file-copy worker for the IQ Rate Update Plugin.

CARRIER ROOT: {root_path}
WORKSTREAM: .iq-workstreams/changes/{workstream-name}/

TASK: Copy Code/ files to new dated versions and update .vbproj references.

READ YOUR CAPSULE: .iq-workstreams/changes/{workstream-name}/execution/capsules/capsule-file-copy.yaml
It contains the exact list of files to copy and .vbproj references to update.

RULES:
  - If target exists and hash matches source: SKIP (log as skipped)
  - If target exists with different hash: FLAG in output as "conflict"
  - If target not exists: cp "{source}" "{target}"
  - For each .vbproj update: find <Compile Include> with old filename,
    replace with new filename. Preserve exact XML structure.
  - Shared modules (listed in capsule): copy ONCE, update ALL .vbproj files
  - Process shared modules FIRST, then LOB-specific files
  - NEVER modify file content — only copy and rename
  - NEVER modify old dated files

OUTPUT: Write results using ATOMIC WRITE PROTOCOL:
  1. Write to {output_file}.tmp
  2. Validate YAML is parseable
  3. Rename {output_file}.tmp -> {output_file}

Use this exact schema:
  capsule_id: "file-copy"
  status: "completed"        # or "partial" or "failed"
  files_copied: [{source, target, hash_after}]
  files_skipped: [{source, target, reason}]
  vbproj_updated: [{vbproj, old_ref, new_ref}]
  conflicts: []              # any unexpected states
  hashes: {filepath: hash}   # all new/updated file hashes
  errors: []                 # structured: [{code, message, file}]

ALSO READ: .iq-workstreams/config.yaml (for carrier_prefix)

IMPORTANT: Do NOT update manifest.yaml or checkpoint.yaml — the orchestrator handles that.
```

Spawn via Agent tool:
```
Agent(name: "file-copy-worker", subagent_type: "general-purpose", prompt: <above>)
```

### Step 5.3: Process Result

```
1. Read execution/results/result-file-copy.yaml
2. If status == "completed":
   - Update file_hashes.yaml with new hashes from result
   - Update checkpoint: completed += ["file-copy"], current_capsule = first modifier
   - Update manifest: phase_status.file_copy -> completed
   - Report: "{N} file(s) copied, {N} .vbproj updated, {N} skipped"
3. If status == "partial" or "failed":
   - Show conflicts/errors to developer
   - Options: retry, skip (warn ops will fail), abort
   - On retry: update checkpoint retry_count, re-spawn worker
   - On abort: leave state EXECUTING, tell developer to investigate
```

---

## 6. Phase 2: Modifications (The Core Loop)

This is the critical section. The orchestrator loops through modifier capsules,
spawning one worker per file. Each worker gets a fresh context.

### Step 6.0: Crash-Safe Loop Protocol

```
RULE: Re-read checkpoint.yaml at the START of every iteration.
RULE: Update checkpoint.yaml AFTER every worker completes, BEFORE spawning next.
RULE: After 5 capsules OR 20 tool calls, suggest context refresh:
      "Checkpoint saved at capsule {N}/{M}. If context feels heavy,
       you can /clear and run /iq-execute again — it resumes from here."
```

### Step 6.1: For Each Modifier Capsule

```
1. Re-read execution/checkpoint.yaml
2. Find next incomplete modifier capsule from capsule_order
3. If none remaining: proceed to Section 7
4. Read the capsule YAML from execution/capsules/
5. RECONCILE: Check if result file already exists for this capsule
   (crash recovery -- worker finished but orchestrator didn't update checkpoint)
   - If result exists AND validates (YAML parseable, status field present):
     Treat as completed. Skip to step 7 (update checkpoint). Log:
     "Reconciled existing result for {capsule_id} (likely crash recovery)"
   - If result exists but INVALID (truncated, unparseable):
     Delete the corrupt result file. Continue to step 6.
6. HASH REFRESH: Re-read execution/file_hashes.yaml.
   If capsule's file_hash differs from current hash in file_hashes.yaml:
   - This is EXPECTED for same-file multi-capsule scenarios (prior capsule
     modified the file). Update the capsule's file_hash to the current value.
   - Write updated capsule YAML to disk before spawning.
   - Log: "Hash refreshed for {capsule_id} (chained from prior capsule)"
7. Spawn worker (see Step 6.2)
8. Read result (see Step 6.3)
9. Update checkpoint (see Step 6.4)
10. Report progress: "[{N}/{M}] {filename} ... {status}"
11. Loop
```

**Hash chaining for same-file multi-capsule:** When the same file has multiple
capsules (e.g., split by agent type), capsule N modifies the file and updates
`file_hashes.yaml`. Capsule N+1's original hash is now stale. Step 6 refreshes
it from the authoritative `file_hashes.yaml` before spawning. This prevents
false TOCTOU failures.

### Step 6.2: Spawn Modifier Worker

Read the capsule to get agent_type and spec_modules. Build the worker prompt:

**Worker prompt template:**
```
You are a {agent_type} worker for the IQ Rate Update Plugin.

CARRIER ROOT: {root_path}
WORKSTREAM: .iq-workstreams/changes/{workstream-name}/

YOUR CAPSULE: {capsule_file_path}
Read it first — it contains your file, operations, and success criteria.

YOUR INSTRUCTIONS (read in this order):
  1. .iq-update/agents/{agent_type}/core.md         (universal rules)
  2. .iq-update/agents/{agent_type}/dispatch.md      (routing reference)
{for each module in spec_modules:}
  3. .iq-update/agents/{agent_type}/{module}          (operation-specific rules)

EXECUTION PROTOCOL:
  1. Read your capsule for the target file, operations list, and config_snapshot
  2. Read the actual op-*.yaml files listed in the capsule for full details
  3. SAFETY CHECK: Verify target file is NOT in config_snapshot.cross_province_shared_files
  4. Take a SNAPSHOT of the target file (if not already in snapshots/)
  5. TOCTOU CHECK: hash the file, compare against capsule's file_hash.
     If mismatch: STOP, write status "toctou_failure" to output, EXIT.
  6. For each operation (in capsule order — already bottom-to-top):
     a. Locate function by name (content-authoritative, line numbers are hints)
     b. Validate current values match op-*.yaml expected values
     c. Apply the change per your module instructions
     d. Verify the change was applied correctly
  7. After all operations: compute new file hash
  8. Write structured results using ATOMIC WRITE PROTOCOL:
     a. Write to {output_file}.tmp
     b. Validate the YAML is parseable
     c. Rename {output_file}.tmp -> {output_file}
     This prevents partial/corrupt results if the session is interrupted.

OUTPUT SCHEMA:
  capsule_id: "{id}"
  status: "completed"              # completed | partial | failed | toctou_failure
  target_file: "{relative path}"   # explicit file path for audit trail
  file_hash_before: "{hash}"       # hash at start of work (from capsule)
  file_hash_after: "{new_hash}"    # hash after modifications
  operations:
    - op_id: "{id}"
      status: "applied"            # applied | skipped | failed
      change_type: "{rate_value | factor | limit | logic_insert}"
      function: "{function_name}"
      before: "{original line or null}"
      after: "{modified line or null}"
      line_number: {N}
      values_changed: {N}          # count of numeric values changed (rate ops)
      lines_added: {N}             # count of lines inserted (logic ops)
      notes: ""
  errors: []                       # structured error objects (see below)
  warnings: []
  next_actor: "orchestrator"
  next_action: "read result, update checkpoint, proceed to next capsule"

ERROR OBJECT SCHEMA (for failed/toctou operations):
  errors:
    - code: "TOCTOU_FAILURE"       # TOCTOU_FAILURE | CONTENT_MISMATCH | PARSE_ERROR | ...
      message: "File hash mismatch"
      expected: "{expected_hash}"
      actual: "{actual_hash}"
      op_id: "{id or null}"       # null for file-level errors

ALSO READ: config_snapshot in your capsule (for cross-province safety checks)

RULES:
  - Do NOT update manifest.yaml or checkpoint.yaml
  - Do NOT read other capsules or results — stay in your lane
  - NEVER modify files listed in config_snapshot.cross_province_shared_files
  - If you encounter an edge case not covered by your loaded modules,
    read .iq-update/agents/{agent_type}/edge-cases.md for guidance
  - Self-correction: 1 retry per operation (restore from snapshot, re-locate)
  - If retry fails: mark operation "failed", continue with remaining ops
  - ALWAYS use atomic write for results (write .tmp, validate, rename)
  - ATOMIC ROLLBACK: If ANY Edit tool call within an operation fails (e.g.,
    old_string not found, non-unique match), IMMEDIATELY restore the file from
    its snapshot BEFORE attempting the next operation. Do NOT leave partial edits
    on disk. The Edit tool writes to disk on each call — edits 1-2 succeed but
    edit 3 fails means the file has been partially modified. Snapshot restoration
    undoes ALL edits for that operation, returning to a clean state.
  - EDIT TOOL DISAMBIGUATION: When a target line's content is not unique within
    the file (context_above/context_below provided in target_lines), construct
    the old_string as a MULTI-LINE string including the context line(s) above
    and/or below. This ensures Edit tool uniqueness. Example:
      old_string = context_above[0].content + "\n" + target_line.content
    Only the target line portion changes in new_string; context lines repeat verbatim.
```

Spawn via Agent tool:
```
Agent(name: "worker-{capsule_id}", subagent_type: "general-purpose", prompt: <above>)
```

### Step 6.3: Process Worker Result

```
1. Read the result file at the path specified in the capsule
   - If file does not exist: worker crashed before writing. Treat as "failed".
   - If file exists but is unparseable YAML: treat as "failed", delete corrupt file.
   - Validate required fields: capsule_id, status, target_file

2. Check status:
   - "completed": all ops applied successfully
   - "partial": some ops applied, some failed
   - "failed": worker could not complete
   - "toctou_failure": file changed since plan — CRITICAL

3. For completed/partial:
   - Update execution/file_hashes.yaml with file_hash_after from result
   - Transform worker result into operations_log.yaml format:
     For each op in result.operations:
       Map to the rich schema expected by /iq-review (see agent core.md Output Schema):
       - Copy: op_id -> operation, status, target_file -> file
       - Copy: function, before, after, line_number -> changes[].line
       - Add: description from op-*.yaml context field
       - Add: summary.lines_changed, values_changed, change_range
     Append the transformed entries to execution/operations_log.yaml
   - Update SRD operation statuses in manifest
   - ATOMIC CHECKPOINT UPDATE:
     a. Write checkpoint to execution/checkpoint.yaml.tmp
     b. Validate YAML parseable
     c. Rename checkpoint.yaml.tmp -> checkpoint.yaml
     This prevents corrupt checkpoint if session interrupted during write.

4. For failed:
   - Read errors[] from result for structured diagnostics
   - Show errors to developer with context
   - Options: retry (re-spawn worker), skip file, abort
   - On retry: increment retry_count in checkpoint, re-spawn
   - Max 2 retries per capsule. After that, escalate to developer.

5. For toctou_failure:
   - CRITICAL: file changed externally since plan approval
   - Show expected vs actual hash from errors[]
   - Options: show diff, re-hash and retry, restore from snapshot, abort
   - On abort: leave state EXECUTING with error in manifest
```

**Result-to-operations_log mapping:** The worker result schema is lean (optimized for
worker context), while `/iq-review` expects the rich operations_log format defined in
the agent core.md files. The orchestrator bridges this gap during Step 6.3 by reading
the original op-*.yaml files for context fields and building the full log entries.

### Step 6.4: Update Checkpoint After Each Worker

```yaml
# Updated checkpoint after each worker completes
completed:
  - "file-copy"
  - "mod-mod_Common_SKHab20260101"            # just completed
current_capsule: "mod-CalcOption_SKHome20260101"  # next up
current_status: "prepared"
next_action: "spawn modifier worker for CalcOption_SKHome20260101"
retry_count: 0
updated_at: "{now}"
```

### Step 6.5: All Modifiers Complete

When all modifier capsules are completed:
```yaml
phase: "internal_review"
phase_status.modifications: {status: "completed", summary: "{N} ops, {M} files"}
```

Report:
```
Modifications complete: {N} operations applied across {M} files.
Running internal review...
```

---

## 7. Phase 3: Internal Review

### Step 7.1: Spawn Review Worker

Read `execution/capsules/capsule-internal-review.yaml`. Update it with the
actual list of modifier result files (now known).

**Worker prompt:**
```
You are the execution-reviewer worker for the IQ Rate Update Plugin.

CARRIER ROOT: {root_path}
WORKSTREAM: .iq-workstreams/changes/{workstream-name}/

TASK: Review each change made by modifier workers and validate correctness.

READ:
  - execution/results/result-mod-*.yaml (all modifier results)
  - execution/snapshots/*.snapshot (pre-edit baselines)
  - analysis/operations/op-*.yaml (expected changes)
  - execution/file_hashes.yaml (current hash state)
  - All modified source files on disk

VALIDATION CHECKS (per operation):
  1. Array6 syntax: matching parens, arg count unchanged, no empty args
  2. No commented code modified: lines starting with ' unchanged
  3. No old file modification: only target-date files edited
  4. Value correctness: actual matches expected from op-*.yaml
  5. Context integrity: 5 lines above/below unchanged vs snapshot
  6. .vbproj references: old ref gone, new ref present, XML well-formed

SELF-CORRECTION:
  If you find a fixable issue (wrong value, extra whitespace):
  1. Fix it directly using Edit tool
  2. Log as "self_correction" in your output
  3. Update the file hash
  Max 1 self-correction per operation. If not fixable: mark "review_failed".

OUTPUT: Write to execution/results/result-internal-review.yaml
  capsule_id: "internal-review"
  status: "completed"            # completed | issues_found
  checks_passed: {N}
  checks_failed: {N}
  self_corrections: [{op_id, issue, fix}]
  persistent_issues: [{op_id, issue, severity}]
  files_verified: [{file, hash_matches: true/false}]

IMPORTANT: Do NOT update manifest.yaml or checkpoint.yaml.
```

### Step 7.2: Process Review Result

```
1. Read execution/results/result-internal-review.yaml
2. If status == "completed" and checks_failed == 0:
   - Proceed to Section 8 (Completion)
3. If persistent_issues exist:
   - Show to developer:
     "Internal review found {N} issue(s) that could not be auto-fixed:
       {op-id}: {issue}
     Options: show file, re-run modifier for this op, skip, abort"
   - On re-run: rebuild capsule for just that file, re-spawn modifier worker
   - Max 2 rework cycles. After that: show all issues and let developer decide.
```

---

## 8. Completion (State: EXECUTED)

### Step 8.1: Final Checkpoint

```yaml
phase: "completed"
completed: [... all capsules ...]
current_capsule: null
next_action: "none — execution complete"
```

### Step 8.2: Update Manifest

```yaml
state: "EXECUTED"
updated_at: "{now}"
phase_status:
  file_copy: {status: "completed", summary: "{N} files copied, {N} .vbproj updated"}
  modifications: {status: "completed", summary: "{N} ops completed, {N} failed"}
  internal_review: {status: "completed", summary: "All checks passed"}
```

### Step 8.3: Present Summary

```
===========================================================================
 EXECUTION COMPLETE: {Province} {LOB(s)} {effective_date}
===========================================================================

 {N} file(s) copied (new dated versions)
 {N} .vbproj reference(s) updated
 {N} operation(s) applied
 {N} value(s) changed

 Internal review: {PASS / {N} self-corrections applied}

---------------------------------------------------------------------------
 Files Modified
---------------------------------------------------------------------------
 {filepath} {(shared across {N} LOBs) if applicable}

---------------------------------------------------------------------------
 Files Created (new Code/ copies)
---------------------------------------------------------------------------
 {new_filepath} (from {old_filepath})

---------------------------------------------------------------------------
 Next Steps
---------------------------------------------------------------------------
 Developer can /clear and run /iq-review for final validation,
 diff report, and traceability matrix.

===========================================================================
```

---

## 9. Error Recovery

### TOCTOU Failure

File hash mismatch when worker attempts to edit.
- Worker writes `toctou_failure` status and EXITS immediately.
- Orchestrator shows expected vs actual hash.
- Options: show diff, re-hash and retry, restore from snapshot, abort.

### Worker Timeout / Crash

Agent tool does not return or returns an error.
- Update checkpoint: current_status = "failed"
- Options: retry (re-spawn from same capsule), skip file, abort.
- On retry: capsule is self-contained, so re-spawn is idempotent.

### Content Not Found

Worker cannot locate function/anchor in the file.
- Worker marks operation "failed" in result, continues with others.
- Orchestrator shows failed ops. Options: re-plan, skip, manual fix.

### Session Interrupted

On next `/iq-execute`:
1. Check 3 finds state: EXECUTING
2. Section 3 reads checkpoint.yaml
3. Identifies completed capsules and next action
4. Resumes from next incomplete capsule

This works because:
- Capsules are self-contained (don't depend on orchestrator memory)
- Results are on disk (not in context)
- Checkpoint tracks exact progress

### Complete Rollback

When developer chooses abort + restore:
```
1. Restore all files from execution/snapshots/
2. Delete new Code/ files created by file-copier
3. Revert .vbproj changes from snapshots
4. Set state -> PLANNED, phase statuses -> rolled_back
5. Delete execution/checkpoint.yaml and execution/capsules/
6. Report: "All files restored. Run /iq-execute to try again,
   or /iq-plan to revise the plan."
```

---

## 10. Conversational Action Mapping

During execution, the developer's action space is minimal. The orchestrator
runs autonomously between errors.

### Action Table

| Category | Phrases | Action | State Change? |
|----------|---------|--------|:------------:|
| STATUS | "status", "progress", "where are we?" | Re-read checkpoint, show capsule progress | NO |
| INVESTIGATE | "show me {file}", "show diff" | Display info, no state change | NO |
| ABORT | "abort", "stop", "cancel", "roll back" | Offer rollback options (Sec 9) | YES (if confirmed) |
| SKIP | "skip", "skip {op-id}", "move on" | Skip failed operation/capsule, continue | YES (marks SKIPPED) |
| RETRY | "retry", "try again" | Re-spawn current capsule worker | NO |
| FIX | "the value should be {X}" | Rebuild capsule with correction, re-spawn | NO |

### Priority

1. ABORT  2. FIX  3. SKIP  4. RETRY  5. INVESTIGATE  6. STATUS

### Autonomous Operation

Between errors, the orchestrator does NOT prompt. It spawns workers, reads
results, updates checkpoints, and reports progress until completion or error.

---

## 11. Implementation Notes

### File Hashes
```bash
python -c "import hashlib; print(hashlib.sha256(open(r'{path}','rb').read()).hexdigest())"
```

### Copying Files
```bash
cp "{source}" "{target}"
```

### Updating .vbproj References

Use Edit tool to replace old `<Compile Include>` path with new. Backslash
paths: `..\..\Code\{old_filename}` -> `..\..\Code\{new_filename}`.
Use `replace_all` if multiple references exist.

### Snapshots
```bash
# Create (only if not exists):
ls "{workstream}/execution/snapshots/{filename}.snapshot" 2>/dev/null || \
  cp "{target}" "{workstream}/execution/snapshots/{filename}.snapshot"
# Restore:
cp "{workstream}/execution/snapshots/{filename}.snapshot" "{original_path}"
```

### Timestamps
```bash
python -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))"
```

### YAML Validation
```bash
python -c "import yaml; yaml.safe_load(open(r'{path}')); print('YAML OK')"
```

### Creating Capsule Directory
```bash
mkdir -p ".iq-workstreams/changes/{workstream-name}/execution/capsules"
mkdir -p ".iq-workstreams/changes/{workstream-name}/execution/results"
```

### Context Budget Per Worker

Target: under 2,500 lines of context per worker agent.

| Component | Lines |
|-----------|-------|
| CLAUDE.md (auto-loaded) | ~200 |
| Worker prompt | ~80 |
| Agent core.md | ~400 |
| Agent dispatch.md | ~100 |
| Module card(s) | ~150-300 |
| Capsule YAML | ~80 |
| Op-*.yaml files (2-6 ops) | ~200-500 |
| VB.NET source file | ~500-2,000 |
| **Total** | **~1,700-3,600** |

Worst case (large VB.NET file + multiple modules) stays under context limits.
Tool call history within one worker is minimal (read capsule, read file,
edit file, write result — ~4-8 tool calls).

### Parallel Operations

- Same file: ALWAYS sequential, bottom-to-top (guaranteed by capsule grouping)
- Different files: sequential by default (simpler, easier to debug)
- **Parallel mode is DISABLED** until .vbproj shared-write conflicts are resolved.
  Multiple logic-modifier workers can converge on the same .vbproj when creating
  new files (Option_*.vb, Liab_*.vb). Sequential execution prevents this race.
- Future: parallel may be safe for pure rate-modifier capsules on different files
  (they never touch .vbproj). Not implemented yet.

---

## 12. Edge Cases

### Shared Module Across LOBs

File-copy capsule handles: copy ONCE, update ALL .vbproj files.
Modifier capsule for shared module: operations from all LOBs that touch this file
are consolidated into one capsule. Edited ONCE.

### No Files to Copy (Workflow 2: Existing Folder)

Skip file-copy capsule entirely. Checkpoint starts at first modifier capsule.

### Zero Operations

Empty execution_order.yaml (all deferred/out-of-scope). Report to developer,
do NOT change state to EXECUTED.

### Single Operation, Single File

Simplest case. One modifier capsule. Worker reads ~1,200 lines total.

### Cross-Province File

NEVER auto-modify. Capsule builder skips these. Flagged as OUT_OF_SCOPE.

### Line Endings

Workers detect CRLF/LF before editing and preserve same style.

### Large File (5,000+ lines)

Worker reads the full file (necessary for function location). Context is higher
but still bounded — one worker per file means no accumulated history.

---

## 13. manifest.yaml Updates

### State Transitions

| From | To | How |
|------|----|-----|
| PLANNED | EXECUTING | /iq-execute starts, checkpoint created |
| EXECUTING | EXECUTING | Operations in progress |
| EXECUTING | EXECUTED | All capsules complete + review passes |
| EXECUTING | PLANNED | Developer aborts + rollback |

### Phase Status Keys

```yaml
phase_status:
  file_copy:
    status: "completed"
    summary: "3 files copied, 6 .vbproj updated"
  modifications:
    status: "completed"
    summary: "7 ops completed, 0 failed, across 3 files"
  internal_review:
    status: "completed"
    summary: "All checks passed, 1 self-correction"
```
