"""
Validator: Array6 Syntax
Severity: BLOCKER

Purpose:
    Verify that all Array6() calls in modified files have correct syntax:
    - Matching parentheses
    - Argument count unchanged from original (NOT "exactly 6" -- Array6 accepts 1-14+ args)
    - No empty arguments (no consecutive commas)
    - Values are reasonable (not negative when they shouldn't be)
    - No syntax-breaking characters introduced

This validator compares the Array6() calls in the modified file against
the pre-edit snapshot to ensure the structural integrity was preserved.

What it checks:
    1. Every Array6() call has balanced parentheses
    2. The number of arguments in each Array6() matches the original file
    3. No empty arguments exist (e.g., Array6(1, , 3))
    4. Numeric values are parseable and reasonable
    5. The variable assignment pattern is preserved (varRates = Array6(...))

What it does NOT check:
    - Whether the values are correct (that's validate_value_sanity)
    - Whether all territories are updated (that's validate_completeness)
    - Whether commented lines were modified (that's validate_no_commented_code)

Return schema:
    {
        "passed": bool,           # True if all checks pass
        "severity": "BLOCKER",    # Always BLOCKER for this validator
        "findings": [             # List of issues found (empty if passed)
            {
                "file": str,      # File path where issue was found
                "line": int,      # Line number
                "issue": str,     # Description of the issue
                "expected": str,  # What was expected (e.g., "6 arguments")
                "actual": str,    # What was found (e.g., "5 arguments")
            }
        ]
    }
"""

import json as _json
import re
import subprocess
from pathlib import Path

from _helpers import (
    build_inventory,
    check_path_containment,
    count_array6_args,
    extract_balanced_parens,
    is_array6_test_usage,
    is_full_line_comment,
    load_context,
    make_result,
    parens_balanced,
    safe_eval_arithmetic,
    split_top_level_commas,
)


# ---------------------------------------------------------------------------
# Phase 1: Operations Log Scan
# ---------------------------------------------------------------------------

def _check_ops_log(ops_log, findings):
    """Scan the operations log for Array6 issues in before/after change pairs.

    For each COMPLETED value-editing or structure-insertion operation,
    compare each change's before and after lines for:
    - Arg count mismatch (before vs after)
    - Empty arguments (consecutive commas)
    - Unmatched parentheses

    Args:
        ops_log: Parsed operations_log.yaml dict.
        findings: List to append finding dicts to (mutated in place).
    """
    for entry in ops_log.get("operations", []):
        change_type = entry.get("change_type", "")
        if change_type not in ("value_editing", "structure_insertion", "flow_modification"):
            continue
        if entry.get("status") != "COMPLETED":
            continue

        filepath = entry.get("file", "")
        operation_id = entry.get("intent_id", entry.get("operation", ""))

        for change in entry.get("changes", []):
            before_line = change.get("before", "") or ""
            after_line = change.get("after", "") or ""
            line_num = change.get("line", 0)

            # Skip if no Array6 in either line
            if "Array6" not in before_line and "Array6" not in after_line:
                continue

            # Skip dual-use: Array6 inside another function call (test/lookup)
            # But if before was a rate assignment and after became test usage,
            # that's corruption — flag it instead of skipping
            before_is_test = is_array6_test_usage(before_line) if before_line else True
            after_is_test = is_array6_test_usage(after_line) if after_line else True
            if before_is_test and after_is_test:
                continue  # Both are test usage — safe to skip
            if not before_is_test and after_is_test:
                # Rate assignment was rewritten to test usage — corruption!
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "issue": "assignment_to_test_mutation",
                    "expected": "rate assignment (var = Array6(...))",
                    "actual": "test/lookup usage",
                    "operation": operation_id,
                    "before": before_line.strip(),
                    "after": after_line.strip(),
                })
                continue

            # --- Check 1: Arg count mismatch ---
            before_count = count_array6_args(before_line) if before_line else 0
            after_count = count_array6_args(after_line) if after_line else 0

            if before_count > 0 and before_count != after_count:
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "issue": "arg_count_mismatch",
                    "expected": f"{before_count} arguments",
                    "actual": f"{after_count} arguments",
                    "operation": operation_id,
                    "before": before_line.strip(),
                    "after": after_line.strip(),
                })

            # --- Check 2: Unmatched parentheses in after line ---
            if after_line and "Array6" in after_line and not parens_balanced(after_line):
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "issue": "unmatched_parens",
                    "expected": "balanced parentheses",
                    "actual": "unbalanced parentheses in modified line",
                    "operation": operation_id,
                    "after": after_line.strip(),
                })

            # --- Check 3: Empty arguments (consecutive commas) ---
            if after_line and "Array6" in after_line:
                _check_empty_args(after_line, filepath, line_num, operation_id, findings)

            # --- Check 4: Arg count = -1 means extract_balanced_parens failed ---
            if after_count == -1:
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "issue": "unmatched_parens",
                    "expected": "Array6() with matching close paren",
                    "actual": "no matching close paren found",
                    "operation": operation_id,
                    "after": after_line.strip(),
                })

            # --- Check 5: Numeric parseability of arguments ---
            if after_line and "Array6" in after_line and after_count > 0:
                _check_numeric_args(after_line, filepath, line_num, operation_id, findings)

            # --- Check 6: Assignment pattern preserved ---
            if before_line and after_line:
                _check_assignment_pattern(before_line, after_line, filepath,
                                         line_num, operation_id, findings)


