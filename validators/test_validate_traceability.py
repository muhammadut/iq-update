"""
Integration tests for validate_traceability.py

Uses tempfile and os.makedirs to create mock workstreams with controlled
SRD files, change_spec.yaml, operations_log.yaml, and manifest.yaml.

Run with:
    cd "E:/intelli-new/Cssi.Net/Portage Mutual/.iq-update/validators"
    python -m pytest test_validate_traceability.py -v
"""

import os
import tempfile

import yaml
import pytest

from validate_traceability import validate


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path, data):
    """Write a dict to a YAML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _build_workstream(tmpdir, *, srd_files=None, change_spec_srds=None,
                      ops_log_operations=None, effective_date="20260101"):
    """Build a complete mock workstream in tmpdir.

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        srd_files: List of dicts with keys: srd_id, description, type.
            Each becomes a parsed/srds/srd-NNN.yaml file.
        change_spec_srds: List of dicts for change_spec.yaml fallback.
            Only used if srd_files is None.
        ops_log_operations: List of operation dicts for operations_log.yaml.
        effective_date: The effective date string in the manifest.

    Returns:
        str: Absolute path to the manifest.yaml file.
    """
    carrier_root = tmpdir
    workstreams_root = os.path.join(carrier_root, ".iq-workstreams")
    workstream_dir = os.path.join(workstreams_root, "changes", "test-ticket")
    execution_dir = os.path.join(workstream_dir, "execution")

    # --- Write SRD files ---
    if srd_files is not None:
        srds_dir = os.path.join(workstream_dir, "parsed", "srds")
        os.makedirs(srds_dir, exist_ok=True)
        for srd in srd_files:
            srd_id = srd["srd_id"]
            srd_path = os.path.join(srds_dir, f"{srd_id}.yaml")
            _write_yaml(srd_path, srd)

    # --- Write change_spec.yaml (fallback) ---
    if change_spec_srds is not None and srd_files is None:
        parsed_dir = os.path.join(workstream_dir, "parsed")
        os.makedirs(parsed_dir, exist_ok=True)
        _write_yaml(
            os.path.join(parsed_dir, "change_spec.yaml"),
            {"srds": change_spec_srds},
        )

    # --- Write operations_log.yaml ---
    ops_log = {"operations": ops_log_operations or []}
    _write_yaml(os.path.join(execution_dir, "operations_log.yaml"), ops_log)

    # --- Write file_hashes.yaml (minimal) ---
    _write_yaml(os.path.join(execution_dir, "file_hashes.yaml"), {"files": {}})

    # --- Write manifest.yaml ---
    manifest = {
        "codebase_root": carrier_root,
        "effective_date": effective_date,
        "state": "EXECUTED",
    }
    manifest_path = os.path.join(workstream_dir, "manifest.yaml")
    _write_yaml(manifest_path, manifest)

    # --- Write config.yaml (minimal) ---
    _write_yaml(os.path.join(workstreams_root, "config.yaml"), {})

    # --- Ensure snapshots dir exists ---
    os.makedirs(os.path.join(execution_dir, "snapshots"), exist_ok=True)

    return manifest_path


# ---------------------------------------------------------------------------
# Test 1: Clean pass -- 3 SRDs, each with 1+ operations
# ---------------------------------------------------------------------------

def test_clean_pass():
    """3 SRDs, each with at least one operation. Should pass cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Increase home base rates by 5%", "type": "rate-modifier"},
                {"srd_id": "srd-002", "description": "Update deductible factors", "type": "rate-modifier"},
                {"srd_id": "srd-003", "description": "Add new eligibility rule", "type": "logic-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "file": "AB/Code/CalcOption_ABHome20260101.vb",
                 "agent": "rate-modifier", "status": "COMPLETED"},
                {"operation": "op-002-01", "file": "AB/Code/mod_Common_ABHab20260101.vb",
                 "agent": "rate-modifier", "status": "COMPLETED"},
                {"operation": "op-003-01", "file": "AB/Code/CalcOption_ABHome20260101.vb",
                 "agent": "logic-modifier", "status": "COMPLETED"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 0
        assert "Full traceability" in result.get("message", "")
        assert "3/3 SRDs traced" in result.get("message", "")
        assert "3 operations mapped" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 2: Untraced SRD -- srd-003 has no operations
# ---------------------------------------------------------------------------

def test_untraced_srd():
    """srd-003 has no operations in the log. Should produce an
    'untraced_srd' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Increase rates", "type": "rate-modifier"},
                {"srd_id": "srd-002", "description": "Update factors", "type": "rate-modifier"},
                {"srd_id": "srd-003", "description": "New eligibility rule", "type": "logic-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                {"operation": "op-002-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file2.vb"},
                # No op-003-XX operations!
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "untraced_srd"
        assert finding["srd"] == "srd-003"
        assert finding["description"] == "New eligibility rule"
        assert "srd-003" in finding["message"]
        assert "1 untraced SRD(s)" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 3: Orphan change -- op-099-01 maps to srd-099 which doesn't exist
# ---------------------------------------------------------------------------

def test_orphan_change():
    """op-099-01 maps to srd-099 which is not in the SRD list. Should
    produce an 'orphan_change' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Increase rates", "type": "rate-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                {"operation": "op-099-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/unknown.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "orphan_change"
        assert finding["operation"] == "op-099-01"
        assert finding["mapped_srd"] == "srd-099"
        assert "srd-099" in finding["message"]
        assert "1 orphan change(s)" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 4: Rework entry skipped -- rework-001 not flagged as orphan
# ---------------------------------------------------------------------------

def test_rework_entry_skipped():
    """rework-001 operation should be skipped in orphan check. Only real
    SRD operations are checked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Increase rates", "type": "rate-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                {"operation": "rework-001", "status": "COMPLETED", "agent": "orchestrator",
                 "file": "AB/Code/file1.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "Full traceability" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 5: No SRDs -- empty srds/ directory
# ---------------------------------------------------------------------------

def test_no_srds():
    """No SRD files and no change_spec.yaml. Should pass with
    'No SRDs found to trace' message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Build workstream with no SRD files and no change_spec
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=None,
            change_spec_srds=None,
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "No SRDs found to trace" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 6: SKIPPED operation counts -- still traces to its SRD
# ---------------------------------------------------------------------------

def test_skipped_operation_counts():
    """An operation with status SKIPPED still counts as a traced log entry.
    The SRD it belongs to should be considered traced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Increase rates", "type": "rate-modifier"},
                {"srd_id": "srd-002", "description": "Update factors", "type": "rate-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                {"operation": "op-002-01", "status": "SKIPPED", "agent": "rate-modifier",
                 "file": "AB/Code/file2.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "2/2 SRDs traced" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 7: Multiple ops per SRD -- srd-001 has op-001-01 and op-001-02
# ---------------------------------------------------------------------------

def test_multiple_ops_per_srd():
    """srd-001 has two operations. Should be fully traced with one SRD
    mapping to multiple ops."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Multi-file rate change", "type": "rate-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                {"operation": "op-001-02", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file2.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "1/1 SRDs traced" in result.get("message", "")
        assert "2 operations mapped" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 8: Mixed issues -- 1 untraced SRD + 1 orphan change
# ---------------------------------------------------------------------------

def test_mixed_issues():
    """One SRD has no operations, and one operation maps to a nonexistent
    SRD. Should produce 2 findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Traced change", "type": "rate-modifier"},
                {"srd_id": "srd-002", "description": "Untraced change", "type": "logic-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                # No op-002-XX -- srd-002 is untraced
                {"operation": "op-050-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/unknown.vb"},
                # op-050-01 maps to srd-050 which doesn't exist -- orphan
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 2

        issues = {f["issue"] for f in result["findings"]}
        assert "untraced_srd" in issues
        assert "orphan_change" in issues

        # Verify message mentions both issue types
        msg = result.get("message", "")
        assert "1 untraced SRD(s)" in msg
        assert "1 orphan change(s)" in msg
        assert "1/2 SRDs traced" in msg


# ---------------------------------------------------------------------------
# Test 9: DAT-file SRD untraced -- SRD about DAT files has no ops
# ---------------------------------------------------------------------------

def test_dat_file_srd_untraced():
    """A SRD describing a DAT file change (outside plugin scope) has no
    operations. Should still be flagged as untraced -- the developer
    decides at Gate 2 if this is acceptable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Increase auto rates", "type": "rate-modifier"},
                {"srd_id": "srd-002", "description": "Update hab dwelling base rates (DAT file)",
                 "type": "dat-file"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                # No op-002-XX -- DAT-file SRD has no plugin operations
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "untraced_srd"
        assert finding["srd"] == "srd-002"
        assert "DAT" in finding["description"]


# ---------------------------------------------------------------------------
# Test 10: Non-standard op ID -- "custom-fix-01" flagged as orphan
# ---------------------------------------------------------------------------

def test_non_standard_op_id():
    """An operation with a non-standard ID (not matching op-NNN-NN) should
    be flagged as an orphan change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            srd_files=[
                {"srd_id": "srd-001", "description": "Increase rates", "type": "rate-modifier"},
            ],
            ops_log_operations=[
                {"operation": "op-001-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/file1.vb"},
                {"operation": "custom-fix-01", "status": "COMPLETED", "agent": "rate-modifier",
                 "file": "AB/Code/fixup.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "orphan_change"
        assert finding["operation"] == "custom-fix-01"
        assert finding["mapped_srd"] is None
        assert "naming convention" in finding["message"]
