"""
Validator: Traceability
Severity: WARNING

Purpose:
    Verify that every CR (change request) maps to at least one code change
    and that no orphan changes exist (changes not linked to any CR).
    This ensures nothing was missed and nothing was added without
    authorization.

What it checks:
    1. Every CR in the parsed/requests/ directory (or change_requests.yaml)
       has at least one corresponding intent in the operations log
    2. Every intent in the operations log traces back to a valid CR
    3. No orphan changes: every intent ID maps to a known CR, and
       non-standard IDs are flagged

What it does NOT check:
    - Whether the changes are correct (other validators)
    - Whether the changes are complete for each CR (validate_completeness)
    - Whether the CRs were correctly parsed from the input (Intake's job)

Edge cases handled:
    - Rework entries (rework-*) are skipped in the orphan check
    - DAT-file CRs with no intents are still flagged as untraced
      (developer decides at Gate 2 if acceptable)
    - SKIPPED intents still count as traced log entries
    - FAILED intents still count for traceability mapping
    - No CRs found returns passed=true with informational message
    - Non-standard intent IDs (not matching intent-NNN-NN) flagged as orphans

Return schema:
    {
        "passed": bool,
        "severity": "WARNING",
        "findings": [
            {
                "issue": str,         # "untraced_cr" | "orphan_change"
                "cr": str,            # CR ID (for untraced_cr)
                "description": str,   # CR description (for untraced_cr)
                "operation": str,     # Intent ID (for orphan_change)
                "mapped_cr": str,     # CR the intent claims to belong to (for orphan_change)
                "message": str,       # Human-readable
            }
        ],
        "message": str
    }
"""

from pathlib import Path

from _helpers import extract_cr_from_intent, load_context, load_yaml, make_result


# ---------------------------------------------------------------------------
# CR Loading
# ---------------------------------------------------------------------------

def _load_crs_from_files(requests_dir):
    """Load CR IDs and descriptions from individual cr-*.yaml files.

    Args:
        requests_dir: Path to the parsed/requests/ directory.

    Returns:
        Tuple of (cr_ids set, cr_descriptions dict).
    """
    cr_ids = set()
    cr_descriptions = {}

    if not requests_dir.exists():
        return cr_ids, cr_descriptions

    for cr_file in requests_dir.glob("cr-*.yaml"):
        try:
            cr_data = load_yaml(cr_file)
        except Exception:
            continue  # Skip malformed YAML files
        if not isinstance(cr_data, dict):
            continue
        cr_id = cr_data.get("id", cr_data.get("cr_id", cr_file.stem))
        cr_ids.add(cr_id)
        cr_descriptions[cr_id] = cr_data.get("description", "")

    return cr_ids, cr_descriptions


def _load_crs_from_change_requests(change_requests_path):
    """Load CR IDs and descriptions from change_requests.yaml as fallback.

    Only used when no individual cr-*.yaml files were found.

    Args:
        change_requests_path: Path to parsed/change_requests.yaml.

    Returns:
        Tuple of (cr_ids set, cr_descriptions dict).
    """
    cr_ids = set()
    cr_descriptions = {}

    if not change_requests_path.exists():
        return cr_ids, cr_descriptions

    try:
        change_requests = load_yaml(change_requests_path)
    except Exception:
        return cr_ids, cr_descriptions  # Malformed YAML
    if not isinstance(change_requests, dict):
        return cr_ids, cr_descriptions

    for cr in (change_requests.get("change_requests")
                or change_requests.get("requests", [])):
        if not isinstance(cr, dict):
            continue
        cr_id = cr.get("id", cr.get("cr_id", ""))
        if cr_id:
            cr_ids.add(cr_id)
            cr_descriptions[cr_id] = cr.get("description", "")

    return cr_ids, cr_descriptions


# ---------------------------------------------------------------------------
# Intent Mapping
# ---------------------------------------------------------------------------

def _build_intent_cr_mapping(ops_log):
    """Build mappings between intents and CRs.

    Args:
        ops_log: Parsed operations_log.yaml dict with "operations" key.

    Returns:
        Tuple of (intents_by_cr dict, all_intent_crs dict).
            intents_by_cr: cr_id -> [intent_id, ...]
            all_intent_crs: intent_id -> cr_id (only for intents matching intent-NNN-NN)
    """
    intents_by_cr = {}   # cr_id -> [intent_id, ...]
    all_intent_crs = {}   # intent_id -> cr_id

    for entry in ops_log.get("operations", []):
        intent_id = entry.get("operation", "")
        cr_id = extract_cr_from_intent(intent_id)
        if cr_id:
            all_intent_crs[intent_id] = cr_id
            intents_by_cr.setdefault(cr_id, []).append(intent_id)

    return intents_by_cr, all_intent_crs


# ---------------------------------------------------------------------------
# Check 1: Every CR has at least one intent
# ---------------------------------------------------------------------------

