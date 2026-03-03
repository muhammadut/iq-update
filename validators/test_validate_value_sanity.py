"""
Tests for validate_value_sanity.py

Uses tempfile to create mock workstreams with controlled
operations_log.yaml, manifest.yaml, and config.yaml entries.

Run with:
    cd "E:/intelli-new/Cssi.Net/Portage Mutual/.iq-update/validators"
    python -m pytest test_validate_value_sanity.py -v
"""

import os
import tempfile

import yaml
import pytest

from validate_value_sanity import validate
from _helpers import (
    try_eval_numeric,
    parse_array6_values,
    compute_pct_change,
    extract_numeric_value,
)


# ---------------------------------------------------------------------------
# Test Fixtures / Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path, data):
    """Write a dict to a YAML file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _build_workstream(tmpdir, *, ops_log_operations=None, config_extras=None):
    """Build a minimal mock workstream for the value sanity validator.

    This validator reads manifest.yaml, operations_log.yaml, and optionally
    config.yaml for the threshold setting.

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        ops_log_operations: list of operation dicts for operations_log.yaml.
        config_extras: dict of extra keys merged into config.yaml.

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

    # --- Write config.yaml ---
    config = {}
    if config_extras:
        config.update(config_extras)
    _write_yaml(os.path.join(workstreams_root, "config.yaml"), config)

    # --- Ensure snapshots dir exists ---
    os.makedirs(os.path.join(execution_dir, "snapshots"), exist_ok=True)

    return manifest_path


# ---------------------------------------------------------------------------
# Test 1: Clean pass -- all changes within 5-10%
# ---------------------------------------------------------------------------

def test_clean_pass():
    """All changes within 5-10% threshold (default 50%).
    Should pass with message containing stats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 200,
                            "before": "    varRates = Array6(100, 200, 300)",
                            "after":  "    varRates = Array6(105, 210, 315)",
                        },
                    ],
                },
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "op-002-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 350,
                            "before": "    Const ACCIDENTBASE = 200",
                            "after":  "    Const ACCIDENTBASE = 210",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 0
        msg = result.get("message", "")
        assert "4 values checked" in msg
        assert "Range:" in msg
        assert "mean" in msg


# ---------------------------------------------------------------------------
# Test 2: Large change detected -- 60% change
# ---------------------------------------------------------------------------

def test_large_change_detected():
    """A 60% change (exceeds 50% threshold) produces a WARNING finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 100,
                            "before": "    varRates = Array6(100, 200)",
                            "after":  "    varRates = Array6(160, 200)",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "large_change"
        assert finding["arg_index"] == 0
        assert finding["before"] == 100.0
        assert finding["after"] == 160.0
        assert finding["pct_change"] == 60.0


# ---------------------------------------------------------------------------
# Test 3: Sentinel modified -- -999 changed
# ---------------------------------------------------------------------------

def test_sentinel_modified():
    """-999 modified to -1049 (as if multiplied by 1.05).
    Should produce a 'sentinel_modified' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 500,
                            "before": "    varRates = Array6(100, -999, 300)",
                            "after":  "    varRates = Array6(105, -1049, 315)",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        sentinel_findings = [f for f in result["findings"]
                            if f["issue"] == "sentinel_modified"]
        assert len(sentinel_findings) == 1
        assert sentinel_findings[0]["arg_index"] == 1
        assert sentinel_findings[0]["before"] == -999.0
        assert sentinel_findings[0]["after"] == -1049.0


# ---------------------------------------------------------------------------
# Test 4: Zero to nonzero
# ---------------------------------------------------------------------------

def test_zero_to_nonzero():
    """0 changed to 50 -- can't compute percentage, flagged as
    'zero_to_nonzero'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 300,
                            "before": "    varRates = Array6(100, 0, 300)",
                            "after":  "    varRates = Array6(105, 50, 315)",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        ztn_findings = [f for f in result["findings"]
                       if f["issue"] == "zero_to_nonzero"]
        assert len(ztn_findings) == 1
        assert ztn_findings[0]["arg_index"] == 1
        assert ztn_findings[0]["before"] == 0.0
        assert ztn_findings[0]["after"] == 50.0


