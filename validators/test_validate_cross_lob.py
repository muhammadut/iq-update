"""
Integration tests for validate_cross_lob.py

Uses tempfile and os.makedirs to create mock workstreams with controlled
manifest.yaml, config.yaml, and mock .vbproj files to test cross-LOB
shared module consistency checking.

Tests use the ACTUAL config.yaml schema produced by /iq-init:
  - provinces keyed by code (SK, AB, etc.)
  - province has "folder" field (full filesystem name)
  - lobs is a LIST of dicts [{name, folder, is_hab, ...}]

Run with:
    cd <plugin-root>/validators
    python -m pytest test_validate_cross_lob.py -v
"""

import os
import tempfile
import textwrap

import yaml
import pytest

from validate_cross_lob import validate


# ---------------------------------------------------------------------------
# Test Fixtures / Helpers
# ---------------------------------------------------------------------------

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


VBPROJ_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
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


def _build_workstream(tmpdir, *, shared_modules=None, province_code="SK",
                      province_folder="Saskatchewan", effective_date="20260101",
                      lobs_list=None, lob_vbproj_includes=None,
                      missing_lob_folders=None, missing_vbproj_lobs=None):
    """Build a complete mock workstream in tmpdir for cross-LOB testing.

    Args:
        tmpdir: Root temp directory (acts as carrier_root).
        shared_modules: list of shared module names for manifest.
        province_code: Province code for manifest (e.g., "SK").
        province_folder: Province folder name on disk (e.g., "Saskatchewan").
        effective_date: The effective date string.
        lobs_list: list of dicts [{name, folder, is_hab}, ...] matching /iq-init
                   schema. If None, defaults to empty list.
        lob_vbproj_includes: dict mapping LOB folder name -> list of Compile
                             Include paths for that LOB's .vbproj.
        missing_lob_folders: set of LOB folder names for which no folder should
                             be created (simulates IQWiz not having run yet).
        missing_vbproj_lobs: set of LOB folder names for which folder exists
                             but no .vbproj is written.

    Returns:
        str: Absolute path to the manifest.yaml file.
    """
    carrier_root = tmpdir
    workstreams_root = os.path.join(carrier_root, ".iq-workstreams")
    workstream_dir = os.path.join(workstreams_root, "changes", "test-ticket")
    execution_dir = os.path.join(workstream_dir, "execution")

    if lobs_list is None:
        lobs_list = []
    if missing_lob_folders is None:
        missing_lob_folders = set()
    if missing_vbproj_lobs is None:
        missing_vbproj_lobs = set()

    # --- Write manifest.yaml ---
    manifest = {
        "codebase_root": carrier_root,
        "effective_date": effective_date,
        "province": province_code,
        "province_name": province_folder,
        "state": "EXECUTED",
    }
    if shared_modules is not None:
        manifest["shared_modules"] = shared_modules

    manifest_path = os.path.join(workstream_dir, "manifest.yaml")
    _write_yaml(manifest_path, manifest)

    # --- Write operations_log.yaml (empty -- not used by this validator) ---
    _write_yaml(
        os.path.join(execution_dir, "operations_log.yaml"),
        {"operations": []},
    )

    # --- Write file_hashes.yaml (empty -- not used by this validator) ---
    _write_yaml(
        os.path.join(execution_dir, "file_hashes.yaml"),
        {"files": {}},
    )

    # --- Write config.yaml (list-based lobs, matching /iq-init schema) ---
    config = {
        "provinces": {
            province_code: {
                "name": province_folder,
                "folder": province_folder,
                "lobs": lobs_list,
            }
        }
    }
    _write_yaml(os.path.join(workstreams_root, "config.yaml"), config)

    # --- Create LOB folders and .vbproj files ---
    if lob_vbproj_includes is None:
        lob_vbproj_includes = {}

    for lob_entry in lobs_list:
        lob_folder = lob_entry.get("folder", lob_entry.get("name", ""))

        if lob_folder in missing_lob_folders:
            continue  # Intentionally skip folder creation

        lob_dir = os.path.join(carrier_root, province_folder, lob_folder,
                               effective_date)
        os.makedirs(lob_dir, exist_ok=True)

        if lob_folder in missing_vbproj_lobs:
            continue  # Create folder but no .vbproj

        # Generate .vbproj with includes for this LOB
        includes = lob_vbproj_includes.get(lob_folder, [
            f"..\\..\\Code\\mod_Common_SKHab{effective_date}.vb",
            "CalcMain.vb",
        ])
        vbproj_xml = _make_vbproj(includes)
        vbproj_name = (f"Cssi.IntelliQuote.PORT{province_code}"
                       f"{lob_folder}{effective_date}.vbproj")
        _write_text(os.path.join(lob_dir, vbproj_name), vbproj_xml)

    # --- Ensure snapshots dir exists ---
    os.makedirs(os.path.join(execution_dir, "snapshots"), exist_ok=True)

    return manifest_path


