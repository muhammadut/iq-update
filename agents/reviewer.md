# Agent: Reviewer

## Purpose

Validate all changes and produce the approval document presented at Gate 2. Run
all 7 validators, produce a traceability matrix, a diff report, and a clean change
summary suitable for SVN commit message.

## Pipeline Position

```
[INPUT] --> Intake --> Decomposer --> Analyzer --> Planner --> [GATE 1] --> Modifiers --> REVIEWER --> [GATE 2]
                                                                                        ^^^^^^^^
```

- **Upstream:** Rate Modifier and Logic Modifier agents (provide modified source files + `execution/operations_log.yaml`)
- **Downstream:** Developer reviews at Gate 2; `summary/change_summary.md` used for SVN commit message

## Input Schema

```yaml
# Reads: manifest.yaml (workflow metadata)
# Reads: parsed/change_spec.yaml (original SRDs for traceability)
# Reads: parsed/srds/srd-NNN.yaml (individual SRD details)
# Reads: analysis/operations/op-NNN.yaml (all operations with line numbers)
# Reads: analysis/files_to_copy.yaml (which files were copied)
# Reads: execution/operations_log.yaml (what was actually done)
# Reads: execution/file_hashes.yaml (file hashes)
# Reads: execution/snapshots/*.snapshot (pre-edit file copies)
# Reads: all modified source files (current state)
# Reads: validators/*.py (validation scripts)
```

## Output Schema

```yaml
# File: verification/validator_results.yaml
workflow_id: "20260101-SK-Hab-rate-update"
validated_at: "2026-01-15T11:10:00Z"
total_validators: 7
passed: 7
failed: 0
blockers: 0
warnings: 0
self_corrections_applied: 0

results:
  - validator: "validate_array6"
    severity: "BLOCKER"
    passed: true
    self_corrected: false
    message: "All Array6() calls have matching parentheses, argument counts unchanged"
    details: []

  - validator: "validate_completeness"
    severity: "BLOCKER"
    passed: true
    self_corrected: false
    message: "All 15 territories updated, all 6 LOBs handled"
    details: []

  - validator: "validate_no_old_modify"
    severity: "BLOCKER"
    passed: true
    self_corrected: false
    message: "Only target-date files modified, all .vbproj refs updated"
    details: []

  - validator: "validate_no_commented_code"
    severity: "BLOCKER"
    passed: true
    self_corrected: false
    message: "No commented lines were modified"
    details: []

  - validator: "validate_value_sanity"
    severity: "WARNING"
    passed: true
    self_corrected: false
    message: "All rate changes within expected range (max 5.2%)"
    details: []

  - validator: "validate_cross_lob"
    severity: "WARNING"
    passed: true
    self_corrected: false
    message: "Shared module consistent across all 6 LOBs"
    details: []

  - validator: "validate_traceability"
    severity: "WARNING"
    passed: true
    self_corrected: false
    message: "All 3 SRDs traced to code changes"
    details: []
```

```markdown
# File: verification/traceability_matrix.md

TRACEABILITY: SRD -> Code Changes
=================================

srd-001: Increase base rates by 5%
  [OK] mod_Common_SKHab20260101.vb:352-366 -- 15 territories x 6 values = 90 changes
  [OK] All values within 4.9%-5.2% of target (rounding)

srd-002: Change $5000 deductible factor
  [OK] mod_Common_SKHab20260101.vb:672 -- Case 5000: -0.20 -> -0.22

srd-003: Add Elite Comp coverage type
  [OK] mod_Common_SKHab20260101.vb:22 -- ELITECOMP constant
  [OK] mod_Common_SKHab20260101.vb:440-445 -- Rate table selection
  [OK] Saskatchewan/Home/20260101/ResourceID.vb:146-147 -- DAT IDs
  [OK] Saskatchewan/Condo/20260101/ResourceID.vb:146-147 -- DAT IDs
  ... (one per LOB)

UNTRACED SRDs: 0
ORPHAN CHANGES (changes not linked to any SRD): 0
```

```markdown
# File: verification/diff_report.md

DIFF REPORT: Saskatchewan Habitational 2026-01-01
==================================================

--- Saskatchewan/Code/mod_Common_SKHab20260101.vb
+++ Saskatchewan/Code/mod_Common_SKHab20260101.vb (modified)

  @@ line 22 @@
  + Public Const ELITECOMP As String = "Elite Comp."   ' SRD-003

  @@ lines 350-366 (GetBasePremium_Home) @@
  - Case 1 : varRates = Array6(basePremium, 233, 274, 319, 372, 432, 502)
  + Case 1 : varRates = Array6(basePremium, 245, 288, 335, 391, 454, 527)
  ... (all territory changes)

  @@ line 672 (SetDisSur_Deductible) @@
  - Case 5000 : dblDedDiscount = -0.20
  + Case 5000 : dblDedDiscount = -0.22

Total: 3 files modified, 97 lines changed
```

```
# File: verification/changes.diff
# Standard unified diff format -- reviewable in any diff tool
# (full unified diff output)
```

```markdown
# File: summary/change_summary.md

RATE UPDATE: Saskatchewan Habitational 2026-01-01
Ticket: DevOps 24778
IQ-Workflow: 20260101-SK-Hab-rate-update

Changes:
  - Base rates increased 5% across all territories (90 value changes)
  - $5000 deductible factor: -20% -> -22%
  - Added Elite Comp coverage type (constant, rate table routing, DAT IDs)

Files modified:
  - Saskatchewan/Code/mod_Common_SKHab20260101.vb (shared across 6 LOBs)
  - Saskatchewan/Home/20260101/ResourceID.vb
  - Saskatchewan/Condo/20260101/ResourceID.vb
  - Saskatchewan/Tenant/20260101/ResourceID.vb
  - Saskatchewan/FEC/20260101/ResourceID.vb
  - Saskatchewan/Farm/20260101/ResourceID.vb
  - Saskatchewan/Seasonal/20260101/ResourceID.vb

Files created (new Code/ copies):
  - Saskatchewan/Code/mod_Common_SKHab20260101.vb (from mod_Common_SKHab20250901.vb)

.vbproj references updated: 6

Validation: 7/7 checks passed (0 BLOCKERs, 0 WARNINGs)
```

## Validators

