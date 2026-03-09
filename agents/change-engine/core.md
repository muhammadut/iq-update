# Change Engine — Core Contract

The unified agent that makes code changes during `/iq-execute`. Receives a
**capsule** (pre-built by the orchestrator) containing the intent, the target
code, and optional context. Reasons about the change, plans the edit, applies it
with Claude Code's Edit tool, and verifies the result.

Replaces the separate Rate Modifier and Logic Modifier. One agent, any change.

---

## Purpose

Execute a single code change described by an **intent** from `intent_graph.yaml`.
The intent says WHAT needs to change and WHERE. This agent figures out HOW —
reading the target code, understanding its structure, and making precise edits
that preserve every formatting detail of the existing VB.NET source.

The Change Engine is the **hands** of the pipeline. By the time it runs, upstream
agents have already:
- Discovered the code structure (Discovery)
- Built Function Understanding Blocks (Analyzer)
- Planned the execution order and resolved all questions (Planner)
- Received developer approval at Gate 1

The engine's job: execute the approved plan accurately, one file at a time
(processing all intents for that file in bottom-to-top order).

## Pipeline Position

```
/iq-plan:    Intake -> Discovery -> Analyzer -> Decomposer -> Planner -> [GATE 1]
/iq-execute: Build Capsules -> [File-Copy Worker] -> [CHANGE ENGINE] -> [EXECUTED]
                                                      ^^^^^^^^^^^^^^
/iq-review:  Validator -> Diff -> Report -> [GATE 2] -> DONE
```

- **Upstream:** File-copier worker (creates target files, updates .vbproj references,
  updates `execution/file_hashes.yaml`); Planner (provides the approved intent graph
  and execution order)
- **Downstream:** /iq-review validators (Array6 format, old-file protection, value
  sanity, cross-LOB consistency, traceability)
- **Orchestrator:** `/iq-execute` builds one capsule per target file (grouping
  all intents for that file), spawns a fresh Change Engine worker for each,
  tracks progress in `checkpoint.yaml`

---

## Capabilities

These are broad capability labels that help the engine focus. They do NOT constrain
what the engine can do — they describe what KIND of change is involved. A single
intent may use multiple capabilities.

| Capability | Description | Examples |
|-----------|-------------|---------|
| `value_editing` | Change values in existing code | Array6 args, factor values, constants, scalar assignments |
| `structure_insertion` | Insert new code structures | Case blocks, function calls, If/ElseIf branches, constants |
| `file_creation` | Create new source files | Option_*.vb, Liab_*.vb from peer templates |
| `flow_modification` | Modify control flow | Add/remove branches, change conditions, refactor logic |

A "refactor the discount calculation" ticket might use `flow_modification` +
`value_editing`. No classification needed — the engine reads the intent and
reasons about what to do.

---

## Input Schema (Capsule)

The `/iq-execute` orchestrator builds one capsule per TARGET FILE (grouping all
intents that touch that file). The Change Engine processes all intents in a single
capsule, executing them bottom-to-top within the file.

```yaml
capsule:
  capsule_id: "capsule-001"
  target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  file_hash: "sha256:abc123..."
  codebase_root: "/path/to/carrier"
  strategy_reference: |                # Optional — loaded from strategies.md
    (relevant strategy guidance, included when any intent has strategy_hint)
  intents:                             # One or more intents, all targeting this file
    - id: "intent-001"
      title: "Increase liability premiums by 3%"
      description: "Multiply all rate-value Array6 arguments by 1.03"
      capability: "value_editing"
      strategy_hint: "array6-multiply"
      function: "GetLiabilityBundlePremiums"
      parameters:
        factor: 1.03
        rounding: "mixed"
      target_lines:
        - line: 4058
          content: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
          context: "Farm > PRIMARYITEM > Enhanced Comp"
          rounding: "banker"
          value_count: 6
        - line: 4062
          content: "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
          context: "Farm > PRIMARYITEM > ELITECOMP"
          rounding: "none"
          value_count: 6
      insertion_point: null
      confidence: 0.95
      function_body: |
        (actual function code, pre-extracted by orchestrator)
      function_line_start: 4012
      function_line_end: 4104
      fub:                             # Function Understanding Block (optional)
        branch_tree: [...]
        hazards: [...]
        adjacent_context:
          above: [...]
          below: [...]
        nearby_functions: [...]
      peer_examples: [...]             # Optional — active peer function bodies
    - id: "intent-002"
      title: "Change $5000 deductible factor from -0.20 to -0.22"
      # ... another intent targeting the same file
```

**Processing order:** Sort intents by their highest `target_lines[].line` descending
(bottom-to-top). This prevents line-number drift when earlier edits shift content.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `capsule_id` | yes | Unique capsule identifier |
| `target_file` | yes | Target file path (relative to codebase root) |
| `file_hash` | yes | SHA-256 hash for TOCTOU check |
| `codebase_root` | yes | Absolute path to carrier root |
| `strategy_reference` | no | Loaded strategy content (if any intent has strategy_hint) |
| `intents[]` | yes | Array of intents to process (1 or more) |
| `intents[].id` | yes | Unique ID from intent_graph.yaml |
| `intents[].title` | yes | Human-readable description of the change |
| `intents[].capability` | yes | Primary capability |
| `intents[].strategy_hint` | no | Reference to a strategy section in strategies.md |
| `intents[].function` | yes* | Target function name (*null for module-level) |
| `intents[].parameters` | yes | Intent-specific parameters |
| `intents[].target_lines` | yes* | Pre-identified target lines (*null for insertions) |
| `intents[].insertion_point` | no | For structure_insertion: where to insert |
| `intents[].function_body` | no | Pre-extracted function code |
| `intents[].function_line_start` | yes* | First line of function |
| `intents[].function_line_end` | yes* | Last line of function |
| `intents[].fub` | no | Function Understanding Block from Analyzer |
| `intents[].peer_examples` | no | Peer function bodies for reference |
| `intents[].confidence` | yes | Confidence score (0.0 to 1.0) |

