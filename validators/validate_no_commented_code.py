"""
Validator: No Commented Code Modified
Severity: BLOCKER

Purpose:
    Verify that no lines starting with a comment character (') were
    modified. Commented-out code is historical -- it should never be
    changed by the plugin. Only active (uncommented) code lines should
    be edited.

What it checks:
    1. For every COMPLETED change in the operations log: the "before"
       line (if present) must NOT be a full-line comment (first
       non-whitespace character is ').
    2. For every COMPLETED change with both before and after lines:
       the change must not be an inline-comment-only change (where
       only the comment portion after an unquoted ' changed, but the
       code portion is identical).
    3. Pure insertions (before=None) are skipped -- no before line to
       check.

What it does NOT check:
    - Whether the plugin ADDED comments (traceability comments are OK)
    - Whether non-comment lines are syntactically correct (validate_array6)

Return schema:
    {
        "passed": bool,
        "severity": "BLOCKER",
        "findings": [
            {
                "file": str,       # File where commented line was modified
                "line": int,       # Line number
                "operation": str,  # Operation ID
                "issue": str,      # "commented_line_modified" | "inline_comment_only_change"
                "before": str,     # Original line (trimmed)
                "after": str,      # Modified line (trimmed)
            }
        ],
        "message": str  # Summary
    }
"""

from _helpers import (
    is_full_line_comment,
    is_inline_comment_only_change,
    load_context,
    make_result,
)


def validate(manifest_path: str) -> dict:
    """Validate that no commented-out code lines were modified.

    Iterates over all COMPLETED operations in the operations log and
    checks each change entry:
      - Skip pure insertions (before is None).
      - Flag full-line comments that were modified.
      - Flag changes where only the inline comment portion changed.

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate operations_log.yaml with before/after
                       line content.

    Returns:
        dict with keys: passed (bool), severity (str), findings (list),
        message (str). See module docstring for full return schema.
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
                "operation": "",
                "issue": "context_load_error",
                "before": "",
                "after": "",
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    ops_log = ctx["ops_log"]
    findings = []
    commented_lines_checked = 0

    for entry in ops_log.get("operations", []):
        if entry.get("status") != "COMPLETED":
            continue

        filepath = entry.get("file", "")
        op_id = entry.get("intent_id", entry.get("operation", ""))

        for change in entry.get("changes", []):
            before_line = change.get("before")
            after_line = change.get("after", "")
            line_num = change.get("line", 0)

            # Pure insertion -- no before line to check
            if before_line is None:
                continue

            commented_lines_checked += 1

            # Check 1: Was a full-line comment modified?
            if is_full_line_comment(before_line):
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "operation": op_id,
                    "issue": "commented_line_modified",
                    "before": before_line.strip(),
                    "after": after_line.strip() if after_line else "",
                })
                continue

            # Check 2: Was only the inline comment portion changed?
            if before_line and after_line and is_inline_comment_only_change(before_line, after_line):
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "operation": op_id,
                    "issue": "inline_comment_only_change",
                    "before": before_line.strip(),
                    "after": after_line.strip(),
                })

    # Build message
    if not findings:
        message = f"No commented code modified. {commented_lines_checked} change(s) checked."
    else:
        comment_mods = sum(1 for f in findings if f["issue"] == "commented_line_modified")
        inline_only = sum(1 for f in findings if f["issue"] == "inline_comment_only_change")
        parts = []
        if comment_mods:
            parts.append(f"{comment_mods} commented line(s) modified")
        if inline_only:
            parts.append(f"{inline_only} inline-comment-only change(s)")
        message = "; ".join(parts)

    return make_result("BLOCKER", len(findings) == 0, findings, message)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print(
            "Usage: python validate_no_commented_code.py <manifest_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
