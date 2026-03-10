"""
Tests for validate_handoff.py — Pipeline Handoff Contract Validator

Uses pytest tmp_path fixtures to create mock workstream directories with
controlled YAML artifacts.

Run with:
    cd <plugin-root>/validators
    python -m pytest test_validate_handoff.py -v
"""

import os

import yaml
import pytest

from validate_handoff import validate_handoff


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path, data):
    """Write a dict/list to a YAML file, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _assert_envelope(result, expect_passed=None):
    """Assert that result is a valid make_result() envelope."""
    assert isinstance(result, dict), f"Expected dict envelope, got {type(result).__name__}"
    assert "passed" in result, "Envelope missing 'passed' key"
    assert "severity" in result, "Envelope missing 'severity' key"
    assert "findings" in result, "Envelope missing 'findings' key"
    assert isinstance(result["findings"], list), "'findings' must be a list"
    if expect_passed is not None:
        assert result["passed"] == expect_passed, (
            f"Expected passed={expect_passed}, got passed={result['passed']}; "
            f"findings: {result['findings']}"
        )


def _build_full_workstream(ws_dir):
    """Build a complete, valid workstream with all 4 handoff artifacts.

    Returns the workstream directory path (same as ws_dir).
    """
    # Handoff 1: parsed/change_requests.yaml
    _write_yaml(str(ws_dir / "parsed" / "change_requests.yaml"), {
        "workflow_id": "20260101-SK-Hab-rate-update",
        "ticket_id": "25545",
        "change_requests": [
            {
                "cr_id": "cr-001",
                "summary": "Increase home base rates by 5%",
                "change_type": "value_editing",
                "extracted": {"factor": 1.05, "scope": "all territories"},
            },
            {
                "cr_id": "cr-002",
                "summary": "Add new territory 5100",
                "change_type": "structure_insertion",
                "extracted": {"territory": "5100", "value": 512.59},
            },
        ],
    })

    # Handoff 2: analysis/code_understanding.yaml (v0.4.0 schema)
    _write_yaml(str(ws_dir / "analysis" / "code_understanding.yaml"), {
        "schema_version": "0.4.0",
        "project_map": {
            "Saskatchewan/Code/mod_Common_SKHab20260101.vb": {
                "functions": ["GetBaseRate"],
            },
        },
        "entry_point": "Saskatchewan/20260101/Cssi.IntelliQuote.PORTSKHab20260101.vbproj",
        "change_requests": {
            "cr-001": {
                "fub": {
                    "function": "GetBaseRate",
                    "file": "mod_Common_SKHab20260101.vb",
                    "line_start": 400,
                    "line_end": 500,
                },
                "target_file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
            },
            "cr-002": {
                "fub": {
                    "function": "GetBaseRate",
                    "file": "mod_Common_SKHab20260101.vb",
                    "line_start": 400,
                    "line_end": 500,
                },
                "target_file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
            },
        },
    })

    # Handoff 3: analysis/intent_graph.yaml
    _write_yaml(str(ws_dir / "analysis" / "intent_graph.yaml"), {
        "workflow_id": "20260101-SK-Hab-rate-update",
        "intents": [
            {
                "intent_id": "intent-001",
                "cr_id": "cr-001",
                "capability": "value_editing",
                "target_file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
                "function": "GetBaseRate",
            },
            {
                "intent_id": "intent-002",
                "cr_id": "cr-002",
                "capability": "structure_insertion",
                "target_file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
                "function": "GetBaseRate",
            },
        ],
    })

    # Handoff 4: plan/execution_order.yaml + execution/file_hashes.yaml
    _write_yaml(str(ws_dir / "plan" / "execution_order.yaml"), [
        {"intent_id": "intent-001", "file": "mod_Common_SKHab20260101.vb"},
        {"intent_id": "intent-002", "file": "mod_Common_SKHab20260101.vb"},
    ])
    _write_yaml(str(ws_dir / "execution" / "file_hashes.yaml"), {
        "files": {"mod_Common_SKHab20260101.vb": "sha256:abc123"},
    })

    return ws_dir


# ===========================================================================
# Test 1: All handoffs valid — zero findings
# ===========================================================================

def test_all_handoffs_valid(tmp_path):
    """Complete workstream with all required fields. Should produce no findings."""
    ws = _build_full_workstream(tmp_path / "ws")
    result = validate_handoff(str(ws))
    _assert_envelope(result, expect_passed=True)
    assert result["findings"] == [], f"Expected no findings, got: {result['findings']}"


# ===========================================================================
# Test 2: Missing required top-level key produces BLOCKER
# ===========================================================================

def test_missing_workflow_id_in_change_requests(tmp_path):
    """change_requests.yaml missing 'workflow_id' (and no 'province') should produce WARNING."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        # "workflow_id" deliberately omitted, no "province" either
        "ticket_id": "25545",
        "change_requests": [
            {"cr_id": "cr-001", "summary": "test", "change_type": "value_editing",
             "extracted": {}},
        ],
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result, expect_passed=False)
    findings = result["findings"]
    warning_findings = [f for f in findings if "workflow_id" in f["message"] or "province" in f["message"]]
    assert len(warning_findings) >= 1
    assert warning_findings[0]["severity"] == "WARNING"
    assert findings[0]["phase"] == "intake\u2192understand"


