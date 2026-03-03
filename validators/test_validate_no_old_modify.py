"""
Integration tests for validate_no_old_modify.py

Uses tempfile and os.makedirs to create mock workstreams with controlled
file_hashes.yaml, operations_log.yaml, manifest.yaml, config.yaml, and
fake .vbproj / source files.

Run with:
    cd "E:/intelli-new/Cssi.Net/Portage Mutual/.iq-update/validators"
    python -m pytest test_validate_no_old_modify.py -v
"""

import hashlib
import os
import tempfile
import textwrap

import yaml
import pytest

from validate_no_old_modify import validate
from _helpers import check_vbproj_refs, find_mod_common_ref


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


VBPROJ_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <Project ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
      <ItemGroup>
        {compile_items}
      </ItemGroup>
    </Project>
""")


def _make_vbproj(compile_includes):
    """Generate a .vbproj XML string with given Compile Include paths."""
    items = "\n        ".join(
        f'<Compile Include="{inc}" />' for inc in compile_includes
    )
    return VBPROJ_TEMPLATE.format(compile_items=items)


def _build_workstream(tmpdir, *, source_files=None, target_files=None,
                      vbproj_files=None, ops_log_operations=None,
                      effective_date="20260101", cross_province_files=None,
                      config_extras=None):
    """Build a complete mock workstream in tmpdir.

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        source_files: dict mapping relative_path -> bytes content for source-role files.
        target_files: dict mapping relative_path -> bytes content for target-role files.
        vbproj_files: dict mapping relative_path -> XML string content for .vbproj files.
        ops_log_operations: list of operation dicts for operations_log.yaml.
        effective_date: The effective date string in the manifest.
        cross_province_files: list of cross-province shared file paths.
        config_extras: dict of extra keys for config.yaml.

    Returns:
        str: Absolute path to the manifest.yaml file.
    """
    carrier_root = tmpdir
    workstreams_root = os.path.join(carrier_root, ".iq-workstreams")
    workstream_dir = os.path.join(workstreams_root, "changes", "test-ticket")
    execution_dir = os.path.join(workstream_dir, "execution")

    # --- Write source files and compute hashes ---
    file_hashes_data = {"files": {}}

    if source_files:
        for rel_path, content in source_files.items():
            full_path = os.path.join(carrier_root, rel_path)
            _write_bytes(full_path, content)
            file_hashes_data["files"][rel_path] = {
                "hash": _sha256(content),
                "role": "source",
            }

    if target_files:
        for rel_path, content in target_files.items():
            full_path = os.path.join(carrier_root, rel_path)
            _write_bytes(full_path, content)
            file_hashes_data["files"][rel_path] = {
                "hash": _sha256(content),
                "role": "target",
            }

    if vbproj_files:
        for rel_path, xml_content in vbproj_files.items():
            full_path = os.path.join(carrier_root, rel_path)
            _write_text(full_path, xml_content)
            content_bytes = xml_content.encode("utf-8")
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

    # --- Write config.yaml ---
    config = {}
    if cross_province_files:
        config["cross_province_shared_files"] = cross_province_files
    if config_extras:
        config.update(config_extras)
    _write_yaml(os.path.join(workstreams_root, "config.yaml"), config)

    # --- Ensure snapshots dir exists ---
    os.makedirs(os.path.join(execution_dir, "snapshots"), exist_ok=True)

    return manifest_path


# ---------------------------------------------------------------------------
# Test 1: Clean pass -- source files unchanged, vbproj refs correct
# ---------------------------------------------------------------------------

def test_clean_pass():
    """All source files unchanged, .vbproj refs point to target date, no
    cross-province violations. Should pass cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_content = b"' Old source file content\r\nPublic Sub OldFunc()\r\nEnd Sub\r\n"
        target_content = b"' New target file content\r\nPublic Sub NewFunc()\r\nEnd Sub\r\n"

        vbproj_xml = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABHome20260101.vb",
            "..\\..\\Code\\mod_Common_ABHab20260101.vb",
            "CalcMain.vb",  # local file -- should be ignored
        ])

        manifest_path = _build_workstream(
            tmpdir,
            source_files={
                "Alberta/Code/CalcOption_ABHome20250601.vb": source_content,
            },
            target_files={
                "Alberta/Code/CalcOption_ABHome20260101.vb": target_content,
            },
            vbproj_files={
                "Alberta/Home/20260101/Cssi.IntelliQuote.PORTABHome20260101.vbproj": vbproj_xml,
            },
            ops_log_operations=[
                {"file": "Alberta/Code/CalcOption_ABHome20260101.vb",
                 "agent": "rate-modifier", "status": "COMPLETED",
                 "operation": "op-001-01"},
            ],
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "BLOCKER"
        assert len(result["findings"]) == 0
        assert "No old file modifications detected" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 2: Source file modified -- hash mismatch
# ---------------------------------------------------------------------------

def test_source_file_modified():
    """Source file was modified after hash was recorded. Should produce
    a 'source_modified' BLOCKER finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_content = b"' Original source content\r\n"
        modified_content = b"' MODIFIED source content\r\n"

        # Build workstream with original hash
        manifest_path = _build_workstream(
            tmpdir,
            source_files={
                "Alberta/Code/CalcOption_ABHome20250601.vb": original_content,
            },
            effective_date="20260101",
        )

        # Now modify the source file on disk AFTER building the workstream
        source_path = os.path.join(tmpdir, "Alberta/Code/CalcOption_ABHome20250601.vb")
        with open(source_path, "wb") as f:
            f.write(modified_content)

        result = validate(manifest_path)
        assert result["passed"] is False
        assert result["severity"] == "BLOCKER"
        assert len(result["findings"]) == 1

        finding = result["findings"][0]
        assert finding["issue"] == "source_modified"
        assert finding["expected_hash"] == _sha256(original_content)
        assert finding["actual_hash"] == _sha256(modified_content)


# ---------------------------------------------------------------------------
# Test 3: Source file missing
# ---------------------------------------------------------------------------

def test_source_file_missing():
    """Source file was deleted from disk. Should produce a
    'source_file_missing' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_content = b"' Will be deleted\r\n"

        manifest_path = _build_workstream(
            tmpdir,
            source_files={
                "Alberta/Code/CalcOption_ABHome20250601.vb": original_content,
            },
            effective_date="20260101",
        )

        # Delete the source file
        source_path = os.path.join(tmpdir, "Alberta/Code/CalcOption_ABHome20250601.vb")
        os.remove(source_path)

        result = validate(manifest_path)
        assert result["passed"] is False
        assert len(result["findings"]) == 1
        assert result["findings"][0]["issue"] == "source_file_missing"


# ---------------------------------------------------------------------------
# Test 4: Old date in .vbproj reference
# ---------------------------------------------------------------------------

def test_old_date_in_vbproj_ref():
    """A .vbproj Code/ Include has an old date instead of target date.
    Should produce an 'old_date_ref' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vbproj_xml = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABHome20260101.vb",  # correct
            "..\\..\\Code\\mod_Common_ABHab20250601.vb",   # OLD date!
            "CalcMain.vb",
        ])

        manifest_path = _build_workstream(
            tmpdir,
            vbproj_files={
                "Alberta/Home/20260101/Cssi.IntelliQuote.PORTABHome20260101.vbproj": vbproj_xml,
            },
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        old_ref_findings = [f for f in result["findings"] if f["issue"] == "old_date_ref"]
        assert len(old_ref_findings) == 1
        assert old_ref_findings[0]["found_date"] == "20250601"
        assert old_ref_findings[0]["expected_date"] == "20260101"
        assert "mod_Common_ABHab20250601.vb" in old_ref_findings[0]["include"]


# ---------------------------------------------------------------------------
# Test 5: Cross-province violation
# ---------------------------------------------------------------------------

def test_cross_province_violation():
    """A file matching cross_province_shared_files appears in the operations
    log. Should produce a 'cross_province_violation' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {"file": "Code/PORTCommonHeat.vb",
                 "agent": "rate-modifier", "status": "COMPLETED",
                 "operation": "op-001-01"},
            ],
            cross_province_files=["Code/PORTCommonHeat.vb", "Code/mod_VICCAuto.vb"],
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        cp_findings = [f for f in result["findings"] if f["issue"] == "cross_province_violation"]
        assert len(cp_findings) == 1
        assert "PORTCommonHeat" in cp_findings[0]["file"]


