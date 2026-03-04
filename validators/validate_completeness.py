"""
Validator: Completeness
Severity: BLOCKER

Purpose:
    Verify that all expected changes were applied -- no partial updates.
    For base rate changes, every territory must be updated. For multi-LOB
    tickets, all LOBs must be handled.

What it checks:
    1. For base rate changes: all territories in the function were updated
       (e.g., if there are 15 Case blocks in GetBasePremium_Home, all 15
       should have modified Array6 values, not just 10)
    2. For multi-LOB tickets: all target LOBs have their LOB-specific
       operations completed (e.g., all 6 ResourceID.vb files updated)
    3. For factor table changes: all specified Case values were updated
    4. Every operation in the execution plan is marked COMPLETED in the
       operations log
    5. No operations are stuck in PENDING or IN_PROGRESS state

What it does NOT check:
    - Whether the values are correct (that's validate_value_sanity)
    - Whether Array6 syntax is valid (that's validate_array6)
    - Whether old files were modified (that's validate_no_old_modify)

Return schema:
    {
        "passed": bool,           # True if all changes are complete
        "severity": "BLOCKER",
        "findings": [
            {
                "file": str,      # File with incomplete changes
                "issue": str,     # Description (e.g., "Territory 12 not updated")
                "operation": str, # Intent ID (e.g., "intent-001")
                "expected": str,  # What was expected
                "actual": str,    # What was found
            }
        ]
    }
"""

import re
from pathlib import Path

from _helpers import load_context, load_yaml, make_result


# ---------------------------------------------------------------------------
# Operation Loader
# ---------------------------------------------------------------------------

def _load_planned_operations(workstream_dir, findings=None):
    """Load planned operations from intent_graph.yaml.

    Reads analysis/intent_graph.yaml (the single source of planned intents).
    If the file does not exist, appends an error finding and returns empty.

    Each intent defines a planned change with id, capability, strategy_hint,
    function, target_lines, file, etc. as written by the Decomposer/Analyzer agents.

    Args:
        workstream_dir: Path to the workstream directory.
        findings: Optional list to append parse error findings to.

    Returns:
        dict mapping intent ID (str) -> parsed intent spec (dict).
        Empty dict if intent_graph.yaml is missing or contains no entries.
    """
    intent_graph_path = workstream_dir / "analysis" / "intent_graph.yaml"
    if not intent_graph_path.exists():
        if findings is not None:
            findings.append({
                "file": str(intent_graph_path),
                "issue": "intent_graph_missing",
                "operation": "",
                "expected": "analysis/intent_graph.yaml exists",
                "actual": "file not found -- no planned operations to validate against",
            })
        return {}

    try:
        graph = load_yaml(intent_graph_path)
    except Exception as e:
        if findings is not None:
            findings.append({
                "file": str(intent_graph_path),
                "issue": "intent_graph_parse_error",
                "operation": "",
                "expected": "valid YAML",
                "actual": str(e),
            })
        return {}

    if graph and isinstance(graph, dict):
        intents = graph.get("intents", [])
        if isinstance(intents, list) and intents:
            operations = {}
            for intent in intents:
                if not isinstance(intent, dict):
                    continue
                intent_id = intent.get("id", "")
                if not intent_id:
                    continue
                operations[intent_id] = intent
            return operations

    return {}


# ---------------------------------------------------------------------------
# Check 1: Every planned operation has a log entry
# ---------------------------------------------------------------------------

def _check_all_ops_logged(operations, ops_log, findings):
    """Verify that every planned operation has a corresponding entry in the
    operations log.

    A planned operation that is not in the log means it was never attempted --
    the execution was incomplete.

    Args:
        operations: dict mapping op_id -> op_spec (from intent_graph.yaml).
        ops_log: Parsed operations_log.yaml dict.
        findings: List to append finding dicts to (mutated in place).
    """
    logged_ops = {
        e["operation"]
        for e in ops_log.get("operations", [])
        if "operation" in e
    }

    for op_id, op_spec in operations.items():
        if op_id not in logged_ops:
            findings.append({
                "file": op_spec.get("file", ""),
                "issue": "not_in_log",
                "operation": op_id,
                "expected": f"Operation {op_id} should have an entry in operations_log",
                "actual": "no log entry found -- operation was never executed",
            })