# ---------------------------------------------------------------------------
# Test 5: Sign flip -- positive to negative
# ---------------------------------------------------------------------------

def test_sign_flip():
    """100 changed to -100 -- sign flip detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 400,
                            "before": "    varRates = Array6(100, 200)",
                            "after":  "    varRates = Array6(-100, 200)",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        flip_findings = [f for f in result["findings"]
                        if f["issue"] == "sign_flip"]
        assert len(flip_findings) == 1
        assert flip_findings[0]["arg_index"] == 0
        assert flip_findings[0]["before"] == 100.0
        assert flip_findings[0]["after"] == -100.0


# ---------------------------------------------------------------------------
# Test 6: Factor table value -- single numeric extraction
# ---------------------------------------------------------------------------

def test_factor_table_value():
    """Factor table line: dblDedDiscount = -0.075 changed to -0.20.
    The percentage change is abs(-0.20 - (-0.075)) / abs(-0.075) * 100 =
    0.125 / 0.075 * 100 = 166.67% -- well above 50% threshold."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "op-002-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 120,
                            "before": "    Case 1000 : dblDedDiscount = -0.075",
                            "after":  "    Case 1000 : dblDedDiscount = -0.20",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        large_findings = [f for f in result["findings"]
                         if f["issue"] == "large_change"]
        assert len(large_findings) == 1
        assert large_findings[0]["before"] == -0.075
        assert large_findings[0]["after"] == -0.20
        assert large_findings[0]["pct_change"] == 166.67
        # Factor table findings should NOT have arg_index
        assert "arg_index" not in large_findings[0]


# ---------------------------------------------------------------------------
# Test 7: Configurable threshold -- set to 10%, flag 15% change
# ---------------------------------------------------------------------------