---

## Output Schema

The Change Engine returns a structured result for the capsule, with per-intent
results inside.

```yaml
result:
  capsule_id: "capsule-001"
  target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  file_hash_after: "sha256:def456..."
  intents:
    - intent_id: "intent-001"
      status: "success"               # success | failed | skipped | needs_review
      edits_applied:
        - edit_type: "replace"         # replace | insert
          old_string: "liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
          new_string: "liabilityPremiumArray = Array6(0, 80, 166, 195, 219, 300)"
          line: 4058
          description: "Farm > PRIMARYITEM > Enhanced Comp — 5 values multiplied by 1.03"
        - edit_type: "replace"
          old_string: "liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
          new_string: "liabilityPremiumArray = Array6(0, 0, 0, 0, 334.02, 476.19)"
          line: 4062
          description: "Farm > PRIMARYITEM > ELITECOMP — 2 values multiplied by 1.03"
      summary:
        values_changed: 7
        lines_added: 0
        lines_modified: 2
        lines_removed: 0
        change_range: "2.6% to 3.2%"
      verification: "All 14 Array6 lines updated, formatting preserved"
      warnings: []
    - intent_id: "intent-002"
      status: "success"
      # ... per-intent results
  started_at: "2026-03-03T11:05:00Z"
  completed_at: "2026-03-03T11:05:03Z"
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `success` | All edits applied and verified |
| `failed` | Could not apply — file mismatch, TOCTOU, target not found |
| `skipped` | Values already match target (change already applied) |
| `needs_review` | Edits applied but confidence is low — flag for developer |

---

## EXECUTION STEPS

These steps define how the Change Engine processes a SINGLE capsule (one target
file, potentially with multiple intents). The orchestrator spawns one Change
Engine worker per capsule. Within a capsule, process intents bottom-to-top.

### Step 1: Validate Capsule

Check that the capsule is well-formed before doing any file I/O.

```
REQUIRED FIELDS:
  - intent_id       (string, non-empty)
  - intent.title    (string, non-empty)
  - intent.capability (string, one of: value_editing, structure_insertion,
                       file_creation, flow_modification)
  - intent.file     (string, relative path)
  - target_file     (string, relative path — must match intent.file)
  - file_hash       (string, sha256)
  - codebase_root   (string, absolute path)

CAPABILITY-SPECIFIC REQUIRED FIELDS:

  value_editing:
    - intent.target_lines   (list, length >= 1)
    - Each target_line: content (string), line (int)

  structure_insertion:
    - intent.insertion_point (object with context and position)

  file_creation:
    - intent.parameters.template_file OR peer_examples (at least one)

  flow_modification:
    - intent.function       (string, function name)
    - intent.target_lines OR intent.insertion_point (at least one)
```

**On validation failure:** Return `status: "FAILED"` with the validation error.
Do NOT proceed to subsequent steps.

### Step 2: Read Target File

If `intent.capability` is NOT `file_creation`, the target file must already exist
on disk (created by the file-copier worker).

```python
def read_target_file(codebase_root, target_file):
    """Read target file, detect line endings, return lines list."""
    target_path = os.path.join(codebase_root, target_file)

    if not os.path.exists(target_path):
        return FAIL(
            f"Target file does not exist: {target_file}. "
            "The file-copier worker should have created it. "
            "Check checkpoint.yaml for file-copy errors."
        )

    with open(target_path, "rb") as f:
        raw = f.read()

    # Detect line ending style (VB.NET typically uses CRLF)
    line_ending = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8-sig")
    lines = text.split(line_ending)

    return lines, line_ending, target_path
```

**Store the line ending style** — it MUST be used when writing the file back.
Changing line endings creates massive diffs in SVN.

For `file_creation` intents, skip to Step 8 (New File Creation).

### Step 3: Locate Function

Find the target function within the file. Use `function_line_start` as a hint,
verify by signature match.

```python
def locate_function(lines, function_name, hint_start, hint_end):
    """Find function boundaries by name. Line numbers are 1-indexed hints.

    Returns (actual_start, actual_end) as 0-indexed line indices,
    or FAIL if function not found.
    """
    import re

    # VB.NET function/sub signatures with optional access modifiers
    sig_pattern = re.compile(
        r'^\s*'
        r'(?:(?:Public|Private|Protected|Friend|Shared|Overrides|Overloads)\s+)*'
        r'(?:Function|Sub)\s+'
        + re.escape(function_name)
        + r'\s*\(',
        re.IGNORECASE
    )

    # Strategy 1: Search near the hint (+/- 50 lines)
    hint_idx = max(0, hint_start - 1 - 50)
    hint_end_idx = min(len(lines), hint_end + 50)

    for i in range(hint_idx, hint_end_idx):
        if sig_pattern.search(lines[i]):
            return (i, find_function_end(lines, i))

    # Strategy 2: Full file scan
    for i in range(len(lines)):
        if sig_pattern.search(lines[i]):
            return (i, find_function_end(lines, i))

    return FAIL(f"Function '{function_name}' not found in file")


def find_function_end(lines, start_idx):
    """Find End Function / End Sub, handling nested blocks.

    Counts depth to handle nested Function/Sub definitions.
    Checks quote count before incrementing depth (string literal fix).
    """
    import re
    depth = 1

    is_function = bool(re.search(r'\bFunction\b', lines[start_idx], re.IGNORECASE))
    end_pattern = re.compile(
        r'^\s*End\s+(Function|Sub)\b', re.IGNORECASE
    )
    nest_keyword = "Function" if is_function else "Sub"
    start_pattern = re.compile(
        r'\b' + nest_keyword + r'\s+\w+\s*\(', re.IGNORECASE
    )

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()

        # Skip commented lines
        if stripped.startswith("'"):
            continue

        # Check for nested Function/Sub
        nest_match = start_pattern.search(line)
        if nest_match and not stripped.startswith("'"):
            # String literal check: count quotes before match position
            prefix = line[:nest_match.start()]
            if prefix.count('"') % 2 == 0:  # Even = NOT inside a string
                depth += 1

        if end_pattern.search(line):
            depth -= 1
            if depth == 0:
                return i

    raise ValueError(
        f"End Function/Sub not found starting at line {start_idx + 1}. "
        "File may be corrupt or truncated."
    )