# ===========================================================================
# Test 3: Missing file produces BLOCKER
# ===========================================================================

def test_missing_code_understanding_file(tmp_path):
    """analysis/code_understanding.yaml does not exist. Should produce BLOCKER."""
    ws = tmp_path / "ws"
    os.makedirs(str(ws), exist_ok=True)
    # No analysis/code_understanding.yaml — but we explicitly ask for understand phase
    result = validate_handoff(str(ws), phase="understand")
    _assert_envelope(result, expect_passed=False)
    findings = result["findings"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "BLOCKER"
    assert "Missing artifact" in findings[0]["message"]
    assert findings[0]["phase"] == "understand\u2192plan"


# ===========================================================================
# Test 4: Empty change_requests list produces BLOCKER
# ===========================================================================

def test_empty_change_requests_list(tmp_path):
    """change_requests: [] should produce a BLOCKER (no CRs)."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        "change_requests": [],
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert len(blockers) == 1
    assert "empty" in blockers[0]["message"].lower()


# ===========================================================================
# Test 5: Partial CR (missing cr_id) produces BLOCKER
# ===========================================================================

def test_partial_cr_missing_cr_id(tmp_path):
    """A CR entry missing both 'cr_id' and 'id' should produce a BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        "change_requests": [
            {
                # "cr_id" and "id" deliberately omitted
                "summary": "Increase rates",
                "change_type": "value_editing",
                "extracted": {"factor": 1.05},
            },
        ],
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("cr_id" in b["message"] for b in blockers)


# ===========================================================================
# Test 6: Non-dict extracted field produces WARNING
# ===========================================================================

def test_non_dict_extracted_produces_warning(tmp_path):
    """'extracted' as a string instead of dict should produce WARNING."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        "change_requests": [
            {
                "cr_id": "cr-001",
                "summary": "Increase rates",
                "change_type": "value_editing",
                "extracted": "not-a-dict",
            },
        ],
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result)
    warnings = [f for f in result["findings"] if f["severity"] == "WARNING"]
    assert len(warnings) == 1
    assert "extracted" in warnings[0]["message"]


# ===========================================================================
# Test 7: code_understanding.yaml missing required top-level keys produces BLOCKER
# ===========================================================================

def test_understand_missing_required_keys(tmp_path):
    """code_understanding.yaml missing schema_version/project_map/entry_point/change_requests. BLOCKER."""
    ws = tmp_path / "ws"
    # File exists but has none of the required keys
    _write_yaml(str(ws / "analysis" / "code_understanding.yaml"), {
        "workflow_id": "test-wf",
    })

    result = validate_handoff(str(ws), phase="understand")
    _assert_envelope(result, expect_passed=False)
    findings = result["findings"]
    blocker_msgs = [f["message"] for f in findings if f["severity"] == "BLOCKER"]
    # Should flag all four missing required keys
    assert any("schema_version" in m for m in blocker_msgs)
    assert any("project_map" in m for m in blocker_msgs)
    assert any("entry_point" in m for m in blocker_msgs)
    assert any("change_requests" in m for m in blocker_msgs)


# ===========================================================================
# Test 8: code_understanding.yaml with empty change_requests dict produces BLOCKER
# ===========================================================================

def test_understand_empty_change_requests(tmp_path):
    """code_understanding.yaml with change_requests: {} should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "code_understanding.yaml"), {
        "schema_version": "0.4.0",
        "project_map": {"file.vb": {"functions": ["Func1"]}},
        "entry_point": "Province/20260101/project.vbproj",
        "change_requests": {},
    })

    result = validate_handoff(str(ws), phase="understand")
    _assert_envelope(result, expect_passed=False)
    findings = result["findings"]
    blockers = [f for f in findings if f["severity"] == "BLOCKER"]
    assert len(blockers) == 1
    assert "empty" in blockers[0]["message"].lower()


