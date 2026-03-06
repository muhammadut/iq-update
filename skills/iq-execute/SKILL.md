---
name: iq-execute
description: Execute the approved plan using the capsule pattern. Spawns per-file worker agents with fresh context, coordinated via checkpoint file for crash recovery.
user-invocable: true
---

# Skill: /iq-execute

## 1. Purpose & Trigger

Execute the approved plan. Picks up after /iq-plan has produced an
approved execution plan (state: PLANNED, gate_1: approved) and applies the actual
file modifications: copy Code/ files, update .vbproj references, take snapshots,
and make code changes.

**Architecture:** The orchestrator is a **crash-only stateless coordinator**. It
builds capsules (self-contained worker briefs), spawns short-lived worker
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

### Check 1: Read paths.md (MANDATORY FIRST STEP)

Read `.iq-workstreams/paths.md`. This file contains all absolute paths you need:
`plugin_root`, `carrier_root`, `python_cmd`, agent spec paths, validator paths, etc.

If `paths.md` does not exist, STOP: `"ERROR: Run /iq-init first to initialize the plugin."`

Use the paths from this file for the entire command. Replace `.iq-update/` with `plugin_root`.

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
- **One found:** Display summary (workflow_id, province, LOBs, date, CR
  count) and proceed.
- **Multiple found:** Present list, ask developer to choose by number.

### Check 4: Validate Workflow State

Read the selected manifest.yaml fully:

1. **State must be PLANNED or EXECUTING.** Any other state: STOP.
2. **Gate 1 must be approved:** `phase_status.gate_1.status == "approved"`.
   If not: STOP, tell developer to run /iq-plan to approve first.
3. **Required files must exist:**
   - `plan/execution_order.yaml`
   - `analysis/intent_graph.yaml`
   - `execution/file_hashes.yaml`
   If any missing: STOP, tell developer to run /iq-plan to regenerate.

   **Optional file:** `analysis/files_to_copy.yaml` — may not exist when no file
   copies are needed (e.g., Workflow 2 where copies were already made). If absent,
   skip the file-copy phase entirely.

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

### Step 4.2: Group Intents by File

```
1. Read plan/execution_order.yaml (full intent execution sequence)
2. Read analysis/intent_graph.yaml for intent details
3. Group intents by target file:
   - file_groups = {}
   - For each intent in execution_order:
       file = intent["file"]
       file_groups[file].append(intent)
   - Intents within each group retain their bottom-to-top order

4. **MAX INTENTS PER CAPSULE: 20.**
   If a file group has more than 20 intents (e.g., 48 territory Array6 changes),
   split into sub-capsules of at most 20 intents each. Maintain bottom-to-top
   order WITHIN each sub-capsule. Sub-capsules for the same file are chained:
   capsule B waits for capsule A to complete, then re-hashes the file before starting.
   Capsule IDs: "mod-{filename}-part1", "mod-{filename}-part2", etc.

   WHY: A worker with 48 intents + the full file + the spec modules approaches
   context window limits. Splitting at 20 ensures each worker has comfortable headroom
   (~120K of 200K context). The hash-chain between sub-capsules preserves TOCTOU safety.

   Token budget per capsule:
     Spec overhead:  ~35-43K tokens
     VB file:        ~85K tokens (worst case, mod_Common_SKHab)
     20 intents:     ~10K tokens (20 * ~500 tokens per intent)
     Conversation:   ~15K tokens
     TOTAL:          ~145-153K tokens -- fits in 200K with headroom
```

### Step 4.2b: Cross-File Dependency Resolution

After grouping intents into capsules, resolve cross-file dependencies to
determine capsule execution order.

```
1. Build capsule dependency graph:
   - For each capsule, collect all depends_on from its intents
   - If any intent in capsule B depends on an intent in capsule A (different file):
     capsule B depends on capsule A

2. Topological sort:
   - Start with file-copy capsule (always first, no dependencies)
   - Then Change Engine capsules in topological order:
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
file-copy > shared modules (mod_Common_*) > LOB-specific Code/ files > Option/Liab files
```