# ---------------------------------------------------------------------------
# Test 6: No source files -- all targets, should pass
# ---------------------------------------------------------------------------

def test_no_source_files():
    """All files in file_hashes have role 'target' -- no source files to
    check. Should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_content = b"' Target file\r\n"

        manifest_path = _build_workstream(
            tmpdir,
            target_files={
                "Alberta/Code/CalcOption_ABHome20260101.vb": target_content,
            },
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert len(result["findings"]) == 0


# ---------------------------------------------------------------------------
# Test 7: Malformed .vbproj -- invalid XML
# ---------------------------------------------------------------------------

def test_malformed_vbproj():
    """A .vbproj file has invalid XML. Should produce a 'vbproj_parse_error'
    finding but NOT crash the validator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_xml = "<Project><ItemGroup><Compile Include='broken.vb'"  # intentionally invalid

        manifest_path = _build_workstream(
            tmpdir,
            vbproj_files={
                "Alberta/Home/20260101/Bad.vbproj": bad_xml,
            },
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        parse_findings = [f for f in result["findings"] if f["issue"] == "vbproj_parse_error"]
        assert len(parse_findings) == 1


# ---------------------------------------------------------------------------
# Test 8: Multiple .vbproj files -- 1 of 3 has old ref
# ---------------------------------------------------------------------------

def test_multiple_vbproj_one_old_ref():
    """Multi-LOB hab ticket with 3 .vbproj files. Two have correct refs,
    one has an old date. Should produce exactly 1 finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        good_vbproj = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABHome20260101.vb",
            "..\\..\\Code\\mod_Common_ABHab20260101.vb",
        ])
        bad_vbproj = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABCondo20260101.vb",
            "..\\..\\Code\\mod_Common_ABHab20250601.vb",  # OLD!
        ])

        manifest_path = _build_workstream(
            tmpdir,
            vbproj_files={
                "Alberta/Home/20260101/Home.vbproj": good_vbproj,
                "Alberta/Condo/20260101/Condo.vbproj": bad_vbproj,
                "Alberta/Tenant/20260101/Tenant.vbproj": good_vbproj,
            },
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        old_ref_findings = [f for f in result["findings"] if f["issue"] == "old_date_ref"]
        assert len(old_ref_findings) == 1
        assert old_ref_findings[0]["found_date"] == "20250601"
        # The finding should reference the Condo vbproj
        assert "Condo" in old_ref_findings[0]["file"]


# ---------------------------------------------------------------------------
# Test 9: Cross-province violation with path suffix matching
# ---------------------------------------------------------------------------

def test_cross_province_suffix_match():
    """Cross-province file listed as just 'PORTCommonHeat.vb' but the
    ops_log has the full relative path. Should still match via suffix."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            ops_log_operations=[
                {"file": "Code/PORTCommonHeat.vb",
                 "agent": "rate-modifier", "status": "COMPLETED",
                 "operation": "op-001-01"},
            ],
            cross_province_files=["PORTCommonHeat.vb"],
            effective_date="20260101",
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        cp_findings = [f for f in result["findings"] if f["issue"] == "cross_province_violation"]
        assert len(cp_findings) == 1