# ===========================================================================
# Test 9: Intent missing required field produces BLOCKER
# ===========================================================================

def test_intent_missing_capability(tmp_path):
    """An intent entry missing 'capability' should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "intent_graph.yaml"), {
        "workflow_id": "test-wf",
        "intents": [
            {
                "intent_id": "intent-001",
                "cr_id": "cr-001",
                # "capability" deliberately omitted
                "target_file": "some_file.vb",
                "function": "SomeFunc",
            },
        ],
    })

    result = validate_handoff(str(ws), phase="plan")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("capability" in b["message"] for b in blockers)


# ===========================================================================
# Test 10: Empty intents list produces BLOCKER
# ===========================================================================

def test_empty_intents_list(tmp_path):
    """intents: [] should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "intent_graph.yaml"), {
        "workflow_id": "test-wf",
        "intents": [],
    })

    result = validate_handoff(str(ws), phase="plan")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert len(blockers) == 1
    assert "empty" in blockers[0]["message"].lower()


# ===========================================================================
# Test 11: execution_order.yaml entry missing intent_id produces BLOCKER
# ===========================================================================

def test_execution_order_missing_intent_id(tmp_path):
    """An entry in execution_order.yaml without 'intent_id'. BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "plan" / "execution_order.yaml"), [
        {"intent_id": "intent-001", "file": "file1.vb"},
        {"file": "file2.vb"},  # missing intent_id
    ])
    _write_yaml(str(ws / "execution" / "file_hashes.yaml"), {"files": {}})

    result = validate_handoff(str(ws), phase="planner")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("intent_id" in b["message"] for b in blockers)


# ===========================================================================
# Test 12: Missing file_hashes.yaml produces BLOCKER
# ===========================================================================

def test_missing_file_hashes(tmp_path):
    """execution/file_hashes.yaml missing. BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "plan" / "execution_order.yaml"), [
        {"intent_id": "intent-001"},
    ])
    # Do NOT create execution/file_hashes.yaml

    result = validate_handoff(str(ws), phase="planner")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("file_hashes" in b["message"] for b in blockers)


# ===========================================================================
# Test 13: Auto-detect skips phases with no artifacts
# ===========================================================================

def test_auto_detect_only_checks_present_artifacts(tmp_path):
    """With only intake artifact present, only intake handoff is checked."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        "change_requests": [
            {"cr_id": "cr-001", "summary": "test", "change_type": "value_editing",
             "extracted": {}},
        ],
    })

    # No other artifacts — auto-detect should only check intake
    result = validate_handoff(str(ws))
    _assert_envelope(result, expect_passed=True)
    # All findings should be from intake->understand phase
    for f in result["findings"]:
        assert f["phase"] == "intake\u2192understand"


# ===========================================================================
# Test 14: Workstream directory does not exist
# ===========================================================================

def test_nonexistent_workstream_dir(tmp_path):
    """Pointing to a nonexistent directory should produce BLOCKER."""
    result = validate_handoff(str(tmp_path / "does-not-exist"))
    _assert_envelope(result, expect_passed=False)
    findings = result["findings"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "BLOCKER"
    assert "does not exist" in findings[0]["message"]


# ===========================================================================
# Test 15: Unknown phase name produces WARNING
# ===========================================================================

def test_unknown_phase_name(tmp_path):
    """Passing an invalid phase name should produce WARNING."""
    ws = tmp_path / "ws"
    os.makedirs(str(ws), exist_ok=True)

    result = validate_handoff(str(ws), phase="nonexistent")
    _assert_envelope(result, expect_passed=False)
    findings = result["findings"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "WARNING"
    assert "Unknown phase" in findings[0]["message"]


# ===========================================================================
# Test 16: Multiple missing CR fields accumulate BLOCKERs
# ===========================================================================

def test_multiple_missing_cr_fields(tmp_path):
    """A CR missing cr_id/id and title/summary should produce 2 BLOCKERs (change_type is optional)."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        "change_requests": [
            {
                # Missing cr_id/id and title/summary — only extracted present
                "extracted": {},
            },
        ],
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    missing_fields = [b["message"] for b in blockers]
    assert any("cr_id" in m for m in missing_fields)
    assert any("title" in m or "summary" in m for m in missing_fields)
    # change_type is now optional (Intake does not produce it)