```

**On failure:** Return `status: "FAILED"`. Do NOT guess or search for similar names.

For module-level intents (no function target), skip this step.

### Step 4: Locate Targets Within Function

This step handles BOTH value editing targets (find lines by content) and insertion
points (find anchors by context). The approach depends on the intent's capability.

#### 4a: Locate Target Lines (value_editing, flow_modification)

For each entry in `intent.target_lines`, find the matching line by **content
match** within the function boundaries. Line numbers are hints; content is truth.

```python
def locate_target_lines(lines, func_start, func_end, target_lines):
    """Find each target line by content within the function.

    Returns list of (target_line_spec, actual_line_idx) tuples.
    """
    results = []

    for tl in target_lines:
        expected_content = tl["content"]
        hint_idx = tl["line"] - 1  # Convert 1-indexed to 0-indexed

        # Strategy 1: Check exact hint location
        if func_start <= hint_idx <= func_end:
            if lines[hint_idx].rstrip() == expected_content.rstrip():
                results.append((tl, hint_idx))
                continue

        # Strategy 2: Content search within function
        found = False
        for i in range(func_start, func_end + 1):
            if lines[i].rstrip() == expected_content.rstrip():
                results.append((tl, i))
                found = True
                break

        # Strategy 3: Fuzzy — strip all whitespace and compare
        if not found:
            expected_stripped = expected_content.strip()
            for i in range(func_start, func_end + 1):
                if lines[i].strip() == expected_stripped:
                    results.append((tl, i))
                    found = True
                    break

        if not found:
            return FAIL(
                f"Target line not found in function "
                f"(hint line {tl['line']}): {expected_content[:80]}..."
            )

    return results
```

**CRITICAL: Content match, not line number.** After the file-copier creates the
target file, line numbers should be identical. But if any preceding intent in the
same file added or removed lines, numbers will drift. Content match handles this.

#### 4b: Locate Insertion Point (structure_insertion)

For intents that INSERT new code, locate the anchor by content-based search.

```python
def locate_insertion_point(lines, insertion_point):
    """Find insertion position using content-based anchor matching.

    Returns (insert_idx, position_type) where insert_idx is the 0-indexed
    anchor line, and position_type is "after", "before_end_select",
    "before_case_else", or "before_end_function".
    """
    import re

    context = insertion_point["context"]
    hint_line = insertion_point.get("line", 0)
    position = insertion_point["position"]
    hint_idx = max(0, hint_line - 1)

    # Parse directive prefix: "After: <content>", "Before: <content>", etc.
    anchor_text = context
    for prefix in ("After:", "Before:", "Inside:"):
        if context.startswith(prefix):
            anchor_text = context[len(prefix):].strip()
            break

    # Strip trailing parenthetical hints like "(line 405)"
    anchor_text = re.sub(r'\s*\(line \d+\)\s*$', '', anchor_text)

    # 3-tier search: hint line -> +/-20 lines -> full file
    match_indices = []

    # Strategy 1: Exact hint position
    if 0 <= hint_idx < len(lines):
        if anchor_text in lines[hint_idx].rstrip():
            match_indices.append(hint_idx)

    # Strategy 2: +/-20 lines
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

    if not match_indices:
        return FAIL(
            f"CONTENT_MISMATCH: Anchor text not found in file.\n"
            f"  Anchor: {anchor_text}\n"
            f"  Hint line: {hint_line}"
        )

    if len(match_indices) > 1:
        return FAIL(
            f"AMBIGUOUS_ANCHOR: Found {len(match_indices)} matches.\n"
            f"  Anchor: {anchor_text}\n"
            f"  Matches at lines: {[i+1 for i in match_indices]}"
        )

    anchor_idx = match_indices[0]

    # Handle positional variants
    if position == "before_end_select":
        end_select_idx = find_end_select(lines, anchor_idx, insertion_point)
        if end_select_idx is None:
            return FAIL("End Select not found after anchor")

        # Check for Case Else — insert BEFORE it, not before End Select
        case_else_idx = find_case_else(lines, anchor_idx, end_select_idx)
        if case_else_idx is not None:
            return (case_else_idx, "before_case_else")
        return (end_select_idx, "before_end_select")

    if position == "before_end_function":
        end_func_idx = find_end_function(lines, anchor_idx)
        if end_func_idx is None:
            return FAIL("End Function not found after anchor")
        return (end_func_idx, "before_end_function")

    # Default: "after" position
    return (anchor_idx, "after")
```

**FUB Pre-Validation:** Before the anchor search, if `fub.adjacent_context` is
available, use it as a confidence check that the file hasn't shifted since
analysis. If adjacent lines don't match, log a note but proceed — the content-
based search handles drift automatically.

### Step 5: Understand the Change

Before making any edit, the engine reads the target code and the intent, then
reasons about WHAT to do. If a `strategy_reference` is provided, it reads
that for guidance on how similar changes were handled before.

```
REASONING PROTOCOL:

1. READ the intent.title and intent.description
2. READ the target code (function_body or the located lines)
3. If strategy_hint exists, READ the strategy_reference for guidance
4. If FUB exists, READ hazards and branch_tree for structural awareness
5. If peer_examples exist, READ them for style reference
6. PLAN the exact edits:
   - For value_editing: what old values become what new values
   - For structure_insertion: what code to generate and where
   - For file_creation: what template to follow and what to customize
   - For flow_modification: what structural changes to make
