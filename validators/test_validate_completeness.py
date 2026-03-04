"""
Tests for validate_completeness.py

Uses tempfile to create mock workstreams with controlled
manifest.yaml, operations_log.yaml, file_hashes.yaml, and
analysis/intent_graph.yaml.

Run with:
    cd <plugin-root>/validators
    python -m pytest test_validate_completeness.py -v
"""

import os
import tempfile

import yaml
import pytest

from validate_completeness import validate


# ---------------------------------------------------------------------------
# Test Fixtures / Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path, data):
    """Write a dict to a YAML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _write_text(path, text):
    """Write a text file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _build_workstream(
    tmpdir,
    *,
    ops_log_operations=None,
    planned_ops=None,
    manifest_extra=None,
    change_requests=None,
    snapshot_files=None,
):
    """Build a minimal mock workstream for the completeness validator.

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        ops_log_operations: list of operation dicts for operations_log.yaml.
        planned_ops: list of intent dicts written into
                     analysis/intent_graph.yaml. Each dict must have an "id" key.
        manifest_extra: extra keys to merge into manifest.yaml.
        change_requests: dict for parsed/change_requests.yaml (optional).
        snapshot_files: dict mapping filename -> file content for
                        execution/snapshots/ directory.

    Returns:
        str: Absolute path to the manifest.yaml file.
    """
    carrier_root = tmpdir
    workstreams_root = os.path.join(carrier_root, ".iq-workstreams")
    workstream_dir = os.path.join(workstreams_root, "changes", "test-ticket")
    execution_dir = os.path.join(workstream_dir, "execution")

    # --- Write operations_log.yaml ---
    ops_log = {"operations": ops_log_operations or []}
    _write_yaml(os.path.join(execution_dir, "operations_log.yaml"), ops_log)

    # --- Write file_hashes.yaml (empty, required by load_context) ---
    _write_yaml(os.path.join(execution_dir, "file_hashes.yaml"), {"files": {}})

    # --- Write manifest.yaml ---
    manifest = {
        "codebase_root": carrier_root,
        "effective_date": "20260101",
        "state": "EXECUTED",
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    manifest_path = os.path.join(workstream_dir, "manifest.yaml")
    _write_yaml(manifest_path, manifest)

    # --- Write config.yaml (empty, required by load_context) ---
    _write_yaml(os.path.join(workstreams_root, "config.yaml"), {})

    # --- Ensure snapshots dir exists ---
    snapshots_dir = os.path.join(execution_dir, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    # --- Write snapshot files if provided ---
    if snapshot_files:
        for filename, content in snapshot_files.items():
            _write_text(os.path.join(snapshots_dir, filename), content)

    # --- Write planned operations as intent_graph.yaml ---
    if planned_ops is not None:
        intent_graph = {"intents": planned_ops}
        analysis_dir = os.path.join(workstream_dir, "analysis")
        os.makedirs(analysis_dir, exist_ok=True)
        _write_yaml(os.path.join(analysis_dir, "intent_graph.yaml"), intent_graph)

    # --- Write change_requests.yaml if provided ---
    if change_requests:
        _write_yaml(
            os.path.join(workstream_dir, "parsed", "change_requests.yaml"),
            change_requests,
        )

    return manifest_path


# ---------------------------------------------------------------------------
# Test 1: Clean pass -- 3 operations all COMPLETED
# ---------------------------------------------------------------------------

def test_clean_pass_all_completed():
    """3 operations all COMPLETED with matching planned ops.
    Should pass with 0 findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "GetDeductibleDiscount"},
                {"id": "intent-002", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "GetLiabilityPremiums"},
                {"id": "intent-003", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "GetSurchargeFactor"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 100, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 200, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-003",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 300, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "BLOCKER"
        assert len(result["findings"]) == 0
        assert "3/3 operations COMPLETED" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 2: Missing operation -- planned but not in log
# ---------------------------------------------------------------------------

def test_missing_operation_not_in_log():
    """ops_log has intent-001 and intent-002 but intent_graph has intent-001,
    intent-002, intent-003. The third intent is missing from the log.
    Should produce a 'not_in_log' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func1"},
                {"id": "intent-002", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func2"},
                {"id": "intent-003", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func3"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 100, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 200, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "not_in_log"
        assert finding["operation"] == "intent-003"
        assert "never executed" in finding["actual"]


# ---------------------------------------------------------------------------
# Test 3: Failed operation
# ---------------------------------------------------------------------------

def test_failed_operation():
    """An operation with status 'FAILED' should produce a 'failed' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func1"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "FAILED",
                    "changes": [],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        failed_findings = [f for f in result["findings"] if f["issue"] == "failed"]
        assert len(failed_findings) == 1
        assert failed_findings[0]["operation"] == "intent-001"
        assert failed_findings[0]["expected"] == "COMPLETED or SKIPPED"
        assert "FAILED" in failed_findings[0]["actual"]


# ---------------------------------------------------------------------------
# Test 4: Stuck operation (PENDING / IN_PROGRESS)
# ---------------------------------------------------------------------------

def test_stuck_operation_pending():
    """An operation with status 'PENDING' should produce a 'pending' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func1"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "PENDING",
                    "changes": [],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        pending_findings = [f for f in result["findings"] if f["issue"] == "pending"]
        assert len(pending_findings) == 1
        assert pending_findings[0]["operation"] == "intent-001"
        assert "never started" in pending_findings[0]["actual"]


def test_stuck_operation_in_progress():
    """An operation with status 'IN_PROGRESS' should produce an
    'in_progress' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-004", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "array6-multiply", "function": "GetBasePremium_Home"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-004",
                    "change_type": "value_editing",
                    "status": "IN_PROGRESS",
                    "changes": [],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        ip_findings = [f for f in result["findings"] if f["issue"] == "in_progress"]
        assert len(ip_findings) == 1
        assert ip_findings[0]["operation"] == "intent-004"
        assert "never finished" in ip_findings[0]["actual"]


# ---------------------------------------------------------------------------
# Test 5: SKIPPED operation is OK
# ---------------------------------------------------------------------------

def test_skipped_operation_ok():
    """An operation with status 'SKIPPED' is acceptable (values already at
    target). Should not produce any finding for that operation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func1"},
                {"id": "intent-002", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func2"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 100, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "SKIPPED",
                    "changes": [],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        msg = result.get("message", "")
        assert "1/2 operations COMPLETED" in msg
        assert "1 SKIPPED" in msg


# ---------------------------------------------------------------------------
# Test 6: Empty operations log -- no planned ops either
# ---------------------------------------------------------------------------

def test_empty_operations_log_no_planned_ops():
    """No operations in the log AND no planned ops. Should pass trivially
    (nothing expected, nothing found)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[],
            ops_log_operations=[],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "0/0 operations COMPLETED" in result.get("message", "")


def test_empty_operations_log_with_planned_ops():
    """No operations in the log but planned ops exist. Each planned op
    should produce a 'not_in_log' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func1"},
                {"id": "intent-002", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func2"},
            ],
            ops_log_operations=[],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        not_in_log = [f for f in result["findings"] if f["issue"] == "not_in_log"]
        assert len(not_in_log) == 2


# ---------------------------------------------------------------------------
# Test 7: Territory completeness -- snapshot-based count mismatch
# ---------------------------------------------------------------------------

def test_territory_count_mismatch_from_snapshot():
    """Snapshot has 15 Case branches in GetBasePremium_Home but the ops log
    only records 14 changes. Should produce a 'territory_count_mismatch'
    finding."""
    # Build a VB.NET snapshot with 15 numeric Case labels
    snapshot_lines = []
    snapshot_lines.append("Public Function GetBasePremium_Home(ByVal territory As Integer) As Variant")
    snapshot_lines.append("    Select Case territory")
    for t in range(1, 16):  # 15 territories
        snapshot_lines.append(f"        Case {t} : varRates = Array6(100, 200, 300)")
    snapshot_lines.append("    End Select")
    snapshot_lines.append("End Function")
    snapshot_content = "\n".join(snapshot_lines) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Only 14 changes recorded (missing territory 15)
        changes = [{"line": i, "before": "old", "after": "new"} for i in range(1, 15)]

        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
                    "strategy_hint": "array6-multiply",
                    "function": "GetBasePremium_Home",
                    "target_lines": [{"line": i} for i in range(1, 16)],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": changes,
                },
            ],
            snapshot_files={
                "Saskatchewan__Code__mod_Common_SKHab20260101.vb.snapshot": snapshot_content,
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        territory_findings = [
            f for f in result["findings"]
            if f["issue"] == "territory_count_mismatch"
        ]
        assert len(territory_findings) == 1
        assert territory_findings[0]["operation"] == "intent-001"
        assert "15 territories" in territory_findings[0]["expected"]
        assert "14 changes" in territory_findings[0]["actual"]


def test_territory_completeness_fallback_to_target_lines():
    """When no snapshot is available, the validator falls back to
    target_lines count from the op-*.yaml. If target_lines lists 10
    entries but only 8 changes recorded, it should flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_lines = [{"line": i} for i in range(1, 11)]  # 10 target lines
        changes = [{"line": i, "before": "old", "after": "new"} for i in range(1, 9)]  # 8 changes

        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-004",
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "strategy_hint": "array6-multiply",
                    "function": "GetBasePremium_Condo",
                    "target_lines": target_lines,
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-004",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": changes,
                },
            ],
            # No snapshot_files -- triggers fallback
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        territory_findings = [
            f for f in result["findings"]
            if f["issue"] == "territory_count_mismatch"
        ]
        assert len(territory_findings) == 1
        assert "10 territories" in territory_findings[0]["expected"]
        assert "8 changes" in territory_findings[0]["actual"]


def test_territory_completeness_all_match():
    """Snapshot has 5 Case branches and exactly 5 changes recorded.
    Should pass with no territory finding."""
    snapshot_lines = []
    snapshot_lines.append("Public Function GetBasePremium_Home(ByVal t As Integer) As Variant")
    snapshot_lines.append("    Select Case t")
    for t in range(1, 6):  # 5 territories
        snapshot_lines.append(f"        Case {t} : varRates = Array6(50, 60, 70)")
    snapshot_lines.append("    End Select")
    snapshot_lines.append("End Function")
    snapshot_content = "\n".join(snapshot_lines) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        changes = [{"line": i, "before": "old", "after": "new"} for i in range(1, 6)]

        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "strategy_hint": "array6-multiply",
                    "function": "GetBasePremium_Home",
                    "target_lines": [{"line": i} for i in range(1, 6)],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": changes,
                },
            ],
            snapshot_files={
                "Alberta__Code__mod_Common_ABHab20260101.vb.snapshot": snapshot_content,
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ---------------------------------------------------------------------------
# Test 8: LOB completeness for hab -- missing LOB
# ---------------------------------------------------------------------------

def test_lob_completeness_missing_lob():
    """Manifest has 3 LOBs (Home, Condo, Tenant) with shared_modules, but
    only Home and Condo have LOB-specific operations. Tenant is missing.
    Should produce a 'lob_missing' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            manifest_extra={
                "lobs": ["Home", "Condo", "Tenant"],
                "shared_modules": ["mod_Common_ABHab20260101.vb"],
                "province": "AB",
            },
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Home/20260101/ResourceID.vb",
                 "strategy_hint": "factor-table", "function": "Func1"},
                {"id": "intent-002", "file": "Alberta/Condo/20260101/ResourceID.vb",
                 "strategy_hint": "factor-table", "function": "Func2"},
                {"id": "intent-003", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "SharedFunc"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Home/20260101/ResourceID.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 10, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Condo/20260101/ResourceID.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 20, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-003",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 30, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        lob_findings = [f for f in result["findings"] if f["issue"] == "lob_missing"]
        assert len(lob_findings) == 1
        assert "Tenant" in lob_findings[0]["expected"]


def test_lob_completeness_all_lobs_present():
    """All 3 LOBs have completed LOB-specific operations. Should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            manifest_extra={
                "lobs": ["Home", "Condo", "Tenant"],
                "shared_modules": ["mod_Common_ABHab20260101.vb"],
                "province": "AB",
            },
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Home/20260101/ResourceID.vb",
                 "strategy_hint": "factor-table", "function": "F1"},
                {"id": "intent-002", "file": "Alberta/Condo/20260101/ResourceID.vb",
                 "strategy_hint": "factor-table", "function": "F2"},
                {"id": "intent-003", "file": "Alberta/Tenant/20260101/ResourceID.vb",
                 "strategy_hint": "factor-table", "function": "F3"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Home/20260101/ResourceID.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 10, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Condo/20260101/ResourceID.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 20, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Tenant/20260101/ResourceID.vb",
                    "operation": "intent-003",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 30, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        # Only check LOB-specific findings -- other checks (territory etc.) may pass too
        lob_findings = [f for f in result["findings"] if f["issue"] == "lob_missing"]
        assert len(lob_findings) == 0


def test_lob_completeness_shared_only_no_lob_specific():
    """All operations are on shared modules only (Code/ path). No LOB-specific
    operations at all. The shared module edit covers all LOBs, so no
    lob_missing finding should be produced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            manifest_extra={
                "lobs": ["Home", "Condo", "Tenant"],
                "shared_modules": ["mod_Common_ABHab20260101.vb"],
                "province": "AB",
            },
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "SharedFunc"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 100, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        lob_findings = [f for f in result["findings"] if f["issue"] == "lob_missing"]
        assert len(lob_findings) == 0


# ---------------------------------------------------------------------------
# Test 9: Comprehensive happy path -- all checks pass
# ---------------------------------------------------------------------------

def test_comprehensive_happy_path():
    """Full happy path: 4 operations across 2 files, 2 agents, including
    a base_rate_increase with matching territory count and a factor_table_change
    with matching target lines. Multi-LOB with all LOBs covered.
    Everything should pass."""
    # 3 territories in the snapshot function
    snapshot_lines = []
    snapshot_lines.append("Public Function GetBasePremium_Home(t As Integer) As Variant")
    snapshot_lines.append("    Select Case t")
    snapshot_lines.append("        Case 1 : varRates = Array6(100, 200)")
    snapshot_lines.append("        Case 2 : varRates = Array6(110, 210)")
    snapshot_lines.append("        Case 3 : varRates = Array6(120, 220)")
    snapshot_lines.append("    End Select")
    snapshot_lines.append("End Function")
    snapshot_content = "\n".join(snapshot_lines) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            manifest_extra={
                "lobs": ["Home", "Condo"],
                "shared_modules": ["mod_Common_ABHab20260101.vb"],
                "province": "AB",
            },
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "strategy_hint": "array6-multiply",
                    "function": "GetBasePremium_Home",
                    "target_lines": [{"line": 3}, {"line": 4}, {"line": 5}],
                },
                {
                    "id": "intent-002",
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "strategy_hint": "factor-table",
                    "function": "GetDeductibleDiscount",
                    "target_lines": [{"line": 50, "context": "Case 500"}, {"line": 51, "context": "Case 1000"}],
                },
                {
                    "id": "intent-004",
                    "file": "Alberta/Home/20260101/ResourceID.vb",
                    "strategy_hint": "factor-table",
                    "function": "Func3",
                    "target_lines": [],
                },
                {
                    "id": "intent-005",
                    "file": "Alberta/Condo/20260101/ResourceID.vb",
                    "strategy_hint": "factor-table",
                    "function": "Func4",
                    "target_lines": [],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 3, "before": "old1", "after": "new1"},
                        {"line": 4, "before": "old2", "after": "new2"},
                        {"line": 5, "before": "old3", "after": "new3"},
                    ],
                },
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 50, "before": "old", "after": "new"},
                        {"line": 51, "before": "old", "after": "new"},
                    ],
                },
                {
                    "file": "Alberta/Home/20260101/ResourceID.vb",
                    "operation": "intent-004",
                    "change_type": "structure_insertion",
                    "status": "COMPLETED",
                    "changes": [{"line": 10, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Condo/20260101/ResourceID.vb",
                    "operation": "intent-005",
                    "change_type": "structure_insertion",
                    "status": "COMPLETED",
                    "changes": [{"line": 20, "before": "old", "after": "new"}],
                },
            ],
            snapshot_files={
                "Alberta__Code__mod_Common_ABHab20260101.vb.snapshot": snapshot_content,
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "BLOCKER"
        assert len(result["findings"]) == 0
        msg = result.get("message", "")
        assert "4/4 operations COMPLETED" in msg
        assert "3 territory changes applied" in msg


# ---------------------------------------------------------------------------
# Test 10: Mixed change types -- value_editing + structure_insertion both completed
# ---------------------------------------------------------------------------

def test_mixed_agents_both_completed():
    """value_editing and structure_insertion ops both COMPLETED. Validator
    should pass regardless of agent type."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "Func1"},
                {"id": "intent-004", "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "pattern": "logic_change", "function": "AddEligibilityCheck"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 100, "before": "old", "after": "new"}],
                },
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-004",
                    "change_type": "structure_insertion",
                    "status": "COMPLETED",
                    "changes": [{"line": 200, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "2/2 operations COMPLETED" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 11: Factor table completeness -- missing Case value
# ---------------------------------------------------------------------------

def test_factor_table_missing_case_value():
    """A factor_table_change op has 3 target_lines but only 2 changes
    recorded. The missing target line should produce a
    'factor_case_not_updated' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "strategy_hint": "factor-table",
                    "function": "GetDeductibleDiscount",
                    "target_lines": [
                        {"line": 50, "context": "Case 500"},
                        {"line": 51, "context": "Case 1000"},
                        {"line": 52, "context": "Case 2500"},
                    ],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 50, "before": "old", "after": "new"},
                        {"line": 51, "before": "old", "after": "new"},
                        # line 52 is missing
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        factor_findings = [
            f for f in result["findings"]
            if f["issue"] == "factor_case_not_updated"
        ]
        assert len(factor_findings) == 1
        assert factor_findings[0]["operation"] == "intent-001"
        assert "line 52" in factor_findings[0]["expected"]
        assert "Case 2500" in factor_findings[0]["expected"]


def test_factor_table_all_cases_updated():
    """A factor_table_change op has 3 target_lines and exactly 3 changes
    recorded on those lines. Should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "strategy_hint": "factor-table",
                    "function": "GetDeductibleDiscount",
                    "target_lines": [
                        {"line": 50, "context": "Case 500"},
                        {"line": 51, "context": "Case 1000"},
                        {"line": 52, "context": "Case 2500"},
                    ],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 50, "before": "old", "after": "new"},
                        {"line": 51, "before": "old", "after": "new"},
                        {"line": 52, "before": "old", "after": "new"},
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ---------------------------------------------------------------------------
# Test 12: Multiple failures combined
# ---------------------------------------------------------------------------

def test_multiple_failures_combined():
    """Combination: one missing operation + one FAILED operation + one
    IN_PROGRESS operation. Should produce 3 findings with different issue types."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {"id": "intent-001", "file": "file1.vb", "strategy_hint": "factor-table", "function": "F1"},
                {"id": "intent-002", "file": "file2.vb", "strategy_hint": "factor-table", "function": "F2"},
                {"id": "intent-003", "file": "file3.vb", "strategy_hint": "factor-table", "function": "F3"},
            ],
            ops_log_operations=[
                {
                    "file": "file1.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "FAILED",
                    "changes": [],
                },
                {
                    "file": "file2.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "IN_PROGRESS",
                    "changes": [],
                },
                # intent-003 is missing from log entirely
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        issues = [f["issue"] for f in result["findings"]]
        assert "not_in_log" in issues
        assert "failed" in issues
        assert "in_progress" in issues
        assert len(result["findings"]) == 3

        msg = result.get("message", "")
        assert "3 findings" in msg


# ---------------------------------------------------------------------------
# Test 13: LOB completeness from change_requests fallback
# ---------------------------------------------------------------------------

def test_lob_completeness_from_change_requests():
    """When manifest does not have lobs/shared_modules, the validator falls
    back to change_requests.yaml. Missing LOBs should still be detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            # manifest does NOT have lobs or shared_modules
            manifest_extra={"province": "SK"},
            change_requests={
                "lobs": ["Home", "Condo", "Tenant"],
                "shared_modules": ["mod_Common_SKHab20260101.vb"],
            },
            planned_ops=[
                {"id": "intent-001", "file": "Saskatchewan/Home/20260101/ResourceID.vb",
                 "strategy_hint": "factor-table", "function": "F1"},
                {"id": "intent-002", "file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "F2"},
            ],
            ops_log_operations=[
                {
                    "file": "Saskatchewan/Home/20260101/ResourceID.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 10, "before": "old", "after": "new"}],
                },
                {
                    "file": "Saskatchewan/Code/mod_Common_SKHab20260101.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 20, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        lob_findings = [f for f in result["findings"] if f["issue"] == "lob_missing"]
        # Condo and Tenant have no LOB-specific operations
        assert len(lob_findings) == 2
        missing_lobs = {f["expected"].split()[1] for f in lob_findings}
        assert "Condo" in missing_lobs
        assert "Tenant" in missing_lobs


# ---------------------------------------------------------------------------
# Test 14: Single-LOB ticket -- LOB check skipped
# ---------------------------------------------------------------------------

def test_single_lob_ticket_lob_check_skipped():
    """A single-LOB ticket should NOT trigger LOB completeness checking,
    even if shared_modules is set. The check only applies when there are
    2+ target LOBs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            manifest_extra={
                "lobs": ["Home"],
                "shared_modules": ["mod_Common_ABHab20260101.vb"],
                "province": "AB",
            },
            planned_ops=[
                {"id": "intent-001", "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                 "strategy_hint": "factor-table", "function": "F1"},
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 100, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        lob_findings = [f for f in result["findings"] if f["issue"] == "lob_missing"]
        assert len(lob_findings) == 0


# ---------------------------------------------------------------------------
# Test 15: No intent_graph.yaml -- reports missing file
# ---------------------------------------------------------------------------

def test_no_intent_graph_file():
    """If intent_graph.yaml does not exist, the validator should report
    an 'intent_graph_missing' finding. This is an error, not a graceful
    degrade -- the intent graph is required."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            # planned_ops NOT provided -- no intent_graph.yaml created
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [{"line": 100, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        # Missing intent_graph.yaml produces a finding
        missing_findings = [f for f in result["findings"]
                           if f["issue"] == "intent_graph_missing"]
        assert len(missing_findings) == 1
        assert "intent_graph.yaml" in missing_findings[0]["expected"]


# ---------------------------------------------------------------------------
# Test 16: Territory counting -- multiline Case format
# ---------------------------------------------------------------------------

def test_territory_counting_multiline_case():
    """Snapshot uses multi-line Case format (Case N on its own line, body
    on next line). The territory counter should still count these correctly."""
    snapshot_lines = [
        "Public Function GetBasePremium_Home(t As Integer) As Variant",
        "    Select Case t",
        "        Case 1",
        "            varRates = Array6(100, 200)",
        "        Case 2",
        "            varRates = Array6(110, 210)",
        "        Case 3",
        "            varRates = Array6(120, 220)",
        "        Case 4",
        "            varRates = Array6(130, 230)",
        "    End Select",
        "End Function",
    ]
    snapshot_content = "\n".join(snapshot_lines) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Only 3 changes recorded for 4 territories
        changes = [
            {"line": 3, "before": "old", "after": "new"},
            {"line": 4, "before": "old", "after": "new"},
            {"line": 5, "before": "old", "after": "new"},
        ]

        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "strategy_hint": "array6-multiply",
                    "function": "GetBasePremium_Home",
                    "target_lines": [],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": changes,
                },
            ],
            snapshot_files={
                "Alberta__Code__mod_Common_ABHab20260101.vb.snapshot": snapshot_content,
            },
        )

        result = validate(manifest_path)
        territory_findings = [
            f for f in result["findings"]
            if f["issue"] == "territory_count_mismatch"
        ]
        assert len(territory_findings) == 1
        assert "4 territories" in territory_findings[0]["expected"]
        assert "3 changes" in territory_findings[0]["actual"]


# ---------------------------------------------------------------------------
# Test 17: Non-base_rate_increase ops -- territory check skipped
# ---------------------------------------------------------------------------

def test_non_base_rate_pattern_skips_territory_check():
    """Operations with pattern != 'base_rate_increase' should NOT trigger
    territory counting, even if they have different change counts vs target_lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "pattern": "logic_change",
                    "function": "AddNewCheck",
                    "target_lines": [{"line": 1}, {"line": 2}, {"line": 3}],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "structure_insertion",
                    "status": "COMPLETED",
                    "changes": [{"line": 1, "before": "old", "after": "new"}],
                },
            ],
        )

        result = validate(manifest_path)
        territory_findings = [
            f for f in result["findings"]
            if f["issue"] == "territory_count_mismatch"
        ]
        assert len(territory_findings) == 0