# ===========================================================================
# Test 17: CR entry missing 'fub' in code_understanding.yaml produces WARNING
# ===========================================================================

def test_understand_cr_missing_fub(tmp_path):
    """A CR entry in code_understanding.yaml missing 'fub' should produce WARNING."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "code_understanding.yaml"), {
        "schema_version": "0.4.0",
        "project_map": {"file.vb": {"functions": ["Func1"]}},
        "entry_point": "Province/20260101/project.vbproj",
        "change_requests": {
            "cr-001": {
                # "fub" deliberately omitted
                "target_file": "some_file.vb",
            },
        },
    })

    result = validate_handoff(str(ws), phase="understand")
    _assert_envelope(result)
    warnings = [f for f in result["findings"] if f["severity"] == "WARNING"]
    assert len(warnings) == 1
    assert "fub" in warnings[0]["message"]


# ===========================================================================
# Test 18: execution_order.yaml as empty list produces BLOCKER
# ===========================================================================

def test_empty_execution_order(tmp_path):
    """execution_order.yaml with [] should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "plan" / "execution_order.yaml"), [])
    _write_yaml(str(ws / "execution" / "file_hashes.yaml"), {"files": {}})

    result = validate_handoff(str(ws), phase="planner")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("empty" in b["message"].lower() for b in blockers)


# ===========================================================================
# Test 19: execution_order.yaml as dict with order key
# ===========================================================================

def test_execution_order_dict_format(tmp_path):
    """execution_order.yaml as dict with 'order' key should work."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "plan" / "execution_order.yaml"), {
        "order": [
            {"intent_id": "intent-001", "file": "file1.vb"},
        ],
    })
    _write_yaml(str(ws / "execution" / "file_hashes.yaml"), {"files": {}})

    result = validate_handoff(str(ws), phase="planner")
    _assert_envelope(result, expect_passed=True)
    # No blockers — dict format with order key is accepted
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert len(blockers) == 0


# ===========================================================================
# Test 19b: execution_order.yaml as v0.4.0 dict with execution_sequence key
# ===========================================================================

def test_execution_order_v040_dict_format(tmp_path):
    """v0.4.0 execution_order.yaml with 'execution_sequence' key should work."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "plan" / "execution_order.yaml"), {
        "plan_version": "3.0",
        "execution_sequence": [
            {"intent_id": "intent-001", "file": "file1.vb", "phase": 1},
        ],
        "file_copies": [],
        "phases": [{"phase": 1, "intents": ["intent-001"]}],
    })
    _write_yaml(str(ws / "execution" / "file_hashes.yaml"), {"files": {}})

    result = validate_handoff(str(ws), phase="planner")
    _assert_envelope(result, expect_passed=True)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert len(blockers) == 0


# ===========================================================================
# Test 19c: execution_order.yaml as dict WITHOUT execution_sequence → BLOCKER
# ===========================================================================