7. CHECK the plan against the RULES below
8. EXECUTE the edits
```

**The engine is a reasoning agent.** It does not blindly follow templates. It
reads the code, reads the intent, and figures out the right edit. The strategy
reference is guidance ("here's how we've done this before"), not a recipe.

### Step 6: Execute Edits

Apply the planned edits using Claude Code's **Edit tool** (old_string ->
new_string replacement). This is the physical edit step.

#### 6a: Value Editing

For each target line, compute the new value and build the edit.

```python
def execute_value_edit(lines, located_targets, intent):
    """Build edit operations for value changes.

    Returns list of edit dicts: {old_string, new_string, line, description}
    """
    edits = []
    params = intent["parameters"]

    # Sort targets by line index DESCENDING (bottom-to-top)
    sorted_targets = sorted(located_targets, key=lambda t: t[1], reverse=True)

    for tl, line_idx in sorted_targets:
        current_line = lines[line_idx]

        # Skip commented lines
        if current_line.strip().startswith("'"):
            return FAIL(f"Line {line_idx + 1} is commented out. Aborting.")

        # Compute the new line based on the intent
        new_line = compute_new_line(current_line, tl, params)
        if new_line is None:
            return FAIL(f"Could not compute new value for line {line_idx + 1}")

        if current_line.rstrip() == new_line.rstrip():
            continue  # Already matches — skip

        edits.append({
            "edit_type": "replace",
            "old_string": current_line.rstrip(),
            "new_string": new_line.rstrip(),
            "line": line_idx + 1,
            "description": tl.get("context", ""),
        })

    return edits
```

The `compute_new_line` function is where the actual value computation happens.
It reads the intent parameters and the current line content, then produces the
new line. The engine reasons about what kind of value is on the line:

- **Array6 with multiplier:** parse args, multiply each numeric arg by the factor,
  apply rounding per the target_line's rounding field
- **Factor/limit replacement:** find the old value on the line, replace with new
- **Const modification:** find the value after `=`, replace, preserve trailing comment

See **strategies.md** for detailed guidance on each of these value change types.

#### 6b: Structure Insertion

For intents that insert new code, generate the code and insert it.

```python
def execute_structure_insertion(lines, insert_idx, position_type, intent, fub):
    """Generate and insert new VB.NET code.

    Returns list of edit dicts with edit_type: "insert".
    """
    # Generate the code to insert
    generated_lines = generate_code(intent, lines, insert_idx, fub)

    # Validate generated code (balanced keywords, indentation)
    validation = validate_generated_code(generated_lines, lines)
    if validation is not OK:
        return validation

    # Determine insertion position
    if position_type == "after":
        insert_at = insert_idx + 1
    elif position_type in ("before_end_select", "before_case_else",
                           "before_end_function"):
        insert_at = insert_idx
    else:
        return FAIL(f"Unknown position_type: {position_type}")

    # Build the edit
    # For insertions, old_string is the line BEFORE which we insert,
    # and new_string is that line preceded by the new code
    anchor_line = lines[insert_at].rstrip() if insert_at < len(lines) else ""
    new_code = "\n".join(ln.rstrip() for ln in generated_lines)

    return [{
        "edit_type": "insert",
        "old_string": anchor_line,
        "new_string": new_code + "\n" + anchor_line,
        "line": insert_at + 1,
        "description": intent.get("title", "Code insertion"),
    }]
```

The `generate_code` function is where the engine reasons about what VB.NET code
to produce. It uses:
- The intent description (what to create)
- Adjacent code in the file (for indentation and style matching)
- FUB branch_tree (for structural understanding)
- Peer examples (for established patterns)
- Strategy reference (for guidance on common patterns)

See **strategies.md** for detailed guidance on code generation patterns.

#### 6c: File Creation

For intents that create new files (Option_*.vb, Liab_*.vb):

```python
def execute_file_creation(capsule):
    """Create a new source file from a template or peer examples.

    Also adds a <Compile Include> entry to the target .vbproj.
    """
    intent = capsule["intent"]
    params = intent["parameters"]
    codebase_root = capsule["codebase_root"]
    target_file = capsule["target_file"]
    target_path = os.path.join(codebase_root, target_file)

    # Determine the template source
    template_file = params.get("template_file")
    peer_examples = capsule.get("peer_examples", [])

    if template_file:
        # Read and transform the template
        new_content = transform_template(codebase_root, template_file, params)
    elif peer_examples:
        # Generate from peer example structure
        best_peer = max(peer_examples, key=lambda p: p.get("call_sites", 0))
        new_content = generate_from_peer(best_peer, params)
    else:
        return FAIL("file_creation requires template_file or peer_examples")

    # Write the new file
    with open(target_path, "wb") as f:
        f.write(new_content.encode("utf-8"))

    # Update .vbproj with Compile Include entry
    vbproj_target = params.get("vbproj_target")
    if vbproj_target:
        update_vbproj(codebase_root, vbproj_target, target_file)

    return [{
        "edit_type": "insert",
        "old_string": None,
        "new_string": f"(new file — {len(new_content.splitlines())} lines)",
        "line": 0,
        "description": f"Created {os.path.basename(target_file)}",
    }]
```

See **strategies.md** Section 5 for guidance on file creation from templates.

### Step 7: Verify Edits

After applying all edits, re-read the modified file and verify each change.

```python
def verify_edits(target_path, edits, line_ending):
    """Re-read the file and verify each edit was applied correctly.

    Returns OK or FAIL with details of the first mismatch.
    """
    with open(target_path, "rb") as f:
        raw = f.read()
    actual_lines = raw.decode("utf-8").split(line_ending)

    for edit in edits:
        if edit["edit_type"] == "replace":
            line_num = edit["line"]
            expected = edit["new_string"]
            actual = actual_lines[line_num - 1].rstrip()
            if actual != expected:
                return FAIL(
                    f"Verification failed at line {line_num}:\n"
                    f"  Expected: {expected}\n"
                    f"  Actual:   {actual}"
                )

    return OK