# ---------------------------------------------------------------------------
# Test 10: Combined failures -- source modified + old ref + cross-province
# ---------------------------------------------------------------------------

def test_combined_failures():
    """Multiple failure types at once. All 3 checks should produce findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_content = b"' Original\r\n"
        modified_content = b"' Modified\r\n"

        bad_vbproj = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABHome20250601.vb",  # old date
        ])

        manifest_path = _build_workstream(
            tmpdir,
            source_files={
                "Alberta/Code/CalcOption_ABHome20250601.vb": original_content,
            },
            vbproj_files={
                "Alberta/Home/20260101/Home.vbproj": bad_vbproj,
            },
            ops_log_operations=[
                {"file": "Code/PORTCommonHeat.vb",
                 "agent": "rate-modifier", "status": "COMPLETED",
                 "operation": "op-001-01"},
            ],
            cross_province_files=["Code/PORTCommonHeat.vb"],
            effective_date="20260101",
        )

        # Modify the source file
        source_path = os.path.join(tmpdir, "Alberta/Code/CalcOption_ABHome20250601.vb")
        with open(source_path, "wb") as f:
            f.write(modified_content)

        result = validate(manifest_path)
        assert result["passed"] is False

        issues = {f["issue"] for f in result["findings"]}
        assert "source_modified" in issues
        assert "old_date_ref" in issues
        assert "cross_province_violation" in issues
        assert len(result["findings"]) >= 3


# ---------------------------------------------------------------------------
# Helper Unit Tests: check_vbproj_refs
# ---------------------------------------------------------------------------

def test_check_vbproj_refs_correct():
    """check_vbproj_refs with all correct dates returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vbproj = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABHome20260101.vb",
            "..\\..\\Code\\mod_Common_ABHab20260101.vb",
            "CalcMain.vb",
        ])
        path = os.path.join(tmpdir, "test.vbproj")
        _write_text(path, vbproj)

        findings = check_vbproj_refs(path, "20260101")
        assert findings == []