def test_execution_order_dict_missing_sequence(tmp_path):
    """v0.4.0 dict without execution_sequence/order key should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "plan" / "execution_order.yaml"), {
        "plan_version": "3.0",
        "file_copies": [],
        "phases": [{"phase": 1}],
        # Missing execution_sequence — this is the bug the Codex review found
    })
    _write_yaml(str(ws / "execution" / "file_hashes.yaml"), {"files": {}})

    result = validate_handoff(str(ws), phase="planner")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("execution_sequence" in b["message"] for b in blockers)


# ===========================================================================
# Test 20: Full workstream with specific phase check
# ===========================================================================

def test_full_workstream_specific_phase(tmp_path):
    """Full workstream, checking only 'plan' phase. Zero findings."""
    ws = _build_full_workstream(tmp_path / "ws")
    result = validate_handoff(str(ws), phase="plan")
    _assert_envelope(result, expect_passed=True)
    assert result["findings"] == []


# ===========================================================================
# Test 21: code_understanding.yaml with change_requests as list (wrong type) produces BLOCKER
# ===========================================================================

def test_understand_change_requests_wrong_type(tmp_path):
    """change_requests as a list instead of dict in code_understanding.yaml should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "code_understanding.yaml"), {
        "schema_version": "0.4.0",
        "project_map": {"file.vb": {"functions": ["Func1"]}},
        "entry_point": "Province/20260101/project.vbproj",
        "change_requests": [{"cr_id": "cr-001"}],  # should be a dict, not list
    })

    result = validate_handoff(str(ws), phase="understand")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("change_requests" in b["message"] and "dict" in b["message"] for b in blockers)


# ===========================================================================
# Test 22: CRs with "id" field instead of "cr_id" pass validation
# ===========================================================================

def test_cr_with_id_instead_of_cr_id(tmp_path):
    """Intake agent uses 'id' instead of 'cr_id'. Should pass."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        "change_requests": [
            {
                "id": "cr-001",  # Intake agent convention
                "summary": "Increase rates",
                "change_type": "value_editing",
                "extracted": {"factor": 1.05},
            },
        ],
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result, expect_passed=True)
    assert result["findings"] == [], f"Expected no findings, got: {result['findings']}"


# ===========================================================================
# Test 23: "requests" top-level key instead of "change_requests" passes
# ===========================================================================

def test_requests_key_instead_of_change_requests(tmp_path):
    """Intake agent uses 'requests' instead of 'change_requests'. Should pass."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        "requests": [
            {
                "id": "cr-001",
                "summary": "Increase rates",
                "change_type": "value_editing",
                "extracted": {"factor": 1.05},
            },
        ],
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result, expect_passed=True)
    assert result["findings"] == [], f"Expected no findings, got: {result['findings']}"


# ===========================================================================
# Test 24: Intents with "id" and "file" instead of "intent_id" and "target_file"
# ===========================================================================

def test_intent_with_id_and_file_aliases(tmp_path):
    """Plan agent uses 'id' and 'file' instead of 'intent_id' and 'target_file'. Should pass."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "intent_graph.yaml"), {
        "workflow_id": "test-wf",
        "intents": [
            {
                "id": "intent-001",        # Plan agent convention
                "cr_id": "cr-001",
                "capability": "value_editing",
                "file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",  # Plan agent convention
                "function": "GetBaseRate",
            },
        ],
    })

    result = validate_handoff(str(ws), phase="plan")
    _assert_envelope(result, expect_passed=True)
    assert result["findings"] == [], f"Expected no findings, got: {result['findings']}"


# ===========================================================================
# Test 25: Intent missing BOTH "intent_id" AND "id" produces BLOCKER
# ===========================================================================

def test_intent_missing_both_id_fields(tmp_path):
    """An intent missing both 'intent_id' and 'id' should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "intent_graph.yaml"), {
        "workflow_id": "test-wf",
        "intents": [
            {
                # No intent_id or id
                "cr_id": "cr-001",
                "capability": "value_editing",
                "target_file": "some_file.vb",
                "function": "SomeFunc",
            },
        ],
    })

    result = validate_handoff(str(ws), phase="plan")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("intent_id" in b["message"] for b in blockers)


# ===========================================================================
# Test 26: Intent missing BOTH "target_file" AND "file" produces BLOCKER
# ===========================================================================

