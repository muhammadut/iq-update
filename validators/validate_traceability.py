"""
Validator: Traceability
Severity: WARNING

Purpose:
    Verify that every SRD requirement maps to at least one code change
    and that no orphan changes exist (changes not linked to any SRD).
    This ensures nothing was missed and nothing was added without
    authorization.

What it checks:
    1. Every SRD in the parsed/srds/ directory (or change_spec.yaml)
       has at least one corresponding operation in the operations log
    2. Every operation in the operations log traces back to a valid SRD
    3. No orphan changes: every operation ID maps to a known SRD, and
       non-standard IDs are flagged

What it does NOT check:
    - Whether the changes are correct (other validators)
    - Whether the changes are complete for each SRD (validate_completeness)
    - Whether the SRDs were correctly parsed from the input (Intake's job)

Edge cases handled:
    - Rework entries (rework-*) are skipped in the orphan check
    - DAT-file SRDs with no operations are still flagged as untraced
      (developer decides at Gate 2 if acceptable)
    - SKIPPED operations still count as traced log entries
    - FAILED operations still count for traceability mapping
    - No SRDs found returns passed=true with informational message
    - Non-standard op IDs (not matching op-NNN-NN) flagged as orphans

Return schema:
    {
        "passed": bool,
        "severity": "WARNING",
        "findings": [
            {
                "issue": str,         # "untraced_srd" | "orphan_change"
                "srd": str,           # SRD ID (for untraced_srd)
                "description": str,   # SRD description (for untraced_srd)
                "operation": str,     # Operation ID (for orphan_change)
                "mapped_srd": str,    # SRD the op claims to belong to (for orphan_change)
                "message": str,       # Human-readable
            }
        ],
        "message": str
    }
"""

from pathlib import Path

from _helpers import extract_srd_from_op, load_context, load_yaml, make_result


# ---------------------------------------------------------------------------
# SRD Loading
# ---------------------------------------------------------------------------

def _load_srds_from_files(srds_dir):
    """Load SRD IDs and descriptions from individual srd-*.yaml files.

    Args:
        srds_dir: Path to the parsed/srds/ directory.

    Returns:
        Tuple of (srd_ids set, srd_descriptions dict).
    """
    srd_ids = set()
    srd_descriptions = {}

    if not srds_dir.exists():
        return srd_ids, srd_descriptions

    for srd_file in srds_dir.glob("srd-*.yaml"):
        try:
            srd_data = load_yaml(srd_file)
        except Exception:
            continue  # Skip malformed YAML files
        if not isinstance(srd_data, dict):
            continue
        srd_id = srd_data.get("id", srd_data.get("srd_id", srd_file.stem))
        srd_ids.add(srd_id)
        srd_descriptions[srd_id] = srd_data.get("description", "")

    return srd_ids, srd_descriptions


def _load_srds_from_change_spec(change_spec_path):
    """Load SRD IDs and descriptions from change_spec.yaml as fallback.

    Only used when no individual srd-*.yaml files were found.

    Args:
        change_spec_path: Path to parsed/change_spec.yaml.

    Returns:
        Tuple of (srd_ids set, srd_descriptions dict).
    """
    srd_ids = set()
    srd_descriptions = {}

    if not change_spec_path.exists():
        return srd_ids, srd_descriptions

    try:
        change_spec = load_yaml(change_spec_path)
    except Exception:
        return srd_ids, srd_descriptions  # Malformed YAML
    if not isinstance(change_spec, dict):
        return srd_ids, srd_descriptions

    for srd in change_spec.get("srds", []):
        if not isinstance(srd, dict):
            continue
        srd_id = srd.get("id", srd.get("srd_id", ""))
        if srd_id:
            srd_ids.add(srd_id)
            srd_descriptions[srd_id] = srd.get("description", "")

    return srd_ids, srd_descriptions


# ---------------------------------------------------------------------------
# Operation Mapping
# ---------------------------------------------------------------------------

def _build_op_srd_mapping(ops_log):
    """Build mappings between operations and SRDs.

    Args:
        ops_log: Parsed operations_log.yaml dict with "operations" key.

    Returns:
        Tuple of (ops_by_srd dict, all_op_srds dict).
            ops_by_srd: srd_id -> [op_id, ...]
            all_op_srds: op_id -> srd_id (only for ops matching op-NNN-NN)
    """
    ops_by_srd = {}   # srd_id -> [op_id, ...]
    all_op_srds = {}   # op_id -> srd_id

    for entry in ops_log.get("operations", []):
        op_id = entry.get("operation", "")
        srd_id = extract_srd_from_op(op_id)
        if srd_id:
            all_op_srds[op_id] = srd_id
            ops_by_srd.setdefault(srd_id, []).append(op_id)

    return ops_by_srd, all_op_srds


# ---------------------------------------------------------------------------
# Check 1: Every SRD has at least one operation
# ---------------------------------------------------------------------------

def _check_untraced_srds(srd_ids, srd_descriptions, ops_by_srd, findings):
    """Check that every SRD has at least one operation in the log.

    SRDs with no operations are flagged as "untraced_srd". This includes
    DAT-file SRDs -- the developer decides at Gate 2 if acceptable.

    Args:
        srd_ids: Set of known SRD IDs.
        srd_descriptions: Dict mapping srd_id -> description.
        ops_by_srd: Dict mapping srd_id -> [op_id, ...].
        findings: List to append finding dicts to (mutated in place).
    """
    for srd_id in sorted(srd_ids):
        if srd_id not in ops_by_srd:
            srd_desc = srd_descriptions.get(srd_id, "")
            findings.append({
                "issue": "untraced_srd",
                "srd": srd_id,
                "description": srd_desc,
                "message": f"SRD {srd_id} has no operations in the log",
            })


