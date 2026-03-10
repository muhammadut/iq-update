"""
Validator: Pipeline Handoff Contracts
Severity: BLOCKER (missing required fields) / WARNING (missing optional fields)

Purpose:
    Verify that YAML artifacts produced by each pipeline phase have the
    required fields before the next phase consumes them. This catches
    incomplete or malformed handoff artifacts early — before a downstream
    agent fails with a cryptic KeyError.

Handoff boundaries checked:
    1. Intake → Understand:   parsed/change_requests.yaml
    2. Understand → Plan:     analysis/code_understanding.yaml
    3. Plan → Execute:        analysis/intent_graph.yaml
    4. Planner → Execute:     plan/execution_order.yaml + execution/file_hashes.yaml

Usage:
    # Check all handoffs that have artifacts present:
    findings = validate_handoff("/path/to/workstream")

    # Check a specific phase boundary:
    findings = validate_handoff("/path/to/workstream", phase="intake")

Returns a standard make_result() envelope:
    {
        "passed": bool,
        "severity": "BLOCKER",
        "findings": [...],
        "message": "human-readable summary",
    }

Each finding is a dict:
    {
        "severity": "BLOCKER" | "WARNING",
        "message": "human-readable description",
        "phase": "intake→understand" | "understand→plan" | ...,
        "file": "relative path to the artifact file",
    }

Field name flexibility:
    - CRs: accepts both "cr_id" and "id"; top-level "change_requests" or "requests"
    - Intents: accepts both "intent_id" and "id"; "target_file" and "file"
"""

import os

import yaml
from pathlib import Path

from _helpers import make_result


# ---------------------------------------------------------------------------
# YAML Loading (local — avoids coupling to _helpers for standalone use)
# ---------------------------------------------------------------------------