```

**On verification failure:** The orchestrator restores from snapshot, reports
`status: "FAILED"`, and continues to the next intent.

---

## CORE RULES

These rules are MANDATORY for every edit. They are distilled from hard-won
experience with the VB.NET rating codebase.

### Rule 1: Bottom-to-Top Execution

Within a single file, process intents from the HIGHEST line number to the LOWEST.
This prevents index drift when insertions or replacements change line counts.

The `/iq-execute` orchestrator enforces this in the capsule ordering. Within a
single capsule that has multiple target lines, sort by line index descending.

### Rule 2: TOCTOU Protection

Before ANY file modification, the orchestrator verifies the file's SHA-256 hash
matches the expected hash from the plan. If the hash doesn't match, the file
changed since planning — ABORT.

The Change Engine receives the `file_hash` in the capsule. The orchestrator
handles the actual hash verification and snapshot management. If the engine is
told to proceed, the hash has already been verified.

### Rule 3: Snapshot Before Edit

The orchestrator takes a per-file snapshot before the first edit to that file.
If any edit fails, the orchestrator restores from snapshot. The Change Engine
does NOT manage snapshots — it reports success or failure, and the orchestrator
handles recovery.

### Rule 4: Preserve Exact VB.NET Formatting

Every edit must preserve:
- **Leading whitespace** (indentation — spaces, tabs, or mixed)
- **Trailing inline comments** (`'Base Surcharge` after a value)
- **Comma-separator style** (`, ` vs `,` — match the original)
- **Line ending style** (CRLF or LF — match the file)
- **Statement separators** (`: ` on single-line Case statements)
- **Whitespace alignment** between value and trailing comment

**Substring replacement, not line replacement.** When changing a value on a line,
replace ONLY the matched value, preserving everything else.

Example:
```
Private Const ACCIDENTBASE As Double = 0.3     'Base Surcharge
```
- CORRECT: Replace `0.3` with `0.35` -> `...0.35     'Base Surcharge`
- WRONG: Replace entire line -> comment and alignment lost

### Rule 5: Never Modify Commented Lines

Lines starting with `'` (VB.NET comment marker) are NEVER modified. If a target
line turns out to be commented, ABORT that edit and report failure. The Analyzer
should have excluded commented lines — finding one means the file changed.

### Rule 6: Re-Locate Anchors After Each Insertion

When multiple intents target the same file, each insertion shifts all line numbers
below it. The engine MUST re-locate targets via content search for each subsequent
intent. Do NOT cache line indices across intents.

The content-based `locate_target_lines()` and `locate_insertion_point()` functions
handle this automatically when called fresh for each intent.

### Rule 7: Negative Lookbehind for Value Matching

When searching for a numeric value on a line, use a negative lookbehind that
includes the minus sign to prevent false matches:

```python
import re

def value_appears_on_line(line, value):
    """Check if a numeric value appears on a VB.NET line.

    Uses negative lookbehind including \- to prevent matching
    0.2 inside -0.2.
    """
    str_val = format_vb_number(value)
    for candidate in (str_val, str(value)):
        pattern = re.escape(candidate)
        if re.search(r'(?<![.\d\-])' + pattern + r'(?![.\d])', line):
            return True
    return False


def replace_value_in_line(line, old_value_str, new_value_str):
    """Replace a numeric value in a line, preserving everything else.

    Handles Array6 args, Const declarations, factor assignments.
    """
    import re
    pattern = re.escape(old_value_str)
    match = re.search(r'(?<![.\d\-])' + pattern + r'(?![.\d])', line)
    if match:
        return line[:match.start()] + new_value_str + line[match.end():]
    return None  # Value not found — caller handles
```

### Rule 8: Depth-Aware Parenthesis Matching for Array6

When parsing `Array6(...)` arguments, use depth-counting to find the matching
close parenthesis. A simple regex like `Array6\((.+?)\)` breaks when arguments
contain nested calls like `CInt(30 + 10)`.

```python
def find_array6_close_paren(line, open_paren_idx):
    """Find the matching ) for Array6( using depth counting."""
    depth = 1
    in_string = False
    for i in range(open_paren_idx + 1, len(line)):
        ch = line[i]
        if ch == '"':
            in_string = not in_string
        if in_string:
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
    return None  # Unbalanced — possible multi-line Array6
```

### Rule 9: Const Trailing Comment Preservation

When modifying a `Const` declaration, use substring replacement to preserve
trailing comments and their whitespace alignment:

```
Before: "    Private Const ACCIDENTBASE As Double = 0.3     'Base Surcharge"
After:  "    Private Const ACCIDENTBASE As Double = 0.35     'Base Surcharge"
```

Use `replace_value_in_line()` from Rule 7 — it replaces only the matched value,
leaving comments intact.

### Rule 10: Short Overflow Check

Many rating functions return `Short` (`As Short` in VB.NET). After computing new
values, check if any value exceeds the Short range (-32768 to 32767). If the
function's return type is `Short` (from FUB `return_type` or Pattern Library) AND
a computed value is out of range, emit a WARNING.

```python
def check_short_overflow(new_values, return_type):
    """Warn if computed values would overflow VB.NET Short."""
    if return_type and return_type.lower() == "short":
        for v in new_values:
            try:
                num = float(v)
                if num > 32767 or num < -32768:
                    return f"WARNING: Value {v} exceeds Short range"
            except ValueError:
                continue
    return None
```

### Rule 11: Case Else Ordering

When inserting new `Case` blocks into a `Select Case` structure, ALWAYS insert
BEFORE `Case Else` (not before `End Select`). `Case Else` is the catch-all and
must remain last. Inserting after it creates dead code.

Use `find_case_else()` during anchor location:

```python
def find_case_else(lines, anchor_idx, end_select_idx):
    """Find Case Else between anchor and End Select at same nesting depth."""
    import re
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
```

### Rule 12: Duplicate Content Disambiguation

When the same line content appears multiple times in a function (e.g., identical
Array6 lines in different Case branches), use `context_above` and `context_below`
from the target_line spec to disambiguate. The Analyzer provides surrounding
context lines when it detects duplicates.

