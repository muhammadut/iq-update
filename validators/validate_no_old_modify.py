"""
Validator: No Old File Modification
Severity: BLOCKER

Purpose:
    Verify that only files matching the target version date were edited.
    Old dated files must NEVER be modified -- they are shared by older
    version folders. Also verify that .vbproj references were updated
    for all new Code/ file copies.

What it checks:
    1. Source file hashes unchanged -- every file with role "source" in
       file_hashes.yaml must have the same SHA-256 hash as when the
       workflow started.
    2. .vbproj references point to target date -- every <Compile Include>
       in a .vbproj that references a Code/ or SHARDCLASS/ or SharedClass/
       file must contain the target effective date, not an old date.
    3. Cross-province shared files were NOT modified -- files listed in
       config.yaml["cross_province_shared_files"] must not appear in the
       operations log.

What it does NOT check:
    - Whether the content of the new files is correct (other validators)
    - Whether the .vbproj XML is otherwise valid (IQWiz's responsibility)

Return schema:
    {
        "passed": bool,
        "severity": "BLOCKER",
        "findings": [
            {
                "file": str,
                "issue": str,         # "source_file_missing" | "source_modified"
                                      # | "old_date_ref" | "cross_province_violation"
                                      # | "vbproj_parse_error"
                "expected_hash": str,  # (for source_modified)
                "actual_hash": str,    # (for source_modified)
                "include": str,        # (for old_date_ref)
                "found_date": str,     # (for old_date_ref)
                "expected_date": str,  # (for old_date_ref)
                "message": str,        # human-readable
            }
        ]
    }
"""

from pathlib import Path

from _helpers import (
    check_vbproj_refs,
    compute_file_hash,
    load_context,
    make_result,
)


# ---------------------------------------------------------------------------
# Check 1: Source file hashes unchanged
# ---------------------------------------------------------------------------

def _check_source_hashes(file_hashes, carrier_root, findings):
    """Verify that every source-role file has the same hash as recorded.

    Source files are the old-dated Code/ files that were used as the basis
    for new copies. They must NEVER be modified -- if a source file hash
    has changed, a critical safety invariant has been violated.

    Args:
        file_hashes: Parsed file_hashes.yaml dict with "files" key.
        carrier_root: Path to the carrier codebase root.
        findings: List to append finding dicts to (mutated in place).
    """
    files = file_hashes.get("files", {})
    if not files:
        return

    for filepath, fh_info in files.items():
        if not isinstance(fh_info, dict):
            continue
        if fh_info.get("role") != "source":
            continue

        path = carrier_root / filepath
        if not path.exists():
            findings.append({
                "file": filepath,
                "issue": "source_file_missing",
                "message": f"Source file no longer exists: {filepath}",
            })
            continue

        current_hash = compute_file_hash(path)
        expected_hash = fh_info.get("hash", "")

        if current_hash != expected_hash:
            findings.append({
                "file": filepath,
                "issue": "source_modified",
                "expected_hash": expected_hash,
                "actual_hash": current_hash,
                "message": (
                    f"Source file was modified: {filepath} "
                    f"(expected {expected_hash}, got {current_hash})"
                ),
            })


# ---------------------------------------------------------------------------
# Check 2: .vbproj references point to target date
# ---------------------------------------------------------------------------

def _check_vbproj_references(file_hashes, carrier_root, target_date, findings):
    """Verify that all .vbproj files have Code/ references pointing to target_date.

    Iterates over all .vbproj files tracked in file_hashes.yaml and uses
    check_vbproj_refs() to parse each one and validate date references.

    Args:
        file_hashes: Parsed file_hashes.yaml dict with "files" key.
        carrier_root: Path to the carrier codebase root.
        target_date: Expected date string (e.g., "20260101").
        findings: List to append finding dicts to (mutated in place).
    """
    if not target_date:
        return  # No effective_date set -- skip this check

    files = file_hashes.get("files", {})
    if not files:
        return

    for filepath in files:
        if not filepath.endswith(".vbproj"):
            continue

        vbproj_path = carrier_root / filepath
        if not vbproj_path.exists():
            continue

        ref_findings = check_vbproj_refs(vbproj_path, target_date)
        findings.extend(ref_findings)


