"""Tests for validate_vbproj.py — .vbproj file integrity validator."""

import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import pytest

import _helpers
import validate_vbproj as vv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_carrier(tmp_path):
    """Create a minimal carrier folder structure for testing."""
    # Create province/LOB/version folder
    version_dir = tmp_path / "Saskatchewan" / "Home" / "20260101"
    version_dir.mkdir(parents=True)

    # Create Code dir
    code_dir = tmp_path / "Saskatchewan" / "Code"
    code_dir.mkdir(parents=True)

    return tmp_path


def _write_vbproj(vbproj_path, includes):
    """Write a minimal .vbproj with the given Compile Include entries."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">',
        '  <ItemGroup>',
    ]
    for inc in includes:
        lines.append(f'    <Compile Include="{inc}" />')
    lines.append('  </ItemGroup>')
    lines.append('</Project>')
    vbproj_path.write_text("\n".join(lines), encoding="utf-8")


def _setup_manifest(tmp_path, carrier_root, vbproj_rel_paths):
    """Create workstream structure with manifest + file_hashes."""
    ws_dir = carrier_root / ".iq-workstreams" / "changes" / "test-ws"
    (ws_dir / "execution").mkdir(parents=True)

    # manifest.yaml
    manifest = {
        "manifest_version": "2.0",
        "workflow_id": "test-ws",
        "state": "EXECUTED",
        "province": "SK",
        "lobs": ["Home"],
        "effective_date": "20260101",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "codebase_root": str(carrier_root),
    }

    import yaml
    manifest_path = ws_dir / "manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest), encoding="utf-8")

    # file_hashes.yaml
    files = {rel: {"hash": "sha256:abc", "role": "target"} for rel in vbproj_rel_paths}
    hashes = {"files": files}
    (ws_dir / "execution" / "file_hashes.yaml").write_text(
        yaml.dump(hashes), encoding="utf-8"
    )

    # ops log (empty)
    (ws_dir / "execution" / "operations_log.yaml").write_text(
        yaml.dump({"operations": []}), encoding="utf-8"
    )

    return str(manifest_path)


# ---------------------------------------------------------------------------
# Tests: All includes valid
# ---------------------------------------------------------------------------

def test_all_includes_exist(tmp_carrier):
    """All Compile Include paths resolve to existing files → pass."""
    version_dir = tmp_carrier / "Saskatchewan" / "Home" / "20260101"
    code_dir = tmp_carrier / "Saskatchewan" / "Code"

    # Create actual files
    (version_dir / "CalcMain.vb").write_text("' CalcMain", encoding="utf-8")
    (code_dir / "mod_Common_SKHab20260101.vb").write_text("' mod", encoding="utf-8")

    # Write .vbproj
    vbproj_path = version_dir / "Test.vbproj"
    _write_vbproj(vbproj_path, [
        "CalcMain.vb",
        "..\\..\\Code\\mod_Common_SKHab20260101.vb",
    ])

    rel = str(vbproj_path.relative_to(tmp_carrier)).replace("\\", "/")
    manifest_path = _setup_manifest(tmp_carrier, tmp_carrier, [rel])

    result = vv.validate(manifest_path)
    assert result["passed"] is True
    assert len(result["findings"]) == 0
    assert "All .vbproj references valid" in result["message"]


# ---------------------------------------------------------------------------
# Tests: Missing include
# ---------------------------------------------------------------------------

def test_missing_include_detected(tmp_carrier):
    """A Compile Include pointing to a non-existent file → finding."""
    version_dir = tmp_carrier / "Saskatchewan" / "Home" / "20260101"

    # CalcMain.vb exists but mod_Common does NOT
    (version_dir / "CalcMain.vb").write_text("' CalcMain", encoding="utf-8")

    vbproj_path = version_dir / "Test.vbproj"
    _write_vbproj(vbproj_path, [
        "CalcMain.vb",
        "..\\..\\Code\\mod_Common_SKHab20260101.vb",  # does NOT exist
    ])

    rel = str(vbproj_path.relative_to(tmp_carrier)).replace("\\", "/")
    manifest_path = _setup_manifest(tmp_carrier, tmp_carrier, [rel])

    result = vv.validate(manifest_path)
    assert result["passed"] is False
    assert result["severity"] == "BLOCKER"
    assert any(f["issue"] == "missing_include" for f in result["findings"])


# ---------------------------------------------------------------------------
# Tests: Duplicate include
# ---------------------------------------------------------------------------

def test_duplicate_include_detected(tmp_carrier):
    """Same file referenced twice in Compile Include → finding."""
    version_dir = tmp_carrier / "Saskatchewan" / "Home" / "20260101"
    (version_dir / "CalcMain.vb").write_text("' CalcMain", encoding="utf-8")

    vbproj_path = version_dir / "Test.vbproj"
    _write_vbproj(vbproj_path, [
        "CalcMain.vb",
        "CalcMain.vb",  # duplicate
    ])

    rel = str(vbproj_path.relative_to(tmp_carrier)).replace("\\", "/")
    manifest_path = _setup_manifest(tmp_carrier, tmp_carrier, [rel])

    result = vv.validate(manifest_path)
    assert result["passed"] is False
    assert any(f["issue"] == "duplicate_include" for f in result["findings"])


# ---------------------------------------------------------------------------
# Tests: Invalid XML
# ---------------------------------------------------------------------------

def test_malformed_vbproj_xml(tmp_carrier):
    """A .vbproj with invalid XML → vbproj_parse_error finding."""
    version_dir = tmp_carrier / "Saskatchewan" / "Home" / "20260101"
    vbproj_path = version_dir / "Bad.vbproj"
    vbproj_path.write_text("<Project><broken>", encoding="utf-8")

    rel = str(vbproj_path.relative_to(tmp_carrier)).replace("\\", "/")
    manifest_path = _setup_manifest(tmp_carrier, tmp_carrier, [rel])

    result = vv.validate(manifest_path)
    assert result["passed"] is False
    assert any(f["issue"] == "vbproj_parse_error" for f in result["findings"])


# ---------------------------------------------------------------------------
# Tests: No vbproj files
# ---------------------------------------------------------------------------

def test_no_vbproj_in_hashes(tmp_carrier):
    """No .vbproj files in file_hashes → pass (nothing to check)."""
    manifest_path = _setup_manifest(tmp_carrier, tmp_carrier, [])
    result = vv.validate(manifest_path)
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# Tests: Message builder
# ---------------------------------------------------------------------------

def test_message_builder_no_findings():
    msg = vv._build_message([], 3)
    assert "All .vbproj references valid" in msg
    assert "3 project file(s)" in msg


def test_message_builder_with_findings():
    findings = [
        {"issue": "missing_include"},
        {"issue": "missing_include"},
        {"issue": "duplicate_include"},
    ]
    msg = vv._build_message(findings, 2)
    assert "FAILED" in msg
    assert "3 findings" in msg


# ---------------------------------------------------------------------------
# Tests: Path traversal blocked
# ---------------------------------------------------------------------------

def test_path_traversal_blocked(tmp_carrier):
    """A .vbproj path like '../../Windows/System32/evil.vbproj' in
    file_hashes should produce a 'path_traversal' BLOCKER finding,
    not a crash or read outside the carrier root."""
    import yaml

    ws_dir = tmp_carrier / ".iq-workstreams" / "changes" / "test-ws"
    (ws_dir / "execution").mkdir(parents=True)

    manifest = {
        "manifest_version": "2.0",
        "workflow_id": "test-ws",
        "state": "EXECUTED",
        "province": "SK",
        "lobs": ["Home"],
        "effective_date": "20260101",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "codebase_root": str(tmp_carrier),
    }
    manifest_path = ws_dir / "manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest), encoding="utf-8")

    # file_hashes with a traversal path
    hashes = {
        "files": {
            "../../Windows/System32/evil.vbproj": {
                "hash": "sha256:abc",
                "role": "target",
            },
        },
    }
    (ws_dir / "execution" / "file_hashes.yaml").write_text(
        yaml.dump(hashes), encoding="utf-8"
    )
    (ws_dir / "execution" / "operations_log.yaml").write_text(
        yaml.dump({"operations": []}), encoding="utf-8"
    )

    result = vv.validate(str(manifest_path))
    assert result["passed"] is False

    traversal_findings = [f for f in result["findings"]
                          if f["issue"] == "path_traversal"]
    assert len(traversal_findings) == 1
    assert "evil.vbproj" in traversal_findings[0]["message"]