If the intent's `target_lines` entry includes `context_above` or `context_below`:
1. Find ALL content matches in the function
2. For each match, check the lines above/below against the context
3. Use the match whose surrounding context matches

If no context is provided and multiple matches exist, ABORT with
`AMBIGUOUS_TARGET` — never silently pick one.

### Rule 13: Never Modify Old-Dated Files

Only edit files that match the target version date. Old Code/ files are shared by
older version folders and MUST NOT be modified. The file-copier creates new dated
copies; the Change Engine edits those copies.

The orchestrator enforces this by only providing capsules for target-date files.
If the engine detects it's being asked to modify an old file (comparing dates),
ABORT immediately.

### Rule 14: Never Modify Cross-Province Shared Files

Files in `config.yaml["cross_province_shared_files"]` (e.g., `Code/PORTCommonHeat.vb`)
are shared across provinces. These are NEVER auto-modified — flag for developer
review instead.

### Rule 15: Never Apply Unverified Constants or API References

Before applying any edit that introduces a new constant, enum value, or
`Cssi.ResourcesConstants.*` reference (i.e., a symbol that does NOT appear in the
`old_string` / before-code), the worker MUST verify the symbol exists in the
codebase by grepping for it. If zero matches are found:

1. Do NOT apply the edit
2. Mark the intent result as `status: "needs_review"`
3. Report: `"Unresolved symbol: {symbol_name} — not found in codebase. Skipping edit."`

This prevents build-breaking errors from fabricated constants. The Planner or
upstream agents may have hallucinated a symbol by pattern extrapolation (e.g.,
observing `DISCOUNT_ANTITHEFTDEVICE` and inventing `DISCOUNT_ALLPERILS`).

**What to grep for:** Extract any `Cssi.ResourcesConstants.MappingCodes.*` or
fully-qualified enum references from the new code. Search the carrier root and
Hub/ directory for each symbol. A valid symbol will appear in at least one
`ResourceID.vb`, `Constants.vb`, or shared class file.

---

## SHARED HELPER FUNCTIONS

These functions are used across all capability types.

### Number Formatting

```python
def format_vb_number(value):
    """Format a number as VB.NET would display it.

    VB.NET trims trailing zeros: -0.20 -> -0.2, 5000.0 -> 5000
    """
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        s = f"{value:.10f}".rstrip("0").rstrip(".")
        return s
    return str(int(value))


def format_vb_decimal(value, original_precision=2):
    """Format a decimal preserving the ORIGINAL source precision.

    Args:
        value: computed decimal result
        original_precision: decimal places in the ORIGINAL value
                           (detected from source code, default 2)

    Rules:
      - Whole number result -> show as integer: 324.00 -> 324
      - Otherwise round to original precision
      - Trim trailing zeros: 334.020 -> 334.02
    """
    if value == int(value):
        return str(int(value))
    rounded = round(value, original_precision)
    if rounded == int(rounded):
        return str(int(rounded))
    s = f"{rounded:.{original_precision}f}".rstrip("0")
    return s


def detect_decimal_places(raw_str):
    """Detect decimal places in a value string.

    "324.29" -> 2, "324.295" -> 3, "324" -> 0, "-0.075" -> 3
    """
    if "." in raw_str:
        return len(raw_str.rstrip().split(".")[1])
    return 0
```

### Banker's Rounding

```python
def bankers_round(value):
    """Banker's rounding (round half to even) — matches VB.NET CInt().

    Uses decimal.Decimal to avoid IEEE 754 floating-point errors near .5
    boundaries (e.g., 50 * 1.05 = 52.50000000000001 in float).

    Examples:
        2.5 -> 2, 3.5 -> 4, 4.5 -> 4, 5.5 -> 6
    """
    from decimal import Decimal, ROUND_HALF_EVEN
    d = Decimal(str(value))
    return int(d.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
```

**CRITICAL: Python's `round()` implements banker's rounding.** This matches
VB.NET's `CInt()`. Do NOT use `math.floor(x + 0.5)` or `int(x + 0.5)`.

### Safe Arithmetic Evaluation

```python
def safe_eval_arithmetic(expr):
    """Evaluate simple arithmetic (+ - * /) using AST whitelist.

    "30 + 10" -> 40, "-30 + 10" -> -20

    Raises ValueError for anything other than numbers and operators.
    """
    import ast
    node = ast.parse(expr.strip(), mode='eval')
    for n in ast.walk(node):
        if isinstance(n, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant)):
            continue
        if isinstance(n, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)):
            continue
        if hasattr(ast, 'Num') and isinstance(n, ast.Num):
            continue
        raise ValueError(f"Unsafe element: {type(n).__name__} in '{expr}'")
    return eval(compile(node, '<string>', 'eval'))
```

### Select Case Helpers

```python
import re

def find_end_select(lines, anchor_idx, insertion_point):
    """Find the End Select closing the Select Case at anchor_idx.

    Uses end_select_line hint if available, otherwise counts nesting.
    """
    hint = insertion_point.get("end_select_line") if insertion_point else None
    if hint:
        hint_idx = hint - 1
        if 0 <= hint_idx < len(lines) and "End Select" in lines[hint_idx]:
            return hint_idx

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


def find_end_function(lines, anchor_idx):
    """Find End Function / End Sub after anchor_idx."""
    for i in range(anchor_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'End\s+(Function|Sub)\b', stripped, re.IGNORECASE):
            return i
    return None


def measure_case_indent(lines, end_select_idx):
    """Measure indentation of existing Case blocks in a Select Case.

    Scans backward from End Select to find a Case line.
    Returns its leading whitespace string.
    """
    for i in range(end_select_idx - 1, max(end_select_idx - 50, -1), -1):
        stripped = lines[i].strip()
        if stripped.startswith("'"):
            continue
        match = re.match(r'^(\s*)Case\s+', lines[i])
        if match:
            return match.group(1)
    # Fallback: End Select indent + 4 spaces
    es_match = re.match(r'^(\s*)', lines[end_select_idx])
    return es_match.group(1) + "    " if es_match else "                    "
```

