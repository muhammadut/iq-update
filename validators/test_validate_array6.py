"""
Integration tests for validate_array6.py (Array6 Syntax BLOCKER validator).

Uses tempfile and os.makedirs to create mock workstreams with controlled
manifest.yaml, operations_log.yaml, file_hashes.yaml, and fake VB.NET
source files on disk.

Run with:
    cd <plugin-root>/validators
    python -m pytest test_validate_array6.py -v
"""

import hashlib
import os
import tempfile
import textwrap

import yaml
import pytest

from validate_array6 import validate
from _helpers import (
    count_array6_args,
    extract_balanced_parens,
    is_array6_test_usage,
    parens_balanced,
    split_top_level_commas,
)


# ---------------------------------------------------------------------------
# Test Fixtures / Helpers
# ---------------------------------------------------------------------------

def _sha256(content_bytes):
    """Compute sha256:hex hash matching compute_file_hash format."""
    return "sha256:" + hashlib.sha256(content_bytes).hexdigest()


def _write_yaml(path, data):
    """Write a dict to a YAML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _write_text(path, text):
    """Write text to a file, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_bytes(path, data):
    """Write bytes to a file, creating parent dirs."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _build_workstream(tmpdir, *, source_files=None, target_files=None,
                      ops_log_operations=None, effective_date="20260101",
                      snapshot_files=None):
    """Build a complete mock workstream in tmpdir.

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        source_files: dict mapping relative_path -> text content for VB files on disk.
        target_files: dict mapping relative_path -> text content for target VB files.
        ops_log_operations: list of operation dicts for operations_log.yaml.
        effective_date: The effective date string in the manifest.
        snapshot_files: dict mapping basename -> text content for snapshot files.

    Returns:
        str: Absolute path to the manifest.yaml file.
    """
    carrier_root = tmpdir
    workstreams_root = os.path.join(carrier_root, ".iq-workstreams")
    workstream_dir = os.path.join(workstreams_root, "changes", "test-ticket")
    execution_dir = os.path.join(workstream_dir, "execution")
    snapshots_dir = os.path.join(execution_dir, "snapshots")

    # --- Write source/target VB files and compute hashes ---
    file_hashes_data = {"files": {}}

    if source_files:
        for rel_path, content in source_files.items():
            full_path = os.path.join(carrier_root, rel_path)
            _write_text(full_path, content)
            content_bytes = content.encode("utf-8")
            file_hashes_data["files"][rel_path] = {
                "hash": _sha256(content_bytes),
                "role": "source",
            }

    if target_files:
        for rel_path, content in target_files.items():
            full_path = os.path.join(carrier_root, rel_path)
            _write_text(full_path, content)
            content_bytes = content.encode("utf-8")
            file_hashes_data["files"][rel_path] = {
                "hash": _sha256(content_bytes),
                "role": "target",
            }

    # --- Write file_hashes.yaml ---
    _write_yaml(os.path.join(execution_dir, "file_hashes.yaml"), file_hashes_data)

    # --- Write operations_log.yaml ---
    ops_log = {"operations": ops_log_operations or []}
    _write_yaml(os.path.join(execution_dir, "operations_log.yaml"), ops_log)

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
    os.makedirs(snapshots_dir, exist_ok=True)

    # --- Write snapshot files ---
    if snapshot_files:
        for basename, content in snapshot_files.items():
            snapshot_path = os.path.join(snapshots_dir, basename)
            _write_text(snapshot_path, content)

    return manifest_path


# ---------------------------------------------------------------------------
# Helper: build operations with Array6 changes
# ---------------------------------------------------------------------------

def _make_rate_op(filepath, operation_id, changes, status="COMPLETED",
                  change_type="value_editing"):
    """Build a single operations_log entry for a value-editing operation.

    Args:
        filepath: Relative file path.
        operation_id: Intent ID string (e.g., "intent-001").
        changes: list of dicts with "line", "before", "after" keys.
        status: Operation status (default: "COMPLETED").
        change_type: Change type (default: "value_editing").

    Returns:
        dict: An operation entry for operations_log.yaml.
    """
    return {
        "file": filepath,
        "change_type": change_type,
        "status": status,
        "operation": operation_id,
        "changes": changes,
    }


# ===========================================================================
# Test 1: Clean pass -- 3 operations with Array6 changes, all arg counts match
# ===========================================================================

def test_clean_pass_all_array6_valid():
    """Three operations with Array6 changes, all arg counts match between
    before and after lines. Full file scan also clean. Should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
        file_content = textwrap.dedent("""\
            ' Saskatchewan Habitational Common Module
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)
                    Case 2 : varRates = Array6(490.00, 25.50, 440.00, 25.50, 550.00, 25.50, 400.00, 25.50, 125.00)
                    Case 3 : varRates = Array6(530.00, 30.00, 480.00, 30.00, 600.00, 30.00, 440.00, 30.00, 140.00)
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-001", [
                {
                    "line": 4,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00, 28.73, 560.00, 28.73, 410.00, 28.73, 130.00)",
                    "after":  "    Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)",
                },
            ]),
            _make_rate_op(rel_path, "intent-002", [
                {
                    "line": 5,
                    "before": "    Case 2 : varRates = Array6(480.00, 25.50, 430.00, 25.50, 540.00, 25.50, 390.00, 25.50, 120.00)",
                    "after":  "    Case 2 : varRates = Array6(490.00, 25.50, 440.00, 25.50, 550.00, 25.50, 400.00, 25.50, 125.00)",
                },
            ]),
            _make_rate_op(rel_path, "intent-003", [
                {
                    "line": 6,
                    "before": "    Case 3 : varRates = Array6(520.00, 30.00, 470.00, 30.00, 590.00, 30.00, 430.00, 30.00, 135.00)",
                    "after":  "    Case 3 : varRates = Array6(530.00, 30.00, 480.00, 30.00, 600.00, 30.00, 440.00, 30.00, 140.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "BLOCKER"
        assert len(result["findings"]) == 0
        assert "valid" in result.get("message", "").lower()


# ===========================================================================
# Test 2: Arg count mismatch -- before has 9 args, after has 8
# ===========================================================================

def test_arg_count_mismatch():
    """Before line has 9 Array6 args, after line has only 8. Should produce
    a BLOCKER finding with issue 'arg_count_mismatch'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
        # The file on disk has the AFTER content (8 args) -- also caught by full scan
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73)
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-001", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00, 28.73, 560.00, 28.73, 410.00, 28.73, 130.00)",
                    "after":  "    Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert result["severity"] == "BLOCKER"

        mismatch_findings = [f for f in result["findings"]
                             if f["issue"] == "arg_count_mismatch"]
        assert len(mismatch_findings) >= 1

        finding = mismatch_findings[0]
        assert finding["expected"] == "9 arguments"
        assert finding["actual"] == "8 arguments"
        assert finding["file"] == rel_path
        assert finding["operation"] == "intent-001"