def test_configurable_threshold():
    """Threshold set to 10% in config. A 15% change is flagged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 200,
                            "before": "    varRates = Array6(100, 200)",
                            "after":  "    varRates = Array6(115, 200)",
                        },
                    ],
                },
            ],
            config_extras={
                "validation": {"value_sanity_threshold_percent": 10},
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "large_change"
        assert finding["pct_change"] == 15.0


# ---------------------------------------------------------------------------
# Test 8: No rate-modifier ops -- only logic-modifier
# ---------------------------------------------------------------------------

def test_no_rate_modifier_ops():
    """Operations only from logic-modifier agent. Value sanity skips them.
    Should pass with 0 values checked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "op-010-01",
                    "agent": "logic-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 50,
                            "before": None,
                            "after": "    If condition Then Exit Sub",
                        },
                    ],
                },
                {
                    "file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                    "operation": "op-010-02",
                    "agent": "logic-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 60,
                            "before": "    dblRate = 0.05",
                            "after":  "    dblRate = 0.10",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        msg = result.get("message", "")
        assert "0 values checked" in msg


# ---------------------------------------------------------------------------
# Test 9: Arithmetic expression in Array6
# ---------------------------------------------------------------------------

def test_arithmetic_expression():
    """Array6(30 + 10, 40) changed to Array6(35 + 10, 42).
    First arg: 40 -> 45 = 12.5%. Second arg: 40 -> 42 = 5%.
    Both within threshold. Should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            "line": 600,
                            "before": "    varRates = Array6(30 + 10, 40)",
                            "after":  "    varRates = Array6(35 + 10, 42)",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0
        msg = result.get("message", "")
        assert "2 values checked" in msg
        # Verify the percentages are reasonable
        assert "Range:" in msg


# ---------------------------------------------------------------------------
# Test 10: Multiple issues combined
# ---------------------------------------------------------------------------

def test_multiple_issues_combined():
    """Sentinel + large change + zero-to-nonzero in one run.
    Should produce 3 findings from one operation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {
                    "file": "Alberta/Code/mod_Common_ABHab20260101.vb",
                    "operation": "op-001-01",
                    "agent": "rate-modifier",
                    "status": "COMPLETED",
                    "changes": [
                        {
                            # Sentinel modification
                            "line": 100,
                            "before": "    varRates = Array6(-999, 200)",
                            "after":  "    varRates = Array6(-1049, 210)",
                        },
                        {
                            # Large change (100 -> 200 = 100%)
                            "line": 200,
                            "before": "    varRates = Array6(100, 50)",
                            "after":  "    varRates = Array6(200, 52)",
                        },
                        {
                            # Zero-to-nonzero
                            "line": 300,
                            "before": "    varRates = Array6(0, 100)",
                            "after":  "    varRates = Array6(50, 105)",
                        },
                    ],
                },
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        issues = [f["issue"] for f in result["findings"]]
        assert "sentinel_modified" in issues
        assert "large_change" in issues
        assert "zero_to_nonzero" in issues

        # Verify the summary message lists all issue types
        msg = result.get("message", "")
        assert "Flagged:" in msg
        assert "sentinel_modified" in msg
        assert "large_change" in msg
        assert "zero_to_nonzero" in msg


# ---------------------------------------------------------------------------
# Helper Unit Tests: try_eval_numeric
# ---------------------------------------------------------------------------

def test_try_eval_numeric_simple():
    """Simple numeric strings."""
    assert try_eval_numeric("50") == 50.0
    assert try_eval_numeric("-0.22") == -0.22
    assert try_eval_numeric("512.59") == 512.59


def test_try_eval_numeric_arithmetic():
    """Arithmetic expressions."""
    assert try_eval_numeric("30 + 10") == 40.0
    assert try_eval_numeric("100 * 1.05") == 105.0


def test_try_eval_numeric_none_cases():
    """Variables, function calls, empty strings return None."""
    assert try_eval_numeric("someVariable") is None
    assert try_eval_numeric("Func(x)") is None
    assert try_eval_numeric("") is None
    assert try_eval_numeric(None) is None


# ---------------------------------------------------------------------------
# Helper Unit Tests: parse_array6_values
# ---------------------------------------------------------------------------

def test_parse_array6_values_basic():
    """Basic Array6 with numeric values."""
    result = parse_array6_values("    varRates = Array6(100, 200, 300)")
    assert result == [100.0, 200.0, 300.0]


def test_parse_array6_values_with_arithmetic():
    """Array6 with arithmetic expressions."""
    result = parse_array6_values("    varRates = Array6(30 + 10, 40)")
    assert result == [40.0, 40.0]


def test_parse_array6_values_no_array6():
    """Line without Array6 returns None."""
    assert parse_array6_values("    dblRate = 0.05") is None


# ---------------------------------------------------------------------------
# Helper Unit Tests: compute_pct_change
# ---------------------------------------------------------------------------

def test_compute_pct_change_normal():
    """Normal percentage change."""
    assert compute_pct_change(100, 110) == 10.0
    assert compute_pct_change(100, 160) == 60.0


def test_compute_pct_change_zero_baseline():
    """Zero baseline returns None."""
    assert compute_pct_change(0, 50) is None


def test_compute_pct_change_negative():
    """Negative values compute absolute percentage."""
    assert compute_pct_change(-0.075, -0.20) == 166.67


# ---------------------------------------------------------------------------
# Helper Unit Tests: extract_numeric_value
# ---------------------------------------------------------------------------

def test_extract_numeric_value_factor():
    """Factor table assignment."""
    assert extract_numeric_value("    Case 1000 : dblDedDiscount = -0.075") == -0.075


def test_extract_numeric_value_const():
    """Const declaration."""
    assert extract_numeric_value("    Const ACCIDENTBASE = 200") == 200.0


def test_extract_numeric_value_with_comment():
    """Line with inline comment -- value extracted from code portion only."""
    assert extract_numeric_value("    dblRate = 0.05 ' old rate") == 0.05


def test_extract_numeric_value_no_assignment():
    """Line without assignment returns None."""
    assert extract_numeric_value("    If x > 0 Then") is None