def _check_empty_args(line, filepath, line_num, operation_id, findings):
    """Check for empty arguments in an Array6() call.

    Empty args manifest as consecutive commas with only whitespace between them
    inside the Array6 content. We extract the balanced content and check each
    split argument for emptiness.

    Args:
        line: The modified VB.NET source line.
        filepath: Relative file path for the finding.
        line_num: 1-indexed line number.
        operation_id: Operation ID string.
        findings: List to append finding dicts to.
    """
    match = re.search(r'Array6\s*\(', line)
    if not match:
        return

    start = match.end()
    content = extract_balanced_parens(line, start)
    if content is None:
        return  # Unmatched parens -- already caught by paren check

    args = split_top_level_commas(content)
    for idx, arg in enumerate(args):
        if arg.strip() == "":
            findings.append({
                "file": filepath,
                "line": line_num,
                "issue": "empty_arg",
                "expected": f"non-empty value at argument position {idx + 1}",
                "actual": "empty argument (consecutive commas)",
                "operation": operation_id,
                "after": line.strip(),
            })


def _check_numeric_args(line, filepath, line_num, operation_id, findings):
    """Check that Array6 arguments are parseable as numeric values.

    Each argument should be either:
    - A numeric literal (integer or decimal, possibly negative)
    - An arithmetic expression (e.g., 30 + 10)
    - A function call (e.g., Func(x))
    - A variable reference

    We only flag arguments that look like they SHOULD be numeric (no letters
    other than function calls) but fail to parse.

    Args:
        line: The modified VB.NET source line.
        filepath: Relative file path.
        line_num: 1-indexed line number.
        operation_id: Operation ID string.
        findings: List to append finding dicts to.
    """
    match = re.search(r'Array6\s*\(', line)
    if not match:
        return

    start = match.end()
    content = extract_balanced_parens(line, start)
    if content is None:
        return

    args = split_top_level_commas(content)
    for idx, arg in enumerate(args):
        arg_stripped = arg.strip()
        if not arg_stripped:
            continue  # Empty args caught by _check_empty_args

        # Skip if it contains function calls (has parens) or variable references (letters)
        if '(' in arg_stripped:
            continue  # Function call like Func(a, b) -- not a simple numeric
        if re.search(r'[a-zA-Z_]', arg_stripped):
            continue  # Contains variable name or keyword -- skip

        # It looks like it should be purely numeric -- try to evaluate
        if not _is_parseable_numeric(arg_stripped):
            findings.append({
                "file": filepath,
                "line": line_num,
                "issue": "unparseable_value",
                "expected": f"parseable numeric value at argument position {idx + 1}",
                "actual": f"cannot parse as number: {arg_stripped!r}",
                "operation": operation_id,
                "after": line.strip(),
            })