def test_intent_missing_both_file_fields(tmp_path):
    """An intent missing both 'target_file' and 'file' should produce BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "analysis" / "intent_graph.yaml"), {
        "workflow_id": "test-wf",
        "intents": [
            {
                "intent_id": "intent-001",
                "cr_id": "cr-001",
                "capability": "value_editing",
                # No target_file or file
                "function": "SomeFunc",
            },
        ],
    })

    result = validate_handoff(str(ws), phase="plan")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("target_file" in b["message"] for b in blockers)


# ===========================================================================
# Test 27: CR missing both "change_requests" AND "requests" produces BLOCKER
# ===========================================================================

def test_missing_both_change_requests_and_requests_keys(tmp_path):
    """Neither 'change_requests' nor 'requests' present. BLOCKER."""
    ws = tmp_path / "ws"
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "test-wf",
        "ticket_id": "12345",
        # No change_requests or requests key
    })

    result = validate_handoff(str(ws), phase="intake")
    _assert_envelope(result, expect_passed=False)
    blockers = [f for f in result["findings"] if f["severity"] == "BLOCKER"]
    assert any("change_requests" in b["message"] for b in blockers)


# ===========================================================================
# Test 28: Full workstream using all agent-convention field names
# ===========================================================================

def test_full_workstream_agent_convention_names(tmp_path):
    """Full workstream using 'requests', 'id', 'file' naming. Should pass all checks."""
    ws = tmp_path / "ws"

    # Handoff 1: parsed/change_requests.yaml (using agent conventions)
    _write_yaml(str(ws / "parsed" / "change_requests.yaml"), {
        "workflow_id": "20260101-SK-Hab-rate-update",
        "ticket_id": "25545",
        "requests": [
            {
                "id": "cr-001",
                "summary": "Increase home base rates by 5%",
                "change_type": "value_editing",
                "extracted": {"factor": 1.05},
            },
        ],
    })

    # Handoff 2: analysis/code_understanding.yaml (v0.4.0 schema)
    _write_yaml(str(ws / "analysis" / "code_understanding.yaml"), {
        "schema_version": "0.4.0",
        "project_map": {
            "Saskatchewan/Code/mod_Common_SKHab20260101.vb": {
                "functions": ["GetBaseRate"],
            },
        },
        "entry_point": "Saskatchewan/20260101/Cssi.IntelliQuote.PORTSKHab20260101.vbproj",
        "change_requests": {
            "cr-001": {
                "fub": {
                    "function": "GetBaseRate",
                    "file": "mod_Common_SKHab20260101.vb",
                    "line_start": 400,
                    "line_end": 500,
                },
                "target_file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
            },
        },
    })

    # Handoff 3: analysis/intent_graph.yaml (using agent conventions)
    _write_yaml(str(ws / "analysis" / "intent_graph.yaml"), {
        "workflow_id": "20260101-SK-Hab-rate-update",
        "intents": [
            {
                "id": "intent-001",
                "cr_id": "cr-001",
                "capability": "value_editing",
                "file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
                "function": "GetBaseRate",
            },
        ],
    })

    # Handoff 4: plan/execution_order.yaml + execution/file_hashes.yaml
    _write_yaml(str(ws / "plan" / "execution_order.yaml"), [
        {"intent_id": "intent-001", "file": "mod_Common_SKHab20260101.vb"},
    ])
    _write_yaml(str(ws / "execution" / "file_hashes.yaml"), {
        "files": {"mod_Common_SKHab20260101.vb": "sha256:abc123"},
    })

    result = validate_handoff(str(ws))
    _assert_envelope(result, expect_passed=True)
    assert result["findings"] == [], f"Expected no findings, got: {result['findings']}"


# ===========================================================================
# Test 29: Envelope always has 'message' key
# ===========================================================================

def test_envelope_has_message_key(tmp_path):
    """The result envelope should always include a 'message' key."""
    ws = _build_full_workstream(tmp_path / "ws")
    result = validate_handoff(str(ws))
    _assert_envelope(result, expect_passed=True)
    assert "message" in result
    assert "All handoff checks passed" in result["message"]

    # Also check failure case
    result_fail = validate_handoff(str(tmp_path / "nonexistent"))
    _assert_envelope(result_fail, expect_passed=False)
    assert "message" in result_fail
    assert "issue(s) found" in result_fail["message"]