def _check_untraced_crs(cr_ids, cr_descriptions, intents_by_cr, findings):
    """Check that every CR has at least one intent in the log.

    CRs with no intents are flagged as "untraced_cr". This includes
    DAT-file CRs -- the developer decides at Gate 2 if acceptable.

    Args:
        cr_ids: Set of known CR IDs.
        cr_descriptions: Dict mapping cr_id -> description.
        intents_by_cr: Dict mapping cr_id -> [intent_id, ...].
        findings: List to append finding dicts to (mutated in place).
    """
    for cr_id in sorted(cr_ids):
        if cr_id not in intents_by_cr:
            cr_desc = cr_descriptions.get(cr_id, "")
            findings.append({
                "issue": "untraced_cr",
                "cr": cr_id,
                "description": cr_desc,
                "message": f"CR {cr_id} has no intents in the log",
            })


# ---------------------------------------------------------------------------
# Check 2: Every intent maps to a known CR
# ---------------------------------------------------------------------------

def _check_orphan_changes(ops_log, cr_ids, all_intent_crs, findings):
    """Check that every intent maps to a known CR.

    Rework entries (starting with "rework-") are skipped. Intents
    whose ID follows intent-NNN-NN but maps to an unknown CR are flagged.
    Intents with non-standard IDs are also flagged.

    Args:
        ops_log: Parsed operations_log.yaml dict.
        cr_ids: Set of known CR IDs.
        all_intent_crs: Dict mapping intent_id -> cr_id.
        findings: List to append finding dicts to (mutated in place).
    """
    for entry in ops_log.get("operations", []):
        intent_id = entry.get("operation", "")

        # Skip rework entries -- they don't map to CRs
        if intent_id.startswith("rework-"):
            continue

        cr_id = all_intent_crs.get(intent_id)
        if cr_id and cr_id not in cr_ids:
            # intent_id matches intent-NNN-NN but the CR doesn't exist
            findings.append({
                "issue": "orphan_change",
                "operation": intent_id,
                "mapped_cr": cr_id,
                "message": f"Intent {intent_id} maps to {cr_id} which is not in the CR list",
            })
        elif not cr_id and intent_id:
            # intent_id doesn't match the intent-NNN-NN pattern
            # Could be a custom intent -- flag but don't block
            findings.append({
                "issue": "orphan_change",
                "operation": intent_id,
                "mapped_cr": None,
                "message": f"Intent {intent_id} does not follow intent-NNN-NN naming convention",
            })


# ---------------------------------------------------------------------------
# Message Builder
# ---------------------------------------------------------------------------

def _build_message(findings, cr_ids, intents_by_cr, all_intent_crs):
    """Build a human-readable summary message.

    Args:
        findings: List of finding dicts.
        cr_ids: Set of known CR IDs.
        intents_by_cr: Dict mapping cr_id -> [intent_id, ...].
        all_intent_crs: Dict mapping intent_id -> cr_id.

    Returns:
        str summary message.
    """
    if not cr_ids:
        return "No CRs found to trace"

    traced_crs = len(cr_ids & set(intents_by_cr.keys()))
    total_intents = len(all_intent_crs)

    if not findings:
        return (
            f"Full traceability: {traced_crs}/{len(cr_ids)} CRs traced, "
            f"{total_intents} intents mapped."
        )

    untraced = sum(1 for f in findings if f["issue"] == "untraced_cr")
    orphans = sum(1 for f in findings if f["issue"] == "orphan_change")
    parts = []
    if untraced:
        parts.append(f"{untraced} untraced CR(s)")
    if orphans:
        parts.append(f"{orphans} orphan change(s)")
    return (
        f"Traceability gaps: {'; '.join(parts)}. "
        f"{traced_crs}/{len(cr_ids)} CRs traced."
    )


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate(manifest_path: str) -> dict:
    """Validate that all CRs trace to code changes and vice versa.

    Runs 2 traceability checks:
      1. Every CR has at least one intent in the operations log.
      2. Every intent maps back to a known CR (rework entries skipped).

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate CR files, change_requests, and
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

    # --- Load CRs ---
    # Primary: individual cr-*.yaml files in parsed/requests/
    requests_dir = workstream_dir / "parsed" / "requests"
    cr_ids, cr_descriptions = _load_crs_from_files(requests_dir)

    # Fallback: change_requests.yaml (only if no individual files found)
    if not cr_ids:
        change_requests_path = workstream_dir / "parsed" / "change_requests.yaml"
        cr_ids, cr_descriptions = _load_crs_from_change_requests(change_requests_path)

    # Edge case: no CRs found at all
    if not cr_ids:
        return make_result(
            severity="WARNING",
            passed=True,
            findings=[],
            message="No CRs found to trace",
        )

    # --- Build intent-to-CR mapping ---
    intents_by_cr, all_intent_crs = _build_intent_cr_mapping(ops_log)

    # --- Check 1: Every CR has at least one intent ---
    try:
        _check_untraced_crs(cr_ids, cr_descriptions, intents_by_cr, findings)
    except Exception as e:
        findings.append({
            "issue": "check1_error",
            "message": f"Untraced CR check crashed: {e}",
        })

    # --- Check 2: Every intent maps to a known CR ---
    try:
        _check_orphan_changes(ops_log, cr_ids, all_intent_crs, findings)
    except Exception as e:
        findings.append({
            "issue": "check2_error",
            "message": f"Orphan change check crashed: {e}",
        })

    # --- Build summary message ---
    message = _build_message(findings, cr_ids, intents_by_cr, all_intent_crs)

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
