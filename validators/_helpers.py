"""
Shared helper functions for all IQ Rate Update Plugin validators.

This module provides common utilities used by 2+ validators:
- YAML loading and context resolution
- Result construction
- File inventory building from operations log
- VB.NET-aware parsing (string-aware character walking, depth-aware
  comma splitting, Array6 extraction, comment detection)
- SHA-256 hash computation

Dependencies: PyYAML (yaml), Python 3.8+ standard library.
"""

import ast
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


# MSBuild namespace used in .vbproj files
MSBUILD_NS = {"msbuild": "http://schemas.microsoft.com/developer/msbuild/2003"}


# ---------------------------------------------------------------------------
# YAML Loading
# ---------------------------------------------------------------------------

def load_yaml(path):
    """Load a YAML file and return parsed contents.

    Args:
        path: str or Path to the YAML file.

    Returns:
        Parsed YAML content (dict, list, or scalar).

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_context(manifest_path):
    """Load manifest.yaml and derive common paths used by all validators.

    Args:
        manifest_path: Absolute path (str or Path) to the workstream manifest.yaml.

    Returns:
        dict with keys:
            manifest       - parsed manifest.yaml dict
            workstream_dir - Path to the workstream directory (parent of manifest.yaml)
            carrier_root   - Path to the carrier codebase root
            workstreams_root - Path to .iq-workstreams/
            ops_log        - parsed operations_log.yaml dict
            file_hashes    - parsed file_hashes.yaml dict
            snapshots_dir  - Path to execution/snapshots/
            config         - parsed config.yaml dict (or None if file missing)
    """
    manifest_path = Path(manifest_path)
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest.yaml is not a dict (got {type(manifest).__name__})")

    workstream_dir = manifest_path.parent

    # Resolve carrier_root: prefer manifest["codebase_root"], fall back to
    # deriving from workstream path (.iq-workstreams/changes/{name}/manifest.yaml
    # → carrier root is 3 levels up from workstream_dir).
    if "codebase_root" in manifest:
        carrier_root = Path(manifest["codebase_root"])
    else:
        # Derive: workstream_dir = {carrier_root}/.iq-workstreams/changes/{name}
        carrier_root = workstream_dir.parent.parent.parent

    workstreams_root = carrier_root / ".iq-workstreams"

    # If config.yaml exists, try root_path from config as a final fallback
    config_path = workstreams_root / "config.yaml"
    config = load_yaml(config_path) if config_path.exists() else None

    if "codebase_root" not in manifest and config and "root_path" in config:
        carrier_root = Path(config["root_path"])
        workstreams_root = carrier_root / ".iq-workstreams"

    # Operations log
    ops_log_path = workstream_dir / "execution" / "operations_log.yaml"
    ops_log = load_yaml(ops_log_path) if ops_log_path.exists() else {"operations": []}

    # File hashes
    file_hashes_path = workstream_dir / "execution" / "file_hashes.yaml"
    file_hashes = load_yaml(file_hashes_path) if file_hashes_path.exists() else {"files": {}}

    # Snapshots directory
    snapshots_dir = workstream_dir / "execution" / "snapshots"

    # Schema warnings (non-fatal — validators still run on older manifests)
    schema_warnings = validate_manifest_schema(manifest)

    return {
        "manifest": manifest,
        "workstream_dir": workstream_dir,
        "carrier_root": carrier_root,
        "workstreams_root": workstreams_root,
        "ops_log": ops_log,
        "file_hashes": file_hashes,
        "snapshots_dir": snapshots_dir,
        "config": config,
        "schema_warnings": schema_warnings,
    }


# ---------------------------------------------------------------------------
# Manifest Schema Validation
# ---------------------------------------------------------------------------

# Current manifest version. Increment when the schema changes.
MANIFEST_VERSION = "2.0"

# Required top-level keys for a valid manifest.yaml.
MANIFEST_REQUIRED_KEYS = {
    "manifest_version", "workflow_id", "state", "province", "lobs",
    "effective_date", "created_at", "updated_at",
}


def validate_manifest_schema(manifest):
    """Validate manifest.yaml has the expected version and required keys.

    Args:
        manifest: Parsed manifest.yaml dict.

    Returns:
        list of warning strings. Empty if the manifest is valid.
    """
    warnings = []

    if not isinstance(manifest, dict):
        return [f"manifest.yaml is not a dict (got {type(manifest).__name__})"]

    # Version check
    version = manifest.get("manifest_version")
    if version is None:
        warnings.append(
            "manifest.yaml missing 'manifest_version' — may be from an older "
            "plugin version. Expected version: " + MANIFEST_VERSION
        )
    elif version != MANIFEST_VERSION:
        warnings.append(
            f"manifest_version mismatch: found '{version}', "
            f"expected '{MANIFEST_VERSION}'. Schema may have changed."
        )

    # Required keys
    missing = MANIFEST_REQUIRED_KEYS - set(manifest.keys())
    if missing:
        warnings.append(
            "manifest.yaml missing required keys: " + ", ".join(sorted(missing))
        )

    return warnings


# ---------------------------------------------------------------------------
# Result Construction
# ---------------------------------------------------------------------------

def make_result(severity, passed, findings, message=""):
    """Construct a standard validator return dict.

    Args:
        severity: "BLOCKER" or "WARNING".
        passed: bool indicating whether the validator passed.
        findings: list of finding dicts.
        message: optional human-readable summary string.

    Returns:
        dict matching the validator return schema:
        {
            "passed": bool,
            "severity": str,
            "findings": list,
            "message": str,   # optional, for reviewer agent
        }
    """
    result = {
        "passed": passed,
        "severity": severity,
        "findings": findings,
    }
    if message:
        result["message"] = message
    return result


# ---------------------------------------------------------------------------
# File Inventory Builder
# ---------------------------------------------------------------------------

def build_inventory(ops_log):
    """Categorize files from the operations log by change type.

    Uses the change_type field to classify each operation entry:
    - "value_editing"        -> value_files
    - "structure_insertion"  -> structure_files
    - "file_creation"        -> structure_files + new_files
    - "flow_modification"    -> structure_files

    Args:
        ops_log: Parsed operations_log.yaml dict with "operations" key.

    Returns:
        dict with keys:
            value_files      - set of relative file paths for value editing
            structure_files  - set of relative file paths for structure changes
            new_files        - set of files created (change_type == "file_creation")
            all_files        - union of all files
    """
    inventory = {
        "value_files": set(),
        "structure_files": set(),
        "new_files": set(),
        "all_files": set(),
    }
    for entry in ops_log.get("operations", []):
        filepath = entry.get("file", "")
        if not filepath:
            continue
        inventory["all_files"].add(filepath)

        change_type = entry.get("change_type", "")
        if change_type == "value_editing":
            inventory["value_files"].add(filepath)
        elif change_type in ("structure_insertion", "file_creation",
                             "flow_modification"):
            inventory["structure_files"].add(filepath)
            if change_type == "file_creation":
                inventory["new_files"].add(filepath)
        elif change_type:
            inventory.setdefault("unknown_types", set()).add(change_type)

    return inventory


# ---------------------------------------------------------------------------
# VB.NET Parsing: String-Aware Character Walking
# ---------------------------------------------------------------------------

def extract_balanced_parens(line, start_after_open):
    """Extract content between an opening paren and its matching close paren.

    Walks from start_after_open (the position immediately after the opening
    parenthesis) and tracks depth, respecting VB.NET string literals.

    VB.NET escapes literal quotes by doubling (""). The toggle logic handles
    this implicitly: first " sets in_string=False, second " immediately sets
    in_string=True again.

    Args:
        line: The full source line string.
        start_after_open: Index right after the opening parenthesis.

    Returns:
        The content string between the parens, or None if no matching
        close paren is found (unbalanced).
    """
    depth = 1
    i = start_after_open
    in_string = False

    while i < len(line):
        ch = line[i]
        if in_string:
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return line[start_after_open:i]
        i += 1

    return None  # Unmatched -- no closing paren found


def parens_balanced(line):
    """Check if all parentheses in a VB.NET source line are balanced.

    String-aware: ignores parentheses inside "..." string literals.
    Handles VB.NET escaped quotes ("") implicitly via toggle logic.

    Args:
        line: A VB.NET source line string.

    Returns:
        True if all parentheses are balanced, False otherwise.
    """
    depth = 0
    in_string = False
    for ch in line:
        if in_string:
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def split_top_level_commas(s):
    """Split a string by commas at parenthesis depth 0 only.

    Uses the same depth-aware, string-aware logic as count_array6_args.
    Handles nested parens, string literals, and arithmetic expressions.

    Examples:
        "Func(a, b), 30 + 10, -5" -> ["Func(a, b)", "30 + 10", "-5"]
        "512.59, 28.73, 463.03"   -> ["512.59", "28.73", "463.03"]
        ""                         -> []

    Args:
        s: The string to split (typically the content inside Array6(...)).

    Returns:
        List of argument strings, each stripped of leading/trailing whitespace.
    """
    if not s or not s.strip():
        return []

    args = []
    current = []
    depth = 0
    in_string = False

    for ch in s:
        if ch == '"' and not in_string:
            in_string = True
            current.append(ch)
        elif ch == '"' and in_string:
            in_string = False  # VB.NET "" (escaped quote) toggles twice, net no change
            current.append(ch)
        elif in_string:
            current.append(ch)
        elif ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)

    if current:
        args.append(''.join(current).strip())

    return args


# ---------------------------------------------------------------------------
# VB.NET Parsing: Array6 Utilities
# ---------------------------------------------------------------------------

def count_array6_args(line):
    """Count arguments in an Array6() call using depth-aware comma splitting.

    Handles:
        - Nested parens:  Array6(Func(a, b), c)  -> 2 args, not 3
        - Strings:        Array6("a, b", c)      -> 2 args, not 3
        - Expressions:    Array6(30 + 10, 40)    -> 2 args
        - Single arg:     Array6(4)              -> 1 arg
        - Negative vals:  Array6(-5, -10)        -> 2 args

    Args:
        line: A VB.NET source line string.

    Returns:
        int: Argument count. 0 if no Array6 call found. -1 if unmatched parens.
    """
    match = re.search(r'Array6\s*\(', line)
    if not match:
        return 0

    start = match.end()  # Position right after "Array6("

    # Extract content up to the MATCHING close paren
    content = extract_balanced_parens(line, start)
    if content is None:
        return -1  # Unmatched parens

    content = content.strip()
    if not content:
        return 0

    # Count top-level commas + 1
    args = split_top_level_commas(content)
    return len(args)


def is_array6_test_usage(line):
    """Detect dual-use: Array6 inside another function call is a test, not a rate.

    Rate usage (modifiable, return False):
        varRates = Array6(...)
        premiumArray = Array6(...)
        liabilityPremiumArray = Array6(...)
        varRates$ = Array6(...)

    Test usage (NEVER modify, return True):
        IsItemInArray(x, Array6(...))
        UBound(Array6(...))

    Args:
        line: A VB.NET source line string.

    Returns:
        True if the Array6 call is a test/lookup usage (should be SKIPPED).
        False if it is a rate assignment usage (should be CHECKED).
        False if no Array6 found.
    """
    if not line or "Array6" not in line:
        return False

    # Rate pattern: identifier (with optional type suffix $) = Array6(...)
    if re.search(r'\w+\$?\s*=\s*Array6\s*\(', line):
        return False  # It IS a rate -- do NOT skip

    # Everything else (function call argument, standalone) is a test/lookup
    return True



# ---------------------------------------------------------------------------
# VB.NET Parsing: Comment Detection
# ---------------------------------------------------------------------------

def is_full_line_comment(line):
    """Check if a line is a full-line VB.NET comment.

    Args:
        line: A VB.NET source line string.

    Returns:
        True if the stripped line starts with a single-quote (').
    """
    return line.strip().startswith("'")


def extract_code_portion(line):
    """Extract the code portion of a VB.NET line (before the first unquoted ').

    Inline comments in VB.NET start with a single-quote outside of string
    literals. This function returns everything before that comment marker.

    Args:
        line: A VB.NET source line string.

    Returns:
        The code portion of the line (everything before the inline comment).
    """
    in_string = False
    for i, ch in enumerate(line):
        if in_string:
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "'":
            return line[:i]
    return line


def is_inline_comment_only_change(before, after):
    """Check if the only difference between two lines is in the inline comment.

    If the code portions (before the first unquoted ') are identical,
    the change is to the comment only -- acceptable.

    Args:
        before: The original line.
        after: The modified line.

    Returns:
        True if only the inline comment changed; False otherwise.
    """
    before_code = extract_code_portion(before)
    after_code = extract_code_portion(after)
    return before_code.rstrip() == after_code.rstrip()


# ---------------------------------------------------------------------------
# Path Containment Check
# ---------------------------------------------------------------------------

def check_path_containment(filepath, root):
    """Verify that filepath resolves within root directory.

    Prevents path traversal attacks where a malformed manifest could cause
    reads outside the carrier root (e.g., "../../etc/passwd").

    On Windows, normalizes case before comparison to avoid false failures
    from case-insensitive filesystems with differing path case.

    Args:
        filepath: Relative file path (str or Path) to check.
        root: Root directory (str or Path) that filepath must stay within.

    Returns:
        Path: The resolved absolute path.

    Raises:
        ValueError: If the resolved path escapes the root directory.
    """
    resolved = (Path(root) / filepath).resolve()
    root_resolved = Path(root).resolve()
    # On Windows, normalize case for case-insensitive filesystem comparison
    if os.name == "nt":
        resolved_cmp = Path(os.path.normcase(str(resolved)))
        root_cmp = Path(os.path.normcase(str(root_resolved)))
        resolved_cmp.relative_to(root_cmp)  # raises ValueError if outside
    else:
        resolved.relative_to(root_resolved)  # raises ValueError if outside
    return resolved


# ---------------------------------------------------------------------------
# Hash Computation
# ---------------------------------------------------------------------------

def compute_file_hash(filepath):
    """Compute SHA-256 hash of a file in the standard format.

    Reads file in binary mode, processes in 8192-byte chunks.

    Args:
        filepath: str or Path to the file.

    Returns:
        str in format "sha256:{hexdigest}" (lowercase hex).

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"



# ---------------------------------------------------------------------------
# Snapshot Path Resolution
# ---------------------------------------------------------------------------

def resolve_snapshot_path(filepath, snapshots_dir):
    """Resolve the snapshot file path for a given source file.

    Uses path-encoded naming (separators replaced with __) to prevent
    basename collisions across directories.

    Example: "Saskatchewan/Code/mod_Common.vb"
        -> "Saskatchewan__Code__mod_Common.vb.snapshot"

    Args:
        filepath: Relative file path (e.g., "Saskatchewan/Code/mod_Common.vb").
        snapshots_dir: Path to the execution/snapshots/ directory.

    Returns:
        Path to the snapshot file if found, or None if no snapshot exists.
    """
    if not snapshots_dir or not snapshots_dir.exists():
        return None

    # Path-encoded snapshot name (separators replaced with __)
    safe_name = filepath.replace("/", "__").replace("\\", "__")
    safe_path = snapshots_dir / f"{safe_name}.snapshot"
    if safe_path.exists():
        return safe_path

    return None


def load_snapshot_lines(filepath, snapshots_dir):
    """Load snapshot file lines for a given source file.

    Uses resolve_snapshot_path() for collision-safe resolution.

    Args:
        filepath: Relative file path.
        snapshots_dir: Path to the execution/snapshots/ directory.

    Returns:
        List of line strings from the snapshot, or None if not found.
    """
    snapshot_path = resolve_snapshot_path(filepath, snapshots_dir)
    if snapshot_path is None:
        return None

    try:
        return snapshot_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Operation ID Parsing
# ---------------------------------------------------------------------------

def extract_cr_from_intent(intent_id):
    """Extract CR ID from an intent ID.

    Format:
        "intent-001" -> "cr-001"
        "intent-012" -> "cr-012"

    Args:
        intent_id: Intent ID string (e.g., "intent-001").

    Returns:
        CR ID string (e.g., "cr-001"), or None if pattern doesn't match.
    """
    match = re.match(r'intent-(\d+)(?:-\d+)?', intent_id)
    if match:
        return f"cr-{match.group(1)}"
    return None


# ---------------------------------------------------------------------------
# .vbproj XML Parsing
# ---------------------------------------------------------------------------

def _find_compile_elements(tree):
    """Find all <Compile Include="..."> elements in a .vbproj XML tree.

    Tries both namespaced (MSBuild) and non-namespaced lookups because some
    .vbproj files may lack the XML namespace declaration.

    Args:
        tree: An ElementTree object parsed from a .vbproj file.

    Returns:
        List of Element objects with an 'Include' attribute.
    """
    root = tree.getroot()

    # Try namespaced first (the common case)
    elements = root.findall(".//msbuild:Compile", MSBUILD_NS)

    # Fallback: non-namespaced
    if not elements:
        elements = root.findall(".//{http://schemas.microsoft.com/developer/msbuild/2003}Compile")

    # Final fallback: truly no namespace
    if not elements:
        elements = root.findall(".//Compile")

    return [el for el in elements if el.get("Include")]


def check_vbproj_refs(vbproj_path, target_date):
    """Check that all Code/ file references in a .vbproj point to target_date.

    Parses the .vbproj as XML (MSBuild namespace), finds all <Compile Include>
    elements. For each Include path that references a Code/, SHARDCLASS/, or
    SharedClass/ file, extracts the date portion using regex and verifies it
    matches the expected target_date.

    Args:
        vbproj_path: Path to the .vbproj file (str or Path).
        target_date: Expected date string (e.g., "20260101").

    Returns:
        list of finding dicts for any old-date references found.
        Empty list if all references are correct.
    """
    vbproj_path = Path(vbproj_path)
    findings = []

    try:
        tree = ET.parse(vbproj_path)
    except ET.ParseError as e:
        findings.append({
            "file": str(vbproj_path),
            "issue": "vbproj_parse_error",
            "message": f"Failed to parse .vbproj XML: {e}",
        })
        return findings

    compile_elements = _find_compile_elements(tree)
    # Patterns that indicate a dated Code/ or shared-class file
    code_markers = ("\\Code\\", "/Code/", "\\SHARDCLASS\\", "/SHARDCLASS/",
                    "\\SharedClass\\", "/SharedClass/")

    for el in compile_elements:
        include_path = el.get("Include", "")

        # Only check paths that reference Code/ or SHARDCLASS/ or SharedClass/
        if not any(marker.lower() in include_path.lower() for marker in code_markers):
            continue

        # Extract the 8-digit date from the filename portion
        date_match = re.search(r'(\d{8})\.vb', include_path, re.IGNORECASE)
        if not date_match:
            continue  # File has no date in its name -- not a dated copy

        found_date = date_match.group(1)
        if found_date != target_date:
            findings.append({
                "file": str(vbproj_path),
                "issue": "old_date_ref",
                "include": include_path,
                "found_date": found_date,
                "expected_date": target_date,
            })

    return findings


def find_mod_common_ref(vbproj_path):
    """Find the mod_Common reference in a .vbproj file.

    Parses the .vbproj as XML (MSBuild namespace) and searches for the first
    <Compile Include="..."> element whose Include path contains "mod_Common".

    Args:
        vbproj_path: Path to the .vbproj file (str or Path).

    Returns:
        The Include path string containing "mod_Common", or None if not found.
    """
    vbproj_path = Path(vbproj_path)

    try:
        tree = ET.parse(vbproj_path)
    except ET.ParseError:
        return None

    compile_elements = _find_compile_elements(tree)

    for el in compile_elements:
        include_path = el.get("Include", "")
        if "mod_Common".lower() in include_path.lower():
            return include_path

    return None


def find_shared_module_ref(vbproj_path, module_name):
    """Find a reference to a specific shared module in a .vbproj file.

    More general than find_mod_common_ref(): searches for any module by name,
    not just "mod_Common". Works for carriers with different shared module
    naming conventions.

    Args:
        vbproj_path: Path to the .vbproj file (str or Path).
        module_name: Module filename to search for (e.g., "mod_Common_SKHab20260101.vb"
                     or just "mod_Common" for a partial match).

    Returns:
        The Include path string containing module_name, or None if not found.
    """
    vbproj_path = Path(vbproj_path)

    try:
        tree = ET.parse(vbproj_path)
    except ET.ParseError:
        return None

    compile_elements = _find_compile_elements(tree)

    # Extract the base name for matching (strip path components from module_name)
    # e.g., "New Brunswick/Code/mod_Common_NBHab20260101.vb" -> "mod_Common_NBHab20260101.vb"
    search_basename = Path(module_name).name

    for el in compile_elements:
        include_path = el.get("Include", "")
        # Match by basename — the Include path may have relative path prefix
        include_basename = Path(include_path.replace("\\", "/")).name
        if include_basename.lower() == search_basename.lower():
            return include_path

    # Fallback: partial match (for cases where module_name is a substring like "mod_Common")
    for el in compile_elements:
        include_path = el.get("Include", "")
        if module_name.lower() in include_path.lower():
            return include_path

    return None


# ---------------------------------------------------------------------------
# Numeric Evaluation & Value Extraction
# ---------------------------------------------------------------------------

def _eval_node(node):
    """Recursively evaluate an AST node without ever calling eval().

    Supports: numeric constants, binary ops (+, -, *, /), unary ops (+, -).
    """
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Non-numeric constant: {node.value!r}")
        return node.value
    # ast.Num for older Python versions (removed in 3.14)
    if type(node).__name__ == "Num":
        return node.n  # noqa: attr-defined — ast.Num.n exists pre-3.14
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        ops = {
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b,
        }
        op_func = ops.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
        return op_func(left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
    raise ValueError(f"Unsupported node: {type(node).__name__}")


def safe_eval_arithmetic(expr):
    """Safely evaluate simple arithmetic expressions (numbers, +, -, *, /).

    Uses a recursive AST evaluator — never calls eval(). Only allows numeric
    literals and basic arithmetic operators. Rejects function calls, attribute
    access, imports, etc.

    Args:
        expr: String expression to evaluate (e.g., "30 + 10", "100 * 1.05").

    Returns:
        The numeric result (int or float).

    Raises:
        ValueError: If the expression is too long, has invalid syntax,
                    or contains unsafe AST nodes.
    """
    if len(expr) > 200:
        raise ValueError(f"Expression too long ({len(expr)} chars)")

    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError:
        raise ValueError(f"Invalid expression: {expr}")

    return _eval_node(tree)


def try_eval_numeric(expr):
    """Try to evaluate a string as a numeric value.

    Handles: "50", "-0.22", "30 + 10", "512.59"
    Returns None for variables, function calls, or complex expressions.

    Uses safe_eval_arithmetic() instead of eval() for security.

    Args:
        expr: String expression to evaluate.

    Returns:
        float or None.
    """
    if expr is None:
        return None
    expr = expr.strip()
    if not expr:
        return None

    try:
        return float(expr)
    except (ValueError, TypeError):
        pass

    # Check if expr contains only safe arithmetic characters
    # Allow digits, whitespace, decimal point, +, -, *, /, and parentheses
    if re.fullmatch(r'[\d\s\.\+\-\*/\(\)]+', expr):
        try:
            result = safe_eval_arithmetic(expr)
            return float(result)
        except (ValueError, Exception):
            return None

    return None


def parse_array6_values(line):
    """Extract numeric values from an Array6() call.

    Uses split_top_level_commas to handle nested parens, then tries
    to evaluate each argument as a number.

    Args:
        line: VB.NET source line.

    Returns:
        List of (float or None) for each arg, or None if no Array6 found.
    """
    if not line or "Array6" not in line:
        return None

    match = re.search(r'Array6\s*\(', line)
    if not match:
        return None

    content = extract_balanced_parens(line, match.end())
    if content is None:
        return None

    args = split_top_level_commas(content)
    if not args:
        return None

    return [try_eval_numeric(arg) for arg in args]


def compute_pct_change(before_val, after_val):
    """Compute percentage change between two values.

    Args:
        before_val: Original numeric value.
        after_val: New numeric value.

    Returns:
        float percentage change (rounded to 2 decimal places),
        or None if before_val is 0.
    """
    if before_val == 0:
        return None
    return round(abs(after_val - before_val) / abs(before_val) * 100, 2)


def extract_numeric_value(line):
    """Extract a numeric value from a factor table line.

    Handles patterns like:
        dblDedDiscount = -0.20
        Case 5000 : dblDedDiscount = -0.22
        Const ACCIDENTBASE = 200

    Args:
        line: VB.NET source line.

    Returns:
        float or None.
    """
    if not line:
        return None

    # Strip inline comment first
    code = extract_code_portion(line)
    code = code.strip()

    if not code:
        return None

    # Find the last '=' and try to parse what follows
    eq_pos = code.rfind('=')
    if eq_pos < 0:
        return None

    rhs = code[eq_pos + 1:].strip()
    if not rhs:
        return None

    return try_eval_numeric(rhs)