# ---------------------------------------------------------------------------
# Check 2: Every operation maps to a known SRD
# ---------------------------------------------------------------------------

def _check_orphan_changes(ops_log, srd_ids, all_op_srds, findings):
    """Check that every operation maps to a known SRD.

    Rework entries (starting with "rework-") are skipped. Operations
    whose op_id follows op-NNN-NN but maps to an unknown SRD are flagged.
    Operations with non-standard IDs are also flagged.

    Args:
        ops_log: Parsed operations_log.yaml dict.
        srd_ids: Set of known SRD IDs.
        all_op_srds: Dict mapping op_id -> srd_id.
        findings: List to append finding dicts to (mutated in place).
    """
    for entry in ops_log.get("operations", []):
        op_id = entry.get("operation", "")

        # Skip rework entries -- they don't map to SRDs
        if op_id.startswith("rework-"):
            continue

        srd_id = all_op_srds.get(op_id)
        if srd_id and srd_id not in srd_ids:
            # op_id matches op-NNN-NN but the SRD doesn't exist
            findings.append({
                "issue": "orphan_change",
                "operation": op_id,
                "mapped_srd": srd_id,
                "message": f"Operation {op_id} maps to {srd_id} which is not in the SRD list",
            })
        elif not srd_id and op_id:
            # op_id doesn't match the op-NNN-NN pattern
            # Could be a custom operation -- flag but don't block
            findings.append({
                "issue": "orphan_change",
                "operation": op_id,
                "mapped_srd": None,
                "message": f"Operation {op_id} does not follow op-NNN-NN naming convention",
            })


# ---------------------------------------------------------------------------
# Message Builder
# ---------------------------------------------------------------------------

def _build_message(findings, srd_ids, ops_by_srd, all_op_srds):
    """Build a human-readable summary message.

    Args:
        findings: List of finding dicts.
        srd_ids: Set of known SRD IDs.
        ops_by_srd: Dict mapping srd_id -> [op_id, ...].
        all_op_srds: Dict mapping op_id -> srd_id.

    Returns:
        str summary message.
    """
    if not srd_ids:
        return "No SRDs found to trace"

    traced_srds = len(srd_ids & set(ops_by_srd.keys()))
    total_ops = len(all_op_srds)

    if not findings:
        return (
            f"Full traceability: {traced_srds}/{len(srd_ids)} SRDs traced, "
            f"{total_ops} operations mapped."
        )

    untraced = sum(1 for f in findings if f["issue"] == "untraced_srd")
    orphans = sum(1 for f in findings if f["issue"] == "orphan_change")
    parts = []
    if untraced:
        parts.append(f"{untraced} untraced SRD(s)")
    if orphans:
        parts.append(f"{orphans} orphan change(s)")
    return (
        f"Traceability gaps: {'; '.join(parts)}. "
        f"{traced_srds}/{len(srd_ids)} SRDs traced."
    )


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate(manifest_path: str) -> dict:
    """Validate that all SRDs trace to code changes and vice versa.

    Runs 2 traceability checks:
      1. Every SRD has at least one operation in the operations log.
      2. Every operation maps back to a known SRD (rework entries skipped).

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate SRD files, change_spec, and
                       operations_log for traceability checking.

    Returns:
        dict with keys: passed (bool), severity (str), findings (list),
        message (str). See module docstring for full return schema.
    """
    try:
        ctx = load_context(manifest_path)
    except Exception as e:
        return make_result(
            severity="WARNING",
            passed=False,
            findings=[{
                "issue": "context_load_error",
                "message": f"Validator crashed during context loading: {e}",
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    ops_log = ctx["ops_log"]
    workstream_dir = ctx["workstream_dir"]

    findings = []

    # --- Load SRDs ---
    # Primary: individual srd-*.yaml files in parsed/srds/
    srds_dir = workstream_dir / "parsed" / "srds"
    srd_ids, srd_descriptions = _load_srds_from_files(srds_dir)

    # Fallback: change_spec.yaml (only if no individual files found)
    if not srd_ids:
        change_spec_path = workstream_dir / "parsed" / "change_spec.yaml"
        srd_ids, srd_descriptions = _load_srds_from_change_spec(change_spec_path)

    # Edge case: no SRDs found at all
    if not srd_ids:
        return make_result(
            severity="WARNING",
            passed=True,
            findings=[],
            message="No SRDs found to trace",
        )

    # --- Build operation-to-SRD mapping ---
    ops_by_srd, all_op_srds = _build_op_srd_mapping(ops_log)

    # --- Check 1: Every SRD has at least one operation ---
    try:
        _check_untraced_srds(srd_ids, srd_descriptions, ops_by_srd, findings)
    except Exception as e:
        findings.append({
            "issue": "check1_error",
            "message": f"Untraced SRD check crashed: {e}",
        })

    # --- Check 2: Every operation maps to a known SRD ---
    try:
        _check_orphan_changes(ops_log, srd_ids, all_op_srds, findings)
    except Exception as e:
        findings.append({
            "issue": "check2_error",
            "message": f"Orphan change check crashed: {e}",
        })

    # --- Build summary message ---
    message = _build_message(findings, srd_ids, ops_by_srd, all_op_srds)

    return make_result(
        severity="WARNING",
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
            "Usage: python validate_traceability.py <manifest_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