def _is_parseable_numeric(expr):
    """Check if a string expression is parseable as a numeric value.

    Accepts:
    - Simple numbers: "512.59", "-28.73", "0", ".5"
    - Arithmetic expressions: "30 + 10", "100 - 5", "2 * 50"
    - Negative numbers: "-5"

    Args:
        expr: String expression to check.

    Returns:
        True if parseable, False otherwise.
    """
    # Remove whitespace for simpler parsing
    cleaned = expr.strip()
    if not cleaned:
        return False

    # Try direct float parse first (handles most cases)
    try:
        float(cleaned)
        return True
    except ValueError:
        pass

    # Try evaluating simple arithmetic (only +, -, *, / with numeric operands)
    # Safety: only allow digits, decimal points, spaces, and arithmetic operators
    if re.fullmatch(r'[\d.\s+\-*/()]+', cleaned):
        try:
            result = safe_eval_arithmetic(cleaned)
            return isinstance(result, (int, float))
        except (ValueError, Exception):
            return False

    return False


def _check_assignment_pattern(before_line, after_line, filepath, line_num,
                              operation_id, findings):
    """Check that the variable assignment pattern is preserved.

    If the before line has "varName = Array6(...)", the after line should also
    have the same variable name on the LHS. This catches cases where the
    modifier accidentally corrupted the assignment.

    Args:
        before_line: Original source line.
        after_line: Modified source line.
        filepath: Relative file path.
        line_num: 1-indexed line number.
        operation_id: Operation ID string.
        findings: List to append finding dicts to.
    """
    before_match = re.search(r'(\w+\$?)\s*=\s*Array6\s*\(', before_line)
    after_match = re.search(r'(\w+\$?)\s*=\s*Array6\s*\(', after_line)

    if before_match and not after_match:
        # Before had an assignment, after lost it
        findings.append({
            "file": filepath,
            "line": line_num,
            "issue": "assignment_pattern_lost",
            "expected": f"assignment to {before_match.group(1)}",
            "actual": "no Array6 assignment found in modified line",
            "operation": operation_id,
            "before": before_line.strip(),
            "after": after_line.strip(),
        })
    elif before_match and after_match:
        before_var = before_match.group(1)
        after_var = after_match.group(1)
        if before_var != after_var:
            findings.append({
                "file": filepath,
                "line": line_num,
                "issue": "assignment_variable_changed",
                "expected": f"assignment to '{before_var}'",
                "actual": f"assignment to '{after_var}'",
                "operation": operation_id,
                "before": before_line.strip(),
                "after": after_line.strip(),
            })


# ---------------------------------------------------------------------------
# Phase 2: Full-File Scan
# ---------------------------------------------------------------------------