# ---------------------------------------------------------------------------
# Check 2: No FAILED or stuck operations (SKIPPED is OK)
# ---------------------------------------------------------------------------

def _check_no_failed_or_stuck(ops_log, findings):
    """Verify no operations have a terminal failure or stuck status.

    Valid terminal statuses:
    - COMPLETED -- operation finished successfully.
    - SKIPPED   -- values already at target (acceptable outcome).

    Invalid statuses:
    - FAILED      -- operation encountered an error.
    - PENDING     -- operation was never started.
    - IN_PROGRESS -- operation started but never finished.

    Args:
        ops_log: Parsed operations_log.yaml dict.
        findings: List to append finding dicts to.
    """
    for entry in ops_log.get("operations", []):
        status = entry.get("status", "UNKNOWN")
        op_id = entry.get("operation", "unknown")
        filepath = entry.get("file", "")

        if status == "FAILED":
            findings.append({
                "file": filepath,
                "issue": "failed",
                "operation": op_id,
                "expected": "COMPLETED or SKIPPED",
                "actual": f"status is FAILED",
            })
        elif status == "PENDING":
            findings.append({
                "file": filepath,
                "issue": "pending",
                "operation": op_id,
                "expected": "COMPLETED or SKIPPED",
                "actual": "status is PENDING -- operation was never started",
            })
        elif status == "IN_PROGRESS":
            findings.append({
                "file": filepath,
                "issue": "in_progress",
                "operation": op_id,
                "expected": "COMPLETED or SKIPPED",
                "actual": "status is IN_PROGRESS -- operation started but never finished",
            })


# ---------------------------------------------------------------------------
# Check 3: Territory counting for array6-multiply operations
# ---------------------------------------------------------------------------

def _find_function_bounds(lines, function_name):
    """Find the start and end line indices of a VB.NET function or sub in source lines.

    Searches for a Function or Sub declaration matching the given name, then
    finds the corresponding End Function / End Sub.

    Args:
        lines: List of source line strings (0-indexed).
        function_name: Name of the function to find (e.g., "GetBasePremium_Home").

    Returns:
        Tuple (start_index, end_index) as 0-based line indices, or (None, None)
        if the function was not found.
    """
    # Match "Function FuncName" or "Sub FuncName" with optional access modifier
    # and parameters. The function name may be followed by ( or whitespace.
    pattern = re.compile(
        r'(?:Public\s+|Private\s+|Friend\s+)?'
        r'(?:Shared\s+)?'
        r'(?:Function|Sub)\s+'
        + re.escape(function_name)
        + r'(?:\s*\(|\s)',
        re.IGNORECASE,
    )

    func_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("'"):
            continue
        if pattern.search(stripped):
            func_start = i
            break

    if func_start is None:
        return None, None

    # Find the End Function / End Sub
    end_pattern = re.compile(r'^\s*End\s+(?:Function|Sub)\s*$', re.IGNORECASE)
    for i in range(func_start + 1, len(lines)):
        if end_pattern.match(lines[i]):
            return func_start, i

    # If no End found, use end of file as a fallback
    return func_start, len(lines) - 1


def _count_territories_in_function(lines, function_name):
    """Count unique numeric Case labels within a function body.

    Uses Algorithm 3 from reviewer.md. Reads the snapshot (pre-edit) file
    to establish the expected count of territory Case blocks. Territory-based
    Select Case blocks use numeric Case labels (Case 1, Case 2, ...).

    Both inline-body (Case N : ...) and multi-line-body (Case N on its own
    line) forms are counted.

    Args:
        lines: List of source line strings (the full file content).
        function_name: Name of the function containing the territory Case blocks.

    Returns:
        int: Count of unique numeric Case labels in the function. Returns 0 if
        the function is not found or has no numeric Case labels.
    """
    func_start, func_end = _find_function_bounds(lines, function_name)
    if func_start is None:
        return 0

    territory_count = 0

    for i in range(func_start, func_end + 1):
        stripped = lines[i].strip()

        # Skip comments
        if stripped.startswith("'"):
            continue

        # Match "Case N :" (inline body) -- numeric territory label with colon
        case_inline = re.match(r'^Case\s+(\d+)\s*:', stripped)
        if case_inline:
            territory_count += 1
            continue

        # Match "Case N" on its own line (multi-line body) -- no colon
        case_multiline = re.match(r'^Case\s+(\d+)\s*$', stripped)
        if case_multiline:
            territory_count += 1

    return territory_count