### Code Validation

```python
def validate_generated_code(generated_lines, existing_lines=None):
    """Validate generated VB.NET code for structural correctness.

    Checks:
    1. Balanced keywords (Function/End Function, Select Case/End Select, etc.)
    2. Indentation consistency (4-space multiples)
    """
    import re

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

    # 2. Indentation consistency
    for ln in generated_lines:
        if ln.strip() == "":
            continue
        leading = len(ln) - len(ln.lstrip(' '))
        if leading % 4 != 0:
            return FAIL(
                f"Indentation not a multiple of 4: {leading} spaces "
                f"on: {ln.rstrip()[:60]}..."
            )

    return OK
```

---

## FUB CONSUMPTION (Context Engineering Level 2)

When the capsule includes a FUB (Function Understanding Block), the engine uses
it for structural awareness before making edits.

### Reading the FUB

```python
def prepare_fub_guidance(capsule):
    """Extract structural guidance from FUB before editing.

    Returns guidance dict. Empty dict if no FUB (Tier 1 fallback).
    """
    fub = capsule.get("fub")
    if not fub:
        return {}

    guidance = {}

    # 1. Branch tree — understand WHERE to edit/insert
    branch_tree = fub.get("branch_tree", [])
    if branch_tree:
        guidance["structure"] = branch_tree
        guidance["insert_depth"] = max(
            (node.get("depth", 0) for node in branch_tree),
            default=1
        )

    # 2. Hazards — adjust editing strategy
    hazards = fub.get("hazards", [])

    if "mixed_rounding" in hazards:
        guidance["rounding_warning"] = (
            "MIXED rounding in this function — some branches use integer "
            "Array6 (banker) and others use decimal (no rounding). "
            "Match the rounding of the NEAREST existing branch."
        )

    if "dual_use_array6" in hazards:
        guidance["array6_warning"] = (
            "DUAL-USE Array6: varRates = Array6(...) is a rate (modify), "
            "but IsItemInArray(Array6(...)) is a test (NEVER modify)."
        )

    if "const_rate_values" in hazards:
        guidance["const_warning"] = (
            "Rate values in Const declarations exist in this function. "
            "If modifying rates, look for Const declarations too."
        )

    if "multi_line_array6" in hazards:
        guidance["multiline_warning"] = (
            "Multi-line Array6 using line continuation ` _`. Treat all "
            "continuation lines as a single logical Array6."
        )

    # 3. Adjacent context — for indentation measurement
    adj = fub.get("adjacent_context", {})
    if adj:
        above_lines = adj.get("above", [])
        if above_lines:
            sample = above_lines[-1].get("content", "")
            actual_indent = len(sample) - len(sample.lstrip())
            guidance["measured_indent"] = actual_indent

    # 4. Peer bodies — structural reference
    peer_bodies = capsule.get("peer_examples", [])
    if peer_bodies:
        best_peer = max(peer_bodies, key=lambda p: p.get("call_sites", 0))
        guidance["peer_template"] = {
            "name": best_peer["name"],
            "body": best_peer.get("body", ""),
        }

    # 5. Nearby functions — dead code warnings
    nearby = fub.get("nearby_functions", [])
    guidance["dead_code_warnings"] = [
        f"{nf['name']} has {nf.get('call_sites', 0)} call sites — DEAD CODE"
        for nf in nearby
        if nf.get("status") == "DEAD" or nf.get("call_sites", 0) == 0
    ]

    return guidance
```

**Rules for FUB-guided editing:**

1. **Read `branch_tree` BEFORE editing.** Understand the nesting structure.
2. **Match indentation from `adjacent_context`**, not assumptions. Especially
   important when hazards include `nested_depth_3plus`.
3. **When inserting Case blocks**, use `branch_tree` to find the parent Select
   Case's depth. Place new Case BEFORE `Case Else`.
4. **When `peer_examples` are available**, copy structure from the peer with the
   HIGHEST `call_sites` — most established pattern.
5. **NEVER copy patterns from dead-code functions** listed in `dead_code_warnings`.

---

## ESTABLISHED PATTERN PREFERENCE

Before generating code that accesses runtime objects, collections, or framework
methods, check for established patterns. This prevents dead-code poisoning.

```python
def check_established_patterns(capsule):
    """Check for established code patterns before generating.

    Sources (in priority order):
    1. code_patterns.canonical_access from Analyzer Step 5.9
    2. peer_examples from capsule (active functions with high call_sites)
    3. FUB nearby_functions (alive/dead signals)
    """
    code_patterns = capsule.get("intent", {}).get("code_patterns", {})
    peer_examples = capsule.get("peer_examples", [])
    fub = capsule.get("fub", {})

    canonical = {}
    warnings = []

    # Source 1: Analyzer-discovered canonical patterns
    for access in code_patterns.get("canonical_access", []):
        canonical[access["need"]] = access["pattern"]

    # Source 2: Peer function style
    active_peers = [p for p in peer_examples
                    if not p.get("dead_code") and p.get("call_sites", 0) > 0]

    # Source 3: Dead code warnings from FUB
    for nf in fub.get("nearby_functions", []):
        if nf.get("call_sites", 0) == 0:
            warnings.append(f"Do NOT copy patterns from {nf['name']} (dead code)")

    return canonical, active_peers, warnings
```

**If established patterns exist:** Use them VERBATIM. Copy structure, naming, and
accessor calls from the `example_snippet`. Adjust indentation only.

**If NO patterns found:** Fall back to live investigation — read 3 similar files
via Glob, extract the common structure, use as template. The Change Engine never
generates code blind.

---

## VBPROJ MANAGEMENT

For file_creation intents, the engine must add a `<Compile Include>` entry to
the target .vbproj.