This matches the natural data flow: shared modules define constants and functions
that LOB-specific and endorsement files reference.

### Step 4.3: Determine Spec Modules Per Capsule

For each file group, determine which spec modules the Change Engine worker needs.

**Change Engine spec loading:**

| Condition | Modules to Load |
|-----------|----------------|
| Always | `change-engine/core.md` |
| Any intent has `strategy_hint` | + `change-engine/strategies.md` |

The Change Engine is a unified agent. It always loads `core.md` (universal rules,
execution steps, output schema). When any intent in the capsule has a `strategy_hint`
field (e.g., "array6_multiply", "case_block_insertion", "factor_table_change"),
it also loads `strategies.md` which contains reference examples for common change
patterns. The strategy hints are informational, not prescriptive — the engine
reasons about each change from the code and the intent description.

### Step 4.3b: Resolve FUBs for Tier 2/3 Capsules

For each file group containing Tier 2 or Tier 3 intents, resolve Function
Understanding Blocks (FUBs) from the Analyzer's output. FUBs provide
workers with structural understanding of the target function (branch tree, hazards,
adjacent context) so they can modify code accurately.

**This step is fully automated — no developer interaction.**

```python
def resolve_fubs_for_capsule(intents, workstream_path, analyzer_output, codebase_root):
    """Resolve FUBs for intents that need enriched context.

    For Tier 1: skip (no FUB needed)
    For Tier 2/3: read FUB from analyzer output (direct `fub:` or resolve `fub_ref:`)
    For Tier 3: also collect peer function bodies and cross-file context

    Args:
        intents: list of intents in this capsule's file group
        workstream_path: path to workstream directory
        analyzer_output: dict of function -> loaded analyzer YAML data

    Returns: dict of intent_id -> {fub, canonical_patterns, peer_function_bodies, cross_file_context}

    IMPORTANT: The returned dict is used to INJECT these fields into per-intent
    entries within the capsule YAML. Workers read enriched fields from their
    capsule intent entry, NOT from the Analyzer's output files. The capsule
    builder (Step 4.5) must merge these fields into each intent's capsule entry.
    """
    fub_data = {}

    for intent in intents:
        tier = intent.get("tier", 2)  # Default to Tier 2 if absent (backward compat)

        if tier == 1:
            continue  # Tier 1: thin capsule, no FUB

        intent_id = intent["id"]
        intent_data = analyzer_output.get(intent_id, {})

        # Resolve FUB (direct or via reference)
        fub = intent_data.get("fub")
        if not fub and intent_data.get("fub_ref"):
            # Resolve reference: read FUB from the referenced intent's function
            ref_data = analyzer_output.get(intent_data["fub_ref"], {})
            fub = ref_data.get("fub")
            # Apply adjacent_context_override if this intent has its own target line
            if fub and intent_data.get("adjacent_context_override"):
                fub = dict(fub)  # Shallow copy to avoid mutating shared FUB
                fub["adjacent_context"] = intent_data["adjacent_context_override"]

        # Extract canonical patterns from code_patterns (if present)
        code_patterns = intent_data.get("code_patterns", {})
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
                fub, intent_data, workstream_path, codebase_root
            )
            result["cross_file_context"] = collect_cross_file_context(
                intent_data, analyzer_output
            )

        fub_data[intent_id] = result

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


def collect_peer_bodies(fub, intent_data, workstream_path, codebase_root):
    """Collect peer function bodies for Tier 3 capsules.

    Reads up to 3 peer functions (max 50 lines each) from source files,
    sorted by call_sites (highest first). Only includes ACTIVE/HIGH_USE peers.

    Sources checked (in order):
    1. fub["nearby_functions"] — lightweight entries from Analyzer
    2. code_patterns["peer_functions"] — richer entries from Analyzer
       (FALLBACK when nearby_functions is empty)

    Args:
        fub: the Function Understanding Block (or None)
        intent_data: the intent's analyzer data
        workstream_path: path to workstream directory
        codebase_root: absolute path to carrier root (from manifest.yaml)

    Returns: list of {name, call_sites, body}
    """
    peers = []
    target_file = fub.get("file") if fub else intent_data.get("source_file", intent_data.get("target_file"))

    # Source 1: FUB nearby_functions
    candidates = []
    if fub and fub.get("nearby_functions"):
        candidates = [
            nf for nf in fub["nearby_functions"]
            if nf.get("status") != "DEAD" and nf.get("call_sites", 0) > 0
        ]

    # Source 2: code_patterns peer_functions (fallback)
    if not candidates:
        code_patterns = intent_data.get("code_patterns", {})
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


def collect_cross_file_context(intent_data, analyzer_output):
    """Collect cross-file dependency context for Tier 3 capsules.

    For intents with depends_on pointing to a different file, include
    the dependent intent's FUB summary.

    Returns: list of {dep_intent, dep_summary}
    """
    cross_ctx = []
    target_file = intent_data.get("target_file")

    for dep_id in intent_data.get("depends_on", []):
        dep_data = analyzer_output.get(dep_id, {})
        if dep_data.get("target_file") != target_file:
            cross_ctx.append({
                "dep_intent": dep_id,
                "dep_summary": dep_data.get("description", f"Intent {dep_id}"),
            })

    return cross_ctx
```

