"""
Validator: .vbproj File Integrity
Severity: BLOCKER

Purpose:
    Verify that all <Compile Include> paths in modified .vbproj files
    resolve to files that actually exist on disk. Catches broken references
    introduced by the file-copy worker or manual edits before the developer
    attempts to build the DLL.

What it checks:
    1. File existence -- every <Compile Include> path resolves to a real file
       relative to the .vbproj directory (the standard MSBuild resolution).
    2. No duplicate entries -- no two <Compile Include> elements point to
       the same normalized file path.

What it does NOT check:
    - Whether the .vbproj XML is valid MSBuild (IQWiz's responsibility)
    - Whether the file contents are correct (other validators handle that)
    - .vbproj files not tracked in file_hashes.yaml (only checks modified ones)

Return schema:
    {
        "passed": bool,
        "severity": "BLOCKER",
        "findings": [
            {
                "file": str,          # .vbproj path
                "issue": str,         # "missing_include" | "duplicate_include"
                                      # | "vbproj_parse_error"
                "include": str,       # the <Compile Include> value
                "resolved_path": str, # absolute path that was checked (for missing)
                "message": str,       # human-readable
            }
        ]
    }
"""

from pathlib import Path

from _helpers import (
    _find_compile_elements,
    check_path_containment,
    load_context,
    make_result,
)

import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# Check 1: All Compile Include paths resolve to existing files
# ---------------------------------------------------------------------------

def _check_include_paths(vbproj_path, carrier_root, findings):
    """Verify every <Compile Include> path in a .vbproj resolves to a file.

    MSBuild resolves Include paths relative to the directory containing
    the .vbproj file. This function mirrors that resolution.

    Args:
        vbproj_path: Path to the .vbproj file.
        carrier_root: Path to the carrier codebase root.
        findings: List to append finding dicts to (mutated in place).

    Returns:
        list of normalized include paths (for duplicate detection).
    """
    vbproj_path = Path(vbproj_path)
    vbproj_dir = vbproj_path.parent

    try:
        tree = ET.parse(vbproj_path)
    except ET.ParseError as e:
        findings.append({
            "file": str(vbproj_path.relative_to(carrier_root)),
            "issue": "vbproj_parse_error",
            "include": "",
            "message": f"Failed to parse .vbproj XML: {e}",
        })
        return []

    compile_elements = _find_compile_elements(tree)
    normalized_paths = []

    for el in compile_elements:
        include = el.get("Include", "")
        if not include:
            continue

        # MSBuild resolves paths relative to .vbproj directory
        # Convert backslashes to forward slashes for Path resolution
        resolved = vbproj_dir / include.replace("\\", "/")

        try:
            resolved = resolved.resolve()
        except (OSError, ValueError):
            # Path resolution failed (e.g., invalid characters)
            pass

        normalized_paths.append(str(resolved).lower())

        if not resolved.exists():
            # Build relative path for readable output
            try:
                rel = vbproj_path.relative_to(carrier_root)
            except ValueError:
                rel = vbproj_path
            findings.append({
                "file": str(rel),
                "issue": "missing_include",
                "include": include,
                "resolved_path": str(resolved),
                "message": (
                    f"Compile Include path does not exist: {include} "
                    f"(resolved to {resolved})"
                ),
            })

    return normalized_paths


# ---------------------------------------------------------------------------
# Check 2: No duplicate Compile Include entries
# ---------------------------------------------------------------------------

def _check_duplicates(vbproj_path, carrier_root, normalized_paths, findings):
    """Check for duplicate <Compile Include> entries pointing to same file.

    Args:
        vbproj_path: Path to the .vbproj file.
        carrier_root: Path to the carrier codebase root.
        normalized_paths: list of lowercase resolved paths from Check 1.
        findings: List to append finding dicts to (mutated in place).
    """
    seen = {}
    for path in normalized_paths:
        if path in seen:
            seen[path] += 1
        else:
            seen[path] = 1

    for path, count in seen.items():
        if count > 1:
            try:
                rel = vbproj_path.relative_to(carrier_root)
            except ValueError:
                rel = vbproj_path
            # Extract just the filename for readability
            basename = Path(path).name
            findings.append({
                "file": str(rel),
                "issue": "duplicate_include",
                "include": basename,
                "message": (
                    f"Duplicate Compile Include entry: {basename} "
                    f"appears {count} times in {rel}"
                ),
            })


# ---------------------------------------------------------------------------
# Message Builder
# ---------------------------------------------------------------------------

def _build_message(findings, vbproj_count):
    """Build a human-readable summary message.

    Args:
        findings: List of finding dicts.
        vbproj_count: Number of .vbproj files checked.

    Returns:
        str summary message.
    """
    if not findings:
        return (
            f"All .vbproj references valid: "
            f"{vbproj_count} project file(s) checked, "
            f"all Compile Include paths resolve to existing files"
        )

    issue_counts = {}
    for f in findings:
        issue = f.get("issue", "unknown")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    parts = [f"{issue}: {count}" for issue, count in sorted(issue_counts.items())]
    return (
        f"Vbproj integrity check FAILED ({len(findings)} findings): "
        + ", ".join(parts)
    )


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def validate(manifest_path: str) -> dict:
    """Validate .vbproj file integrity for all modified project files.

    Checks that every <Compile Include> path in .vbproj files tracked by
    file_hashes.yaml resolves to an existing file on disk, and that no
    duplicate entries exist.

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.

    Returns:
        dict with keys: passed (bool), severity (str), findings (list).
        See module docstring for full return schema.
    """
    try:
        ctx = load_context(manifest_path)
    except Exception as e:
        return make_result(
            severity="BLOCKER",
            passed=False,
            findings=[{
                "file": str(manifest_path),
                "issue": "context_load_error",
                "message": f"Validator crashed during context loading: {e}",
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    carrier_root = ctx["carrier_root"]
    file_hashes = ctx["file_hashes"]

    findings = []
    vbproj_count = 0

    # Find all .vbproj files in file_hashes
    files = file_hashes.get("files", {})
    for filepath in files:
        if not filepath.endswith(".vbproj"):
            continue

        # Path containment check — reject paths that escape carrier root
        try:
            vbproj_path = check_path_containment(filepath, carrier_root)
        except ValueError:
            findings.append({
                "file": filepath,
                "issue": "path_traversal",
                "include": "",
                "message": f"Path escapes carrier root: {filepath}",
            })
            continue

        if not vbproj_path.exists():
            findings.append({
                "file": filepath,
                "issue": "missing_vbproj",
                "include": "",
                "message": f"Project file not found on disk: {filepath}",
            })
            continue

        vbproj_count += 1

        try:
            normalized = _check_include_paths(vbproj_path, carrier_root, findings)
            _check_duplicates(vbproj_path, carrier_root, normalized, findings)
        except Exception as e:
            findings.append({
                "file": filepath,
                "issue": "check_error",
                "include": "",
                "message": f"Vbproj check crashed: {e}",
            })

    message = _build_message(findings, vbproj_count)

    return make_result(
        severity="BLOCKER",
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
            "Usage: python validate_vbproj.py <manifest_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