```python
import re

def update_vbproj(codebase_root, vbproj_rel_path, new_file_rel_path):
    """Add <Compile Include> entry for a new file.

    Finds the ItemGroup with existing Code/ Compile Includes and appends
    the new entry before </ItemGroup>.
    """
    vbproj_path = os.path.join(codebase_root, vbproj_rel_path)
    if not os.path.exists(vbproj_path):
        return FAIL(f"VBPROJ not found: {vbproj_rel_path}")

    with open(vbproj_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Build include path (relative from version folder to Code/)
    filename = os.path.basename(new_file_rel_path)
    include_path = f"..\\..\\Code\\{filename}"

    # Idempotency check
    if include_path in content:
        return SKIPPED(f"Compile Include already exists for {filename}")

    # Find ItemGroup with Code\ references
    pattern = re.compile(
        r'(.*<Compile\s+Include="[^"]*\\Code\\[^"]*"[^/]*/>\s*\n)'
        r'(\s*)(</ItemGroup>)',
        re.DOTALL
    )

    match = None
    for m in pattern.finditer(content):
        match = m

    if not match:
        return FAIL("Cannot find suitable ItemGroup for Compile Include")

    new_entry = f'\t\t<Compile Include="{include_path}"/>\n'
    insert_pos = match.start(match.lastindex)
    new_content = content[:insert_pos] + new_entry + content[insert_pos:]

    with open(vbproj_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return OK
```

**Key conventions:**
- Tab indentation for XML elements (2 tabs for `<Compile Include>` lines)
- Self-closing tag: `<Compile Include="..\..\Code\{filename}.vb"/>`
- Backslashes in paths (Windows convention in .vbproj)
- Insert before `</ItemGroup>`, not alphabetically sorted

---

## STRATEGY LOADING

When the capsule includes a `strategy_hint`, the orchestrator pre-loads the
relevant section from `strategies.md` into `strategy_reference`. The engine reads
this as guidance — "here's how we've handled this kind of change before."

Strategy hints are optional. The engine can reason about any change without one.
But when a hint is provided, it helps the engine avoid common pitfalls and follow
established patterns.

Available strategy hints (map to sections in strategies.md):
- `array6-multiply` — Array6 value changes with multipliers and rounding
- `factor-table` — Select Case factor/limit value replacements
- `case-block-insertion` — Adding new Case entries to Select Case structures
- `constant-management` — Adding or modifying Const declarations
- `new-file-creation` — Creating Option_*.vb / Liab_*.vb from templates
- `expressions` — Handling arithmetic expressions in Array6 values

---

## EDGE CASE HANDLING

### Sentinel Values
If a value is -999 or all zeros in an Array6, SKIP it during multiplication.
Zero times anything is zero. -999 is a sentinel — modifying it would break
the business logic.

### IsItemInArray(Array6(...))
Array6 inside `IsItemInArray()` is a membership test, NOT a rate value. NEVER
modify these. The Analyzer should have excluded them via `skipped_lines`. If
one is found in target_lines, ABORT immediately.

### Enum Collection Array6
Array6 calls like `varCovTypes = Array6(TBWApplication.BasePremEnum.bpeTPLBI, ...)`
are enum collections, NOT rate values. Identified by member-access syntax (letter
dot letter) in arguments. NEVER modify.

### String Case Values
Some `Case` statements use string values: `Case "5000"`, `Case "Policy Limits"`.
Match strings exactly, including quotes.

### Case Syntax Variations
The codebase contains multiple Case formats:
- `Case 5000` (numeric literal)
- `Case "5000"` (string literal)
- `Case 0 To 25` (range)
- `Case Is <= 3000` (comparison)
- `Case "Policy Limits", "Unlimited Form"` (multi-value)

### Multi-Line Array6
Some Array6 calls use ` _` line continuation. Treat all continuation lines as
a single logical Array6. Preserve the ` _` structure in the output.

### Implicit Line Continuation
VB.NET 10+ allows continuation after `+`, `-`, `*`, `/`, commas, and open parens
without a trailing `_`. Join such continued lines before parsing.

### GoTo Statements
Some functions contain `GoTo` for non-linear flow. The engine handles existing
GoTo when inserting into such functions but NEVER introduces new GoTo patterns.

### Duplicate Array6 Lines
Identical Array6 content may appear at multiple lines (e.g., Farm vs Home tiers).
Use `context_above`/`context_below` to disambiguate (Rule 12).

### Function-Local Constants
`Const dblMultiVehicleDis As Double = -0.1` inside a function body (not module
level). Treat the same as module-level Const for value replacement.

### Already-Applied Changes
If the target value already matches the expected result, report `status: "SKIPPED"`
(not "FAILED"). This makes re-execution safe.

---

## KEY RESPONSIBILITIES

1. **Read the intent and target code** before making any edit
2. **Locate targets by content match** — line numbers are hints, content is truth
3. **Reason about the change** — use strategy guidance when available
4. **Apply precise edits** preserving all VB.NET formatting
5. **Verify every edit** by re-reading the modified file
6. **Execute bottom-to-top** within each file
7. **Skip commented lines** — never modify code starting with `'`
8. **Handle rounding correctly** — banker's for integers, preserve precision for decimals
9. **Log every change** with before/after for the operations log
10. **Detect already-applied changes** and report as skipped
11. **Create new files** from templates when the intent requires it
12. **Update .vbproj** for every new file created

**Responsibilities handled by the orchestrator:**

| Responsibility | Handled By |
|---------------|-----------|
| File copying (Code/ files to new dates) | File-copier worker |
| .vbproj reference updates for copies | File-copier worker |
| Snapshot creation/restoration | /iq-execute orchestrator |
| TOCTOU hash verification | /iq-execute orchestrator |
| Hash update after modification | /iq-execute orchestrator |
| Capsule building and ordering | /iq-execute orchestrator |
| Checkpoint tracking (crash recovery) | /iq-execute orchestrator |

---

## LOADING STRATEGY REFERENCE

After reading this core contract, if the capsule includes a `strategy_hint`,
read the corresponding section from `strategies.md` for additional guidance.
The strategy reference is informational — it helps the engine avoid pitfalls
but does not constrain what it can do.