def _check_full_file_scan(inventory, carrier_root, snapshots_dir, findings):
    """Scan every modified file on disk for corrupt Array6 calls.

    Reads each file in the value_files inventory set and checks
    every Array6 call for:
    - Unmatched parentheses
    - Empty arguments
    - Arg count mismatch vs snapshot (if snapshot available)

    Args:
        inventory: File inventory dict from build_inventory().
        carrier_root: Path to the carrier codebase root.
        snapshots_dir: Path to the execution/snapshots/ directory.
        findings: List to append finding dicts to.
    """
    for filepath in sorted(inventory["value_files"]):
        # Path containment check — reject paths that escape carrier root
        try:
            full_path = check_path_containment(filepath, carrier_root)
        except ValueError:
            findings.append({
                "file": filepath,
                "line": 0,
                "issue": "path_traversal",
                "expected": "file path within carrier root",
                "actual": f"path escapes carrier root: {filepath}",
            })
            continue

        if not full_path.exists():
            findings.append({
                "file": filepath,
                "line": 0,
                "issue": "file_not_found",
                "expected": "file exists on disk",
                "actual": f"file not found: {full_path}",
            })
            continue

        try:
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            findings.append({
                "file": filepath,
                "line": 0,
                "issue": "file_read_error",
                "expected": "readable file",
                "actual": str(e),
            })
            continue

        # Load snapshot for arg-count comparison (if available)
        snapshot_lines = _load_snapshot_lines(filepath, snapshots_dir)

        for i, line in enumerate(lines):
            line_num = i + 1

            if "Array6" not in line:
                continue

            # Skip comments
            if is_full_line_comment(line):
                continue

            # Skip dual-use (test/lookup)
            if is_array6_test_usage(line):
                continue

            # Check 1: Balanced parentheses
            if not parens_balanced(line):
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "issue": "unmatched_parens_fullscan",
                    "expected": "balanced parentheses",
                    "actual": line.strip()[:120],
                })

            # Check 2: Empty args in the full file
            arg_count = count_array6_args(line)
            if arg_count == -1:
                # Already caught by paren check above; skip duplicate
                continue

            match = re.search(r'Array6\s*\(', line)
            if match:
                start = match.end()
                content = extract_balanced_parens(line, start)
                if content is not None:
                    args = split_top_level_commas(content)
                    for idx, arg in enumerate(args):
                        if arg.strip() == "":
                            findings.append({
                                "file": filepath,
                                "line": line_num,
                                "issue": "empty_arg_fullscan",
                                "expected": f"non-empty value at position {idx + 1}",
                                "actual": "empty argument found in current file",
                            })

            # Check 3: Arg count vs snapshot
            if snapshot_lines is not None and arg_count > 0:
                _check_arg_count_vs_snapshot(
                    filepath, line_num, line, arg_count,
                    snapshot_lines, findings
                )