| # | Validator | Severity | What It Checks |
|---|-----------|----------|----------------|
| 1 | validate_array6 | BLOCKER | Matching parens, arg count unchanged, no empty args, values reasonable |
| 2 | validate_completeness | BLOCKER | All territories updated, all LOBs in multi-LOB ticket handled |
| 3 | validate_no_old_modify | BLOCKER | Only target-date files edited, old files untouched, .vbproj refs updated |
| 4 | validate_no_commented_code | BLOCKER | No commented lines (starting with ') were changed |
| 5 | validate_value_sanity | WARNING | Rate changes within expected range (flags > 50% as suspicious) |
| 5.1 | validate_semantic_spotcheck | WARNING | Spot-check: re-derive sample values from SRD formula, compare to actual |
| 6 | validate_cross_lob | WARNING | Shared module consistent across all LOBs |
| 7 | validate_traceability | WARNING | Every SRD maps to at least one file:line change |

**BLOCKERs prevent Gate 2 approval.** The Reviewer will attempt to self-correct
BLOCKER failures by restoring from snapshots and re-applying. If self-correction
fails, the developer is asked to intervene.

**WARNINGs are informational.** Shown to the developer but don't block approval.

## Key Responsibilities

- Run all 7 validators and aggregate results
- Produce traceability matrix (every SRD maps to file:line changes)
- Produce human-readable diff report
- Produce unified diff (changes.diff) for external diff tools
- Produce clean change summary suitable for SVN commit message
- Clearly separate BLOCKERs from WARNINGs
- On BLOCKER failure: attempt self-correction via snapshot restore + re-apply
- On persistent BLOCKER failure: present error to developer with recovery options
- Include workflow ID in change summary for bidirectional audit trail
- Prompt developer to record SVN revision after commit

## Edge Cases

1. **BLOCKER validator fails:** Attempt self-correction (restore snapshot, re-apply), then re-validate
2. **Self-correction fails:** Present error details to developer, suggest manual intervention
3. **WARNING with large deviation:** Value sanity flags 52% change -- show to developer, let them decide
4. **Orphan changes:** Changes in operations_log that don't map to any SRD -- flag as suspicious
5. **Missing SRD trace:** An SRD has no corresponding code change -- flag as incomplete
6. **Re-validation requested:** Developer says "re-run validation" -- run all validators again on current file state
7. **Developer rejects at Gate 2:** Identify which changes need fixing, re-enter modifier phase

---

## Execution Steps

12 steps the Reviewer agent follows when launched by the `/iq-review` orchestrator.
The orchestrator splits these across 3 sub-agents (validator, diff, report), but
this spec describes the FULL logical flow. Each sub-agent reads the relevant steps.

```
Validator agent:  Steps 1-7  (load, inventory, verify, validate, self-correct, write results)
Diff agent:       Steps 8-9  (generate diff, traceability matrix)
Report agent:     Steps 10-12 (change summary, corrections, signal completion)
```

---

### Step 1: Load Context

#### Variables Available to All Steps

The following variables are resolved once at startup and available throughout:

```python
# Resolved by the orchestrator before launching the Reviewer agent:
carrier_root     = Path(manifest["codebase_root"])       # e.g., "E:/intelli-new/Cssi.Net/Portage Mutual"
workstreams_root = carrier_root / ".iq-workstreams"       # e.g., carrier_root / ".iq-workstreams"
workstream_dir   = workstreams_root / "changes" / manifest["workstream_name"]

# Severity markers used in pseudocode (not real functions — shorthand for result recording):
# FAIL(msg)    → append to findings with severity="BLOCKER", set passed=False
# WARNING(msg) → append to findings with severity="WARNING", passed remains True
# read_yaml(path) → load YAML file and return parsed dict
```

---

Read all input files and validate preconditions.

```python
def step_1_load_context(workstream_dir):
    """Load and validate all inputs.

    Reads: manifest.yaml, config.yaml, operations_log.yaml, file_hashes.yaml.
    Validates: state is EXECUTED or VALIDATING.
    """
    manifest = read_yaml(workstream_dir / "manifest.yaml")
    config = read_yaml(workstreams_root / "config.yaml")  # workstreams_root defined in Variables preamble

    assert manifest["state"] in ("EXECUTED", "VALIDATING"), \
        f"Expected EXECUTED or VALIDATING, got {manifest['state']}"

    ops_log = read_yaml(workstream_dir / "execution/operations_log.yaml")
    file_hashes = read_yaml(workstream_dir / "execution/file_hashes.yaml")
    change_spec = read_yaml(workstream_dir / "parsed/change_spec.yaml")

    # Load all SRD files
    srds = {}
    for srd_file in glob(workstream_dir / "parsed/srds/srd-*.yaml"):
        srd = read_yaml(srd_file)
        srds[srd["id"]] = srd

    # Load all operation files
    operations = {}
    for op_file in glob(workstream_dir / "analysis/operations/op-*.yaml"):
        op = read_yaml(op_file)
        operations[op["id"]] = op

    return manifest, config, ops_log, file_hashes, change_spec, srds, operations
```

---

### Step 2: Inventory Modified Files

Build a categorized list of all files touched during `/iq-execute`.

```python
def step_2_inventory(ops_log, file_hashes, carrier_root):
    """Build file inventory from operations_log.

    Categorize files into: rate-modifier, logic-modifier, new (no snapshot).
    Verify each file exists on disk.
    """
    inventory = {
        "rate_modifier_files": set(),
        "logic_modifier_files": set(),
        "new_files": set(),          # Created by logic-modifier, no snapshot
        "all_files": set(),
    }

    for entry in ops_log.get("operations", []):
        filepath = entry["file"]
        agent = entry["agent"]
        full_path = carrier_root / filepath

        if not full_path.exists():
            FAIL(f"File missing from disk: {filepath}")

        inventory["all_files"].add(filepath)

        if agent == "rate-modifier" or agent == "orchestrator":
            inventory["rate_modifier_files"].add(filepath)
        elif agent == "logic-modifier":
            inventory["logic_modifier_files"].add(filepath)
            if entry.get("summary", {}).get("new_file_created"):
                inventory["new_files"].add(filepath)

    # Cross-check: every file in file_hashes should be in inventory or be a source
    # NOTE: file_hashes["files"] is a dict keyed by filepath (from Planner)
    for filepath, fh_info in file_hashes.get("files", {}).items():
        if fh_info["role"] == "target" and filepath not in inventory["all_files"]:
            WARNING(f"File in hashes but not in ops_log: {filepath}")

    return inventory
```

---

### Step 3: Verify File Integrity (TOCTOU)

Detect if any file was modified outside the plugin between `/iq-execute` and
`/iq-review`.

```python
import hashlib

def step_3_verify_integrity(file_hashes, carrier_root):
    """Compare current SHA-256 hashes to stored post-execution hashes.

    If mismatch: file was modified outside the plugin. Flag but don't abort --
    the developer decides at Gate 2.
    """
    mismatches = []

    # NOTE: file_hashes["files"] is a dict keyed by filepath (from Planner)
    for filepath, fh_info in file_hashes.get("files", {}).items():
        path = carrier_root / filepath
        if not path.exists():
            mismatches.append({
                "file": filepath,
                "issue": "file_missing",
                "expected_hash": fh_info["hash"],
                "actual_hash": None,
            })
            continue

        current_hash = "sha256:" + hashlib.sha256(
            open(path, "rb").read()
        ).hexdigest()

        if current_hash != fh_info["hash"]:
            mismatches.append({
                "file": filepath,
                "issue": "hash_mismatch",
                "expected_hash": fh_info["hash"],
                "actual_hash": current_hash,
                "role": fh_info["role"],
            })

    if mismatches:
        # Don't abort -- log and let the developer decide at Gate 2
        WARNING(f"{len(mismatches)} file(s) have hash mismatches")

    return mismatches
```

---

### Step 4: Run BLOCKER Validators (1-4)

Run the four BLOCKER validators. If any fails, attempt self-correction in Step 5.

#### Step 4a: Array6 Syntax Validator

```python
def validate_array6(ops_log, inventory, carrier_root, snapshots_dir):
    """BLOCKER: Verify all Array6() calls have correct syntax and arg counts.

    Checks:
    1. Matching parentheses in every Array6() call
    2. Arg count identical to snapshot (before) version
    3. No empty args (no ,, pattern)
    4. Skip dual-use: IsItemInArray(x, Array6(...)) is a test, not a rate

    Uses depth-aware comma splitting -- see Section 6 for full algorithm.
    """
    findings = []

    for entry in ops_log.get("operations", []):
        if entry["agent"] not in ("rate-modifier", "orchestrator"):
            continue
        if entry["status"] != "COMPLETED":
            continue

        for change in entry.get("changes", []):
            before_line = change.get("before", "")
            after_line = change.get("after", "")

            # Skip if no Array6 in either line
            if "Array6" not in (before_line or "") and "Array6" not in (after_line or ""):
                continue

            # Skip dual-use: Array6 inside another function call (test/lookup)
            if is_array6_test_usage(after_line):
                continue

            before_count = count_array6_args(before_line) if before_line else 0
            after_count = count_array6_args(after_line) if after_line else 0

            if before_count != after_count and before_count > 0:
                findings.append({
                    "file": entry["file"],
                    "line": change["line"],
                    "operation": entry["operation"],
                    "expected_args": before_count,
                    "actual_args": after_count,
                    "before": before_line.strip(),
                    "after": after_line.strip(),
                })

            # Check for empty args pattern
            if after_line and ",," in after_line:
                findings.append({
                    "file": entry["file"],
                    "line": change["line"],
                    "operation": entry["operation"],
                    "issue": "empty_arg",
                    "after": after_line.strip(),
                })

            # Check matching parentheses
            if after_line and not parens_balanced(after_line):
                findings.append({
                    "file": entry["file"],
                    "line": change["line"],
                    "operation": entry["operation"],
                    "issue": "unmatched_parens",
                    "after": after_line.strip(),
                })

    # ALSO: Full-file scan of every modified file for corrupt Array6 calls
    for filepath in inventory["rate_modifier_files"]:
        full_path = carrier_root / filepath
        lines = open(full_path, "r").readlines()
        for i, line in enumerate(lines):
            if "Array6" not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("'"):
                continue  # Skip comments
            if is_array6_test_usage(line):
                continue
            if not parens_balanced(line):
                findings.append({
                    "file": filepath,
                    "line": i + 1,
                    "issue": "unmatched_parens_fullscan",
                    "content": stripped[:120],
                })

    return ValidatorResult(
        validator_name="validate_array6",
        severity="BLOCKER",
        passed=len(findings) == 0,
        message=_array6_message(findings),
        details=findings,
    )


def is_array6_test_usage(line):
    """Detect dual-use: Array6 inside another function call is a test, not a rate.

    Rate usage:   varRates = Array6(...)
    Test usage:   IsItemInArray(x, Array6(...))
                  UBound(Array6(...))
    """
    import re
    if not line or "Array6" not in line:
        return False
    # If Array6 is on the RHS of an assignment, it's a rate
    # Pattern: identifier = Array6(...)  OR  identifier = Array6(...)
    if re.search(r'\w+\s*=\s*Array6\s*\(', line):
        return False
    # Otherwise it's a test/lookup argument
    return True
```

#### Step 4b: Completeness Validator

```python
def validate_completeness(ops_log, operations, workstream_dir, carrier_root, snapshots_dir):
    """BLOCKER: Verify every planned operation was executed.

    Checks:
    1. Every op-*.yaml has a corresponding entry in operations_log
    2. No operation has status FAILED (unless developer accepted)
    3. Territory counting: for territory-based changes, count Case branches
       in the snapshot and confirm all were updated
    4. LOB completeness: for multi-LOB hab tickets, all LOBs handled
    """
    findings = []

    # Check 1: Every planned operation has a log entry
    logged_ops = {e["operation"] for e in ops_log.get("operations", [])}
    for op_id, op_spec in operations.items():
        if op_id not in logged_ops:
            findings.append({
                "operation": op_id,
                "issue": "not_in_log",
                "message": f"Operation {op_id} planned but not in operations_log",
            })

    # Check 2: No FAILED operations (SKIPPED is OK)
    for entry in ops_log.get("operations", []):
        if entry["status"] == "FAILED":
            findings.append({
                "operation": entry["operation"],
                "issue": "failed",
                "message": f"Operation {entry['operation']} has status FAILED",
                "file": entry.get("file"),
            })

    # Check 3: Territory counting for territory-based operations
    #   Uses Algorithm 3 (count_territories_in_function) to verify against
    #   the SNAPSHOT (original file), not just the op-*.yaml target_lines count.
    for entry in ops_log.get("operations", []):
        if entry["status"] != "COMPLETED":
            continue
        op_spec = operations.get(entry["operation"])
        if not op_spec:
            continue
        if op_spec.get("pattern") != "base_rate_increase":
            continue

        # Count territories from snapshot (ground truth)
        snapshot_path = workstream_dir / "execution/snapshots" / (
            Path(entry["file"]).name + ".snapshot"
        )
        if snapshot_path.exists() and op_spec.get("function"):
            snapshot_territory_count = count_territories_in_function(
                snapshot_path, op_spec["function"]
            )
        else:
            # Fallback: use op-*.yaml target_lines count
            snapshot_territory_count = len(op_spec.get("target_lines", []))

        actual_count = len(entry.get("changes", []))
        if snapshot_territory_count > 0 and actual_count != snapshot_territory_count:
            findings.append({
                "operation": entry["operation"],
                "issue": "territory_count_mismatch",
                "expected": snapshot_territory_count,
                "actual": actual_count,
                "message": f"Expected {snapshot_territory_count} territories, got {actual_count}",
            })

    # Check 4: LOB completeness for multi-LOB hab tickets
    #   If manifest indicates multiple LOBs sharing a module, verify all LOBs
    #   have at least one COMPLETED operation in the operations_log.
    shared_modules = manifest.get("shared_modules", [])
    if shared_modules and len(manifest.get("lobs", [])) > 1:
        lobs_with_ops = set()
        for entry in ops_log.get("operations", []):
            if entry["status"] == "COMPLETED":
                # Extract LOB from file path (e.g., "Saskatchewan/Home/..." -> "Home")
                parts = Path(entry["file"]).parts
                if len(parts) >= 2:
                    lobs_with_ops.add(parts[1])
        expected_lobs = set(manifest.get("lobs", []))
        missing_lobs = expected_lobs - lobs_with_ops
        for lob in missing_lobs:
            findings.append({
                "issue": "lob_missing",
                "lob": lob,
                "message": f"LOB {lob} has no completed operations in a multi-LOB ticket",
            })

    return ValidatorResult(
        validator_name="validate_completeness",
        severity="BLOCKER",
        passed=len(findings) == 0,
        message=_completeness_message(findings, operations),
        details=findings,
    )
```

#### Step 4c: No Old File Modification Validator

```python
def validate_no_old_modify(file_hashes, carrier_root, manifest):
    """BLOCKER: Verify original source files were not modified.

    Args:
        file_hashes: Parsed file_hashes.yaml (dict with "files" key)
        carrier_root: Path to the carrier root directory
        manifest: Parsed manifest.yaml (needed for effective_date)

    Checks:
    1. Every file with role="source" has an unchanged hash
    2. No file outside the target date folder was modified
    3. All .vbproj Compile Include refs point to new-dated files
    """
    findings = []

    # NOTE: file_hashes["files"] is a dict keyed by filepath (from Planner)
    for filepath, fh_info in file_hashes.get("files", {}).items():
        if fh_info["role"] != "source":
            continue

        path = carrier_root / filepath
        if not path.exists():
            findings.append({
                "file": filepath,
                "issue": "source_file_missing",
            })
            continue

        current_hash = "sha256:" + hashlib.sha256(
            open(path, "rb").read()
        ).hexdigest()

        if current_hash != fh_info["hash"]:
            findings.append({
                "file": filepath,
                "issue": "source_modified",
                "expected_hash": fh_info["hash"],
                "actual_hash": current_hash,
            })

    # Check .vbproj references: all Compile Include paths should reference
    # the target date, not the old date
    for filepath, fh_info in file_hashes.get("files", {}).items():
        if not filepath.endswith(".vbproj"):
            continue
        vbproj_findings = check_vbproj_refs(
            carrier_root / filepath,
            manifest["effective_date"],  # from manifest, not file_hashes
        )
        findings.extend(vbproj_findings)

    return ValidatorResult(
        validator_name="validate_no_old_modify",
        severity="BLOCKER",
        passed=len(findings) == 0,
        message=_no_old_modify_message(findings),
        details=findings,
    )
```

#### Step 4d: No Commented Code Modified Validator

```python
def validate_no_commented_code(ops_log):
    """BLOCKER: Verify no commented-out lines were modified.

    Rule: A line is a comment if its first non-whitespace character is '
    VB.NET only uses ' for comments (no REM in this codebase, no block comments).

    Inline comments (code followed by ') are NOT full-line comments.
    Modifying the code portion of a line with an inline comment is OK.
    """
    findings = []

    for entry in ops_log.get("operations", []):
        if entry["status"] != "COMPLETED":
            continue
        for change in entry.get("changes", []):
            before_line = change.get("before")
            if before_line is None:
                continue  # Pure insertion (logic-modifier) -- no before line

            # Check if the ORIGINAL line was a full-line comment
            if before_line.strip().startswith("'"):
                findings.append({
                    "file": entry["file"],
                    "line": change["line"],
                    "operation": entry["operation"],
                    "issue": "commented_line_modified",
                    "before": before_line.strip(),
                    "after": change.get("after", "").strip(),
                })

            # Also check if only the inline comment portion was changed
            # (code before ' is the same, only comment text after ' changed)
            if is_inline_comment_only_change(before_line, change.get("after", "")):
                findings.append({
                    "file": entry["file"],
                    "line": change["line"],
                    "operation": entry["operation"],
                    "issue": "inline_comment_only_change",
                    "before": before_line.strip(),
                    "after": change.get("after", "").strip(),
                })

    # Count commented lines that were correctly LEFT UNTOUCHED (for developer confidence)
    commented_lines_untouched = 0
    for entry in ops_log.get("operations", []):
        if entry["status"] != "COMPLETED":
            continue
        # Check surrounding context -- if any skipped_lines in op-spec were comments
        op_spec = operations.get(entry["operation"], {})
        for sl in op_spec.get("skipped_lines", []):
            if sl.get("reason") == "commented":
                commented_lines_untouched += 1

    return ValidatorResult(
        validator_name="validate_no_commented_code",
        severity="BLOCKER",
        passed=len(findings) == 0,
        message=_commented_code_message(findings, commented_lines_untouched),
        details=findings,
    )
```

---

### Step 5: Handle BLOCKER Failures (Self-Correction)

If any BLOCKER validator fails, attempt ONE self-correction per validator:
restore from snapshot, re-apply all operations for the affected file, re-validate.

```python
def step_5_self_correct(failed_validators, ops_log, operations, carrier_root,
                        snapshots_dir, workstream_dir):
    """Attempt self-correction for BLOCKER failures.

    Strategy: snapshot-restore-reapply (database-like rollback+replay).

    CRITICAL: Restoring a file from snapshot reverts ALL changes to that file.
    Therefore we must re-apply ALL operations for that file, not just the failing one.

    Max 1 retry per BLOCKER. If retry fails, mark as unresolvable.
    """
    corrections = []

    for vr in failed_validators:
        if vr.severity != "BLOCKER" or vr.passed:
            continue

        # Identify affected files from the validator details
        affected_files = set()
        for detail in vr.details:
            if "file" in detail:
                affected_files.add(detail["file"])

        for filepath in affected_files:
            snapshot_path = snapshots_dir / f"{basename(filepath)}.snapshot"
            target_path = carrier_root / filepath

            if not snapshot_path.exists():
                corrections.append({
                    "file": filepath,
                    "validator": vr.validator_name,
                    "action": "SKIP",
                    "reason": "No snapshot available",
                    "result": "UNRESOLVABLE",
                })
                continue

            # 1. Restore from snapshot
            copy_file(snapshot_path, target_path)

            # 2. Re-apply ALL operations for this file (bottom-to-top order)
            file_ops = [
                e for e in ops_log.get("operations", [])
                if e["file"] == filepath and e["status"] == "COMPLETED"
            ]
            # Sort by line number descending (bottom-to-top)
            file_ops_sorted = sorted(
                file_ops,
                key=lambda e: max(c["line"] for c in e.get("changes", [{"line": 0}])),
                reverse=True,
            )

            reapply_success = True
            for op_entry in file_ops_sorted:
                op_spec = operations.get(op_entry["operation"])
                if op_spec:
                    result = reapply_operation(target_path, op_spec)
                    if not result.ok:
                        reapply_success = False
                        break

            # 3. Update file hash after re-apply
            new_hash = "sha256:" + hashlib.sha256(
                open(target_path, "rb").read()
            ).hexdigest()
            update_file_hash(workstream_dir, filepath, new_hash)

            # 4. Re-run the failing validator
            re_result = rerun_validator(vr.validator_name, ...)

            corrections.append({
                "file": filepath,
                "validator": vr.validator_name,
                "original_error": vr.details[0].get("message", str(vr.details[0])),
                "action": "snapshot_restore_reapply",
                "operations_reapplied": [e["operation"] for e in file_ops_sorted],
                "re_validated": re_result.passed,
                "result": "PASSED" if re_result.passed else "UNRESOLVABLE",
                "timestamp": now_utc(),
            })

            # Update the validator result if self-correction succeeded
            if re_result.passed:
                vr.passed = True
                vr.self_corrected = True
                vr.message += " (self-corrected)"

    return corrections
```

**Helper: `reapply_operation()`**

```python
def reapply_operation(target_path, op_spec):
    """Re-apply a single operation to a restored file.

    Handles both agent types:
    - Rate Modifier (agent="rate-modifier"): line replacement (before -> after)
    - Logic Modifier (agent="logic-modifier"): insertion (change_type="insert")

    Returns a result object with .ok (bool) and .error (str or None).
    """
    lines = open(target_path, "r").readlines()

    for change in reversed(op_spec.get("changes", [])):
        line_idx = change["line"] - 1  # 0-indexed

        if change.get("change_type") == "insert":
            # Logic modifier: insert new lines at position
            insert_lines = change["after"].split("\n")
            for i, il in enumerate(insert_lines):
                lines.insert(line_idx + i, il + "\n")
        else:
            # Rate modifier: replace existing line
            if line_idx < len(lines):
                lines[line_idx] = change["after"] + "\n"
            else:
                return Result(ok=False, error=f"Line {change['line']} out of range")

    open(target_path, "w").writelines(lines)
    return Result(ok=True, error=None)


def update_file_hash(workstream_dir, filepath, new_hash):
    """Update file_hashes.yaml with a new hash for the given filepath."""
    fh_path = workstream_dir / "execution/file_hashes.yaml"
    fh = read_yaml(fh_path)
    if filepath in fh.get("files", {}):
        fh["files"][filepath]["hash"] = new_hash
    write_yaml(fh_path, fh)
```

**When self-correction should NOT be attempted:**

- Logic errors (wrong values computed) -- re-applying produces same wrong result
- Missing operations (SKIPPED/FAILED upstream) -- nothing to re-apply
- TOCTOU violations (file modified externally) -- warn developer instead
- Cross-file dependencies (file A depends on file B) -- fixing A alone may not help

---

### Step 6: Run WARNING Validators (5-7)

WARNING validators do not block Gate 2. They flag suspicious conditions for
developer review.

#### Step 6a: Value Sanity Validator

```python
def validate_value_sanity(ops_log):
    """WARNING: Flag rate changes exceeding 50% or involving sentinel values.

    Computes percentage change per modified value. Reports min/max across all.
    Handles edge cases: zero-to-nonzero, negative values, arithmetic expressions.
    """
    findings = []
    all_pct_changes = []

    for entry in ops_log.get("operations", []):
        if entry["agent"] not in ("rate-modifier", "orchestrator"):
            continue
        if entry["status"] != "COMPLETED":
            continue

        for change in entry.get("changes", []):
            before_line = change.get("before", "")
            after_line = change.get("after", "")

            if not before_line or not after_line:
                continue

            before_args = parse_array6_values(before_line)
            after_args = parse_array6_values(after_line)

            if before_args is None or after_args is None:
                # Not an Array6 line -- check for factor_table single-value change
                before_val = extract_numeric_value(before_line)
                after_val = extract_numeric_value(after_line)
                if before_val is not None and after_val is not None:
                    pct = compute_pct_change(before_val, after_val)
                    _check_value(findings, all_pct_changes, entry, change,
                                 before_val, after_val, pct)
                continue

            for i, (bv, av) in enumerate(zip(before_args, after_args)):
                if bv is None or av is None:
                    continue  # Variable or unparseable arg -- skip

                # Sentinel check: -999 should never change
                if bv == -999 and av != -999:
                    findings.append({
                        "file": entry["file"],
                        "line": change["line"],
                        "operation": entry["operation"],
                        "issue": "sentinel_modified",
                        "arg_index": i,
                        "before": bv,
                        "after": av,
                    })
                    continue

                pct = compute_pct_change(bv, av)
                _check_value(findings, all_pct_changes, entry, change, bv, av, pct, i)

    summary = {}
    if all_pct_changes:
        summary["min_pct"] = min(all_pct_changes)
        summary["max_pct"] = max(all_pct_changes)
        summary["mean_pct"] = sum(all_pct_changes) / len(all_pct_changes)

    return ValidatorResult(
        validator_name="validate_value_sanity",
        severity="WARNING",
        passed=len(findings) == 0,
        message=_value_sanity_message(findings, summary),
        details=findings,
    )


def compute_pct_change(before, after):
    """Compute percentage change, handling edge cases.

    0 -> non-zero: return None (report as "new value")
    negative -> negative: use absolute values
    """
    if before == 0:
        return None  # Can't compute percentage from zero baseline
    return abs(after - before) / abs(before) * 100


def _check_value(findings, all_pct, entry, change, bv, av, pct, arg_idx=None):
    """Record a value change, flagging if > 50% or zero-to-nonzero."""
    if pct is None:
        if bv == 0 and av != 0:
            findings.append({
                "file": entry["file"],
                "line": change["line"],
                "operation": entry["operation"],
                "issue": "zero_to_nonzero",
                "arg_index": arg_idx,
                "before": bv,
                "after": av,
            })
        return

    all_pct.append(pct)
    if pct > 50:
        findings.append({
            "file": entry["file"],
            "line": change["line"],
            "operation": entry["operation"],
            "issue": "large_change",
            "arg_index": arg_idx,
            "before": bv,
            "after": av,
            "pct_change": round(pct, 2),
        })
```

#### Step 6a.1: Semantic Spot-Check Validator (NEW)

```python
def validate_semantic_spotcheck(ops_log, srd_files, source_files):
    """WARNING: Re-derive a SAMPLE of values from the SRD formula and compare
    to actual file content. Catches "right syntax, wrong number" errors.

    For each rate-modifier operation with pattern base_rate_increase:
    1. Read the SRD's factor (e.g., 1.05)
    2. Read 3 RANDOM before/after pairs from the operations_log
    3. Compute: expected_after = round(before * factor, precision)
    4. Compare expected_after to actual after value in the log
    5. If ANY mismatch: flag as WARNING with the specific discrepancy

    For factor_table_change operations:
    1. Read old_value and new_value from the SRD
    2. Check that EVERY before value matches old_value and after matches new_value

    This catches:
    - Wrong factor applied (e.g., 1.03 instead of 1.05)
    - Factor applied to values that should be exempt
    - Rounding discrepancies (integer vs decimal)
    - Double-application of a factor
    """
    import random
    findings = []

    for entry in ops_log.get("operations", []):
        if entry["status"] != "COMPLETED":
            continue
        if entry["agent"] != "rate-modifier":
            continue

        srd = load_srd_for_op(entry, srd_files)
        if not srd:
            continue

        changes = entry.get("changes", [])
        if not changes:
            continue

        # Sample up to 3 changes for spot-checking
        sample = random.sample(changes, min(3, len(changes)))

        if srd.get("pattern") == "base_rate_increase":
            factor = srd.get("factor")
            if factor is None:
                continue
            for change in sample:
                before_args = parse_array6_values(change.get("before", ""))
                after_args = parse_array6_values(change.get("after", ""))
                if before_args and after_args:
                    for i, (bv, av) in enumerate(zip(before_args, after_args)):
                        if bv is None or av is None or bv == -999:
                            continue
                        # Determine precision from original value
                        precision = detect_decimal_places_from_value(bv)
                        expected = round(bv * factor, max(precision, 2))
                        if abs(expected - av) > 0.01:
                            findings.append({
                                "file": entry["file"],
                                "line": change["line"],
                                "operation": entry["operation"],
                                "issue": "value_mismatch",
                                "arg_index": i,
                                "before": bv,
                                "expected": expected,
                                "actual": av,
                                "factor": factor,
                            })

        elif srd.get("pattern") == "factor_table_change":
            old_val = srd.get("old_value")
            new_val = srd.get("new_value")
            if old_val is not None and new_val is not None:
                for change in sample:
                    before_val = extract_numeric_value(change.get("before", ""))
                    after_val = extract_numeric_value(change.get("after", ""))
                    if before_val is not None and after_val is not None:
                        if abs(before_val - old_val) > 0.001:
                            findings.append({
                                "file": entry["file"],
                                "line": change["line"],
                                "operation": entry["operation"],
                                "issue": "unexpected_before_value",
                                "expected_before": old_val,
                                "actual_before": before_val,
                            })
                        if abs(after_val - new_val) > 0.001:
                            findings.append({
                                "file": entry["file"],
                                "line": change["line"],
                                "operation": entry["operation"],
                                "issue": "unexpected_after_value",
                                "expected_after": new_val,
                                "actual_after": after_val,
                            })

    return ValidatorResult(
        validator_name="validate_semantic_spotcheck",
        severity="WARNING",
        passed=len(findings) == 0,
        message=_semantic_spotcheck_message(findings),
        details=findings,
    )
```

**Why this matters:** The existing validators check structural correctness (Array6
syntax, arg count, completeness). This spot-check validator adds SEMANTIC verification
— it re-derives values from the original SRD formula and compares to what the worker
actually wrote. If a worker applied a 1.03 factor instead of 1.05, or modified a
value that should have been exempt, this catches it.

**Cost:** Negligible. Reads 3 random samples per operation from the already-loaded
operations_log. No file I/O.

#### Step 6b: Cross-LOB Consistency Validator

```python
def validate_cross_lob(manifest, config, carrier_root):
    """WARNING: Verify shared modules are consistent across all hab LOBs.

    For each shared module (e.g., mod_Common_SKHab20260101.vb):
    1. Find ALL .vbproj files in the province that reference mod_Common
    2. Verify they ALL point to the SAME dated file
    3. If any point to a different date, flag as inconsistent
    """
    findings = []

    shared_modules = manifest.get("shared_modules", [])
    if not shared_modules:
        return ValidatorResult(
            validator_name="validate_cross_lob",
            severity="WARNING",
            passed=True,
            message="No shared modules in this workflow",
            details=[],
        )

    province = manifest["province"]
    target_date = manifest["effective_date"]

    # Find all hab LOBs for this province from config
    hab_lobs = [
        lob for lob in config["provinces"][province]["lobs"]
        if config["provinces"][province]["lobs"][lob].get("is_hab", False)
    ]

    for shared_mod in shared_modules:
        refs_found = {}  # lob -> path referenced in .vbproj

        for lob in hab_lobs:
            # Glob for .vbproj in {Province}/{LOB}/{target_date}/
            vbproj_pattern = carrier_root / province / lob / target_date / "*.vbproj"
            for vbproj_path in glob(vbproj_pattern):
                # Parse .vbproj XML for Compile Include containing mod_Common
                ref_path = find_mod_common_ref(vbproj_path)
                if ref_path:
                    refs_found[lob] = ref_path

        # All refs should resolve to the same physical file
        unique_refs = set(refs_found.values())
        if len(unique_refs) > 1:
            findings.append({
                "shared_module": shared_mod,
                "issue": "inconsistent_refs",
                "refs": refs_found,
                "message": f"{shared_mod} referenced inconsistently across {len(refs_found)} LOBs",
            })

        # Check for missing LOBs (no .vbproj found)
        for lob in hab_lobs:
            if lob not in refs_found:
                findings.append({
                    "shared_module": shared_mod,
                    "issue": "missing_lob_ref",
                    "lob": lob,
                    "message": f"No .vbproj found for {lob}/{target_date}",
                })

    return ValidatorResult(
        validator_name="validate_cross_lob",
        severity="WARNING",
        passed=len(findings) == 0,
        message=_cross_lob_message(findings, shared_modules, hab_lobs),
        details=findings,
    )
```

#### Step 6c: Traceability Validator

```python
def validate_traceability(srds, ops_log):
    """WARNING: Verify every SRD maps to at least one operation, and vice versa.

    Reports:
    - UNTRACED SRDs: SRD with no corresponding operation in operations_log
    - ORPHAN CHANGES: operation in operations_log with no corresponding SRD
    """
    findings = []

    # Build mapping: operation_id -> SRD (from op-*.yaml, each has an srd_ref)
    op_to_srd = {}
    for entry in ops_log.get("operations", []):
        op_id = entry["operation"]
        # Operation IDs follow pattern: op-{SRD_NUM}-{SEQ}
        # e.g., op-001-01 maps to srd-001, op-002-03 maps to srd-002
        srd_num = extract_srd_num(op_id)  # "op-001-01" -> "srd-001"
        if srd_num:
            op_to_srd[op_id] = srd_num

    # Check 1: Every SRD has at least one operation
    ops_by_srd = {}
    for op_id, srd_id in op_to_srd.items():
        ops_by_srd.setdefault(srd_id, []).append(op_id)

    for srd_id in srds:
        if srd_id not in ops_by_srd:
            findings.append({
                "issue": "untraced_srd",
                "srd": srd_id,
                "description": srds[srd_id].get("description", ""),
                "message": f"SRD {srd_id} has no operations in the log",
            })

    # Check 2: Every operation maps to a known SRD
    for entry in ops_log.get("operations", []):
        op_id = entry["operation"]
        if op_id.startswith("rework-"):
            continue  # Rework entries don't map to SRDs
        srd_id = op_to_srd.get(op_id)
        if srd_id and srd_id not in srds:
            findings.append({
                "issue": "orphan_change",
                "operation": op_id,
                "mapped_srd": srd_id,
                "message": f"Operation {op_id} maps to {srd_id} which doesn't exist",
            })

    return ValidatorResult(
        validator_name="validate_traceability",
        severity="WARNING",
        passed=len(findings) == 0,
        message=_traceability_message(findings, srds, ops_by_srd),
        details=findings,
    )
```

---

### Step 7: Write validator_results.yaml

Aggregate all validator results into the output schema.

```python
def step_7_write_results(all_results, workstream_dir, workflow_id):
    """Write verification/validator_results.yaml.

    Schema matches the output schema in Section 4 of this spec, with the
    addition of self_corrected and correction_log fields.
    """
    blocker_fails = sum(
        1 for r in all_results
        if r.severity == "BLOCKER" and not r.passed
    )
    warning_fails = sum(
        1 for r in all_results
        if r.severity == "WARNING" and not r.passed
    )
    self_corrections = sum(
        1 for r in all_results if r.self_corrected
    )

    output = {
        "workflow_id": workflow_id,
        "validated_at": now_utc(),
        "total_validators": len(all_results),
        "passed": sum(1 for r in all_results if r.passed),
        "failed": sum(1 for r in all_results if not r.passed),
        "blockers": blocker_fails,
        "warnings": warning_fails,
        "self_corrections_applied": self_corrections,
        "results": [
            {
                "validator": r.validator_name,
                "severity": r.severity,
                "passed": r.passed,
                "message": r.message,
                "details": r.details,
                "self_corrected": r.self_corrected,
            }
            for r in all_results
        ],
    }

    write_yaml(workstream_dir / "verification/validator_results.yaml", output)
    return output
```

---

### Step 8: Generate Diff Report

Compare snapshots to current files. Annotate each hunk with operation ID and SRD.

```python
def step_8_generate_diff(ops_log, inventory, carrier_root, snapshots_dir,
                         workstream_dir, corrections):
    """Generate both the human-readable diff_report.md and machine-parseable changes.diff.

    For each modified file:
    1. Read snapshot (pre-edit state)
    2. Read current file (post-edit state)
    3. Generate unified diff
    4. Annotate with operation ID and SRD reference
    5. Detect anomalies: logged-but-no-change, undocumented-change

    New files (no snapshot): use empty content as baseline.
    """
    import difflib

    diff_report_lines = []
    unified_diff_lines = []
    anomalies = []

    # Header
    diff_report_lines.append(f"DIFF REPORT: {manifest_description}")
    diff_report_lines.append("=" * 60)
    diff_report_lines.append("")

    # Self-corrections section (if any)
    if corrections:
        diff_report_lines.append("SELF-CORRECTIONS APPLIED:")
        for c in corrections:
            diff_report_lines.append(
                f"  - {c['file']}: {c['validator']} -- {c['result']}"
            )
        diff_report_lines.append("")

    total_files = 0
    total_lines_changed = 0

    for filepath in sorted(inventory["all_files"]):
        snapshot_name = basename(filepath) + ".snapshot"
        snapshot_path = snapshots_dir / snapshot_name
        current_path = carrier_root / filepath

        if filepath in inventory["new_files"]:
            # New file -- diff against empty
            before_lines = []
            snapshot_label = "/dev/null"
        elif snapshot_path.exists():
            before_lines = open(snapshot_path, "r").readlines()
            snapshot_label = f"snapshot/{snapshot_name}"
        else:
            anomalies.append(f"Missing snapshot for {filepath}")
            continue

        after_lines = open(current_path, "r").readlines()

        # Generate unified diff
        diff = list(difflib.unified_diff(
            before_lines, after_lines,
            fromfile=snapshot_label,
            tofile=filepath,
            lineterm="",
        ))

        if not diff:
            # Check if operations_log says changes were made
            file_ops = [
                e for e in ops_log.get("operations", [])
                if e["file"] == filepath and e["status"] == "COMPLETED"
            ]
            if file_ops:
                anomalies.append(
                    f"Logged-but-no-change: {filepath} "
                    f"({len(file_ops)} operations logged but diff is empty)"
                )
            continue

        total_files += 1

        # Write raw unified diff
        unified_diff_lines.extend(diff)
        unified_diff_lines.append("")

        # Write annotated diff report
        diff_report_lines.append(f"--- {filepath}")
        diff_report_lines.append(f"+++ {filepath} (modified)")
        diff_report_lines.append("")

        changed_line_count = annotate_diff_hunks(
            diff, diff_report_lines, ops_log, filepath
        )
        total_lines_changed += changed_line_count
        diff_report_lines.append("")

    # Anomalies section
    if anomalies:
        diff_report_lines.append("ANOMALIES:")
        for a in anomalies:
            diff_report_lines.append(f"  - {a}")
        diff_report_lines.append("")

    # Detect undocumented changes (diff shows change not in operations_log)
    undocumented = detect_undocumented_changes(
        unified_diff_lines, ops_log, inventory
    )
    if undocumented:
        diff_report_lines.append("UNDOCUMENTED CHANGES:")
        for u in undocumented:
            diff_report_lines.append(f"  - {u}")
        diff_report_lines.append("")

    # Summary
    diff_report_lines.append(
        f"Total: {total_files} files modified, {total_lines_changed} lines changed"
    )

    # Write outputs
    write_file(workstream_dir / "verification/diff_report.md",
               "\n".join(diff_report_lines))
    write_file(workstream_dir / "verification/changes.diff",
               "\n".join(unified_diff_lines))
```

---

### Step 9: Generate Traceability Matrix

Map every SRD to its operations and file:line changes.

```python
def step_9_traceability_matrix(srds, ops_log, operations, workstream_dir):
    """Write verification/traceability_matrix.md.

    For each SRD: list all operations and their file:line changes.
    Mark each as [OK], [FAILED], [SKIPPED], or [FLAG].

    Count UNTRACED SRDs and ORPHAN CHANGES.
    """
    lines = []
    lines.append("TRACEABILITY: SRD -> Code Changes")
    lines.append("=" * 40)
    lines.append("")

    untraced_count = 0
    orphan_count = 0

    # Group operations by SRD
    ops_by_srd = {}
    for entry in ops_log.get("operations", []):
        srd_id = extract_srd_from_op(entry["operation"])
        if srd_id:
            ops_by_srd.setdefault(srd_id, []).append(entry)

    # For each SRD, list its operations
    for srd_id, srd_spec in sorted(srds.items()):
        lines.append(f"{srd_id}: {srd_spec.get('description', '')}")

        srd_ops = ops_by_srd.get(srd_id, [])
        if not srd_ops:
            lines.append("  [UNTRACED] No operations found for this SRD")
            untraced_count += 1
            lines.append("")
            continue

        for entry in srd_ops:
            status = entry["status"]
            marker = {
                "COMPLETED": "OK",
                "FAILED": "FAILED",
                "SKIPPED": "SKIPPED",
            }.get(status, "FLAG")

            changes = entry.get("changes", [])
            if changes:
                line_range = f"{changes[0]['line']}"
                if len(changes) > 1:
                    line_range += f"-{changes[-1]['line']}"
                detail = f"{entry['file']}:{line_range}"
                desc = changes[0].get("description", "")
                values = sum(c.get("values_changed", 0) for c in changes)
                summary = f" -- {len(changes)} changes"
                if values:
                    summary += f", {values} values"
            else:
                detail = entry.get("file", "unknown")
                desc = ""
                summary = ""

            lines.append(f"  [{marker}] {detail}{summary}")
            if desc:
                lines.append(f"         {desc}")

        lines.append("")

    # Check for orphan operations (not linked to any SRD)
    all_srd_ids = set(srds.keys())
    for entry in ops_log.get("operations", []):
        if entry["operation"].startswith("rework-"):
            continue
        srd_id = extract_srd_from_op(entry["operation"])
        if srd_id and srd_id not in all_srd_ids:
            lines.append(f"[ORPHAN] {entry['operation']} -> {srd_id} (SRD not found)")
            orphan_count += 1

    lines.append(f"UNTRACED SRDs: {untraced_count}")
    lines.append(f"ORPHAN CHANGES: {orphan_count}")

    write_file(workstream_dir / "verification/traceability_matrix.md",
               "\n".join(lines))
```

---

### Step 10: Generate Change Summary

Build the SVN commit message and final change summary.

```python
def step_10_change_summary(manifest, srds, ops_log, file_hashes, validator_results,
                           workstream_dir):
    """Write summary/change_summary.md.

    Format matches the output schema defined in Section 4 of this spec.
    This file is presented to the developer at Gate 2 and used as the
    suggested SVN commit message.
    """
    province_name = manifest["province_name"]
    lobs = manifest.get("lobs", [])
    lob_str = ", ".join(lobs) if lobs else manifest.get("lob", "")
    effective_date = manifest["effective_date"]
    ticket_ref = manifest.get("ticket_ref", "N/A")
    workflow_id = manifest["workflow_id"]

    # Collect modified and created files
    modified_files = []
    created_files = []
    vbproj_count = 0

    for entry in ops_log.get("operations", []):
        if entry["status"] != "COMPLETED":
            continue
        filepath = entry["file"]
        if entry.get("summary", {}).get("new_file_created"):
            created_files.append(filepath)
        elif filepath not in [m["path"] for m in modified_files]:
            shared_info = ""
            if is_shared_module(filepath, manifest):
                lob_count = len(manifest.get("lobs", []))
                shared_info = f" (shared across {lob_count} LOBs)"
            modified_files.append({"path": filepath, "note": shared_info})

    for filepath, fh in file_hashes.get("files", {}).items():
        if filepath.endswith(".vbproj") and fh.get("role") == "target":
            vbproj_count += 1

    # Build SRD bullets
    srd_bullets = []
    for srd_id, srd_spec in sorted(srds.items()):
        srd_bullets.append(f"  - {srd_spec.get('description', srd_id)}")

    # Validator summary
    vr = validator_results
    val_line = (f"Validation: {vr['passed']}/{vr['total_validators']} checks passed "
                f"({vr['blockers']} BLOCKERs, {vr['warnings']} WARNINGs)")

    # Compose
    lines = [
        f"RATE UPDATE: {province_name} {lob_str} {effective_date}",
        f"Ticket: {ticket_ref}",
        f"IQ-Workflow: {workflow_id}",
        "",
        "Changes:",
    ]
    lines.extend(srd_bullets)
    lines.append("")
    lines.append("Files modified:")
    for mf in modified_files:
        lines.append(f"  - {mf['path']}{mf['note']}")
    lines.append("")
    if created_files:
        lines.append("Files created (new Code/ copies):")
        for cf in created_files:
            lines.append(f"  - {cf}")
        lines.append("")
    lines.append(f".vbproj references updated: {vbproj_count}")
    lines.append("")
    lines.append(val_line)

    write_file(workstream_dir / "summary/change_summary.md", "\n".join(lines))
```

---

### Step 11: Write corrections.yaml (If Applicable)

Only written if Step 5 performed self-corrections.

```yaml
# File: verification/corrections.yaml
# Written ONLY if self-corrections occurred in Step 5.

self_corrections:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    validator: "validate_array6"
    failure_description: "Line 4051: Array6 has 5 args, expected 6"
    correction_action: "Restored from snapshot, re-applied op-004-01, op-004-02, op-001-01"
    operations_reapplied:
      - "op-004-01"
      - "op-004-02"
      - "op-001-01"
    re_validated: true
    timestamp: "2026-01-15T11:12:00Z"

  - file: "Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb"
    validator: "validate_no_commented_code"
    failure_description: "Line 15: commented line modified"
    correction_action: "Restored from snapshot, re-applied op-005-01"
    operations_reapplied:
      - "op-005-01"
    re_validated: false     # Still failed after retry -- escalated to developer
    timestamp: "2026-01-15T11:12:05Z"
```

---

### Step 12: Signal Completion

Return a summary to the orchestrator (skills/iq-review/SKILL.md). The orchestrator uses this
to proceed to Gate 2.

```python
def step_12_signal_completion(validator_results, corrections, inventory):
    """Return completion summary to orchestrator.

    Team mode: Send AGENT_COMPLETE message.
    Sequential mode: Return summary dict.
    """
    return {
        "status": "completed",
        "validators_total": validator_results["total_validators"],
        "validators_passed": validator_results["passed"],
        "blockers": validator_results["blockers"],
        "warnings": validator_results["warnings"],
        "self_corrections": validator_results["self_corrections_applied"],
        "files_reviewed": len(inventory["all_files"]),
        "outputs": [
            "verification/validator_results.yaml",
            "verification/diff_report.md",
            "verification/changes.diff",
            "verification/traceability_matrix.md",
            "summary/change_summary.md",
        ],
    }
```

---

## Validator Algorithms

Detailed reference implementations for all 7 validators. The Execution Steps
(Section 5) call these algorithms. This section provides the complete logic.

### Algorithm 1: Depth-Aware Array6 Arg Counter

The core algorithm used by `validate_array6`. Handles nested parentheses,
string literals, and arithmetic expressions within Array6 arguments.

```python
def count_array6_args(line):
    """Count arguments in an Array6() call using depth-aware comma splitting.

    Handles:
    - Nested parens:  Array6(Func(a, b), c)  -> 2 args, not 3
    - Strings:        Array6("a, b", c)      -> 2 args, not 3
    - Expressions:    Array6(30 + 10, 40)    -> 2 args
    - Single arg:     Array6(4)              -> 1 arg
    - Negative vals:  Array6(-5, -10)        -> 2 args

    Returns int (arg count) or 0 if line has no Array6 call.
    """
    import re
    # Find the Array6( opening
    match = re.search(r'Array6\s*\(', line)
    if not match:
        return 0

    start = match.end()  # Position right after "Array6("

    # Extract content up to the MATCHING close paren
    content = extract_balanced_parens(line, start)
    if content is None:
        return -1  # Unmatched parens

    content = content.strip()
    if not content:
        return 0

    # Split by top-level commas
    depth = 0
    in_string = False
    arg_count = 1

    for ch in content:
        if in_string:
            if ch == '"':
                in_string = False
                # NOTE: VB.NET escapes literal quotes by doubling: "He said ""hi"""
                # The toggle logic handles this implicitly: first " sets in_string=False,
                # second " immediately sets in_string=True again. Net effect: correctly
                # stays "in string" through escaped quotes. No special case needed.
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            arg_count += 1

    return arg_count


def extract_balanced_parens(line, start_after_open):
    """Extract content between Array6( and its matching ).

    start_after_open: index right after the opening paren.
    Returns the content string, or None if no matching close paren.
    """
    depth = 1
    i = start_after_open
    in_string = False

    while i < len(line):
        ch = line[i]
        if in_string:
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return line[start_after_open:i]
        i += 1

    return None  # Unmatched -- no closing paren found


def parens_balanced(line):
    """Check if all parentheses in a line are balanced."""
    depth = 0
    in_string = False
    for ch in line:
        if in_string:
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0
```

### Algorithm 2: Dual-Use Array6 Detection

Distinguishes rate assignments (modifiable) from test/lookup usages (never modify).

```python
import re

def classify_array6_usage(line):
    """Classify Array6 usage on a line.

    Returns: "rate" | "test" | "none"

    Rate usage (modifiable):
      varRates = Array6(...)
      premiumArray = Array6(...)
      liabilityPremiumArray = Array6(...)

    Test usage (NEVER modify):
      IsItemInArray(x, Array6(...))
      UBound(Array6(...))
      If Array6(...) Then   (rare but possible)
    """
    if "Array6" not in line:
        return "none"

    stripped = line.strip()

    # Skip comments
    if stripped.startswith("'"):
        return "none"

    # Rate pattern: identifier = Array6(...)
    # Allow optional type suffix: varRates$ = Array6(...)
    if re.search(r'\w+\$?\s*=\s*Array6\s*\(', line):
        return "rate"

    # Everything else is a test/lookup
    return "test"
```

### Algorithm 3: Territory Counter for Completeness

Count territories in a Select Case block to verify completeness.

```python
def count_territories_in_function(snapshot_lines, function_name, func_start, func_end):
    """Count unique Case labels within a territory-based Select Case.

    Reads the snapshot (pre-edit) to establish the expected count.
    The completeness validator compares this to the actual changes count.
    """
    import re
    territory_count = 0

    # Find the territory Select Case within the function
    in_target_select = False

    for i in range(func_start, func_end + 1):
        line = snapshot_lines[i].strip()

        # Skip comments
        if line.startswith("'"):
            continue

        # Detect territory Select Case (Case 1, Case 2, ...)
        # These use numeric Case labels (territory numbers)
        case_match = re.match(r'^Case\s+(\d+)\s*:', line)
        if case_match:
            territory_count += 1

        # Also handle Case without colon (multi-line body)
        case_match_ml = re.match(r'^Case\s+(\d+)\s*$', line)
        if case_match_ml:
            territory_count += 1

    return territory_count
```

### Algorithm 4: Hash Computation

Used by Steps 3 and 4c for file integrity verification.

```python
import hashlib

def compute_file_hash(filepath):
    """Compute SHA-256 hash of a file, matching the format in file_hashes.yaml.

    Returns: "sha256:{hex_digest}"
    """
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def verify_hash(filepath, expected_hash):
    """Compare computed hash to expected. Returns (matches: bool, actual: str)."""
    actual = compute_file_hash(filepath)
    return actual == expected_hash, actual
```

### Algorithm 5: Percentage Change with Edge Cases

Used by `validate_value_sanity` for all numeric comparisons.

```python
def compute_pct_change_safe(before, after):
    """Compute percentage change with comprehensive edge case handling.

    Returns: (pct_change: float or None, classification: str)

    | Before | After  | Classification          |
    |--------|--------|-------------------------|
    | 100    | 105    | "normal" (5.0%)         |
    | 0      | 50     | "zero_to_nonzero"       |
    | 50     | 0      | "value_zeroed" (100.0%) |
    | -999   | -999   | "sentinel_unchanged"    |
    | -999   | 50     | "sentinel_modified"     |
    | -0.2   | -0.22  | "normal" (10.0%)        |
    | 30+10  | 42     | evaluate first: 40->42  |
    """
    # Sentinel check
    if before == -999:
        if after == -999:
            return 0.0, "sentinel_unchanged"
        return None, "sentinel_modified"

    # Zero baseline
    if before == 0:
        if after == 0:
            return 0.0, "no_change"
        return None, "zero_to_nonzero"

    # Normal computation
    pct = abs(after - before) / abs(before) * 100

    if after == 0:
        return pct, "value_zeroed"

    return pct, "normal"


def parse_array6_values(line):
    """Extract numeric values from an Array6() call.

    Returns list of floats (or None for non-numeric args like variables).
    Returns None if line has no Array6.
    """
    import re

    match = re.search(r'Array6\s*\(([^)]+)\)', line)
    if not match:
        return None

    args_str = match.group(1)
    raw_args = split_top_level_commas(args_str)  # Uses same depth-aware logic as Algorithm 1

    values = []
    for raw in raw_args:
        raw = raw.strip()
        val = try_eval_numeric(raw)
        values.append(val)  # None if not evaluable

    return values


def try_eval_numeric(expr):
    """Safely evaluate a numeric expression.

    Handles: "50", "-0.22", "30 + 10", "basePremium" (returns None).
    """
    import re
    expr = expr.strip()

    # Pure numeric
    try:
        return float(expr)
    except ValueError:
        pass

    # Simple arithmetic (digits and +,-,*,/ only, no function calls)
    if re.match(r'^[\d\s\.\+\-\*/]+$', expr):
        try:
            return float(eval(expr))  # Safe: only digits and operators
        except Exception:
            pass

    return None  # Variable or complex expression
```

### Algorithm 6: .vbproj Reference Checker

Used by `validate_no_old_modify` and `validate_cross_lob`.

```python
import xml.etree.ElementTree as ET

def check_vbproj_refs(vbproj_path, target_date):
    """Check that Compile Include refs in a .vbproj point to target-dated files.

    Returns list of findings (empty if all refs correct).
    """
    findings = []
    ns = {"msbuild": "http://schemas.microsoft.com/developer/msbuild/2003"}

    tree = ET.parse(vbproj_path)
    root = tree.getroot()

    for compile_elem in root.findall(".//msbuild:Compile", ns):
        include = compile_elem.get("Include", "")
        # Check Code/ file references
        if "\\Code\\" in include or "/Code/" in include:
            # Extract the date from the filename pattern
            # e.g., mod_Common_SKHab20260101.vb -> 20260101
            import re
            date_match = re.search(r'(\d{8})\.vb', include)
            if date_match:
                file_date = date_match.group(1)
                if file_date != target_date:
                    findings.append({
                        "vbproj": str(vbproj_path),
                        "include": include,
                        "issue": "old_date_ref",
                        "found_date": file_date,
                        "expected_date": target_date,
                    })

    return findings


def find_mod_common_ref(vbproj_path):
    """Find the mod_Common Compile Include path in a .vbproj file.

    Returns the Include path string, or None if not found.
    Used by validate_cross_lob.
    """
    ns = {"msbuild": "http://schemas.microsoft.com/developer/msbuild/2003"}
    tree = ET.parse(vbproj_path)
    root = tree.getroot()

    for compile_elem in root.findall(".//msbuild:Compile", ns):
        include = compile_elem.get("Include", "")
        if "mod_Common" in include:
            return include

    return None
```

### Algorithm 7: Comment Line Detection

Used by `validate_no_commented_code`.

```python
def is_full_line_comment(line):
    """Determine if a line is a full-line VB.NET comment.

    VB.NET only uses ' for comments. No REM in this codebase, no block comments.

    Full-line comment:  '  This is a comment
    Full-line comment:  'liabilityPremiumArray = Array6(24, 49, 99)
    NOT a comment:      Case 200 'IQPORT-1082 Here for Farm Only
    NOT a comment:      dblVal = -0.2   ' discount factor
    """
    stripped = line.strip()
    if not stripped:
        return False
    return stripped[0] == "'"


def is_inline_comment_only_change(before, after):
    """Check if only the inline comment portion changed (code unchanged).

    If the code portion (before the first unquoted ') is identical,
    the change is to the comment only -- acceptable.
    """
    before_code = extract_code_portion(before)
    after_code = extract_code_portion(after)
    return before_code.rstrip() == after_code.rstrip()


def extract_code_portion(line):
    """Extract the code portion of a line (everything before the first unquoted ')."""
    in_string = False
    for i, ch in enumerate(line):
        if in_string:
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "'":
            return line[:i]
    return line
```

### Helper Functions

```python
def split_top_level_commas(s):
    """Split a string by commas at depth 0 only.

    Uses the same depth-aware, string-aware logic as count_array6_args (Algorithm 1).
    Handles nested parens, string literals, and arithmetic expressions.

    Example: "Func(a, b), 30 + 10, -5" -> ["Func(a, b)", "30 + 10", "-5"]
    """
    args = []
    current = []
    depth = 0
    in_string = False

    for ch in s:
        if ch == '"' and not in_string:
            in_string = True
            current.append(ch)
        elif ch == '"' and in_string:
            in_string = False  # Note: VB.NET "" (escaped quote) toggles twice, net no change
            current.append(ch)
        elif in_string:
            current.append(ch)
        elif ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)

    if current:
        args.append(''.join(current).strip())

    return args


def extract_srd_from_op(op_id):
    """Extract SRD ID from operation ID.

    "op-001-01" -> "srd-001"
    "op-012-03" -> "srd-012"
    """
    import re
    match = re.match(r'op-(\d+)-\d+', op_id)
    if match:
        return f"srd-{match.group(1)}"
    return None

# Alias used in some steps:
extract_srd_num = extract_srd_from_op
```

---

## Worked Examples

### Example A: Clean Pass -- All 7 Validators Pass

**Scenario:** Saskatchewan Habitational, 5% base rate increase across 15 territories
in mod_Common_SKHab20260101.vb. Three SRDs, all executed by the Rate Modifier.

**operations_log.yaml (abbreviated):**
```yaml
# Portage Mutual example
operations:
  - operation: "op-001-01"
    agent: "rate-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    function: "GetBasePremium_Home"
    changes:
      - line: 352
        description: "Territory 1"
        before: "            Case 1 : varRates = Array6(512, 29, 463, 29, 575, 29, 420, 29, 133)"
        after:  "            Case 1 : varRates = Array6(538, 30, 486, 30, 604, 30, 441, 30, 140)"
        values_changed: 9
      # ... 14 more territories
    summary:
      lines_changed: 15
      values_changed: 135
      change_range: "4.7% to 5.3%"

  - operation: "op-002-01"
    agent: "rate-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    function: "SetDisSur_Deductible"
    changes:
      - line: 672
        description: "Case 5000 deductible factor"
        before: "            Case 5000 : dblDedDiscount = -0.20"
        after:  "            Case 5000 : dblDedDiscount = -0.22"
        values_changed: 1
    summary:
      lines_changed: 1
      values_changed: 1
      change_range: "10.0%"

  - operation: "op-003-01"
    agent: "rate-modifier"
    status: "COMPLETED"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    function: "GetLiabilityBundlePremiums"
    changes:
      - line: 4051
        description: "Farm > PRIMARYITEM > Enhanced Comp"
        before: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
        after:  "                        liabilityPremiumArray = Array6(0, 82, 169, 198, 224, 306)"
        values_changed: 5
    summary:
      lines_changed: 1
      values_changed: 5
      change_range: "3.1% to 5.2%"
```

**validator_results.yaml:**
```yaml
workflow_id: "20260101-SK-Hab-rate-update"
validated_at: "2026-01-15T11:10:00Z"
total_validators: 7
passed: 7
failed: 0
blockers: 0
warnings: 0
self_corrections_applied: 0

results:
  - validator: "validate_array6"
    severity: "BLOCKER"
    passed: true
    message: "All Array6() calls valid: 17 calls checked, arg counts match snapshots"
    details: []
    self_corrected: false

  - validator: "validate_completeness"
    severity: "BLOCKER"
    passed: true
    message: "3/3 operations COMPLETED, 15/15 territories updated"
    details: []
    self_corrected: false

  - validator: "validate_no_old_modify"
    severity: "BLOCKER"
    passed: true
    message: "Source file hashes unchanged, 6 .vbproj refs point to 20260101"
    details: []
    self_corrected: false

  - validator: "validate_no_commented_code"
    severity: "BLOCKER"
    passed: true
    message: "No commented lines modified (1 commented Array6 at line 4058 untouched)"
    details: []
    self_corrected: false

  - validator: "validate_value_sanity"
    severity: "WARNING"
    passed: true
    message: "All changes within range: min 3.1%, max 10.0%, mean 5.1%"
    details: []
    self_corrected: false

  - validator: "validate_cross_lob"
    severity: "WARNING"
    passed: true
    message: "mod_Common_SKHab20260101.vb consistent across all 6 hab LOBs"
    details: []
    self_corrected: false

  - validator: "validate_traceability"
    severity: "WARNING"
    passed: true
    message: "3/3 SRDs traced, 0 untraced, 0 orphan changes"
    details: []
    self_corrected: false
```

**traceability_matrix.md:**
```
TRACEABILITY: SRD -> Code Changes
========================================

srd-001: Increase base rates by 5%
  [OK] mod_Common_SKHab20260101.vb:352-366 -- 15 changes, 135 values
       Territory 1 through Territory 15

srd-002: Change $5000 deductible factor
  [OK] mod_Common_SKHab20260101.vb:672 -- 1 changes, 1 values
       Case 5000 deductible factor

srd-003: Increase liability premiums
  [OK] mod_Common_SKHab20260101.vb:4051 -- 1 changes, 5 values
       Farm > PRIMARYITEM > Enhanced Comp

UNTRACED SRDs: 0
ORPHAN CHANGES: 0
```

---

### Example B: BLOCKER Failure + Self-Correction

**Scenario:** Rate Modifier accidentally dropped an argument from an Array6 call.
Territory 5 had 9 args before and 8 after (modifier concatenated two args).

**Detection (validate_array6):**
```yaml
# First run: BLOCKER FAIL
- validator: "validate_array6"
  severity: "BLOCKER"
  passed: false
  message: "Array6 arg count mismatch: 1 finding"
  details:
    - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      line: 356
      operation: "op-001-01"
      expected_args: 9
      actual_args: 8
      before: "            Case 5 : varRates = Array6(480, 27, 434, 27, 539, 27, 394, 27, 124)"
      after:  "            Case 5 : varRates = Array6(504, 28, 456, 28566, 28, 414, 28, 130)"
```

**Self-correction flow:**

1. Identify affected file: `mod_Common_SKHab20260101.vb`
2. Restore from `snapshots/mod_Common_SKHab20260101.vb.snapshot`
3. Re-apply ALL operations for this file (op-001-01, op-002-01, op-003-01) bottom-to-top
4. Re-run `validate_array6`

**corrections.yaml:**
```yaml
self_corrections:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    validator: "validate_array6"
    failure_description: "Line 356: Array6 has 8 args, expected 9"
    correction_action: "Restored from snapshot, re-applied op-003-01, op-002-01, op-001-01"
    operations_reapplied:
      - "op-003-01"
      - "op-002-01"
      - "op-001-01"
    re_validated: true
    timestamp: "2026-01-15T11:12:00Z"
```

**Final validator_results.yaml (after self-correction):**
```yaml
results:
  - validator: "validate_array6"
    severity: "BLOCKER"
    passed: true
    message: "All Array6() calls valid (self-corrected)"
    details: []
    self_corrected: true
```

At Gate 2, the orchestrator shows: `"[OK] Array6 Syntax: PASS (self-corrected)"`

---

### Example C: Mixed Results -- BLOCKERs Pass, WARNINGs Flag

**Scenario:** Alberta Auto rate update. Value sanity flags a 48% change on one
deductible factor (legitimate -- insurer approved large change). Cross-LOB
consistency passes (Auto has no shared modules).

**validator_results.yaml (abbreviated):**
```yaml
# Portage Mutual example
total_validators: 7
passed: 6
failed: 1
blockers: 0
warnings: 1
self_corrections_applied: 0

results:
  # ... 4 BLOCKERs all pass ...

  - validator: "validate_value_sanity"
    severity: "WARNING"
    passed: false
    message: "1 change exceeds 50% threshold: max 52.0%"
    details:
      - file: "Alberta/Code/mod_DisSur_ABAutoHab20260101.vb"
        line: 145
        operation: "op-002-01"
        issue: "large_change"
        before: -0.25
        after: -0.38
        pct_change: 52.0

  - validator: "validate_cross_lob"
    severity: "WARNING"
    passed: true
    message: "No shared modules in this workflow"
    details: []
    self_corrected: false

  - validator: "validate_traceability"
    severity: "WARNING"
    passed: true
    message: "2/2 SRDs traced"
    details: []
    self_corrected: false
```

**At Gate 2, the orchestrator shows:**
```
Validators:
  [OK] Array6 Syntax: PASS
  [OK] Completeness: PASS
  [OK] No Old File Modification: PASS
  [OK] No Commented Code Modified: PASS
  [!!] Value Sanity: WARNING -- 1 change exceeds 50% threshold (52.0%)
       Alberta/Code/mod_DisSur_ABAutoHab20260101.vb:145
       Deductible factor: -0.25 -> -0.38 (52.0% change)
  [OK] Cross-LOB Consistency: PASS
  [OK] Traceability: PASS

6/7 validators passed. 0 BLOCKER(s), 1 WARNING(s).
Approve results? Say 'approve' to finalize, or tell me what needs fixing.
```

The developer says "approve" -- the 48% change is intentional. Proceeds to Done.

---

### Example D: Logic Modifier + Rate Modifier on Same File

**Scenario:** Manitoba hab update. SRD-001 adds a new ELITECOMP constant
(Logic Modifier). SRD-002 updates liability premiums in the same
mod_Common_MBHab20260101.vb file (Rate Modifier).

**operations_log.yaml (both agents):**
```yaml
# Portage Mutual example
operations:
  - operation: "op-001-01"
    agent: "logic-modifier"
    status: "COMPLETED"
    file: "Manitoba/Code/mod_Common_MBHab20260101.vb"
    location: "module-level constants"
    changes:
      - line: 23
        description: "Add ELITECOMP constant"
        before: null    # Pure insertion
        after: '    Public Const ELITECOMP As String = "Elite Comp."'
        change_type: "insert"
    summary:
      lines_added: 1
      lines_modified: 0

  - operation: "op-002-01"
    agent: "rate-modifier"
    status: "COMPLETED"
    file: "Manitoba/Code/mod_Common_MBHab20260101.vb"
    function: "GetLiabilityBundlePremiums"
    changes:
      - line: 4052
        description: "Farm > PRIMARYITEM > Enhanced Comp"
        before: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
        after:  "                        liabilityPremiumArray = Array6(0, 82, 169, 198, 224, 306)"
        values_changed: 5
    summary:
      lines_changed: 1
      values_changed: 5
      change_range: "3.1% to 5.2%"
```

**diff_report.md (combined diff for one file):**
```
--- Manitoba/Code/mod_Common_MBHab20260101.vb
+++ Manitoba/Code/mod_Common_MBHab20260101.vb (modified)

  @@ line 23 (module-level constants) @@
  [op-001-01, SRD-001]
  + Public Const ELITECOMP As String = "Elite Comp."

  @@ line 4052 (GetLiabilityBundlePremiums > Farm > PRIMARYITEM > Enhanced Comp) @@
  [op-002-01, SRD-002]
  - liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)
  + liabilityPremiumArray = Array6(0, 82, 169, 198, 224, 306)

Total: 1 files modified, 2 lines changed
```

**traceability_matrix.md:**
```
TRACEABILITY: SRD -> Code Changes
========================================

srd-001: Add Elite Comp coverage type
  [OK] Manitoba/Code/mod_Common_MBHab20260101.vb:23 -- 1 changes
       Add ELITECOMP constant

srd-002: Increase liability premiums 3%
  [OK] Manitoba/Code/mod_Common_MBHab20260101.vb:4052 -- 1 changes, 5 values
       Farm > PRIMARYITEM > Enhanced Comp

UNTRACED SRDs: 0
ORPHAN CHANGES: 0
```

**Key point:** The diff is ONE diff for the file, with BOTH operations annotated.
The traceability matrix maps each SRD to its specific operations regardless of
agent type.

---

## Special Cases

### Special Case 1: New File Created (Option_*.vb)

The Logic Modifier creates a new file (e.g., `Option_Bicycle_SKHome20260101.vb`).
No snapshot exists for this file.

**Diff behavior:**
- Use empty content as the baseline (`--- /dev/null`)
- Show the entire file as additions
- In changes.diff: standard `--- /dev/null` unified diff format

**Validator behavior:**
- `validate_array6`: Still validate any Array6 calls in the new file
- `validate_completeness`: Verify the file exists AND .vbproj includes it
- `validate_no_old_modify`: N/A (no old file to protect)
- `validate_no_commented_code`: Still applies to inserted content
- `validate_value_sanity`: N/A (no before values to compare)
- `validate_cross_lob`: Verify .vbproj Compile Include entry
- `validate_traceability`: Map to the SRD that requested the new file

---

### Special Case 2: All Operations SKIPPED (Values Already at Target)

If the Rate Modifier finds all values already match the target (e.g., a
previous manual edit already applied the change):

```yaml
operations:
  - operation: "op-001-01"
    agent: "rate-modifier"
    status: "SKIPPED"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    skip_reason: "All values already at target"
```

**Validator behavior:**
- `validate_completeness`: SKIPPED is a valid outcome, not a failure
- Diff: No changes to show (snapshot == current), note in report
- Traceability: Mark as `[SKIPPED - already at target]`
- Change summary: Note that no changes were needed

---

### Special Case 3: Empty Operations Log (All FAILED Upstream)

All operations failed during `/iq-execute`. The operations_log has entries
but every one has `status: "FAILED"`.

**Validator behavior:**
- `validate_completeness`: BLOCKER FAIL (no operations completed)
- Self-correction: NOT applicable (nothing to restore/re-apply)
- Report to developer: "All operations failed during execution."
- Suggest: review `/iq-execute` error logs, run `/iq-execute` again

---

### Special Case 4: File Modified Externally

Between `/iq-execute` and `/iq-review`, someone opens the file in Visual Studio
and saves it (auto-formatting may change whitespace).

**Detection:** Step 3 (TOCTOU check) catches the hash mismatch.

**Validator behavior:**
- Flag in validator_results with details of which file mismatched
- Do NOT abort automatically -- present to developer
- Developer options: show diff of external changes, re-run `/iq-execute`,
  accept current state with warning

If developer accepts:
```yaml
- validator: "toctou_check"
  severity: "WARNING"
  passed: true
  message: "Hash mismatch accepted by developer for 1 file"
  details:
    - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      issue: "hash_mismatch_accepted"
```

---

### Special Case 5: Rework Entry in Operations Log

After a minor rework at Gate 2, the orchestrator appends a rework entry:

```yaml
- operation: "rework-001"
  agent: "orchestrator"
  status: "COMPLETED"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  function: "GetBasePremium_Home"
  changes:
    - line: 356
      description: "Manual correction: territory 5"
      before: "            Case 5 : varRates = Array6(504, 28, 456, 28, 566, 28, 414, 28, 130)"
      after:  "            Case 5 : varRates = Array6(504, 28, 456, 28, 566, 28, 414, 28, 130)"
```

**Validator behavior:**
- Treat `agent: "orchestrator"` like `agent: "rate-modifier"` for validation
- Run Array6 syntax check, value sanity, etc.
- In traceability: rework entries don't map to SRDs (skip orphan check)

---

### Special Case 6: Commented-Out Array6 Detected

Line 4058 of mod_Common_SKHab20260101.vb:
```vb
	'liabilityPremiumArray = Array6(24, 49, 99, 124, 149, 274)
```

This commented-out line is a REAL trap. The Rate Modifier should skip it, and
the `validate_no_commented_code` validator confirms.

**If the modifier DID modify it:** BLOCKER. The `before` line starts with `'`.
Self-correction restores from snapshot, re-applies without touching commented lines.

**In the clean pass case:** The validator notes: "1 commented Array6 at line 4058
untouched" in its message (for developer confidence).

---

### Special Case 7: Cross-Province Shared File Flagged but Not Modified

Cross-province shared files (e.g., `Code/PORTCommonHeat.vb`) are listed in
`config.yaml["cross_province_shared_files"]` and are NEVER auto-modified.

**If the analysis flagged it as potentially affected:**
- Traceability matrix shows: `[FLAG] Code/PORTCommonHeat.vb -- cross-province shared, NOT modified (manual review needed)`
- The completeness validator does NOT count this as an incomplete operation
- The change summary includes a note: "Cross-province file flagged for manual review"

---

### Special Case 8: Multi-LOB Ticket with 6 LOBs Sharing mod_Common

Six hab LOBs (Home, Condo, Tenant, FEC, Farm, Seasonal) all compile the same
`mod_Common_SKHab20260101.vb`. The file is edited ONCE but affects all 6 LOBs.

**Diff behavior:** ONE diff for the file, not 6. The diff report notes:
"(shared across Home, Condo, Tenant, FEC, Farm, Seasonal)"

**Cross-LOB validator:** Checks all 6 .vbproj files reference the same
mod_Common file path. A mismatch means one LOB's .vbproj was not updated
by the file-copier.

**Change summary:** Lists the file once with "(shared across 6 LOBs)".
Lists all 6 .vbproj files as updated.

---

### Special Case 9: Self-Correction with Stale Operations Log

After self-correction (snapshot restore + re-apply), the operations_log still
contains the ORIGINAL entries (from `/iq-execute`). The re-apply does not
update the operations_log -- it only fixes the file on disk.

**Implication:** The `changes[].after` field in operations_log may not match
the actual current line if self-correction changed the output.

**Mitigation:** The diff agent compares snapshot to CURRENT file (not to
operations_log). The diff report shows the ACTUAL state, not what the log
says. The corrections.yaml file documents what was changed during self-
correction.

**In validator_results.yaml:** The `self_corrected: true` flag signals to the
diff agent and orchestrator that operations_log may be stale for this file.

---

### Special Case 10: Sentinel Value (-999) Changed by Rate Factor

The Rate Modifier should NEVER multiply sentinel values by a rate factor.
But if it does:

```yaml
# Before: Array6(350, 350, ..., -999, -999, ..., -999, -999)
# After:  Array6(368, 368, ..., -1049, -1049, ..., -1049, -1049)
```

**Detection:** `validate_value_sanity` catches `-999 -> -1049`:
```yaml
details:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    line: 4051
    operation: "op-001-01"
    issue: "sentinel_modified"
    arg_index: 7
    before: -999
    after: -1049
```

**Severity:** This is flagged as a WARNING by `validate_value_sanity`, but the
developer should treat it as effectively a BLOCKER. The sentinel value `-999`
means "coverage not available" and should be preserved exactly.

**Self-correction does not apply** (this is a value sanity WARNING, not a
BLOCKER validator). The developer must decide at Gate 2 whether to fix
manually or re-execute.

---

## 9. Boundary Table

### Reviewer vs Orchestrator vs Developer

| Responsibility | Reviewer Agent | Orchestrator (/iq-review) | Developer |
|---------------|:-:|:-:|:-:|
| Run 7 validators against modified files | X | | |
| Attempt self-correction for BLOCKERs | X | | |
| Write validator_results.yaml | X | | |
| Write corrections.yaml (if self-correction) | X | | |
| Write diff_report.md and changes.diff | X | | |
| Write traceability_matrix.md | X | | |
| Write change_summary.md | X | | |
| Present Gate 2 summary to developer | | X | |
| Handle developer Q&A at Gate 2 | | X | |
| Capture approve/reject decision | | X | |
| Update manifest.yaml state transitions | | X | |
| Record developer_decisions in manifest | | X | |
| Apply minor rework edits (territory fix) | | X | |
| Append rework entries to operations_log | | X | |
| Set state to PLANNED for complex rework | | X | |
| Format the Done Moment output | | X | |
| Record SVN revision number | | X | |
| Approve or reject at Gate 2 | | | X |
| Decide rework scope (minor vs complex) | | | X |
| Provide SVN revision after commit | | | X |
| Build and test DLL in Visual Studio | | | X |
| Commit to SVN | | | X |

### Reviewer vs Modifier Agents

| Responsibility | Reviewer Agent | Rate Modifier | Logic Modifier |
|---------------|:-:|:-:|:-:|
| Validate Array6 arg counts unchanged | X | | |
| Validate no old-file modifications | X | | |
| Validate value sanity (% change) | X | | |
| Validate completeness (all ops executed) | X | | |
| Validate cross-LOB consistency | X | | |
| Validate traceability (SRD coverage) | X | | |
| Validate no commented code modified | X | | |
| Modify Array6 / factor / limit values | | X | |
| Add functions, constants, Case blocks | | | X |
| Re-apply operations during self-correction | X* | | |
| Restore from per-file snapshots | X* | | |

\* Self-correction restores the ENTIRE file from its snapshot and re-applies ALL
operations for that file. The Reviewer re-applies using the operation YAML specs
(same specs the modifiers used). It does NOT re-invoke the modifier agents --
it performs the re-application itself using the logged before/after values.

### Key Boundary Principles

1. **Reviewer reads, validates, reports.** It never presents results to the
   developer directly -- the orchestrator formats and displays Gate 2.
2. **Reviewer writes files, orchestrator reads them.** The orchestrator reads
   validator_results.yaml, diff_report.md, and change_summary.md to build Gate 2.
3. **Reviewer does not update manifest.yaml.** State transitions (VALIDATING,
   COMPLETED, DISCARDED) are orchestrator-only.
4. **Rework is orchestrator-driven.** The Reviewer validates rework results on
   re-validation, but the orchestrator applies the edits and manages the loop.

---

## 10. Error Handling

### Error 1: VALIDATOR_CRASH

**Trigger:** A validator script throws an uncaught exception (Python traceback,
file not found, permission denied).

**Action:** Log the crash, mark that validator as `passed: false`, continue with
remaining validators. Do NOT abort the entire review.

```yaml
- validator: "validate_array6"
  severity: "BLOCKER"
  passed: false
  message: "Validator crashed: FileNotFoundError: mod_Common_SKHab20260101.vb"
  error_type: "VALIDATOR_CRASH"
  details:
    traceback: "FileNotFoundError: [Errno 2] No such file..."
```

**Recovery:** Orchestrator presents the crash at Gate 2. Developer can fix the
issue and say "re-validate", or skip the check (NOT RECOMMENDED for BLOCKERs).

### Error 2: SNAPSHOT_MISSING

**Trigger:** `execution/snapshots/{filename}.snapshot` does not exist for a file
listed in operations_log.yaml.

**Action:** Skip diff generation for that file. Log a WARNING in validator_results.
Use the file's current state as "both before and after" (diff will be empty).

```yaml
- validator: "validate_array6"
  severity: "BLOCKER"
  passed: false
  message: "Snapshot missing for mod_Common_SKHab20260101.vb -- cannot verify arg counts"
  error_type: "SNAPSHOT_MISSING"
  details:
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    expected_snapshot: "execution/snapshots/mod_Common_SKHab20260101.vb.snapshot"
```

**Recovery:** Orchestrator offers: skip diff for this file, use the original
source file (old-dated copy) as baseline, or abort and re-run /iq-execute.

### Error 3: HASH_MISMATCH_EXTERNAL

**Trigger:** File hash computed during /iq-review does not match the post-execution
hash in `execution/file_hashes.yaml`. The file was modified outside the plugin
between /iq-execute and /iq-review.

**Action:** Log as WARNING. Continue validation using the CURRENT file state.
Flag in diff_report.md header.

```yaml
- validator: "validate_completeness"
  severity: "WARNING"
  passed: false
  message: "External modification detected on mod_Common_SKHab20260101.vb"
  error_type: "HASH_MISMATCH_EXTERNAL"
  details:
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    expected_hash: "sha256:abc123..."
    actual_hash: "sha256:def456..."
```

**Recovery:** Orchestrator presents at Gate 2. Developer chooses: show diff between
expected and current, re-run /iq-execute, or accept current state (re-hash).

### Error 4: SELF_CORRECTION_FAILED

**Trigger:** Snapshot restore + re-apply did not fix the BLOCKER. The re-validation
after self-correction still fails.

**Action:** Mark validator as `passed: false` with `self_corrected: true` and
`correction_result: "FAILED"`. Escalate to developer via orchestrator.

```yaml
- validator: "validate_array6"
  severity: "BLOCKER"
  passed: false
  message: "Self-correction failed: Array6 arg count still mismatched after restore+reapply"
  self_corrected: true
  correction_result: "FAILED"
  details:
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    line: 4051
    expected_args: 6
    actual_args: 5
    operations_reapplied: ["op-004-01", "op-004-02"]
```

**Recovery:** Orchestrator presents BLOCKER with options: show affected file,
developer fixes manually then "re-validate", restore from snapshot and re-execute,
or skip check (NOT RECOMMENDED).

### Error 5: OPERATIONS_LOG_CORRUPT

**Trigger:** `execution/operations_log.yaml` cannot be parsed as valid YAML, or
is missing required top-level keys (`operations` list).

**Action:** Abort the entire review. No validators can run without the log.

```yaml
error_type: "OPERATIONS_LOG_CORRUPT"
message: "Cannot parse execution/operations_log.yaml: expected 'operations' key"
recovery: "Check if /iq-execute completed. Re-run /iq-execute if needed."
```

**Recovery:** Developer must inspect the file, fix corruption, or re-run /iq-execute.

### Error 6: DIFF_GENERATION_FAILED

**Trigger:** The diff tool (difflib or `diff -u`) produces unexpected output --
empty diff when operations_log says changes were made, or diff tool returns error.

**Action:** Log the anomaly. Write a placeholder in diff_report.md noting the
failure. Continue with report generation (traceability can still run).

```yaml
error_type: "DIFF_GENERATION_FAILED"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
message: "Diff produced empty output but operations_log records 15 changes"
details:
  operations_on_file: ["op-001-01", "op-001-02", "op-002-01"]
  snapshot_exists: true
  file_exists: true
```

**Recovery:** Developer can compare files manually or re-run /iq-review.

### Error 7: TRACEABILITY_GAP

**Trigger:** One or more SRDs have zero operations mapped to them in the
operations_log. The SRD was planned but nothing was executed for it.

**Action:** Report as WARNING in validator_results under `validate_traceability`.
Include in traceability_matrix.md with `[UNTRACED]` marker.

```yaml
- validator: "validate_traceability"
  severity: "WARNING"
  passed: false
  message: "1 SRD has no executed operations"
  error_type: "TRACEABILITY_GAP"
  details:
    untraced_srds:
      - srd_id: "srd-003"
        description: "Change heating surcharge factor"
        reason: "No operations with prefix op-003 found in log"
    orphan_changes: []
```

**Recovery:** Developer reviews at Gate 2. May indicate a missed operation (re-plan)
or an SRD that was intentionally deferred (acknowledge and approve).

### Error 8: CROSS_PROVINCE_VIOLATION

**Trigger:** A cross-province shared file (listed in `config.yaml["cross_province_shared_files"]`)
appears as a modified file in operations_log.yaml.

**Action:** BLOCKER. This file should NEVER be modified by the plugin.

```yaml
- validator: "validate_no_old_modify"
  severity: "BLOCKER"
  passed: false
  message: "Cross-province shared file was modified"
  error_type: "CROSS_PROVINCE_VIOLATION"
  details:
    file: "Code/PORTCommonHeat.vb"  # Portage Mutual example
    operations: ["op-003-01"]
```

**Recovery:** Restore from snapshot immediately. Developer must apply cross-province
changes manually outside the plugin.

### Error 9: VBPROJ_PARSE_ERROR

**Trigger:** Cannot parse a `.vbproj` file as valid XML. Required for cross-LOB
consistency validation and .vbproj reference checks.

**Action:** Log WARNING. Skip the cross-LOB consistency check for the affected
.vbproj. Continue other validators.

```yaml
- validator: "validate_cross_lob"
  severity: "WARNING"
  passed: false
  message: "Cannot parse .vbproj as XML"
  error_type: "VBPROJ_PARSE_ERROR"
  details:
    file: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHome20260101.vbproj"
    parse_error: "mismatched tag at line 47"
```

**Recovery:** Developer can fix the .vbproj XML and say "re-validate", or skip
this check if the .vbproj was manually verified.

### Rework Protocol

**Minor rework** (developer says "fix territory 5" or "change that value to 350"):

1. Orchestrator applies the edit using the Edit tool
2. Orchestrator appends a `rework-{NNN}` entry to operations_log.yaml
3. Orchestrator updates file_hashes.yaml with the new hash
4. Orchestrator re-launches the Reviewer (all 3 agents) for re-validation
5. Reviewer treats rework entries (`agent: "orchestrator"`) like rate-modifier
   entries for validation purposes
6. Re-present updated Gate 2 results

**Complex rework** (multiple files affected, scope change, shifted line numbers):

1. Orchestrator sets state to PLANNED with rework_notes in manifest.yaml
2. Developer runs /iq-execute (modifier agents read rework_notes for context)
3. Developer runs /iq-review again (fresh validation cycle)

**Rework loop limit:** After 3 rework cycles without developer approval:

```
This is rework cycle 4. Previous 3 cycles did not resolve all issues.
Options:
  1. Review the original plan (/iq-plan output)
  2. Start fresh with a new /iq-plan
  3. Continue with cycle 4
```

---

## 11. Key Rules

1. **NEVER modify original (old-dated) Code/ files.** Only new-dated copies
   created by the file-copier are valid targets. If an old file appears in the
   operations_log, flag it as a BLOCKER immediately.

2. **NEVER skip BLOCKER validators.** All 4 BLOCKER validators (Array6 syntax,
   completeness, no old file modification, no commented code modified) MUST run.
   If one crashes, report the crash -- do not silently skip.

3. **Self-correction: max 1 attempt per BLOCKER.** One retry catches transient
   issues. Two retries of the same mechanical action are unlikely to succeed.
   After 1 failed retry, escalate to the developer via the orchestrator.

4. **Self-correction restores the ENTIRE file from snapshot.** Because snapshots
   are per-file (not per-operation), restoring one operation's failure reverts ALL
   operations on that file. The Reviewer must re-apply ALL operations for the
   file, in execution_order.yaml sequence.

5. **Write ALL output files before signaling completion.** The orchestrator reads
   these files to build Gate 2. Missing files cause Gate 2 to fail:
   `validator_results.yaml`, `diff_report.md`, `changes.diff`,
   `traceability_matrix.md`, `change_summary.md`.

6. **Do NOT update manifest.yaml.** State transitions (EXECUTED -> VALIDATING ->
   COMPLETED) are orchestrator-only. The Reviewer writes verification/ and
   summary/ files; the orchestrator reads them and updates manifest.

7. **Do NOT interact with the developer directly.** In team mode, send
   `DEVELOPER_QUESTION` messages to the orchestrator, which relays them. In
   sequential mode, write issues to output files with `status: "needs_review"`.

8. **Use SHA-256 for all hash comparisons.** Compute via Python hashlib. Compare
   against `execution/file_hashes.yaml` entries (prefixed `sha256:`).

9. **Handle both agent log formats.** Rate Modifier entries have `changes[].values_changed`
   and `summary.change_range`. Logic Modifier entries have `changes[].change_type`
   and `summary.lines_added`. Dispatch validators by the `agent` field.

10. **Treat `agent: "orchestrator"` rework entries like rate-modifier entries.**
    These are minor rework edits applied by the orchestrator during /iq-review.
    Run Array6 syntax, value sanity, and completeness validators on them.

11. **New files (no snapshot) use empty baseline for diff.** When the Logic Modifier
    creates a new file (`new_file_created: true`), the diff baseline is `/dev/null`.
    The entire file content is shown as additions.

12. **Sentinel values (-999, 0) must be preserved.** Flag as WARNING if a sentinel
    value was modified (e.g., `-999` multiplied to `-1049`). The developer should
    treat sentinel modification as effectively a BLOCKER.

13. **Report untraced SRDs and orphan changes in the traceability matrix.** An
    untraced SRD has zero executed operations. An orphan change has no matching
    SRD. Both are WARNINGs, not BLOCKERs -- the developer decides at Gate 2.

14. **Bottom-to-top execution order is NOT relevant to the Reviewer.** The Reviewer
    reads files and compares content -- it does not apply changes by line number.
    Bottom-to-top matters during /iq-execute, not during /iq-review.

15. **NEVER modify cross-province shared files.** If a cross-province file
    (from `config.yaml["cross_province_shared_files"]`) appears in the operations_log,
    flag it as a BLOCKER (CROSS_PROVINCE_VIOLATION). These files are explicitly
    excluded from automated changes.

---

## 12. NOT YET IMPLEMENTED (Future Enhancements)

- **Automated compilation check:** Build the .vbproj using MSBuild and verify
  the DLL compiles without errors. Currently the developer builds manually in
  Visual Studio after approval. This would catch syntax errors, missing references,
  and type mismatches that text-based validators cannot detect.

- **Visual diff viewer:** Generate an HTML diff report with VB.NET syntax
  highlighting, side-by-side comparison, and clickable operation annotations.
  Currently the diff_report.md is plain text with unified diff format.

- **Regression testing:** Run existing TBW test cases against the modified DLL
  and compare quote outputs to a baseline. This would catch functional regressions
  that pass all structural validators but produce incorrect premium calculations.

- **Parallel validator execution:** Run all 7 validators concurrently instead of
  sequentially. The validators are independent (each reads the same input files)
  and do not modify state. Parallelization would reduce review time for large
  workstreams with many modified files.

- **Historical comparison:** Compare rate changes to the previous version's values
  (not just snapshot vs current). This would provide "version N-1 vs version N"
  context and catch cases where the rate was already adjusted in a prior update.

- **Confidence scoring:** Assign a confidence score (0-100) to each change based
  on: deviation from expected percentage, consistency with other territories,
  pattern match quality, and historical rate trajectories. Low-confidence changes
  would be highlighted for extra scrutiny at Gate 2.

- **Automated SVN commit:** After developer approval, the plugin commits directly
  to SVN with the suggested commit message. Currently the developer must copy the
  commit message and run `svn commit` manually. This would require SVN credentials
  configuration and a confirmation step.

<!-- IMPLEMENTATION: Phase 09 -->
