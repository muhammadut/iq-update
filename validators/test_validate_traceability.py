"""
Integration tests for validate_traceability.py

Uses tempfile and os.makedirs to create mock workstreams with controlled
CR files, change_requests.yaml, operations_log.yaml, and manifest.yaml.

Run with:
    cd <plugin-root>/validators
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


def _build_workstream(tmpdir, *, cr_files=None, change_requests_crs=None,
                      ops_log_operations=None, effective_date="20260101"):
    """Build a complete mock workstream in tmpdir.

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        cr_files: List of dicts with keys: cr_id, description, type.
            Each becomes a parsed/requests/cr-NNN.yaml file.
        change_requests_crs: List of dicts for change_requests.yaml fallback.
            Only used if cr_files is None.
        ops_log_operations: List of operation dicts for operations_log.yaml.
        effective_date: The effective date string in the manifest.

    Returns:
        str: Absolute path to the manifest.yaml file.
    """
    carrier_root = tmpdir
    workstreams_root = os.path.join(carrier_root, ".iq-workstreams")
    workstream_dir = os.path.join(workstreams_root, "changes", "test-ticket")
    execution_dir = os.path.join(workstream_dir, "execution")

    # --- Write CR files ---
    if cr_files is not None:
        requests_dir = os.path.join(workstream_dir, "parsed", "requests")
        os.makedirs(requests_dir, exist_ok=True)
        for cr in cr_files:
            cr_id = cr["cr_id"]
            cr_path = os.path.join(requests_dir, f"{cr_id}.yaml")
            _write_yaml(cr_path, cr)

    # --- Write change_requests.yaml (fallback) ---
    if change_requests_crs is not None and cr_files is None:
        parsed_dir = os.path.join(workstream_dir, "parsed")
        os.makedirs(parsed_dir, exist_ok=True)
        _write_yaml(
            os.path.join(parsed_dir, "change_requests.yaml"),
            {"change_requests": change_requests_crs},
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
# Test 1: Clean pass -- 3 CRs, each with 1+ intents
# ---------------------------------------------------------------------------

def test_clean_pass():
    """3 CRs, each with at least one intent. Should pass cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Increase home base rates by 5%", "type": "value_editing"},
                {"cr_id": "cr-002", "description": "Update deductible factors", "type": "value_editing"},
                {"cr_id": "cr-003", "description": "Add new eligibility rule", "type": "structure_insertion"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "file": "AB/Code/CalcOption_ABHome20260101.vb",
                 "change_type": "value_editing", "status": "COMPLETED"},
                {"operation": "intent-002", "file": "AB/Code/mod_Common_ABHab20260101.vb",
                 "change_type": "value_editing", "status": "COMPLETED"},
                {"operation": "intent-003", "file": "AB/Code/CalcOption_ABHome20260101.vb",
                 "change_type": "structure_insertion", "status": "COMPLETED"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 0
        assert "Full traceability" in result.get("message", "")
        assert "3/3 CRs traced" in result.get("message", "")
        assert "3 intents mapped" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 2: Untraced CR -- cr-003 has no intents
# ---------------------------------------------------------------------------

def test_untraced_cr():
    """cr-003 has no intents in the log. Should produce an
    'untraced_cr' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Increase rates", "type": "value_editing"},
                {"cr_id": "cr-002", "description": "Update factors", "type": "value_editing"},
                {"cr_id": "cr-003", "description": "New eligibility rule", "type": "structure_insertion"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                {"operation": "intent-002", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file2.vb"},
                # No intent-003 intents!
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "untraced_cr"
        assert finding["cr"] == "cr-003"
        assert finding["description"] == "New eligibility rule"
        assert "cr-003" in finding["message"]
        assert "1 untraced CR(s)" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 3: Orphan change -- intent-099 maps to cr-099 which doesn't exist
# ---------------------------------------------------------------------------

def test_orphan_change():
    """intent-099 maps to cr-099 which is not in the CR list. Should
    produce an 'orphan_change' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Increase rates", "type": "value_editing"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                {"operation": "intent-099", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/unknown.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "orphan_change"
        assert finding["operation"] == "intent-099"
        assert finding["mapped_cr"] == "cr-099"
        assert "cr-099" in finding["message"]
        assert "1 orphan change(s)" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 4: Rework entry skipped -- rework-001 not flagged as orphan
# ---------------------------------------------------------------------------

def test_rework_entry_skipped():
    """rework-001 operation should be skipped in orphan check. Only real
    CR intents are checked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Increase rates", "type": "value_editing"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                {"operation": "rework-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "Full traceability" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 5: No CRs -- empty requests/ directory
# ---------------------------------------------------------------------------

def test_no_crs():
    """No CR files and no change_requests.yaml. Should pass with
    'No CRs found to trace' message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Build workstream with no CR files and no change_requests
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=None,
            change_requests_crs=None,
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "No CRs found to trace" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 6: SKIPPED intent counts -- still traces to its CR
# ---------------------------------------------------------------------------

def test_skipped_intent_counts():
    """An intent with status SKIPPED still counts as a traced log entry.
    The CR it belongs to should be considered traced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Increase rates", "type": "value_editing"},
                {"cr_id": "cr-002", "description": "Update factors", "type": "value_editing"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                {"operation": "intent-002", "status": "SKIPPED", "change_type": "value_editing",
                 "file": "AB/Code/file2.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "2/2 CRs traced" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 7: Multiple operations for same CR -- cr-001 has intent-001 twice
# ---------------------------------------------------------------------------

def test_multiple_ops_per_cr():
    """cr-001 has two operation entries (same intent, different files).
    Should be fully traced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Multi-file rate change", "type": "value_editing"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file2.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "1/1 CRs traced" in result.get("message", "")
        assert "1 intents mapped" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 8: Mixed issues -- 1 untraced CR + 1 orphan change
# ---------------------------------------------------------------------------

def test_mixed_issues():
    """One CR has no intents, and one intent maps to a nonexistent
    CR. Should produce 2 findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Traced change", "type": "value_editing"},
                {"cr_id": "cr-002", "description": "Untraced change", "type": "structure_insertion"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                # No intent-002 -- cr-002 is untraced
                {"operation": "intent-050", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/unknown.vb"},
                # intent-050 maps to cr-050 which doesn't exist -- orphan
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 2

        issues = {f["issue"] for f in result["findings"]}
        assert "untraced_cr" in issues
        assert "orphan_change" in issues

        # Verify message mentions both issue types
        msg = result.get("message", "")
        assert "1 untraced CR(s)" in msg
        assert "1 orphan change(s)" in msg
        assert "1/2 CRs traced" in msg


# ---------------------------------------------------------------------------
# Test 9: DAT-file CR untraced -- CR about DAT files has no intents
# ---------------------------------------------------------------------------

def test_dat_file_cr_untraced():
    """A CR describing a DAT file change (outside plugin scope) has no
    intents. Should still be flagged as untraced -- the developer
    decides at Gate 2 if this is acceptable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Increase auto rates", "type": "value_editing"},
                {"cr_id": "cr-002", "description": "Update hab dwelling base rates (DAT file)",
                 "type": "dat-file"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                # No intent-002 -- DAT-file CR has no plugin intents
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "untraced_cr"
        assert finding["cr"] == "cr-002"
        assert "DAT" in finding["description"]


# ---------------------------------------------------------------------------
# Test 10: Non-standard intent ID -- "custom-fix-01" flagged as orphan
# ---------------------------------------------------------------------------

def test_non_standard_intent_id():
    """An intent with a non-standard ID (not matching intent-NNN) should
    be flagged as an orphan change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            cr_files=[
                {"cr_id": "cr-001", "description": "Increase rates", "type": "value_editing"},
            ],
            ops_log_operations=[
                {"operation": "intent-001", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/file1.vb"},
                {"operation": "custom-fix-01", "status": "COMPLETED", "change_type": "value_editing",
                 "file": "AB/Code/fixup.vb"},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "orphan_change"
        assert finding["operation"] == "custom-fix-01"
        assert finding["mapped_cr"] is None
        assert "naming convention" in finding["message"]