def _load_snapshot_lines(filepath, snapshots_dir):
    """Load snapshot file lines for territory counting.

    Delegates to the shared load_snapshot_lines() helper in _helpers.py,
    which uses collision-safe path resolution (path-safe encoding first,
    basename fallback for backward compatibility).

    Args:
        filepath: Relative file path (e.g., "Saskatchewan/Code/mod_Common_SKHab20260101.vb").
        snapshots_dir: Path to the execution/snapshots/ directory.

    Returns:
        List of line strings from the snapshot, or None if snapshot not found.
    """
    from _helpers import load_snapshot_lines
    return load_snapshot_lines(filepath, snapshots_dir)


def _check_territory_completeness(operations, ops_log, snapshots_dir, findings):
    """For array6-multiply operations (strategy_hint), verify all territories were updated.

    Counts the number of numeric Case labels in the function from the pre-edit
    snapshot (ground truth), then compares to the number of changes actually
    recorded in the operations log.

    If the snapshot is unavailable, falls back to the target_lines count from
    the intent_graph.yaml file (the Analyzer's best guess).

    Args:
        operations: dict mapping op_id -> op_spec.
        ops_log: Parsed operations_log.yaml dict.
        snapshots_dir: Path to execution/snapshots/ directory.
        findings: List to append finding dicts to.
    """
    for entry in ops_log.get("operations", []):
        if entry.get("status") != "COMPLETED":
            continue

        op_id = entry.get("operation", "")
        op_spec = operations.get(op_id)
        if not op_spec:
            continue

        # Only applies to array6-multiply strategy (base rate changes)
        if op_spec.get("strategy_hint") != "array6-multiply":
            continue

        filepath = entry.get("file", "")
        function_name = op_spec.get("function")

        # Determine expected territory count
        expected_count = 0

        # Prefer snapshot-based count (ground truth)
        snapshot_lines = _load_snapshot_lines(filepath, snapshots_dir)
        if snapshot_lines is not None and function_name:
            expected_count = _count_territories_in_function(
                snapshot_lines, function_name
            )

        # Fallback: use target_lines count from intent_graph.yaml
        if expected_count == 0:
            expected_count = len(op_spec.get("target_lines", []))

        # Count actual changes recorded
        actual_count = len(entry.get("changes", []))

        if expected_count > 0 and actual_count != expected_count:
            findings.append({
                "file": filepath,
                "issue": "territory_count_mismatch",
                "operation": op_id,
                "expected": f"{expected_count} territories",
                "actual": f"{actual_count} changes recorded",
            })


# ---------------------------------------------------------------------------
# Check 4: Factor table completeness
# ---------------------------------------------------------------------------

def _check_factor_table_completeness(operations, ops_log, findings):
    """For factor-table operations (strategy_hint), verify all specified Case values
    were updated.

    The intent spec for a factor-table change lists target_lines, each with a
    specific Case value context. The operations log should have a change entry
    for each target line.

    Args:
        operations: dict mapping op_id -> op_spec.
        ops_log: Parsed operations_log.yaml dict.
        findings: List to append finding dicts to.
    """
    for entry in ops_log.get("operations", []):
        if entry.get("status") != "COMPLETED":
            continue

        op_id = entry.get("operation", "")
        op_spec = operations.get(op_id)
        if not op_spec:
            continue

        if op_spec.get("strategy_hint") != "factor-table":
            continue

        filepath = entry.get("file", "")
        target_lines = op_spec.get("target_lines", [])
        actual_changes = entry.get("changes", [])

        # Always check for missing targets — wrong-line edits may have
        # matching counts but different line numbers (set difference).
        if len(target_lines) > 0:
            changed_line_nums = {c.get("line") for c in actual_changes}
            missing_targets = [
                t for t in target_lines
                if t.get("line") not in changed_line_nums
            ]
            for target in missing_targets:
                findings.append({
                    "file": filepath,
                    "issue": "factor_case_not_updated",
                    "operation": op_id,
                    "expected": (
                        f"line {target.get('line', '?')} updated "
                        f"(context: {target.get('context', 'unknown')})"
                    ),
                    "actual": "no change recorded for this target line",
                })


# ---------------------------------------------------------------------------
# Check 5: LOB completeness for multi-LOB hab tickets
# ---------------------------------------------------------------------------