# ===========================================================================
# Test 3: Empty argument (,,) in after line
# ===========================================================================

def test_empty_argument():
    """After line has an empty argument (consecutive commas: ,,). Should
    produce a finding with issue 'empty_arg'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/mod_Common_ABHab20260101.vb"
        # File on disk has the corrupted line too
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(512.59,, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-004", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00, 28.73, 560.00, 28.73, 410.00, 28.73, 130.00)",
                    "after":  "    Case 1 : varRates = Array6(512.59,, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        empty_findings = [f for f in result["findings"]
                          if f["issue"] in ("empty_arg", "empty_arg_fullscan")]
        assert len(empty_findings) >= 1

        # At least the ops-log phase finding should be present
        ops_empty = [f for f in result["findings"] if f["issue"] == "empty_arg"]
        assert len(ops_empty) >= 1
        assert ops_empty[0]["file"] == rel_path
        assert "empty argument" in ops_empty[0]["actual"]


# ===========================================================================
# Test 4: Unmatched parentheses in after line
# ===========================================================================

def test_unmatched_parens():
    """After line is missing the closing parenthesis of Array6(. Should
    produce a finding with issue 'unmatched_parens'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/mod_Common_ABHab20260101.vb"
        # File on disk also has unmatched parens
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-005", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00, 28.73, 560.00)",
                    "after":  "    Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        paren_findings = [f for f in result["findings"]
                          if "unmatched_parens" in f["issue"]]
        assert len(paren_findings) >= 1

        # Check at least one from the ops log phase
        ops_paren = [f for f in result["findings"]
                     if f["issue"] == "unmatched_parens"]
        assert len(ops_paren) >= 1
        assert ops_paren[0]["file"] == rel_path


