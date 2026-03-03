"""
Validator: Cross-LOB Consistency
Severity: WARNING

Purpose:
    For multi-LOB hab tickets, verify that shared modules (like
    mod_Common_SKHab20260101.vb) are consistently referenced across all
    habitational LOBs in the province. For single-LOB or Auto tickets,
    this validator is N/A and returns passed=true immediately.

What it checks:
    1. All hab LOB .vbproj files in the province reference the SAME
       mod_Common shared module path (no inconsistent date references)
    2. Every hab LOB has a .vbproj that includes a mod_Common reference
       (no silently skipped LOBs)
    3. All hab LOB target date folders exist (IQWiz may not have created
       them all yet)

What it does NOT check:
    - Whether the shared module content is correct (other validators)
    - Whether the .vbproj XML is otherwise valid (IQWiz's responsibility)
    - Single-LOB tickets (this validator is N/A for single LOB)
    - Auto tickets (Auto does not share mod_Common)

Return schema:
    {
        "passed": bool,
        "severity": "WARNING",
        "findings": [
            {
                "shared_module": str,  # Module name
                "issue": str,          # "inconsistent_refs" | "missing_lob_ref"
                                       #   | "missing_lob_folder"
                "lob": str,            # (for missing_lob_ref / missing_lob_folder)
                "refs": dict,          # (for inconsistent_refs) {lob: ref_path}
                "message": str,
            }
        ],
        "message": str
    }
"""

from pathlib import Path

from _helpers import find_mod_common_ref, find_shared_module_ref, load_context, make_result


# ---------------------------------------------------------------------------
# Province Lookup
# ---------------------------------------------------------------------------

def _get_hab_lobs(config, province_code):
    """Find all hab LOBs for a province from config.yaml.

    Handles both config schemas:
      - List format (actual /iq-init output): lobs: [{name, folder, is_hab}, ...]
      - Dict format (legacy/test):            lobs: {name: {folder, is_hab}, ...}

    Args:
        config: Parsed config.yaml dict (or None).
        province_code: Province code string (e.g., "SK").

    Returns:
        List of dicts with keys "name" and "folder" for LOBs that have is_hab=True.
        Empty list if config is None or province not found.
    """
    if not config:
        return []

    province_config = config.get("provinces", {}).get(province_code, {})
    lobs_config = province_config.get("lobs", [])

    hab_lobs = []
    if isinstance(lobs_config, list):
        # Actual /iq-init schema: [{name, folder, is_hab, ...}, ...]
        for lob_entry in lobs_config:
            if isinstance(lob_entry, dict) and lob_entry.get("is_hab", False):
                hab_lobs.append({
                    "name": lob_entry.get("name", ""),
                    "folder": lob_entry.get("folder", lob_entry.get("name", "")),
                })
    elif isinstance(lobs_config, dict):
        # Legacy/test schema: {name: {folder, is_hab}, ...}
        for lob_name, lob_info in lobs_config.items():
            if isinstance(lob_info, dict) and lob_info.get("is_hab", False):
                hab_lobs.append({
                    "name": lob_name,
                    "folder": lob_info.get("folder", lob_name),
                })

    return hab_lobs


# ---------------------------------------------------------------------------
# Cross-LOB Reference Check
# ---------------------------------------------------------------------------

def _check_shared_module(shared_mod, hab_lobs, carrier_root, province_folder,
                         target_date, findings):
    """Check that all hab LOBs consistently reference a shared module.

    For each hab LOB, looks up the .vbproj in the target date folder and
    extracts the mod_Common reference. Flags inconsistencies and missing
    references.

    Args:
        shared_mod: Name of the shared module (for finding context).
        hab_lobs: List of dicts with "name" and "folder" keys.
        carrier_root: Path to the carrier codebase root.
        province_folder: Province folder name (e.g., "Saskatchewan", not "SK").
        target_date: Target effective date string (e.g., "20260101").
        findings: List to append finding dicts to (mutated in place).
    """
    refs_found = {}  # lob_name -> include_path

    for lob in hab_lobs:
        lob_name = lob["name"]
        lob_folder = lob["folder"]
        lob_dir = carrier_root / province_folder / lob_folder / target_date

        if not lob_dir.exists():
            findings.append({
                "shared_module": shared_mod,
                "issue": "missing_lob_folder",
                "lob": lob_name,
                "message": f"No folder {province_folder}/{lob_folder}/{target_date}",
            })
            continue

        vbproj_files = list(lob_dir.glob("*.vbproj"))
        if not vbproj_files:
            findings.append({
                "shared_module": shared_mod,
                "issue": "missing_lob_ref",
                "lob": lob_name,
                "message": f"No .vbproj found in {province_folder}/{lob_folder}/{target_date}",
            })
            continue

        for vbproj_path in vbproj_files:
            # Use specific module name for carrier-agnostic matching
            ref_path = find_shared_module_ref(vbproj_path, shared_mod)
            # Fall back to mod_Common match ONLY when the shared module
            # is actually a mod_Common variant (not for unrelated modules)
            if not ref_path and "mod_Common" in shared_mod:
                ref_path = find_mod_common_ref(vbproj_path)
            if ref_path:
                refs_found[lob_name] = ref_path

    # Check consistency: all refs should resolve to same path
    if refs_found:
        unique_refs = set(refs_found.values())
        if len(unique_refs) > 1:
            findings.append({
                "shared_module": shared_mod,
                "issue": "inconsistent_refs",
                "refs": dict(refs_found),
                "message": (
                    f"Inconsistent mod_Common refs across LOBs: "
                    f"{unique_refs}"
                ),
            })

    # Check for LOBs without refs (had .vbproj but no mod_Common include)
    lob_names = [lob["name"] for lob in hab_lobs]
    for lob_name in lob_names:
        if lob_name not in refs_found and not any(
            f.get("lob") == lob_name and f.get("shared_module") == shared_mod
            for f in findings
        ):
            findings.append({
                "shared_module": shared_mod,
                "issue": "missing_lob_ref",
                "lob": lob_name,
                "message": f"{lob_name} .vbproj has no mod_Common reference",
            })