def _extract_lob_from_path(filepath):
    """Extract the LOB name from a file path.

    Path format for LOB-specific files:
        {Province}/{LOB}/{date}/...  ->  parts[1] is the LOB

    Path format for shared Code/ files:
        {Province}/Code/...  ->  not LOB-specific (returns None)

    Args:
        filepath: Relative file path string.

    Returns:
        LOB name string, or None if the path is not LOB-specific.
    """
    parts = Path(filepath).parts
    if len(parts) >= 2:
        candidate = parts[1]
        # Code/ and SHARDCLASS/ and SharedClass/ are not LOB-specific
        if candidate.lower() in ("code", "shardclass", "sharedclass"):
            return None
        return candidate
    return None


def _check_lob_completeness(manifest, change_spec, ops_log, findings):
    """For multi-LOB hab tickets, verify all target LOBs have completed operations.

    When a ticket targets multiple LOBs (e.g., all 6 hab LOBs sharing
    mod_Common), each LOB should have at least one COMPLETED or SKIPPED
    operation. Shared module operations (in Code/) do not count toward any
    specific LOB -- only LOB-specific operations (in {LOB}/{date}/ folders)
    contribute.

    Note: Some multi-LOB tickets may ONLY touch shared modules (mod_Common),
    with no LOB-specific file changes needed. In that case, the check
    considers the shared module operations as covering all LOBs and does
    not flag missing LOBs.

    Args:
        manifest: Parsed manifest.yaml dict.
        change_spec: Parsed change_requests.yaml dict (or None).
        ops_log: Parsed operations_log.yaml dict.
        findings: List to append finding dicts to.
    """
    # Check both manifest and change_spec for shared_modules
    shared_modules = manifest.get("shared_modules", [])
    if not shared_modules and change_spec:
        shared_modules = change_spec.get("shared_modules", [])

    # Get target LOBs from manifest (or change_spec as fallback)
    target_lobs = manifest.get("lobs", [])
    if not target_lobs and change_spec:
        target_lobs = change_spec.get("lobs", [])

    # Only applies to multi-LOB tickets with shared modules
    if not shared_modules or len(target_lobs) <= 1:
        return

    # Collect LOBs that have at least one COMPLETED or SKIPPED operation
    lobs_with_ops = set()
    has_lob_specific_ops = False
    has_shared_module_ops = False

    for entry in ops_log.get("operations", []):
        if entry.get("status") not in ("COMPLETED", "SKIPPED"):
            continue

        filepath = entry.get("file", "")
        lob = _extract_lob_from_path(filepath)
        if lob is not None:
            lobs_with_ops.add(lob)
            has_lob_specific_ops = True
        else:
            has_shared_module_ops = True

    # If ALL operations are on shared modules only (no LOB-specific ops at all),
    # the shared module edit covers all LOBs -- do not flag missing LOBs.
    if has_shared_module_ops and not has_lob_specific_ops:
        return

    # If there ARE LOB-specific operations, each target LOB should have at least one
    expected_lobs = set(target_lobs)
    missing_lobs = expected_lobs - lobs_with_ops
    for lob in sorted(missing_lobs):
        findings.append({
            "file": "",
            "issue": "lob_missing",
            "operation": "",
            "expected": f"LOB {lob} should have at least one completed operation",
            "actual": f"no completed LOB-specific operations found for {lob}",
        })


# ---------------------------------------------------------------------------
# Message Builder
# ---------------------------------------------------------------------------