**Capsule injection protocol:** After `resolve_fubs_for_capsule` returns, the capsule
builder (Step 4.5) MUST merge the resolved fields into each intent's entry within
the capsule YAML:

```python
# In Step 4.5, when building each capsule's intents list:
for intent_entry in capsule["intents"]:
    enrichment = fub_data.get(intent_entry["id"])
    if enrichment:
        intent_entry["fub"] = enrichment["fub"]
        intent_entry["canonical_patterns"] = enrichment["canonical_patterns"]
        if enrichment.get("peer_function_bodies"):
            intent_entry["peer_function_bodies"] = enrichment["peer_function_bodies"]
        if enrichment.get("cross_file_context"):
            intent_entry["cross_file_context"] = enrichment["cross_file_context"]
```

This ensures workers read ALL enriched fields from the capsule intent entry —
they never need to look outside their capsule for FUB/peer/cross-file data.

**Backward compatibility:** If `tier` is absent from intent data (pre-enhancement
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

### Step 4.5: Build Change Engine Capsules (Tiered)

For each file group from Step 4.2, build a capsule with context depth matching the
highest tier among its intents. FUB data comes from Step 4.3b.

**Token budget by tier:**

| Tier | Capsule Overhead | When |
|------|-----------------|------|
| 1 | ~300 tokens | Simple rate changes, constant insertions |
| 2 | ~1,700 tokens | Changes with known patterns |
| 3 | ~5,000 tokens | Novel changes, cross-file, unconfirmed targets |

#### Tier 1 Capsule (thin — no FUB, no extra context)

```yaml
# execution/capsules/capsule-{sanitized-filename}.yaml
capsule_id: "mod-{sanitized-filename}"
capsule_type: "change-engine"
phase: "modifications"
agent_type: "change-engine"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"  # relative to codebase_root
file_hash: "{current hash from file_hashes.yaml}"
codebase_root: "{carrier_root}"                  # absolute path, from paths.md
spec_modules:                                    # from Step 4.3
  - "change-engine/core.md"
depends_on_capsules: []                          # capsule IDs that must complete first
config_snapshot:                                 # carrier-specific safety constraints
  carrier_prefix: "PORT"
  cross_province_shared_files:                   # files worker must NEVER modify
    - "Code/PORTCommonHeat.vb"
intents:
  - id: "intent-001"
    title: "Multiply base rates by 1.05"        # human-readable description
    description: "Multiply each numeric arg by 1.05, banker round"
    capability: "value_editing"
    function: "GetBasePremium_Home"
    function_line_start: 412
    function_line_end: 489
    target_lines:
      - line: 430
        content: "Case 1 : varRates = Array6(512.59, 28.73"
    parameters:
      factor: 1.05
      rounding: "banker"
    strategy_hint: null
    confidence: 0.95
    tier: 1
  - id: "intent-002"
    title: "Multiply base rates by 1.05"
    description: "Multiply each numeric arg by 1.05, banker round"
    capability: "value_editing"
    function: "GetBasePremium_Home"
    function_line_start: 412
    function_line_end: 489
    target_lines:
      - line: 445
        content: "Case 2 : varRates = Array6(489.22"
    parameters:
      factor: 1.05
      rounding: "banker"
    strategy_hint: null
    confidence: 0.95
    tier: 1
  # ... intents in bottom-to-top order
output_file: "execution/results/result-{capsule-id}.yaml"
success_criteria:
  - "All intents applied"
  - "Array6 arg counts unchanged"
  - "File hash updated in output"
```

#### Tier 2 Capsule (adds FUB + canonical patterns)

```yaml
capsule_id: "mod-{sanitized-filename}"
capsule_type: "change-engine"
phase: "modifications"
agent_type: "change-engine"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_hash: "{current hash from file_hashes.yaml}"
codebase_root: "{carrier_root}"
spec_modules:
  - "change-engine/core.md"
  - "change-engine/strategies.md"
depends_on_capsules: []
config_snapshot:
  carrier_prefix: "PORT"
  cross_province_shared_files:
    - "Code/PORTCommonHeat.vb"
intents:
  - id: "intent-003"
    title: "Add Elite Comp Case block"
    description: "Add Case \"ELITECOMP\" before Case Else"
    capability: "structure_insertion"
    function: "GetRateTableID"
    function_line_start: 405
    function_line_end: 486
    insertion_point:
      after_line: 438
      context: "Case \"COMPREHENSIVE\""
    parameters:
      case_value: "\"ELITECOMP\""
    strategy_hint: "case_block_insertion"
    confidence: 0.9
    tier: 2
    fub:                                        # From Analyzer (via Step 4.3b)
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
  - "All intents applied"
  - "Generated code compiles structurally"
  - "File hash updated in output"
```

#### Tier 3 Capsule (adds peer function bodies + cross-file context)

```yaml
# Same base as Tier 2 (target_file, codebase_root, etc.), plus:
intents:
  - id: "intent-006"
    title: "Add new coverage type premium calculation"
    description: "Insert new Case block with premium Array6 values"
    capability: "structure_insertion"
    function: "GetLiabilityBundlePremiums"
    function_line_start: 4012
    function_line_end: 4104
    insertion_point:
      after_line: 4095
      context: "Case \"COMPREHENSIVE\""
    parameters: {}
    strategy_hint: "case_block_insertion"
    confidence: 0.8
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
      - dep_intent: "intent-003"
        dep_summary: "Adds ELITECOMP constant at line 23"
```

#### Worker Prompt Enhancement

When spawning a Change Engine worker for a Tier 2 or Tier 3 capsule, append these
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

Given capsule intent with FUB:
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

### Step 4.6: Write Initial Checkpoint

```yaml
# execution/checkpoint.yaml
run_id: "exec-{workstream-name}-{timestamp}"
workstream: "{workstream-name}"
phase: "file_copy"                             # file_copy | modifications | completed
capsule_order:
  - "file-copy"                                # always first (if files to copy)
  - "mod-mod_Common_SKHab20260101"             # grouped by file
  - "mod-CalcOption_SKHome20260101"
  - "mod-Option_EliteComp_NB20260701"
completed: []
current_capsule: "file-copy"
current_status: "prepared"                     # prepared | spawned | completed | failed
next_action: "spawn file-copy worker"
retry_count: 0
updated_at: "{timestamp}"
```

### Step 4.7: Update Manifest

```yaml
state: "EXECUTING"
updated_at: "{now}"
phase_status:
  file_copy: {status: "pending"}
  change_engine: {status: "pending"}
```

Tell developer:
```
EXECUTING: {Province} {LOB(s)} {effective_date}
============================================================
Workflow:    {workflow_id}
Intents:     {N} across {M} file(s)
Capsules:    {K} Change Engine workers will be spawned
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

CARRIER ROOT: {carrier_root}
PLUGIN ROOT: {plugin_root}
WORKSTREAM: {carrier_root}/.iq-workstreams/changes/{workstream-name}/
PYTHON: {python_cmd}

TASK: Copy Code/ files to new dated versions and update .vbproj references.

READ YOUR CAPSULE: {carrier_root}/.iq-workstreams/changes/{workstream-name}/execution/capsules/capsule-file-copy.yaml

IMPORTANT: For file path operations, use Python (os.path). For XML parsing,
use Python (xml.etree.ElementTree). NEVER use sed, awk, or Perl.
IMPORTANT: NEVER use sleep or retry loops.
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
  - SNAPSHOT every .vbproj BEFORE modifying it (path-encoded name, same scheme as
    Change Engine snapshots). Rollback and review depend on these snapshots.
  - Create execution/snapshots/ directory if it doesn't exist (os.makedirs)

OUTPUT: Write results using ATOMIC WRITE PROTOCOL:
  1. Write to {output_file}.tmp
  2. Validate YAML is parseable
  3. Rename {output_file}.tmp -> {output_file}

Use this exact schema:
  capsule_id: "file-copy"
  status: "COMPLETED"        # or "PARTIAL" or "FAILED"
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
2. If status == "COMPLETED":
   - Update file_hashes.yaml with new hashes from result
   - Update checkpoint: completed += ["file-copy"], current_capsule = first Change Engine capsule
   - Update manifest: phase_status.file_copy -> COMPLETED
   - Report: "{N} file(s) copied, {N} .vbproj updated, {N} skipped"
3. If status == "PARTIAL" or "FAILED":
   - Show conflicts/errors to developer
   - Options: retry, skip (warn ops will fail), abort
   - On retry: update checkpoint retry_count, re-spawn worker
   - On abort: leave state EXECUTING, tell developer to investigate
```

---

## 6. Phase 2: Change Engine (The Core Loop)

This is the critical section. The orchestrator loops through Change Engine capsules,
spawning one worker per file. Each worker gets a fresh context.

### Step 6.0: Crash-Safe Loop Protocol

```
RULE: Re-read checkpoint.yaml at the START of every iteration.
RULE: Update checkpoint.yaml AFTER every worker completes, BEFORE spawning next.
RULE: After 5 capsules OR 20 tool calls, suggest context refresh:
      "Checkpoint saved at capsule {N}/{M}. If context feels heavy,
       you can /clear and run /iq-execute again — it resumes from here."
```

### Step 6.1: For Each Change Engine Capsule

```
1. Re-read execution/checkpoint.yaml
2. Find next incomplete Change Engine capsule from capsule_order
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
capsules (e.g., split when >20 intents), capsule N modifies the file and updates
`file_hashes.yaml`. Capsule N+1's original hash is now stale. Step 6 refreshes
it from the authoritative `file_hashes.yaml` before spawning. This prevents
false TOCTOU failures.

### Step 6.2: Spawn Change Engine Worker

Read the capsule to get spec_modules. Build the worker prompt:

**Worker prompt template:**
```
You are a Change Engine worker for the IQ Rate Update Plugin.

CARRIER ROOT: {carrier_root}
PLUGIN ROOT: {plugin_root}
WORKSTREAM: {carrier_root}/.iq-workstreams/changes/{workstream-name}/

YOUR CAPSULE: {capsule_file_path}
Read it first — it contains your file, intents, and success criteria.

YOUR INSTRUCTIONS (read in this order):
  1. {plugin_root}/agents/change-engine/core.md         (universal rules)
{if strategies.md in spec_modules:}
  2. {plugin_root}/agents/change-engine/strategies.md    (reference examples for common patterns)

PYTHON: {python_cmd}

IMPORTANT: For file path operations, use Python (os.path). For XML parsing,
use Python (xml.etree.ElementTree). NEVER use sed, awk, or Perl.
IMPORTANT: NEVER use sleep or retry loops.

EXECUTION PROTOCOL:
  1. Read your capsule for the target file, intents list, and config_snapshot
  2. Read each intent's details from the capsule (description, what_to_change, how)
  3. SAFETY CHECK: Verify target file is NOT in config_snapshot.cross_province_shared_files
  4. Take a SNAPSHOT of the target file (if not already in snapshots/)
  5. TOCTOU CHECK: hash the file, compare against capsule's file_hash.
     If mismatch: STOP, write status "toctou_failure" to output, EXIT.
  6. For each intent (in capsule order — already bottom-to-top):
     a. Locate function by name (content-authoritative, line numbers are hints)
     b. Understand the current code state using FUB if provided
     c. Apply the change as described in the intent's how field
     d. Verify the change was applied correctly
  7. After all intents: compute new file hash
  8. Write structured results using ATOMIC WRITE PROTOCOL:
     a. Write to {output_file}.tmp
     b. Validate the YAML is parseable
     c. Rename {output_file}.tmp -> {output_file}
     This prevents partial/corrupt results if the session is interrupted.

OUTPUT SCHEMA (must match change-engine/core.md output contract):
  capsule_id: "{id}"
  target_file: "{relative path}"
  file_hash_after: "{new_hash}"
  intents:
    - intent_id: "{id}"
      status: "success"            # success | failed | skipped | needs_review
      edits_applied:
        - edit_type: "replace"     # replace | insert
          old_string: "{original}"
          new_string: "{modified}"
          line: {N}
          description: "{context}"
      summary:
        values_changed: {N}
        lines_added: {N}
        lines_modified: {N}
        lines_removed: {N}
      verification: "{brief verification note}"
      warnings: []
  started_at: "{timestamp}"
  completed_at: "{timestamp}"
  errors: []                       # structured error objects (see below)

ERROR OBJECT SCHEMA (for failed/toctou):
  errors:
    - code: "TOCTOU_FAILURE"       # TOCTOU_FAILURE | CONTENT_MISMATCH | PARSE_ERROR | ...
      message: "File hash mismatch"
      expected: "{expected_hash}"
      actual: "{actual_hash}"
      intent_id: "{id or null}"   # null for file-level errors

ALSO READ: config_snapshot in your capsule (for cross-province safety checks)

RULES:
  - Do NOT update manifest.yaml or checkpoint.yaml
  - Do NOT read other capsules or results — stay in your lane
  - NEVER modify files listed in config_snapshot.cross_province_shared_files
  - Self-correction: 1 retry per intent (restore from snapshot, re-locate)
  - If retry fails: mark intent "FAILED", continue with remaining intents
  - ALWAYS use atomic write for results (write .tmp, validate, rename)
  - ATOMIC ROLLBACK: If ANY Edit tool call within an intent fails (e.g.,
    old_string not found, non-unique match), IMMEDIATELY restore the file from
    its snapshot BEFORE attempting the next intent. Do NOT leave partial edits
    on disk. The Edit tool writes to disk on each call — edits 1-2 succeed but
    edit 3 fails means the file has been partially modified. Snapshot restoration
    undoes ALL edits for that intent, returning to a clean state.
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
   - If file does not exist: worker crashed before writing. Treat as "FAILED".
   - If file exists but is unparseable YAML: treat as "FAILED", delete corrupt file.
   - Validate required fields: capsule_id, target_file, intents array

2. Derive capsule-level status from per-intent statuses:
   - ALL intents "success": capsule COMPLETED
   - SOME "success" + SOME "failed": capsule PARTIAL
   - ALL intents "failed": capsule FAILED
   - Any TOCTOU error in errors[]: capsule TOCTOU_FAILURE
   (Change Engine uses lowercase per-intent: success/failed/skipped/needs_review.
    Orchestrator derives capsule status from these.)

3. For COMPLETED/PARTIAL:
   - Update execution/file_hashes.yaml with file_hash_after from result
   - Transform worker result into operations_log.yaml format:
     For each intent in result.intents:
       Map to the rich schema expected by /iq-review:
       - Copy: intent_id → operation
       - Map status: "success" → "COMPLETED", "failed" → "FAILED",
                     "skipped" → "SKIPPED", "needs_review" → "NEEDS_REVIEW"
       - Copy: target_file → file, edits_applied[], summary
       - Add: capability from intent_graph.yaml → change_type
       - Add: description from intent_graph.yaml
     Append the transformed entries to execution/operations_log.yaml
   **Operations log status values MUST be UPPERCASE** — the Python validators require uppercase.
   - Update CR intent statuses in manifest
   - ATOMIC CHECKPOINT UPDATE:
     a. Write checkpoint to execution/checkpoint.yaml.tmp
     b. Validate YAML parseable
     c. Rename checkpoint.yaml.tmp -> checkpoint.yaml
     This prevents corrupt checkpoint if session interrupted during write.

4. For FAILED:
   - Read errors[] from result for structured diagnostics
   - Show errors to developer with context
   - Options: retry (re-spawn worker), skip file, abort
   - On retry: increment retry_count in checkpoint, re-spawn
   - Max 2 retries per capsule. After that, escalate to developer.

5. For TOCTOU_FAILURE:
   - CRITICAL: file changed externally since plan approval
   - Show expected vs actual hash from errors[]
   - Options: show diff, re-hash and retry, restore from snapshot, abort
   - On abort: leave state EXECUTING with error in manifest
```

**Result-to-operations_log mapping:** The worker result schema is lean (optimized for
worker context), while `/iq-review` expects the rich operations_log format. The
orchestrator bridges this gap during Step 6.3 by reading the intent_graph.yaml
for description fields and building the full log entries.

### Step 6.4: Update Checkpoint After Each Worker

```yaml
# Updated checkpoint after each worker completes
completed:
  - "file-copy"
  - "mod-mod_Common_SKHab20260101"            # just completed
current_capsule: "mod-CalcOption_SKHome20260101"  # next up
current_status: "prepared"
next_action: "spawn Change Engine worker for CalcOption_SKHome20260101"
retry_count: 0
updated_at: "{now}"
```

### Step 6.5: All Change Engine Workers Complete

When all Change Engine capsules are completed, proceed directly to Section 8
(Completion). No separate internal review phase — `/iq-review` handles validation.

```yaml
phase_status.change_engine: {status: "COMPLETED", summary: "{N} intents, {M} files"}
```

Report:
```
Changes complete: {N} intents applied across {M} files.
```

---

## 7. Completion (State: EXECUTED)

### Step 7.1: Final Checkpoint

```yaml
phase: "COMPLETED"
completed: [... all capsules ...]
current_capsule: null
next_action: "none — execution complete"
```

### Step 7.2: Update Manifest

```yaml
state: "EXECUTED"
updated_at: "{now}"
phase_status:
  file_copy: {status: "COMPLETED", summary: "{N} files copied, {N} .vbproj updated"}
  change_engine: {status: "COMPLETED", summary: "{N} intents completed, {N} failed"}
```

### Step 7.3: Present Summary

```
===========================================================================
 EXECUTION COMPLETE: {Province} {LOB(s)} {effective_date}
===========================================================================

 {N} file(s) copied (new dated versions)
 {N} .vbproj reference(s) updated
 {N} intent(s) applied
 {N} value(s) changed

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
- Update checkpoint: current_status = "FAILED"
- Options: retry (re-spawn from same capsule), skip file, abort.
- On retry: capsule is self-contained, so re-spawn is idempotent.

### Content Not Found

Worker cannot locate function/anchor in the file.
- Worker marks intent "FAILED" in result, continues with others.
- Orchestrator shows failed intents. Options: re-plan, skip, manual fix.

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
| SKIP | "skip", "skip {intent-id}", "move on" | Skip failed intent/capsule, continue | YES (marks SKIPPED) |
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
{python_cmd} -c "import hashlib; print(hashlib.sha256(open(r'{path}','rb').read()).hexdigest())"
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

Use **path-encoded** snapshot names to prevent basename collisions across directories.
Replace path separators with `__` and append `.snapshot`:

```python
# Path-encode: "MB/Code/mod_Common_MBHab20260301.vb" -> "MB__Code__mod_Common_MBHab20260301.vb"
import os, shutil
safe_name = relative_path.replace('/', '__').replace('\\', '__')
snapshot_path = os.path.join(workstream, 'execution', 'snapshots', safe_name + '.snapshot')

# Create snapshots/ directory if needed:
os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)

# Create (only if not exists):
if not os.path.exists(snapshot_path):
    shutil.copy2(target_path, snapshot_path)

# Restore:
shutil.copy2(snapshot_path, original_path)
```

**NEVER use sed or bash string manipulation for path encoding.** Use Python only.

**Do NOT use basename-only** — files like `mod_Common.vb` in different province
directories would collide.

### Timestamps
```bash
{python_cmd} -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))"
```

### YAML Validation
```bash
{python_cmd} -c "import yaml; yaml.safe_load(open(r'{path}')); print('YAML OK')"
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
| change-engine/core.md | ~400 |
| change-engine/strategies.md (if needed) | ~200 |
| Capsule YAML | ~80 |
| Intent details (2-20 intents) | ~200-500 |
| VB.NET source file | ~500-2,000 |
| **Total** | **~1,500-3,400** |

Worst case (large VB.NET file + multiple modules) stays under context limits.
Tool call history within one worker is minimal (read capsule, read file,
edit file, write result — ~4-8 tool calls).

### Parallel Operations

- Same file: ALWAYS sequential, bottom-to-top (guaranteed by capsule grouping)
- Different files: sequential by default (simpler, easier to debug)
- **Parallel mode is DISABLED** until .vbproj shared-write conflicts are resolved.
  Multiple Change Engine workers can converge on the same .vbproj when creating
  new files (Option_*.vb, Liab_*.vb). Sequential execution prevents this race.
- Future: parallel may be safe for pure value-editing capsules on different files
  (they never touch .vbproj). Not implemented yet.

---

## 12. Edge Cases

### Shared Module Across LOBs

File-copy capsule handles: copy ONCE, update ALL .vbproj files.
Change Engine capsule for shared module: intents from all LOBs that touch this file
are consolidated into one capsule. Edited ONCE.

### No Files to Copy (Workflow 2: Existing Folder)

Skip file-copy capsule entirely. Checkpoint starts at first Change Engine capsule.

### Zero Operations

Empty execution_order.yaml (all deferred/out-of-scope intents). Report to developer,
do NOT change state to EXECUTED.

### Single Operation, Single File

Simplest case. One Change Engine capsule. Worker reads ~1,200 lines total.

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
    status: "COMPLETED"
    summary: "3 files copied, 6 .vbproj updated"
  change_engine:
    status: "COMPLETED"
    summary: "7 intents completed, 0 failed, across 3 files"
```