def test_check_vbproj_refs_old_date():
    """check_vbproj_refs detects an old-date reference."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vbproj = _make_vbproj([
            "..\\..\\Code\\mod_Common_ABHab20250601.vb",
        ])
        path = os.path.join(tmpdir, "test.vbproj")
        _write_text(path, vbproj)

        findings = check_vbproj_refs(path, "20260101")
        assert len(findings) == 1
        assert findings[0]["issue"] == "old_date_ref"
        assert findings[0]["found_date"] == "20250601"


def test_check_vbproj_refs_shardclass():
    """check_vbproj_refs detects old dates in SHARDCLASS/ paths too."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vbproj = _make_vbproj([
            "..\\..\\SHARDCLASS\\clsHelper20250601.vb",
        ])
        path = os.path.join(tmpdir, "test.vbproj")
        _write_text(path, vbproj)

        findings = check_vbproj_refs(path, "20260101")
        assert len(findings) == 1
        assert findings[0]["issue"] == "old_date_ref"


# ---------------------------------------------------------------------------
# Helper Unit Tests: find_mod_common_ref
# ---------------------------------------------------------------------------

def test_find_mod_common_ref_found():
    """find_mod_common_ref returns the Include path when mod_Common is present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vbproj = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABHome20260101.vb",
            "..\\..\\Code\\mod_Common_ABHab20260101.vb",
        ])
        path = os.path.join(tmpdir, "test.vbproj")
        _write_text(path, vbproj)

        result = find_mod_common_ref(path)
        assert result is not None
        assert "mod_Common_ABHab20260101.vb" in result


def test_find_mod_common_ref_not_found():
    """find_mod_common_ref returns None when no mod_Common in .vbproj."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vbproj = _make_vbproj([
            "..\\..\\Code\\CalcOption_ABHome20260101.vb",
        ])
        path = os.path.join(tmpdir, "test.vbproj")
        _write_text(path, vbproj)

        result = find_mod_common_ref(path)
        assert result is None


def test_find_mod_common_ref_malformed():
    """find_mod_common_ref returns None on malformed XML (no crash)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.vbproj")
        _write_text(path, "<not valid xml")

        result = find_mod_common_ref(path)
        assert result is None