# ===========================================================================
# Test 5: Full file scan -- clean
# ===========================================================================

def test_full_file_scan_clean():
    """Rate modifier file on disk has correct Array6 syntax everywhere.
    No ops log changes with Array6 either. Should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Manitoba/Code/mod_Common_MBHab20260101.vb"
        file_content = textwrap.dedent("""\
            ' Manitoba Habitational Common Module
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(100.00, 200.00, 300.00, 400.00, 500.00)
                    Case 2 : varRates = Array6(110.00, 210.00, 310.00, 410.00, 510.00)
                End Select
            End Function

            Public Function GetLiabilityPremium()
                liabilityPremiumArray = Array6(50.00, 75.00, 100.00)
            End Function
        """)

        # Operation touches the file but changes are non-Array6
        ops = [
            _make_rate_op(rel_path, "intent-006", [
                {
                    "line": 20,
                    "before": "    dblDedDiscount = -0.075",
                    "after":  "    dblDedDiscount = -0.080",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ===========================================================================
# Test 6: Full file scan -- corruption (unmatched parens on disk)
# ===========================================================================

def test_full_file_scan_corruption():
    """File on disk has an Array6 call with unmatched parentheses, even
    though the ops log does not mention this line. The full-file scan
    should catch it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Ontario/Code/mod_Common_ONHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(100.00, 200.00, 300.00)
                    Case 2 : varRates = Array6(110.00, 210.00, 310.00
                End Select
            End Function
        """)

        # Ops log references this file so it goes into inventory, but changes
        # don't involve the corrupt line (the corruption is pre-existing
        # or was introduced by a different edit)
        ops = [
            _make_rate_op(rel_path, "intent-007", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(90.00, 190.00, 290.00)",
                    "after":  "    Case 1 : varRates = Array6(100.00, 200.00, 300.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        fullscan_findings = [f for f in result["findings"]
                             if f["issue"] == "unmatched_parens_fullscan"]
        assert len(fullscan_findings) >= 1
        assert fullscan_findings[0]["line"] == 4  # 1-indexed: line 4 has the bad Array6
        assert fullscan_findings[0]["file"] == rel_path


# ===========================================================================
# Test 7: Test usage skipped -- IsItemInArray(x, Array6(...))
# ===========================================================================

def test_test_usage_skipped():
    """Operations log has a change where both before and after lines use
    Array6 inside IsItemInArray (dual-use test pattern). These should be
    skipped by the validator -- no findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/CalcOption_ABHome20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function CheckEligibility()
                If IsItemInArray(intClass, Array6(1, 2, 3, 4, 5)) Then
                    ' eligible
                End If
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-008", [
                {
                    "line": 2,
                    "before": "    If IsItemInArray(intClass, Array6(1, 2, 3, 4)) Then",
                    "after":  "    If IsItemInArray(intClass, Array6(1, 2, 3, 4, 5)) Then",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        # Phase 1 skips both lines (both are test usage).
        # Phase 2 also skips lines detected as test usage.
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ===========================================================================
# Test 8: Commented Array6 skipped in full file scan
# ===========================================================================

def test_commented_array6_skipped():
    """File on disk has a commented-out Array6 line with bad syntax.
    The full-file scan should skip commented lines entirely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "NewBrunswick/Code/mod_Common_NBHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    ' varRates = Array6(100.00,, 300.00   <-- old code, bad syntax
                    Case 1 : varRates = Array6(150.00, 250.00, 350.00)
                End Select
            End Function
        """)

        # A simple non-Array6 operation to put this file in inventory
        ops = [
            _make_rate_op(rel_path, "intent-009", [
                {
                    "line": 4,
                    "before": "    Case 1 : varRates = Array6(140.00, 240.00, 340.00)",
                    "after":  "    Case 1 : varRates = Array6(150.00, 250.00, 350.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        # The commented line (line 3) should be skipped.
        # The valid Array6 on line 4 should pass.
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ===========================================================================
# Test 9: No Array6 in changes -- operations don't involve Array6
# ===========================================================================

def test_no_array6_in_changes():
    """All operations are factor table changes (Select Case / dblDedDiscount),
    no Array6 involved at all. Should pass cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "PrinceEdwardIsland/Code/mod_Common_PEHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetDeductibleDiscount()
                Select Case intDeductible
                    Case 500  : dblDedDiscount = 0
                    Case 1000 : dblDedDiscount = -0.080
                    Case 2500 : dblDedDiscount = -0.150
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-010", [
                {
                    "line": 4,
                    "before": "    Case 1000 : dblDedDiscount = -0.075",
                    "after":  "    Case 1000 : dblDedDiscount = -0.080",
                },
            ]),
            _make_rate_op(rel_path, "intent-011", [
                {
                    "line": 5,
                    "before": "    Case 2500 : dblDedDiscount = -0.140",
                    "after":  "    Case 2500 : dblDedDiscount = -0.150",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ===========================================================================
# Test 10: Assignment to test mutation (Codex fix)
# ===========================================================================

def test_assignment_to_test_mutation():
    """Before line was a rate assignment (varRates = Array6(...)) but the
    after line is test usage (IsItemInArray(x, Array6(...))). This is
    corruption -- should produce 'assignment_to_test_mutation' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : If IsItemInArray(intClass, Array6(512.59, 28.73, 463.03)) Then
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-012", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00)",
                    "after":  "    Case 1 : If IsItemInArray(intClass, Array6(512.59, 28.73, 463.03)) Then",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        mutation_findings = [f for f in result["findings"]
                             if f["issue"] == "assignment_to_test_mutation"]
        assert len(mutation_findings) == 1
        assert mutation_findings[0]["file"] == rel_path
        assert mutation_findings[0]["expected"] == "rate assignment (var = Array6(...))"
        assert mutation_findings[0]["actual"] == "test/lookup usage"
        assert mutation_findings[0]["operation"] == "intent-012"


# ===========================================================================
# Test 11: Assignment pattern lost -- bare Array6 without variable assignment
# ===========================================================================

def test_assignment_pattern_lost():
    """Before line has 'varRates = Array6(...)' but after line lost the
    variable assignment (bare Array6). Since is_array6_test_usage classifies
    a bare Array6 (no 'var = Array6(...)') as test usage, this scenario is
    caught by 'assignment_to_test_mutation' rather than 'assignment_pattern_lost'.
    The validator correctly treats this as corruption because a rate assignment
    was rewritten to a non-assignment form."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Manitoba/Code/mod_Common_MBHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : Array6(512.59, 28.73, 463.03)
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-013", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00)",
                    "after":  "    Case 1 : Array6(512.59, 28.73, 463.03)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        # A bare Array6 without assignment is classified as "test usage" by
        # is_array6_test_usage, so the validator reports assignment_to_test_mutation
        mutation_findings = [f for f in result["findings"]
                             if f["issue"] == "assignment_to_test_mutation"]
        assert len(mutation_findings) >= 1
        assert mutation_findings[0]["expected"] == "rate assignment (var = Array6(...))"
        assert mutation_findings[0]["actual"] == "test/lookup usage"


# ===========================================================================
# Test 12: Assignment variable changed -- varRates -> premiumRates
# ===========================================================================

def test_assignment_variable_changed():
    """Before line assigns Array6 to 'varRates', after line assigns to
    'premiumRates'. Should produce 'assignment_variable_changed' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Ontario/Code/mod_Common_ONHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : premiumRates = Array6(512.59, 28.73, 463.03)
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-014", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00)",
                    "after":  "    Case 1 : premiumRates = Array6(512.59, 28.73, 463.03)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        var_findings = [f for f in result["findings"]
                        if f["issue"] == "assignment_variable_changed"]
        assert len(var_findings) >= 1
        assert var_findings[0]["expected"] == "assignment to 'varRates'"
        assert var_findings[0]["actual"] == "assignment to 'premiumRates'"


# ===========================================================================
# Test 13: Snapshot arg count mismatch (full-file scan Phase 2)
# ===========================================================================

def test_snapshot_arg_count_mismatch():
    """File on disk has an Array6 call with 3 args, but the snapshot shows
    5 args for the same variable assignment. Should produce
    'arg_count_mismatch_snapshot' finding from the full-file scan."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "BritishColumbia/Code/mod_Common_BCHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(512.59, 28.73, 463.03)
                End Select
            End Function
        """)

        snapshot_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(500.00, 28.73, 450.00, 28.73, 560.00)
                End Select
            End Function
        """)

        # Operation adds this file to the value_editing inventory
        ops = [
            _make_rate_op(rel_path, "intent-015", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00, 28.73, 560.00)",
                    "after":  "    Case 1 : varRates = Array6(512.59, 28.73, 463.03)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
            snapshot_files={
                "BritishColumbia__Code__mod_Common_BCHab20260101.vb.snapshot": snapshot_content,
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        # Phase 1 should catch arg_count_mismatch (5 vs 3)
        mismatch_findings = [f for f in result["findings"]
                             if f["issue"] == "arg_count_mismatch"]
        assert len(mismatch_findings) >= 1

        # Phase 2 may also catch snapshot mismatch
        all_mismatches = [f for f in result["findings"]
                          if "arg_count_mismatch" in f["issue"]]
        assert len(all_mismatches) >= 1


# ===========================================================================
# Test 14: Non-COMPLETED operations are skipped
# ===========================================================================

def test_non_completed_operations_skipped():
    """Operations with status other than COMPLETED (e.g., PENDING, FAILED)
    should be ignored by the ops log scan."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/mod_Common_ABHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Case 1 : varRates = Array6(100.00, 200.00, 300.00)
            End Function
        """)

        # One PENDING op with bad arg count, one FAILED op with empty arg
        ops = [
            _make_rate_op(rel_path, "intent-016", [
                {
                    "line": 2,
                    "before": "    Case 1 : varRates = Array6(100.00, 200.00, 300.00)",
                    "after":  "    Case 1 : varRates = Array6(100.00, 200.00)",
                },
            ], status="PENDING"),
            _make_rate_op(rel_path, "intent-017", [
                {
                    "line": 2,
                    "before": "    Case 1 : varRates = Array6(100.00, 200.00, 300.00)",
                    "after":  "    Case 1 : varRates = Array6(100.00,, 300.00)",
                },
            ], status="FAILED"),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        # Non-COMPLETED ops should not be checked. The file on disk is fine.
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ===========================================================================
# Test 15: Non-value-editing change types are skipped
# ===========================================================================

def test_non_value_editing_change_type_skipped():
    """Operations with change_type other than value_editing or
    structure_insertion should not be checked by Phase 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/CalcOption_ABHome20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function NewEligibilityRule()
                ' No Array6 in this file at all
                If intClass > 5 Then Exit Function
            End Function
        """)

        # flow_modification operation with Array6 in changes (unusual but possible)
        ops = [
            _make_rate_op(rel_path, "intent-018", [
                {
                    "line": 2,
                    "before": "    varRates = Array6(100.00, 200.00, 300.00)",
                    "after":  "    varRates = Array6(100.00, 200.00)",
                },
            ], change_type="flow_modification"),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        # flow_modification ops are not checked by _check_ops_log
        # and this file is not in value_files inventory
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ===========================================================================
# Test 16: Full file scan -- empty arg on disk
# ===========================================================================

def test_full_file_scan_empty_arg():
    """File on disk has an Array6 call with an empty argument (,,).
    The full-file scan should catch it with 'empty_arg_fullscan'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "NovaScotia/Code/mod_Common_NSHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(100.00, 200.00, 300.00)
                    Case 2 : varRates = Array6(110.00,, 310.00)
                End Select
            End Function
        """)

        # A clean operation to get this file into inventory
        ops = [
            _make_rate_op(rel_path, "intent-019", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(90.00, 190.00, 290.00)",
                    "after":  "    Case 1 : varRates = Array6(100.00, 200.00, 300.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        empty_fullscan = [f for f in result["findings"]
                          if f["issue"] == "empty_arg_fullscan"]
        assert len(empty_fullscan) >= 1
        assert empty_fullscan[0]["line"] == 4


# ===========================================================================
# Test 17: Multiple findings in one operation (arg mismatch + empty arg)
# ===========================================================================

def test_multiple_findings_one_operation():
    """A single operation change has BOTH an arg count mismatch AND an
    empty argument. Both findings should be reported."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Select Case intTerritory
                    Case 1 : varRates = Array6(512.59,, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73)
                End Select
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-020", [
                {
                    "line": 3,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00, 28.73, 560.00, 28.73, 410.00, 28.73, 130.00)",
                    "after":  "    Case 1 : varRates = Array6(512.59,, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        issues = {f["issue"] for f in result["findings"]}
        # Should have both arg_count_mismatch and empty_arg (at minimum)
        assert "arg_count_mismatch" in issues
        assert "empty_arg" in issues or "empty_arg_fullscan" in issues


# ===========================================================================
# Test 18: structure_insertion changes are also checked
# ===========================================================================

def test_structure_insertion_also_checked():
    """Operations with change_type 'structure_insertion' (not just
    'value_editing') should also be checked for Array6 issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/mod_Common_ABHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Case 1 : varRates = Array6(512.59, 28.73)
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-021", [
                {
                    "line": 2,
                    "before": "    Case 1 : varRates = Array6(500.00, 28.73, 450.00)",
                    "after":  "    Case 1 : varRates = Array6(512.59, 28.73)",
                },
            ], change_type="structure_insertion"),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        mismatch = [f for f in result["findings"]
                     if f["issue"] == "arg_count_mismatch"]
        assert len(mismatch) >= 1
        assert mismatch[0]["expected"] == "3 arguments"
        assert mismatch[0]["actual"] == "2 arguments"


# ===========================================================================
# Test 19: File not found in full-file scan
# ===========================================================================

def test_file_not_found_fullscan():
    """Operations log references a file that does not exist on disk.
    The full-file scan should report 'file_not_found'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/mod_MISSING_FILE20260101.vb"

        ops = [
            _make_rate_op(rel_path, "intent-022", [
                {
                    "line": 3,
                    "before": "    varRates = Array6(100.00, 200.00)",
                    "after":  "    varRates = Array6(110.00, 210.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        not_found = [f for f in result["findings"]
                     if f["issue"] == "file_not_found"]
        assert len(not_found) == 1
        assert not_found[0]["file"] == rel_path


# ===========================================================================
# Test 20: Message builder output
# ===========================================================================

def test_message_on_clean_pass():
    """When all checks pass, the message should mention 'valid' and the
    count of Array6 calls checked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/mod_Common_ABHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Case 1 : varRates = Array6(100.00, 200.00, 300.00)
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-023", [
                {
                    "line": 2,
                    "before": "    Case 1 : varRates = Array6(90.00, 190.00, 290.00)",
                    "after":  "    Case 1 : varRates = Array6(100.00, 200.00, 300.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert "message" in result
        assert "valid" in result["message"].lower()
        assert "calls checked" in result["message"].lower()


def test_message_on_failure():
    """When checks fail, the message should list issue types and counts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rel_path = "Alberta/Code/mod_Common_ABHab20260101.vb"
        file_content = textwrap.dedent("""\
            Public Function GetBasePremium_Home()
                Case 1 : varRates = Array6(100.00, 200.00)
            End Function
        """)

        ops = [
            _make_rate_op(rel_path, "intent-024", [
                {
                    "line": 2,
                    "before": "    Case 1 : varRates = Array6(90.00, 190.00, 290.00)",
                    "after":  "    Case 1 : varRates = Array6(100.00, 200.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            target_files={rel_path: file_content},
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert "message" in result
        assert "failed" in result["message"].lower()
        assert "arg_count_mismatch" in result["message"]


# ===========================================================================
# Helper Unit Tests: count_array6_args
# ===========================================================================

class TestCountArray6Args:
    """Unit tests for the count_array6_args helper."""

    def test_simple_9_args(self):
        line = "varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)"
        assert count_array6_args(line) == 9

    def test_single_arg(self):
        assert count_array6_args("x = Array6(4)") == 1

    def test_nested_parens(self):
        line = "varRates = Array6(Func(a, b), 30 + 10, -5)"
        assert count_array6_args(line) == 3

    def test_no_array6(self):
        assert count_array6_args("dblDedDiscount = -0.075") == 0

    def test_unmatched_parens_returns_negative1(self):
        assert count_array6_args("varRates = Array6(100, 200, 300") == -1

    def test_arithmetic_expression_args(self):
        line = "varRates = Array6(30 + 10, 40 * 2, 50 - 5)"
        assert count_array6_args(line) == 3


# ===========================================================================
# Helper Unit Tests: is_array6_test_usage
# ===========================================================================

class TestIsArray6TestUsage:
    """Unit tests for the is_array6_test_usage helper."""

    def test_rate_assignment(self):
        assert is_array6_test_usage("varRates = Array6(1, 2, 3)") is False

    def test_type_suffix_assignment(self):
        assert is_array6_test_usage("varRates$ = Array6(1, 2, 3)") is False

    def test_isiteminarray(self):
        assert is_array6_test_usage("IsItemInArray(x, Array6(1, 2, 3))") is True

    def test_ubound(self):
        assert is_array6_test_usage("UBound(Array6(1, 2, 3))") is True

    def test_no_array6(self):
        assert is_array6_test_usage("x = 5") is False

    def test_empty_line(self):
        assert is_array6_test_usage("") is False


# ===========================================================================
# Helper Unit Tests: parens_balanced
# ===========================================================================

class TestParensBalanced:
    """Unit tests for the parens_balanced helper."""

    def test_balanced(self):
        assert parens_balanced("Array6(1, 2, 3)") is True

    def test_unbalanced_missing_close(self):
        assert parens_balanced("Array6(1, 2, 3") is False

    def test_unbalanced_extra_close(self):
        assert parens_balanced("Array6(1, 2, 3))") is False

    def test_nested_balanced(self):
        assert parens_balanced("Func(Array6(1, 2), 3)") is True

    def test_string_with_parens(self):
        """Parens inside VB.NET strings should be ignored."""
        assert parens_balanced('x = "hello (world)"') is True


# ===========================================================================
# Helper Unit Tests: split_top_level_commas
# ===========================================================================

class TestSplitTopLevelCommas:
    """Unit tests for the split_top_level_commas helper."""

    def test_simple(self):
        assert split_top_level_commas("512.59, 28.73, 463.03") == [
            "512.59", "28.73", "463.03"
        ]

    def test_nested_func(self):
        result = split_top_level_commas("Func(a, b), 30 + 10, -5")
        assert result == ["Func(a, b)", "30 + 10", "-5"]

    def test_empty_string(self):
        assert split_top_level_commas("") == []

    def test_single_value(self):
        assert split_top_level_commas("42") == ["42"]


# ===========================================================================
# Test: Path traversal produces BLOCKER finding, not a crash
# ===========================================================================

def test_path_traversal_blocked():
    """A file path like '../../etc/passwd' in the operations log should
    produce a 'path_traversal' BLOCKER finding, not a crash or file read
    outside the carrier root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traversal_path = "../../etc/passwd"

        ops = [
            _make_rate_op(traversal_path, "intent-099", [
                {
                    "line": 1,
                    "before": "    varRates = Array6(100.00, 200.00)",
                    "after":  "    varRates = Array6(110.00, 210.00)",
                },
            ]),
        ]

        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=ops,
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        traversal_findings = [f for f in result["findings"]
                              if f["issue"] == "path_traversal"]
        assert len(traversal_findings) == 1
        assert "etc/passwd" in traversal_findings[0]["actual"]