# ---------------------------------------------------------------------------
# Test 18: Factor table wrong-line detection -- same count, different lines
# ---------------------------------------------------------------------------

def test_factor_table_wrong_lines_same_count():
    """A factor_table_change op has 3 target_lines (50, 51, 52) but the
    actual changes were applied to 3 DIFFERENT lines (50, 51, 99).
    Counts match (3 == 3) but line 52 was never touched and line 99 was
    edited instead. Should produce a 'factor_case_not_updated' finding
    for the missing line 52."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            planned_ops=[
                {
                    "id": "intent-001",
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "strategy_hint": "factor-table",
                    "function": "GetDeductibleDiscount",
                    "target_lines": [
                        {"line": 50, "context": "Case 500"},
                        {"line": 51, "context": "Case 1000"},
                        {"line": 52, "context": "Case 2500"},
                    ],
                },
            ],
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 50, "before": "old", "after": "new"},
                        {"line": 51, "before": "old", "after": "new"},
                        {"line": 99, "before": "wrong line", "after": "wrong edit"},
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        factor_findings = [
            f for f in result["findings"]
            if f["issue"] == "factor_case_not_updated"
        ]
        assert len(factor_findings) == 1
        assert factor_findings[0]["operation"] == "intent-001"
        assert "line 52" in factor_findings[0]["expected"]
        assert "Case 2500" in factor_findings[0]["expected"]