def _load_snapshot_lines(filepath, snapshots_dir):
    """Load snapshot file lines for comparison.

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


def _check_arg_count_vs_snapshot(filepath, line_num, current_line, current_count,
                                  snapshot_lines, findings):
    """Compare Array6 arg count on a specific line against the snapshot.

    Finds the corresponding line in the snapshot by searching for an Array6
    call with the same variable name assignment or the same Case label context.

    Args:
        filepath: Relative file path.
        line_num: 1-indexed line number in the current file.
        current_line: The current (modified) line text.
        current_count: Number of Array6 args in the current line.
        snapshot_lines: List of lines from the snapshot file.
        findings: List to append finding dicts to.
    """
    # Extract the variable name from the current line to match against snapshot
    current_var_match = re.search(r'(\w+\$?)\s*=\s*Array6\s*\(', current_line)
    if not current_var_match:
        return  # Can't match without a variable name

    current_var = current_var_match.group(1)

    # Extract the Case label context (if any) from the current line or nearby context
    # We use a simpler approach: search the snapshot line-by-line for the same
    # variable name + Array6 pattern
    case_label = _extract_case_label(current_line)

    # Search snapshot for matching Array6 assignment
    snapshot_count = _find_snapshot_arg_count(snapshot_lines, current_var, case_label)

    if snapshot_count is not None and snapshot_count > 0:
        if snapshot_count != current_count:
            findings.append({
                "file": filepath,
                "line": line_num,
                "issue": "arg_count_mismatch_snapshot",
                "expected": f"{snapshot_count} arguments (from snapshot)",
                "actual": f"{current_count} arguments",
            })


def _extract_case_label(line):
    """Extract a Case label from a line, if present.

    Patterns:
        "Case 1 : varRates = Array6(...)"  -> "1"
        "Case 15 : varRates = Array6(...)" -> "15"
        "varRates = Array6(...)"           -> None

    Args:
        line: A VB.NET source line.

    Returns:
        The Case label string, or None if no Case label found.
    """
    match = re.search(r'Case\s+(\d+)\s*:', line)
    if match:
        return match.group(1)
    return None


def _find_snapshot_arg_count(snapshot_lines, var_name, case_label):
    """Find the Array6 arg count for a matching line in the snapshot.

    Searches the snapshot for a line with the same variable name assignment
    and (optionally) the same Case label.

    Args:
        snapshot_lines: List of lines from the snapshot.
        var_name: Variable name on the LHS of the Array6 assignment.
        case_label: Case label string (e.g., "1"), or None.

    Returns:
        int arg count from the matching snapshot line, or None if not found.
    """
    # Build pattern: look for same variable + Array6 assignment
    pattern = re.compile(
        re.escape(var_name) + r'\$?\s*=\s*Array6\s*\('
    )

    candidates = []
    for line in snapshot_lines:
        if pattern.search(line) and not is_full_line_comment(line):
            candidates.append(line)

    if not candidates:
        return None

    # If we have a Case label, narrow down
    if case_label is not None:
        case_pattern = re.compile(r'Case\s+' + re.escape(case_label) + r'\s*:')
        for cand in candidates:
            if case_pattern.search(cand):
                return count_array6_args(cand)

    # If only one candidate (or no Case label), use the first match
    # This is a best-effort heuristic -- the ops_log Phase 1 check is
    # more precise because it has exact before/after pairs
    if len(candidates) == 1:
        return count_array6_args(candidates[0])

    # Multiple candidates without a distinguishing Case label -- can't
    # reliably match. Return None to skip this check.
    return None


# ---------------------------------------------------------------------------
# Phase 3: Parser-Based Syntax Verification (optional)
# ---------------------------------------------------------------------------

def _check_parser_syntax(inventory, carrier_root, vb_parser_path, findings):
    """Run vb-parser on each modified file and flag any parse errors.

    If vb-parser reports parseErrors in its JSON output, each error is
    appended as a CRITICAL finding.  Requires vb_parser_path to point to
    a working vb-parser executable; skipped silently when None.

    Args:
        inventory: File inventory dict from build_inventory().
        carrier_root: Path to the carrier codebase root.
        vb_parser_path: Absolute path to vb-parser.exe (str or Path), or None.
        findings: List to append finding dicts to (mutated in place).
    """
    if not vb_parser_path:
        return

    vb_parser_path = str(vb_parser_path)

    for filepath in sorted(inventory["all_files"]):
        try:
            full_path = check_path_containment(filepath, carrier_root)
        except ValueError:
            continue  # Already caught by Phase 2
        if not full_path.exists():
            continue

        try:
            result = subprocess.run(
                [vb_parser_path, "parse", str(full_path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                findings.append({
                    "file": filepath,
                    "line": 0,
                    "type": "parse_error",
                    "severity": "CRITICAL",
                    "issue": "parser_nonzero_exit",
                    "expected": "vb-parser exits 0",
                    "actual": f"exit code {result.returncode}: {result.stderr.strip()[:200]}",
                })
                continue

            data = _json.loads(result.stdout)
            parse_errors = data.get("parseErrors", [])
            for err in parse_errors:
                findings.append({
                    "file": filepath,
                    "line": err.get("line", 0),
                    "type": "parse_error",
                    "severity": "CRITICAL",
                    "issue": "parse_error",
                    "expected": "no parse errors",
                    "actual": err.get("message", str(err)),
                })
        except subprocess.TimeoutExpired:
            findings.append({
                "file": filepath,
                "line": 0,
                "type": "parse_error",
                "severity": "CRITICAL",
                "issue": "parser_timeout",
                "expected": "vb-parser completes within 30s",
                "actual": "parser timed out",
            })
        except Exception as e:
            findings.append({
                "file": filepath,
                "line": 0,
                "type": "parse_error",
                "severity": "CRITICAL",
                "issue": "parser_error",
                "expected": "vb-parser runs successfully",
                "actual": str(e),
            })


# ---------------------------------------------------------------------------
# Message Builder
# ---------------------------------------------------------------------------

def _build_message(findings, total_array6_calls):
    """Build a human-readable summary message for the validator results.

    Args:
        findings: List of finding dicts.
        total_array6_calls: Total number of Array6 calls checked.

    Returns:
        str summary message.
    """
    if not findings:
        return f"All Array6() calls valid: {total_array6_calls} calls checked, arg counts match"

    # Group findings by issue type
    issue_counts = {}
    for f in findings:
        issue = f.get("issue", "unknown")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    parts = []
    for issue, count in sorted(issue_counts.items()):
        parts.append(f"{issue}: {count}")

    return f"Array6 validation failed ({len(findings)} findings): {', '.join(parts)}"


# ---------------------------------------------------------------------------
# Array6 Call Counter (for message)
# ---------------------------------------------------------------------------

def _count_total_array6_calls(ops_log, inventory, carrier_root):
    """Count total Array6 calls checked across ops log and file scans.

    This is used for the summary message only (not for validation logic).

    Args:
        ops_log: Parsed operations_log.yaml dict.
        inventory: File inventory dict.
        carrier_root: Path to the carrier codebase root.

    Returns:
        int total count of Array6 calls examined.
    """
    count = 0

    # Count from ops log
    for entry in ops_log.get("operations", []):
        change_type = entry.get("change_type", "")
        if change_type not in ("value_editing", "structure_insertion", "flow_modification"):
            continue
        if entry.get("status") != "COMPLETED":
            continue
        for change in entry.get("changes", []):
            before = change.get("before", "") or ""
            after = change.get("after", "") or ""
            if "Array6" in before or "Array6" in after:
                count += 1

    # Count from full file scan
    for filepath in inventory.get("value_files", set()):
        full_path = carrier_root / filepath
        if not full_path.exists():
            continue
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line in text.splitlines():
            if "Array6" in line and not is_full_line_comment(line) and not is_array6_test_usage(line):
                count += 1

    return count


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate(manifest_path: str, vb_parser_path: str = None) -> dict:
    """Validate Array6() syntax in all modified files.

    Runs a two- or three-phase validation:
      Phase 1: Scan the operations log for before/after Array6 issues.
      Phase 2: Full-file scan of every modified file for corrupt Array6 calls.
      Phase 3: (optional) Run vb-parser on each modified file to detect parse errors.

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate the operations_log.yaml, snapshots,
                       and modified source files.
        vb_parser_path: Optional absolute path to the vb-parser executable.
                        When provided, Phase 3 runs Roslyn-based syntax
                        verification on each modified file.  When None,
                        Phase 3 is skipped.

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
                "line": 0,
                "issue": "context_load_error",
                "expected": "valid manifest and context files",
                "actual": str(e),
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    ops_log = ctx["ops_log"]
    carrier_root = ctx["carrier_root"]
    snapshots_dir = ctx["snapshots_dir"]

    # Build file inventory from operations log
    inventory = build_inventory(ops_log)

    findings = []

    # Phase 1: Operations log scan
    try:
        _check_ops_log(ops_log, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "line": 0,
            "issue": "phase1_error",
            "expected": "operations log scan succeeds",
            "actual": f"Phase 1 crashed: {e}",
        })

    # Phase 2: Full-file scan
    try:
        _check_full_file_scan(inventory, carrier_root, snapshots_dir, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "line": 0,
            "issue": "phase2_error",
            "expected": "full-file scan succeeds",
            "actual": f"Phase 2 crashed: {e}",
        })

    # Phase 3: Parser-based syntax verification (optional)
    if vb_parser_path:
        try:
            _check_parser_syntax(inventory, carrier_root, vb_parser_path, findings)
        except Exception as e:
            findings.append({
                "file": "",
                "line": 0,
                "issue": "phase3_error",
                "expected": "parser syntax check succeeds",
                "actual": f"Phase 3 crashed: {e}",
            })

    # Deduplicate findings (same file + line + issue)
    findings = _deduplicate_findings(findings)

    # Build summary message
    total_calls = _count_total_array6_calls(ops_log, inventory, carrier_root)
    message = _build_message(findings, total_calls)

    return make_result(
        severity="BLOCKER",
        passed=len(findings) == 0,
        findings=findings,
        message=message,
    )


def _deduplicate_findings(findings):
    """Remove duplicate findings based on (file, line, issue) tuple.

    When both Phase 1 (ops log) and Phase 2 (full-file scan) detect the same
    issue on the same line, we keep only the more specific Phase 1 finding
    (which includes operation ID and before/after context).

    Args:
        findings: List of finding dicts.

    Returns:
        Deduplicated list of finding dicts.
    """
    seen = set()
    result = []
    for f in findings:
        key = (f.get("file", ""), f.get("line", 0), f.get("issue", ""))
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("Usage: python validate_array6.py <manifest_path>", file=sys.stderr)
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
