"""
Tests for validate_no_commented_code.py

Uses tempfile to create mock workstreams with controlled
operations_log.yaml and manifest.yaml entries.

Run with:
    cd <plugin-root>/validators
    python -m pytest test_validate_no_commented_code.py -v
"""

import os
import tempfile

import yaml
import pytest

from validate_no_commented_code import validate


# ---------------------------------------------------------------------------
# Test Fixtures / Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path, data):
    """Write a dict to a YAML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _build_workstream(tmpdir, *, ops_log_operations=None):
    """Build a minimal mock workstream for the no-commented-code validator.

    This validator only reads manifest.yaml and operations_log.yaml,
    so we only need those two files plus file_hashes.yaml (required by
    load_context but can be empty).

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        ops_log_operations: list of operation dicts for operations_log.yaml.

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
    manifest_path = os.path.join(workstream_dir, "manifest.yaml")
    _write_yaml(manifest_path, manifest)

    # --- Write config.yaml (empty, required by load_context) ---
    _write_yaml(os.path.join(workstreams_root, "config.yaml"), {})

    # --- Ensure snapshots dir exists ---
    os.makedirs(os.path.join(execution_dir, "snapshots"), exist_ok=True)

    return manifest_path


# ---------------------------------------------------------------------------
# Test 1: Clean pass -- 3 operations, no commented lines modified
# ---------------------------------------------------------------------------

def test_clean_pass():
    """3 operations with normal code changes, no comments touched.
    Should pass with 0 findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 100, "before": "    Case 500 : dblRate = 0.05", "after": "    Case 500 : dblRate = 0.06"},
                    ],
                },
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 200, "before": "    varRates = Array6(100, 200, 300)", "after": "    varRates = Array6(110, 220, 330)"},
                    ],
                },
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-003",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {"line": 350, "before": "    Const ACCIDENTBASE = 200", "after": "    Const ACCIDENTBASE = 250"},
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "BLOCKER"
        assert len(result["findings"]) == 0
        assert "No commented code modified" in result.get("message", "")
        assert "3 change(s) checked" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 2: Commented line modified -- before starts with '
# ---------------------------------------------------------------------------

def test_commented_line_modified():
    """A line starting with ' was modified. Should produce a BLOCKER finding
    with issue 'commented_line_modified'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 50,
                            "before": "' This is an old comment",
                            "after": "' This is a modified comment",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert result["severity"] == "BLOCKER"
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "commented_line_modified"
        assert finding["line"] == 50
        assert finding["operation"] == "intent-001"
        assert finding["before"] == "' This is an old comment"
        assert finding["after"] == "' This is a modified comment"


# ---------------------------------------------------------------------------
# Test 3: Inline comment only change
# ---------------------------------------------------------------------------

def test_inline_comment_only_change():
    """Code portion identical, only the inline comment changed.
    Should produce a finding with issue 'inline_comment_only_change'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-002",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 120,
                            "before": "    Case 200 'IQPORT-1082 Here for Farm Only",
                            "after": "    Case 200 'IQPORT-1099 Updated comment",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "inline_comment_only_change"
        assert finding["line"] == 120


# ---------------------------------------------------------------------------
# Test 4: Pure insertion skipped -- before=None
# ---------------------------------------------------------------------------

def test_pure_insertion_skipped():
    """Pure insertion (before=None) should be skipped entirely.
    No findings expected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-003",
                    "change_type": "structure_insertion",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 75,
                            "before": None,
                            "after": "    ' New traceability comment inserted",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "0 change(s) checked" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 5: Multiple issues -- 2 commented + 1 inline-only
# ---------------------------------------------------------------------------

def test_multiple_issues():
    """2 commented line modifications + 1 inline-comment-only change.
    Should produce 3 findings total."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 10,
                            "before": "' Old comment line 1",
                            "after": "' Modified comment line 1",
                        },
                        {
                            "line": 20,
                            "before": "' Old comment line 2",
                            "after": "' Modified comment line 2",
                        },
                        {
                            "line": 30,
                            "before": "    Case 500 'Old note",
                            "after": "    Case 500 'New note",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 3

        comment_mods = [f for f in result["findings"] if f["issue"] == "commented_line_modified"]
        inline_only = [f for f in result["findings"] if f["issue"] == "inline_comment_only_change"]
        assert len(comment_mods) == 2
        assert len(inline_only) == 1

        # Check the message reports both counts
        msg = result.get("message", "")
        assert "2 commented line(s) modified" in msg
        assert "1 inline-comment-only change(s)" in msg


# ---------------------------------------------------------------------------
# Test 6: Empty operations log -- no operations
# ---------------------------------------------------------------------------

def test_empty_operations_log():
    """No operations in the log at all. Should pass with 0 changes checked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "0 change(s) checked" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 7: FAILED operation skipped
# ---------------------------------------------------------------------------

def test_failed_operation_skipped():
    """An operation with status != 'COMPLETED' (e.g., 'FAILED') should
    be entirely skipped. Even if it has a commented line change, no
    finding should be produced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-001",
                    "change_type": "value_editing",
                    "status": "FAILED",
                    "changes": [
                        {
                            "line": 50,
                            "before": "' This comment was changed",
                            "after": "' But it should not matter",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        assert "0 change(s) checked" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 8: Commented Array6 line -- the canonical trap
# ---------------------------------------------------------------------------

def test_commented_array6_line():
    """A commented-out Array6 line is modified. This is the classic trap:
    'liabilityPremiumArray = Array6(24, 49, 99, 124, 149, 274)
    Must be detected as a BLOCKER."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "intent-004",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 4058,
                            "before": "'liabilityPremiumArray = Array6(24, 49, 99, 124, 149, 274)",
                            "after": "'liabilityPremiumArray = Array6(30, 55, 110, 130, 160, 290)",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "commented_line_modified"
        assert finding["line"] == 4058
        assert "Array6" in finding["before"]


# ---------------------------------------------------------------------------
# Test 9: String with apostrophe -- code changed, NOT inline-comment-only
# ---------------------------------------------------------------------------

def test_string_with_apostrophe():
    """A line containing a string with an apostrophe (e.g., "It's") has
    its code portion changed. This must NOT be flagged as
    'inline_comment_only_change' because the code itself changed.
    The ' inside the string is not a comment delimiter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-005",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 90,
                            "before": '    s = "It\'s a test"',
                            "after": '    s = "It\'s new"',
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        # The code portions are different ("It's a test" vs "It's new"),
        # so this is a valid code change, not an inline-comment-only change.


# ---------------------------------------------------------------------------
# Test 10: Indented comment -- should be detected
# ---------------------------------------------------------------------------

def test_indented_comment():
    """An indented comment line (leading whitespace + ') is modified.
    Should be detected as a 'commented_line_modified' finding since
    is_full_line_comment strips whitespace before checking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "intent-006",
                    "change_type": "value_editing",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 200,
                            "before": "    ' old code here that was commented out",
                            "after": "    ' modified old code here",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "commented_line_modified"
        assert finding["line"] == 200
        # The before/after should be trimmed (stripped)
        assert finding["before"] == "' old code here that was commented out"
        assert finding["after"] == "' modified old code here"