# Convenience: standard 3-LOB hab list
HAB_3_LOBS = [
    {"name": "Home", "folder": "Home", "is_hab": True},
    {"name": "Condo", "folder": "Condo", "is_hab": True},
    {"name": "Tenant", "folder": "Tenant", "is_hab": True},
]


# ---------------------------------------------------------------------------
# Test 1: No shared modules -- Auto or single-LOB
# ---------------------------------------------------------------------------

def test_no_shared_modules():
    """Empty shared_modules in manifest. Should return passed=true with
    'No shared modules' message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=[],
            lobs_list=HAB_3_LOBS,
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 0
        assert "No shared modules" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 2: Single hab LOB -- cross-LOB check N/A
# ---------------------------------------------------------------------------

def test_single_hab_lob():
    """Only 1 hab LOB in config. Cross-LOB check is N/A, should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=[{"name": "Home", "folder": "Home", "is_hab": True}],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "WARNING"
        assert "1 hab LOB" in result.get("message", "")
        assert "N/A" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 3: Consistent refs -- all LOBs reference same mod_Common
# ---------------------------------------------------------------------------

def test_consistent_refs():
    """3 hab LOBs all reference the same mod_Common path. Should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        common_ref = "..\\..\\Code\\mod_Common_SKHab20260101.vb"

        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=HAB_3_LOBS,
            lob_vbproj_includes={
                "Home": [common_ref, "CalcMain.vb"],
                "Condo": [common_ref, "CalcMain.vb"],
                "Tenant": [common_ref, "CalcMain.vb"],
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert result["severity"] == "WARNING"
        assert len(result["findings"]) == 0
        assert "Cross-LOB consistency verified" in result.get("message", "")
        assert "3 hab LOBs" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 4: Inconsistent refs -- 1 LOB has old date
# ---------------------------------------------------------------------------

def test_inconsistent_refs():
    """3 hab LOBs: 2 reference new date, 1 has old date. Should produce
    an 'inconsistent_refs' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        new_ref = "..\\..\\Code\\mod_Common_SKHab20260101.vb"
        old_ref = "..\\..\\Code\\mod_Common_SKHab20250601.vb"

        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=HAB_3_LOBS,
            lob_vbproj_includes={
                "Home": [new_ref, "CalcMain.vb"],
                "Condo": [new_ref, "CalcMain.vb"],
                "Tenant": [old_ref, "CalcMain.vb"],  # OLD date!
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is False
        assert result["severity"] == "WARNING"

        inconsistent = [
            f for f in result["findings"]
            if f["issue"] == "inconsistent_refs"
        ]
        assert len(inconsistent) == 1
        assert "refs" in inconsistent[0]
        assert "Home" in inconsistent[0]["refs"]
        assert "Tenant" in inconsistent[0]["refs"]
        assert "Cross-LOB issues" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 5: Missing LOB folder
# ---------------------------------------------------------------------------

def test_missing_lob_folder():
    """LOB directory doesn't exist (IQWiz hasn't created it). Should
    produce a 'missing_lob_folder' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        common_ref = "..\\..\\Code\\mod_Common_SKHab20260101.vb"

        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=HAB_3_LOBS,
            lob_vbproj_includes={
                "Home": [common_ref, "CalcMain.vb"],
                "Condo": [common_ref, "CalcMain.vb"],
                "Tenant": [common_ref, "CalcMain.vb"],
            },
            missing_lob_folders={"Tenant"},
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        missing_folder = [
            f for f in result["findings"]
            if f["issue"] == "missing_lob_folder"
        ]
        assert len(missing_folder) == 1
        assert missing_folder[0]["lob"] == "Tenant"
        assert "No folder" in missing_folder[0]["message"]


# ---------------------------------------------------------------------------
# Test 6: Missing .vbproj in LOB folder
# ---------------------------------------------------------------------------

def test_missing_vbproj():
    """LOB directory exists but has no .vbproj file. Should produce a
    'missing_lob_ref' finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        common_ref = "..\\..\\Code\\mod_Common_SKHab20260101.vb"

        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=HAB_3_LOBS,
            lob_vbproj_includes={
                "Home": [common_ref, "CalcMain.vb"],
                "Condo": [common_ref, "CalcMain.vb"],
                "Tenant": [common_ref, "CalcMain.vb"],
            },
            missing_vbproj_lobs={"Condo"},
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        missing_ref = [
            f for f in result["findings"]
            if f["issue"] == "missing_lob_ref"
        ]
        assert len(missing_ref) == 1
        assert missing_ref[0]["lob"] == "Condo"
        assert "No .vbproj" in missing_ref[0]["message"]


# ---------------------------------------------------------------------------
# Test 7: No mod_Common in .vbproj
# ---------------------------------------------------------------------------

def test_no_mod_common_in_vbproj():
    """.vbproj exists but has no mod_Common Compile Include. Should produce
    a 'missing_lob_ref' finding for that LOB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        common_ref = "..\\..\\Code\\mod_Common_SKHab20260101.vb"

        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=HAB_3_LOBS,
            lob_vbproj_includes={
                "Home": [common_ref, "CalcMain.vb"],
                "Condo": ["CalcMain.vb"],  # No mod_Common!
                "Tenant": [common_ref, "CalcMain.vb"],
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        missing_ref = [
            f for f in result["findings"]
            if f["issue"] == "missing_lob_ref"
        ]
        assert len(missing_ref) == 1
        assert missing_ref[0]["lob"] == "Condo"
        assert "no mod_Common reference" in missing_ref[0]["message"]


# ---------------------------------------------------------------------------
# Test 8: Auto ticket -- no shared_modules key in manifest
# ---------------------------------------------------------------------------

def test_auto_ticket_no_shared_modules():
    """Auto ticket: manifest has no shared_modules key at all. Should
    return passed=true, no checks performed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=None,
            province_code="AB",
            province_folder="Alberta",
            lobs_list=[
                {"name": "Auto", "folder": "Auto", "is_hab": False},
            ],
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert "No shared modules" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 9: Multiple shared modules -- one consistent, one not
# ---------------------------------------------------------------------------

def test_multiple_shared_modules():
    """2 shared modules with 2 LOBs: 1 LOB inconsistent. Both shared module
    iterations find the same inconsistency."""
    with tempfile.TemporaryDirectory() as tmpdir:
        new_ref = "..\\..\\Code\\mod_Common_SKHab20260101.vb"
        old_ref = "..\\..\\Code\\mod_Common_SKHab20250601.vb"

        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=[
                "mod_Common_SKHab20260101.vb",
                "mod_Common_SKHab_Liability20260101.vb",
            ],
            lobs_list=[
                {"name": "Home", "folder": "Home", "is_hab": True},
                {"name": "Condo", "folder": "Condo", "is_hab": True},
            ],
            lob_vbproj_includes={
                "Home": [new_ref, "CalcMain.vb"],
                "Condo": [old_ref, "CalcMain.vb"],
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        inconsistent = [
            f for f in result["findings"]
            if f["issue"] == "inconsistent_refs"
        ]
        # At least 1 finding (could be 2 -- one per shared module)
        assert len(inconsistent) >= 1
        assert "Cross-LOB issues" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test 10: All LOBs missing -- no folders at all
# ---------------------------------------------------------------------------

def test_all_lobs_missing():
    """All hab LOB folders are missing. Should produce a 'missing_lob_folder'
    finding for each LOB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = _build_workstream(
            tmpdir,
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=HAB_3_LOBS,
            missing_lob_folders={"Home", "Condo", "Tenant"},
        )

        result = validate(manifest_path)
        assert result["passed"] is False

        missing_folder = [
            f for f in result["findings"]
            if f["issue"] == "missing_lob_folder"
        ]
        assert len(missing_folder) == 3

        lobs_found = {f["lob"] for f in missing_folder}
        assert lobs_found == {"Home", "Condo", "Tenant"}


# ---------------------------------------------------------------------------
# Test 11: Province code vs folder name (regression for Codex finding #2)
# ---------------------------------------------------------------------------

def test_province_code_vs_folder():
    """Manifest has province='SK' (code) but filesystem uses 'Saskatchewan'.
    Validator must resolve the folder name from config.provinces.SK.folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        common_ref = "..\\..\\Code\\mod_Common_SKHab20260101.vb"

        manifest_path = _build_workstream(
            tmpdir,
            province_code="SK",
            province_folder="Saskatchewan",
            shared_modules=["mod_Common_SKHab20260101.vb"],
            lobs_list=[
                {"name": "Home", "folder": "Home", "is_hab": True},
                {"name": "Condo", "folder": "Condo", "is_hab": True},
            ],
            lob_vbproj_includes={
                "Home": [common_ref, "CalcMain.vb"],
                "Condo": [common_ref, "CalcMain.vb"],
            },
        )

        result = validate(manifest_path)
        assert result["passed"] is True
        assert "Cross-LOB consistency verified" in result.get("message", "")