def _load_yaml(path):
    """Load a YAML file, returning None if it does not exist or is invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError):
        return None


# ---------------------------------------------------------------------------
# Individual Handoff Checks
# ---------------------------------------------------------------------------

def _check_intake_to_understand(ws, findings):
    """Handoff 1: Intake → Understand.

    File: parsed/change_requests.yaml
    Top-level: workflow_id or province (WARNING if missing), ticket_id or ticket_ref (WARNING if missing)
    Required top-level list: change_requests (or requests)
    Each CR requires: cr_id (or id), title (or summary), extracted (dict)
    change_type is optional (Intake does not produce it)
    """
    phase = "intake→understand"
    rel_path = "parsed/change_requests.yaml"
    full_path = ws / "parsed" / "change_requests.yaml"

    if not full_path.exists():
        findings.append({
            "severity": "BLOCKER",
            "message": f"Missing artifact: {rel_path}",
            "phase": phase,
            "file": rel_path,
        })
        return

    data = _load_yaml(full_path)
    if data is None:
        findings.append({
            "severity": "BLOCKER",
            "message": f"Cannot parse YAML: {rel_path}",
            "phase": phase,
            "file": rel_path,
        })
        return

    if not isinstance(data, dict):
        findings.append({
            "severity": "BLOCKER",
            "message": f"Expected dict at top level, got {type(data).__name__}",
            "phase": phase,
            "file": rel_path,
        })
        return

    # workflow_id may not exist in Intake output (lives in manifest.yaml)
    # ticket_id may appear as ticket_ref in Intake output
    if not (data.get("workflow_id") or data.get("province")):
        findings.append({
            "severity": "WARNING",
            "message": "Missing top-level identifier: 'workflow_id' or 'province' (Intake uses province/effective_date)",
            "phase": phase,
            "file": rel_path,
        })
    if not (data.get("ticket_id") or data.get("ticket_ref")):
        findings.append({
            "severity": "WARNING",
            "message": "Missing top-level key: 'ticket_id' (or 'ticket_ref')",
            "phase": phase,
            "file": rel_path,
        })

    # Accept both "change_requests" (validator convention) and "requests" (Intake agent output)
    # Use key-existence checks to avoid falsy-value pitfalls (empty list is valid to detect)
    if "change_requests" in data:
        crs = data["change_requests"]
    elif "requests" in data:
        crs = data["requests"]
    else:
        crs = None

    if crs is None:
        findings.append({
            "severity": "BLOCKER",
            "message": "Missing required top-level key: 'change_requests' (or 'requests')",
            "phase": phase,
            "file": rel_path,
        })
    elif not isinstance(crs, list):
        findings.append({
            "severity": "BLOCKER",
            "message": f"'change_requests'/'requests' must be a list, got {type(crs).__name__}",
            "phase": phase,
            "file": rel_path,
        })
    elif len(crs) == 0:
        findings.append({
            "severity": "BLOCKER",
            "message": "'change_requests'/'requests' list is empty — Intake produced no CRs",
            "phase": phase,
            "file": rel_path,
        })
    else:
        # Validate each CR entry
        # Accept both naming conventions: cr_id/id, summary, change_type, extracted
        for idx, cr in enumerate(crs):
            if not isinstance(cr, dict):
                findings.append({
                    "severity": "BLOCKER",
                    "message": f"change_requests[{idx}] is not a dict",
                    "phase": phase,
                    "file": rel_path,
                })
                continue
            # cr_id OR id (Intake agent uses "id")
            if not (cr.get("cr_id") or cr.get("id")):
                findings.append({
                    "severity": "BLOCKER",
                    "message": f"change_requests[{idx}] missing required field: 'cr_id' (or 'id')",
                    "phase": phase,
                    "file": rel_path,
                })
            # title OR summary (Intake agent uses "title")
            if not (cr.get("title") or cr.get("summary")):
                findings.append({
                    "severity": "BLOCKER",
                    "message": f"change_requests[{idx}] missing required field: 'title' (or 'summary')",
                    "phase": phase,
                    "file": rel_path,
                })
            # extracted is always required
            if "extracted" not in cr:
                findings.append({
                    "severity": "BLOCKER",
                    "message": f"change_requests[{idx}] missing required field: 'extracted'",
                    "phase": phase,
                    "file": rel_path,
                })
            # change_type is optional (Intake does not produce it; downstream agents classify)
            # extracted should be a dict
            extracted = cr.get("extracted")
            if extracted is not None and not isinstance(extracted, dict):
                findings.append({
                    "severity": "WARNING",
                    "message": f"change_requests[{idx}]['extracted'] should be a dict, got {type(extracted).__name__}",
                    "phase": phase,
                    "file": rel_path,
                })


def _check_understand_to_plan(ws, findings):
    """Handoff 2: Understand → Plan.

    File: analysis/code_understanding.yaml
    Required top-level: workflow_id, change_requests (dict with at least one CR)
    Each CR should have: fub (dict), target_file
    """
    phase = "understand→plan"
    rel_path = "analysis/code_understanding.yaml"
    full_path = ws / "analysis" / "code_understanding.yaml"

    if not full_path.exists():
        findings.append({
            "severity": "BLOCKER",
            "message": f"Missing artifact: {rel_path}",
            "phase": phase,
            "file": rel_path,
        })
        return

    data = _load_yaml(full_path)
    if data is None:
        findings.append({
            "severity": "BLOCKER",
            "message": f"Cannot parse YAML: {rel_path}",
            "phase": phase,
            "file": rel_path,
        })
        return

    if not isinstance(data, dict):
        findings.append({
            "severity": "BLOCKER",
            "message": f"Expected dict at top level, got {type(data).__name__}",
            "phase": phase,
            "file": rel_path,
        })
        return

    # Required top-level keys (v0.4.0 schema)
    for key in ("schema_version", "project_map", "entry_point", "change_requests"):
        if key not in data:
            findings.append({
                "severity": "BLOCKER",
                "message": f"Missing required top-level key: '{key}'",
                "phase": phase,
                "file": rel_path,
            })

    # Required top-level key: change_requests (dict)
    crs = data.get("change_requests")
    if crs is None:
        findings.append({
            "severity": "BLOCKER",
            "message": "Missing required top-level key: 'change_requests'",
            "phase": phase,
            "file": rel_path,
        })
    elif not isinstance(crs, dict):
        findings.append({
            "severity": "BLOCKER",
            "message": f"'change_requests' must be a dict, got {type(crs).__name__}",
            "phase": phase,
            "file": rel_path,
        })
    elif len(crs) == 0:
        findings.append({
            "severity": "BLOCKER",
            "message": "'change_requests' is empty — Understand agent produced no CR analyses",
            "phase": phase,
            "file": rel_path,
        })
    else:
        # Validate each CR entry has fub data
        for cr_id, cr_data in crs.items():
            if not isinstance(cr_data, dict):
                findings.append({
                    "severity": "BLOCKER",
                    "message": f"change_requests['{cr_id}'] is not a dict",
                    "phase": phase,
                    "file": rel_path,
                })
                continue
            if "fub" not in cr_data:
                findings.append({
                    "severity": "WARNING",
                    "message": f"change_requests['{cr_id}'] missing 'fub' (Function Understanding Block)",
                    "phase": phase,
                    "file": rel_path,
                })


def _check_plan_to_execute(ws, findings):
    """Handoff 3: Plan → Execute.

    File: analysis/intent_graph.yaml
    Required top-level: workflow_id, intents (list)
    Each intent requires: intent_id, cr_id, capability, target_file, function
    """
    phase = "plan→execute"
    rel_path = "analysis/intent_graph.yaml"
    full_path = ws / "analysis" / "intent_graph.yaml"

    if not full_path.exists():
        findings.append({
            "severity": "BLOCKER",
            "message": f"Missing artifact: {rel_path}",
            "phase": phase,
            "file": rel_path,
        })
        return

    data = _load_yaml(full_path)
    if data is None:
        findings.append({
            "severity": "BLOCKER",
            "message": f"Cannot parse YAML: {rel_path}",
            "phase": phase,
            "file": rel_path,
        })
        return

    if not isinstance(data, dict):
        findings.append({
            "severity": "BLOCKER",
            "message": f"Expected dict at top level, got {type(data).__name__}",
            "phase": phase,
            "file": rel_path,
        })
        return

    # Required top-level keys
    for key in ("workflow_id", "intents"):
        if key not in data:
            findings.append({
                "severity": "BLOCKER",
                "message": f"Missing required top-level key: '{key}'",
                "phase": phase,
                "file": rel_path,
            })

    # intents must be a non-empty list
    intents = data.get("intents")
    if intents is not None:
        if not isinstance(intents, list):
            findings.append({
                "severity": "BLOCKER",
                "message": f"'intents' must be a list, got {type(intents).__name__}",
                "phase": phase,
                "file": rel_path,
            })
        elif len(intents) == 0:
            findings.append({
                "severity": "BLOCKER",
                "message": "'intents' list is empty — Plan agent produced no intents",
                "phase": phase,
                "file": rel_path,
            })
        else:
            # Validate each intent entry
            # Accept both naming conventions:
            #   intent_id / id  (Plan agent uses "id")
            #   target_file / file  (Plan agent uses "file")
            #   cr_id / cr  (Plan agent uses "cr")
            #   capability, function — no known aliases
            for idx, intent in enumerate(intents):
                if not isinstance(intent, dict):
                    findings.append({
                        "severity": "BLOCKER",
                        "message": f"intents[{idx}] is not a dict",
                        "phase": phase,
                        "file": rel_path,
                    })
                    continue
                # intent_id OR id
                if not (intent.get("intent_id") or intent.get("id")):
                    findings.append({
                        "severity": "BLOCKER",
                        "message": f"intents[{idx}] missing required field: 'intent_id' (or 'id')",
                        "phase": phase,
                        "file": rel_path,
                    })
                # cr_id OR cr (Plan agent uses "cr")
                if not (intent.get("cr_id") or intent.get("cr")):
                    findings.append({
                        "severity": "BLOCKER",
                        "message": f"intents[{idx}] missing required field: 'cr_id' (or 'cr')",
                        "phase": phase,
                        "file": rel_path,
                    })
                # capability — no alias
                if "capability" not in intent:
                    findings.append({
                        "severity": "BLOCKER",
                        "message": f"intents[{idx}] missing required field: 'capability'",
                        "phase": phase,
                        "file": rel_path,
                    })
                # target_file OR file
                if not (intent.get("target_file") or intent.get("file")):
                    findings.append({
                        "severity": "BLOCKER",
                        "message": f"intents[{idx}] missing required field: 'target_file' (or 'file')",
                        "phase": phase,
                        "file": rel_path,
                    })
                # function — no alias
                if "function" not in intent:
                    findings.append({
                        "severity": "BLOCKER",
                        "message": f"intents[{idx}] missing required field: 'function'",
                        "phase": phase,
                        "file": rel_path,
                    })


def _check_planner_to_execute(ws, findings):
    """Handoff 4: Plan → Execute (execution_order + file_hashes).

    File: plan/execution_order.yaml — v0.4.0 dict with execution_sequence, or legacy flat list
    File: execution/file_hashes.yaml — must exist
    """
    phase = "plan→execute"

    # --- execution_order.yaml ---
    eo_rel = "plan/execution_order.yaml"
    eo_path = ws / "plan" / "execution_order.yaml"

    if not eo_path.exists():
        findings.append({
            "severity": "BLOCKER",
            "message": f"Missing artifact: {eo_rel}",
            "phase": phase,
            "file": eo_rel,
        })
    else:
        data = _load_yaml(eo_path)
        if data is None:
            findings.append({
                "severity": "BLOCKER",
                "message": f"Cannot parse YAML: {eo_rel}",
                "phase": phase,
                "file": eo_rel,
            })
        elif isinstance(data, list):
            if len(data) == 0:
                findings.append({
                    "severity": "BLOCKER",
                    "message": "execution_order.yaml is an empty list",
                    "phase": phase,
                    "file": eo_rel,
                })
            else:
                for idx, entry in enumerate(data):
                    if not isinstance(entry, dict):
                        findings.append({
                            "severity": "BLOCKER",
                            "message": f"execution_order[{idx}] is not a dict",
                            "phase": phase,
                            "file": eo_rel,
                        })
                    elif "intent_id" not in entry:
                        findings.append({
                            "severity": "BLOCKER",
                            "message": f"execution_order[{idx}] missing required field: 'intent_id'",
                            "phase": phase,
                            "file": eo_rel,
                        })
        elif isinstance(data, dict):
            # v0.4.0 format: dict with "execution_sequence" key (preferred)
            # Legacy formats: dict with "order" or "execution_order" key
            order = (
                data.get("execution_sequence")
                or data.get("order")
                or data.get("execution_order")
            )
            if order is not None and isinstance(order, list):
                if len(order) == 0:
                    findings.append({
                        "severity": "BLOCKER",
                        "message": "execution_sequence list is empty",
                        "phase": phase,
                        "file": eo_rel,
                    })
                else:
                    for idx, entry in enumerate(order):
                        if isinstance(entry, dict) and "intent_id" not in entry:
                            findings.append({
                                "severity": "BLOCKER",
                                "message": f"execution_sequence[{idx}] missing required field: 'intent_id'",
                                "phase": phase,
                                "file": eo_rel,
                            })
            elif order is None:
                # Dict without any recognized intent-list key
                findings.append({
                    "severity": "BLOCKER",
                    "message": "execution_order.yaml dict missing required key: 'execution_sequence'",
                    "phase": phase,
                    "file": eo_rel,
                })
        else:
            findings.append({
                "severity": "BLOCKER",
                "message": f"execution_order.yaml has unexpected type: {type(data).__name__}",
                "phase": phase,
                "file": eo_rel,
            })

    # --- file_hashes.yaml ---
    fh_rel = "execution/file_hashes.yaml"
    fh_path = ws / "execution" / "file_hashes.yaml"

    if not fh_path.exists():
        findings.append({
            "severity": "BLOCKER",
            "message": f"Missing artifact: {fh_rel}",
            "phase": phase,
            "file": fh_rel,
        })


# ---------------------------------------------------------------------------
# Phase → Checker Mapping
# ---------------------------------------------------------------------------

_PHASE_CHECKERS = {
    "intake":     _check_intake_to_understand,
    "understand": _check_understand_to_plan,
    "plan":       _check_plan_to_execute,
    "planner":    _check_planner_to_execute,
}

# Files that indicate a phase has produced output (used for auto-detection)
_PHASE_INDICATORS = {
    "intake":     "parsed/change_requests.yaml",
    "understand": "analysis/code_understanding.yaml",
    "plan":       "analysis/intent_graph.yaml",
    "planner":    "plan/execution_order.yaml",
}


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate_handoff(workstream_dir, phase=None):
    """Validate artifacts at phase boundaries.

    Args:
        workstream_dir: Path to the workstream directory
            (e.g., .iq-workstreams/changes/ticket-25545).
        phase: Optional specific phase to check. If None, checks all phases
               that have artifacts present.
               Values: "intake", "understand", "plan", "planner"

    Returns:
        dict: Standard make_result() envelope with keys:
            passed   - bool (True if zero findings)
            severity - "BLOCKER"
            findings - list of finding dicts (severity, message, phase, file)
            message  - human-readable summary string
    """
    findings = []
    ws = Path(workstream_dir)

    if not ws.exists():
        findings.append({
            "severity": "BLOCKER",
            "message": f"Workstream directory does not exist: {workstream_dir}",
            "phase": "pre-check",
            "file": str(workstream_dir),
        })
        return make_result(
            severity="BLOCKER",
            passed=False,
            findings=findings,
            message=f"Handoff validation: {len(findings)} issue(s) found",
        )

    if phase is not None:
        # Validate a specific phase
        checker = _PHASE_CHECKERS.get(phase)
        if checker is None:
            findings.append({
                "severity": "WARNING",
                "message": f"Unknown phase: '{phase}'. Valid phases: {', '.join(sorted(_PHASE_CHECKERS))}",
                "phase": "pre-check",
                "file": "",
            })
            return make_result(
                severity="BLOCKER",
                passed=False,
                findings=findings,
                message=f"Handoff validation: {len(findings)} issue(s) found",
            )
        checker(ws, findings)
    else:
        # Auto-detect: check all phases whose indicator artifact exists
        for phase_name, indicator in _PHASE_INDICATORS.items():
            indicator_path = ws / indicator
            if indicator_path.exists():
                _PHASE_CHECKERS[phase_name](ws, findings)

    return make_result(
        severity="BLOCKER",
        passed=len(findings) == 0,
        findings=findings,
        message=f"Handoff validation: {len(findings)} issue(s) found" if findings else "All handoff checks passed",
    )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python validate_handoff.py <workstream_dir> [phase]",
              file=sys.stderr)
        sys.exit(1)

    ws_dir = sys.argv[1]
    ph = sys.argv[2] if len(sys.argv) > 2 else None

    result = validate_handoff(ws_dir, phase=ph)
    print(json.dumps(result, indent=2))

    sys.exit(0 if result["passed"] else 1)