# ---------------------------------------------------------------------------
# Message Builder
# ---------------------------------------------------------------------------

def _build_message(findings, hab_lobs):
    """Build a human-readable summary message.

    Args:
        findings: List of finding dicts.
        hab_lobs: List of hab LOB name strings.

    Returns:
        str summary message.
    """
    if not findings:
        lob_names = sorted(lob["name"] for lob in hab_lobs) if hab_lobs and isinstance(hab_lobs[0], dict) else sorted(hab_lobs)
        lob_list = ", ".join(lob_names)
        return (
            f"Cross-LOB consistency verified. {len(hab_lobs)} hab LOBs "
            f"({lob_list}) all reference same shared module(s)."
        )

    issue_counts = {}
    for f in findings:
        issue = f.get("issue", "unknown")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    return "Cross-LOB issues: " + ", ".join(
        f"{v} {k}" for k, v in issue_counts.items()
    )


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate(manifest_path: str) -> dict:
    """Validate cross-LOB consistency for multi-LOB hab tickets.

    Checks that shared modules (mod_Common_*Hab*) are consistently
    referenced across all hab LOBs in the province. For single-LOB or
    Auto tickets, returns passed=true immediately.

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate shared_modules, province, effective_date,
                       config.yaml, and .vbproj files on disk.

    Returns:
        dict with keys: passed (bool), severity (str), findings (list),
        message (str). See module docstring for full return schema.
    """
    try:
        ctx = load_context(manifest_path)
    except Exception as e:
        return make_result(
            severity="WARNING",
            passed=False,
            findings=[{
                "shared_module": "",
                "issue": "context_load_error",
                "lob": "",
                "message": f"Validator crashed during context loading: {e}",
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    manifest = ctx["manifest"]
    config = ctx["config"]
    carrier_root = ctx["carrier_root"]

    # Get shared modules from manifest.
    # Normalize: manifest may have strings ["mod_Common.vb"] or dicts
    # [{"file": "Province/Code/mod_Common.vb", "shared_by": [...]}]
    raw_modules = manifest.get("shared_modules", [])
    if not raw_modules:
        return make_result(
            "WARNING", True, [],
            "No shared modules in this workflow",
        )

    shared_modules = []
    for mod in raw_modules:
        if isinstance(mod, str):
            shared_modules.append(mod)
        elif isinstance(mod, dict):
            shared_modules.append(mod.get("file", mod.get("name", str(mod))))
        else:
            shared_modules.append(str(mod))

    province_code = manifest.get("province", "")
    target_date = manifest.get("effective_date", "")

    # Resolve province folder name from config (filesystem name, not code)
    # e.g., "SK" -> "Saskatchewan"
    province_folder = manifest.get("province_name", province_code)
    if config:
        prov_config = config.get("provinces", {}).get(province_code, {})
        province_folder = prov_config.get("folder", province_folder)

    # Find all hab LOBs for this province from config
    hab_lobs = _get_hab_lobs(config, province_code)

    if len(hab_lobs) < 2:
        return make_result(
            "WARNING", True, [],
            f"Only {len(hab_lobs)} hab LOB(s) -- cross-LOB check N/A",
        )

    findings = []

    # For each shared module, check all hab LOBs
    for shared_mod in shared_modules:
        try:
            _check_shared_module(
                shared_mod, hab_lobs, carrier_root, province_folder,
                target_date, findings,
            )
        except Exception as e:
            findings.append({
                "shared_module": shared_mod,
                "issue": "check_error",
                "lob": "",
                "message": f"Error checking shared module {shared_mod}: {e}",
            })

    message = _build_message(findings, hab_lobs)

    return make_result(
        severity="WARNING",
        passed=len(findings) == 0,
        findings=findings,
        message=message,
    )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print(
            "Usage: python validate_cross_lob.py <manifest_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