def _build_message(findings, operations, ops_log):
    """Build a human-readable summary message for the validator results.

    Args:
        findings: List of finding dicts.
        operations: dict mapping op_id -> op_spec (planned operations).
        ops_log: Parsed operations_log.yaml dict.

    Returns:
        str summary message.
    """
    if not findings:
        total_planned = len(operations)

        # Count completed + skipped
        completed = 0
        skipped = 0
        for entry in ops_log.get("operations", []):
            status = entry.get("status", "")
            if status == "COMPLETED":
                completed += 1
            elif status == "SKIPPED":
                skipped += 1

        parts = [f"{completed}/{total_planned} operations COMPLETED"]
        if skipped:
            parts.append(f"{skipped} SKIPPED")

        # Count total territory changes for base_rate_increase ops
        territory_total = 0
        for entry in ops_log.get("operations", []):
            if entry.get("status") != "COMPLETED":
                continue
            op_spec = operations.get(entry.get("operation", ""))
            if op_spec and op_spec.get("strategy_hint") == "array6-multiply":
                territory_total += len(entry.get("changes", []))

        if territory_total > 0:
            parts.append(f"{territory_total} territory changes applied")

        return "All completeness checks passed: " + ", ".join(parts)

    # Build failure summary
    issue_counts = {}
    for f in findings:
        issue = f.get("issue", "unknown")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    parts = []
    for issue, count in sorted(issue_counts.items()):
        parts.append(f"{issue}: {count}")

    return (
        f"Completeness check FAILED ({len(findings)} findings): "
        + ", ".join(parts)
    )


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate(manifest_path: str) -> dict:
    """Validate that all expected changes were applied completely.

    Runs 5 completeness checks:
      1. Every planned intent (from intent_graph.yaml) has a log entry in
         operations_log.yaml.
      2. No operations are FAILED, PENDING, or IN_PROGRESS.
      3. For array6-multiply (strategy_hint): territory counts match snapshot ground truth.
      4. For factor-table (strategy_hint): all target Case values were updated.
      5. For multi-LOB hab tickets: all LOBs have completed operations.

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate change_requests, operations, and
                       operations_log for completeness checking.

    Returns:
        dict with keys: passed (bool), severity (str), findings (list).
        See module docstring for full return schema.
    """
    try:
        ctx = load_context(manifest_path)
    except Exception as e:
        return make_result(
            severity="BLOCKER",
            passed=False,
            findings=[{
                "file": str(manifest_path),
                "issue": "context_load_error",
                "operation": "",
                "expected": "valid manifest and context files",
                "actual": str(e),
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    manifest = ctx["manifest"]
    workstream_dir = ctx["workstream_dir"]
    ops_log = ctx["ops_log"]
    snapshots_dir = ctx["snapshots_dir"]

    findings = []

    # Load planned operations from intent_graph.yaml
    try:
        operations = _load_planned_operations(workstream_dir, findings=findings)
    except Exception as e:
        return make_result(
            severity="BLOCKER",
            passed=False,
            findings=[{
                "file": "",
                "issue": "operations_load_error",
                "operation": "",
                "expected": "readable intent_graph.yaml",
                "actual": str(e),
            }],
            message=f"Validator crashed loading planned operations: {e}",
        )

    # Load change_requests for LOB completeness check (optional)
    change_spec = None
    change_requests_path = workstream_dir / "parsed" / "change_requests.yaml"
    if change_requests_path.exists():
        try:
            change_spec = load_yaml(change_requests_path)
        except Exception:
            pass  # Non-fatal; LOB check will use manifest only

    # Check 1: Every planned operation has a log entry
    try:
        _check_all_ops_logged(operations, ops_log, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check1_error",
            "operation": "",
            "expected": "planned-vs-logged check succeeds",
            "actual": f"Check 1 crashed: {e}",
        })

    # Check 2: No FAILED / PENDING / IN_PROGRESS operations
    try:
        _check_no_failed_or_stuck(ops_log, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check2_error",
            "operation": "",
            "expected": "status check succeeds",
            "actual": f"Check 2 crashed: {e}",
        })

    # Check 3: Territory counting for array6-multiply operations
    try:
        _check_territory_completeness(operations, ops_log, snapshots_dir, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check3_error",
            "operation": "",
            "expected": "territory counting succeeds",
            "actual": f"Check 3 crashed: {e}",
        })

    # Check 4: Factor table completeness
    try:
        _check_factor_table_completeness(operations, ops_log, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check4_error",
            "operation": "",
            "expected": "factor table completeness check succeeds",
            "actual": f"Check 4 crashed: {e}",
        })

    # Check 5: LOB completeness for multi-LOB hab tickets
    try:
        _check_lob_completeness(manifest, change_spec, ops_log, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check5_error",
            "operation": "",
            "expected": "LOB completeness check succeeds",
            "actual": f"Check 5 crashed: {e}",
        })

    # Build summary message
    message = _build_message(findings, operations, ops_log)

    return make_result(
        severity="BLOCKER",
        passed=len(findings) == 0,
        findings=findings,
        message=message,
    )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print(
            "Usage: python validate_completeness.py <manifest_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