# ---------------------------------------------------------------------------
# Check 3: Cross-province shared files not modified
# ---------------------------------------------------------------------------

def _check_cross_province_violations(ops_log, config, findings):
    """Verify that no cross-province shared files appear in the operations log.

    Cross-province shared files (e.g., Code/PORTCommonHeat.vb) are listed in
    config.yaml["cross_province_shared_files"]. These files are shared across
    provinces and must NEVER be automatically modified.

    Args:
        ops_log: Parsed operations_log.yaml dict.
        config: Parsed config.yaml dict (or None if unavailable).
        findings: List to append finding dicts to (mutated in place).
    """
    cross_province_files = []
    if config:
        cross_province_files = config.get("cross_province_shared_files", [])

    if not cross_province_files:
        return

    for entry in ops_log.get("operations", []):
        filepath = entry.get("file", "")
        if not filepath:
            continue

        for cpf in cross_province_files:
            if (filepath == cpf
                    or filepath.endswith("/" + cpf)
                    or filepath.endswith("\\" + cpf)):
                findings.append({
                    "file": filepath,
                    "issue": "cross_province_violation",
                    "message": f"Cross-province shared file was modified: {filepath}",
                })
                break  # One finding per ops_log entry is sufficient


# ---------------------------------------------------------------------------
# Message Builder
# ---------------------------------------------------------------------------

def _build_message(findings, file_hashes):
    """Build a human-readable summary message for the validator results.

    Args:
        findings: List of finding dicts.
        file_hashes: Parsed file_hashes.yaml dict.

    Returns:
        str summary message.
    """
    if not findings:
        files = file_hashes.get("files", {})
        source_count = sum(
            1 for fh in files.values()
            if isinstance(fh, dict) and fh.get("role") == "source"
        )
        vbproj_count = sum(
            1 for fp in files if fp.endswith(".vbproj")
        )
        return (
            f"No old file modifications detected: "
            f"{source_count} source files verified, "
            f"{vbproj_count} .vbproj references checked"
        )

    # Build failure summary
    issue_counts = {}
    for f in findings:
        issue = f.get("issue", "unknown")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    parts = []
    for issue, count in sorted(issue_counts.items()):
        parts.append(f"{issue}: {count}")

    return (
        f"Old-file-modification check FAILED ({len(findings)} findings): "
        + ", ".join(parts)
    )


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate(manifest_path: str) -> dict:
    """Validate that no old dated files were modified and .vbproj refs updated.

    Runs 3 safety checks:
      1. Every source-role file hash is unchanged from file_hashes.yaml.
      2. Every .vbproj Code/ reference points to the target effective_date.
      3. No cross-province shared files appear in the operations log.

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate file_hashes.yaml, operations_log,
                       config.yaml, and target .vbproj files.

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
                "message": f"Validator crashed during context loading: {e}",
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    carrier_root = ctx["carrier_root"]
    file_hashes = ctx["file_hashes"]
    ops_log = ctx["ops_log"]
    config = ctx["config"]
    target_date = ctx["manifest"].get("effective_date", "")

    findings = []

    # Check 1: Source file hashes unchanged
    try:
        _check_source_hashes(file_hashes, carrier_root, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check1_error",
            "message": f"Source hash check crashed: {e}",
        })

    # Check 2: .vbproj references point to target date
    try:
        _check_vbproj_references(file_hashes, carrier_root, target_date, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check2_error",
            "message": f"Vbproj reference check crashed: {e}",
        })

    # Check 3: Cross-province shared files not modified
    try:
        _check_cross_province_violations(ops_log, config, findings)
    except Exception as e:
        findings.append({
            "file": "",
            "issue": "check3_error",
            "message": f"Cross-province check crashed: {e}",
        })

    # Build summary message
    message = _build_message(findings, file_hashes)

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
            "Usage: python validate_no_old_modify.py <manifest_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
