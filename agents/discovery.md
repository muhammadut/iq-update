# Discovery Agent

## Purpose

Read the actual code for the target province + LOB. Trace the calculation flow
from CalcMain through shared code files. Identify every function relevant to the
change requests. Return a structured code understanding document that feeds ALL
downstream agents.

**Runs EVERY TIME — not confidence-gated.** Tokens are cheap. Always read the code.

## Pipeline Position

```
Intake → [DISCOVERY] → Analyzer → Decomposer → Planner
          ^^^^^^^^^^^
          YOU ARE HERE
```

**Input:**
- `parsed/change_requests.yaml` — province, LOBs, effective_date, target_folders
- `parsed/requests/cr-NNN.yaml` — individual change request files from Intake
- `.iq-workstreams/config.yaml` — carrier configuration
- Target .vbproj files, CalcMain.vb, Code/ files (on disk)

**Output:**
- `analysis/code_discovery.yaml` — structured code map for downstream agents

## Discovery Framework (Carrier-Agnostic)

The PATTERN of discovery is universal across TBW carriers — CalcMain calls shared
code calls functions calls rate tables. Specific names differ but the discovery
steps are the same. The agent discovers what exists rather than assuming.

---

### Step 1: FIND THE ENTRY POINT

Read CalcMain.vb from the target version folder (path from change_requests.yaml
target_folders). CalcMain is always a thin shell — a single main function that
calls out to shared code.

1.1. Pick the first target folder from `change_requests.yaml["target_folders"]`.
     Resolve the full path:

```python
import os

codebase_root = manifest["codebase_root"]
target_folder = change_requests["target_folders"][0]
calcmain_path = os.path.join(codebase_root, target_folder["path"], "CalcMain.vb")
```

1.2. Read CalcMain.vb. Find the main calculation function (typically named
     `TotPrem`, `CalcPrem`, or similar — look for the largest Public Function/Sub
     in the file).

1.3. Extract every function/sub call from the main function body, in order:

**File reading convention:** Throughout this agent, `lines` is a plain `list[str]`
(one string per line, 0-indexed). Read files with `encoding="utf-8-sig"` to handle
the UTF-8 BOM present in Visual Studio VB.NET files:

```python
def read_vb_file(filepath):
    """Read a VB.NET source file into a list of strings (0-indexed)."""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        return [line.rstrip("\n\r") for line in f.readlines()]
```

**Parameters `func_start` and `func_end` are 0-indexed** throughout this spec
(matching the `lines` list indexing). Convert from 1-indexed function index
values by subtracting 1.

```python
import re

# VB.NET keywords and built-in functions that match the call regex but
# are NOT user-defined function calls. Comprehensive list to prevent
# false positives in the calculation_flow output.
VB_KEYWORDS = {
    # Control flow
    "IF", "FOR", "WHILE", "SELECT", "CASE", "DO", "LOOP", "EACH",
    "USING", "WITH", "TRY", "CATCH", "THROW", "WHEN",
    # Declarations
    "DIM", "REDIM", "RETURN", "NEW", "ADDHANDLER", "REMOVEHANDLER",
    "RAISEEVENT", "GETTYPE",
    # Type conversions
    "CTYPE", "CINT", "CDBL", "CSTR", "CBOOL", "CBYTE", "CSHORT",
    "CLNG", "CSNG", "COBJ", "CCHAR", "CDATE", "CUINT", "CULNG",
    "CUSHORT", "CDEC", "DIRECTCAST", "TRYCAST", "TYPEOF",
    # String/Math built-ins
    "MATH", "STRING", "LEN", "MID", "LEFT", "RIGHT", "TRIM",
    "REPLACE", "SPLIT", "JOIN", "FORMAT", "INT", "FIX", "SGN",
    "ABS", "SQR", "EXP", "LOG", "ROUND",
    # Array/type checks
    "UBOUND", "LBOUND", "ISNOTHING", "ISNUMERIC", "ISDATE",
    "ISARRAY", "IIF",
    # Known codebase utility calls (not part of calculation flow)
    "ARRAY6", "ISITEMINARRAY",
    # Logical operators (can appear as function-like in some contexts)
    "NOT", "AND", "OR",
}

def extract_call_sequence(lines, func_start, func_end):
    """Extract ordered function calls from a CalcMain function body.

    Args:
        lines: list[str], 0-indexed file lines
        func_start: 0-indexed start line of function body
        func_end: 0-indexed end line (exclusive)

    Returns list of {name, line_number} dicts (line_number is 1-indexed).
    """
    calls = []
    # Pattern 1: FunctionName(args) or Call FunctionName(args) or var = FunctionName(args)
    call_pattern = re.compile(
        r'(?:Call\s+)?(?:\w+\s*=\s*)?(\w+)\s*\(',
        re.IGNORECASE
    )
    # Pattern 2: Call SubName (no parentheses — valid VB.NET for zero-arg Subs)
    bare_call_pattern = re.compile(
        r'^\s*Call\s+(\w+)\s*$',
        re.IGNORECASE
    )

    for i in range(func_start, func_end):
        line = lines[i].strip()
        if line.startswith("'"):  # Skip comments
            continue

        # Check bare Call syntax first
        bare_match = bare_call_pattern.match(line)
        if bare_match:
            name = bare_match.group(1)
            if name.upper() not in VB_KEYWORDS:
                calls.append({"name": name, "line_number": i + 1})
            continue

        for match in call_pattern.finditer(line):
            name = match.group(1)
            if name.upper() not in VB_KEYWORDS:
                calls.append({"name": name, "line_number": i + 1})
    return calls
```

This list IS the calculation flow. Every downstream operation should map to one
of these calls (or a sub-call of one of them).

---

### Step 2: READ THE SHARED CODE

Identify primary shared code files from the .vbproj `<Compile Include>` entries.
The .vbproj has already been parsed by /iq-init; re-read it here for the actual
file list.

2.1. Parse the target .vbproj using an XML parser (same approach as Analyzer Step 2):

```python
import xml.etree.ElementTree as ET

ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"
tree = ET.parse(vbproj_path)
root = tree.getroot()

code_files = []
for item_group in root.findall(f"{ns}ItemGroup"):
    for compile_elem in item_group.findall(f"{ns}Compile"):
        include = compile_elem.get("Include")
        if include:
            # Match Code/ files (both backslash and forward-slash separators)
            if "Code\\" in include or "Code/" in include:
                resolved = os.path.normpath(os.path.join(vbproj_dir, include))
                # Exclude cross-province shared files (3+ levels up, e.g., ..\..\..\Code\)
                # These are NEVER auto-modified (CLAUDE.md rule #5)
                relative_depth = include.count("..\\") + include.count("../")
                if relative_depth >= 3:
                    continue  # Cross-province shared — skip
                code_files.append(resolved)
```

```
CRITICAL — WINDOWS PATH SAFETY:
- NEVER use sed, awk, or bash string manipulation for file path operations
- ALWAYS use Python os.path.normpath() and os.path.join() for path resolution
- ALWAYS use Python xml.etree.ElementTree for .vbproj parsing (never regex)
- To check if a file exists, use: python -c "import os; print(os.path.exists('...'))"
```

2.2. Categorize shared code files by type:

```
FILE CATEGORIES
------------------------------------------------------------
Category              Pattern                                 Read?
Shared module (hab)   mod_Common_{PROV}Hab{DATE}.vb           YES — primary target
Algorithms (auto)     mod_Algorithms_{PROV}Auto{DATE}.vb      YES — if auto LOB
DisSur (auto)         mod_DisSur_{PROV}Auto{DATE}.vb          YES — if auto LOB
CalcOption dispatch   CalcOption_{PROV}{LOB}{DATE}.vb          YES — for endorsement requests
Option files          Option_*_{PROV}{LOB}{DATE}.vb            Read if request targets endorsements
Liability files       Liab_*_{PROV}{LOB}{DATE}.vb              Read if request targets liability options
Other                 (everything else)                         Skip unless request grep hits
```

2.3. Read the primary shared code file(s). For large files (>2,000 lines), build
     a function index first (scan for `Function|Sub` declarations), then read
     function bodies on demand in Step 3.

---

### Step 3: TRACE THE CALL CHAIN (Per Change Request)

For each change request from Intake, find where its target concept appears in the
calculation flow and read the actual function body.

3.1. For each change request, determine the search strategy:

```
CHANGE REQUEST MATCHING STRATEGIES
------------------------------------------------------------
Request Title Pattern           Search Strategy
"liability premiums"        Find functions with "Liability" in CalcMain flow
"deductible factor"         Find functions with "Deductible" or "DisSur" in flow
"base rates" (auto)         Find functions with "BasePrem" or "BaseRate" in mod_Algorithms
"base rates" (hab)          DAT file — flag as not-editable, still trace for context
"new endorsement"           Read CalcOption dispatch → which category code?
"sewer backup"              Find "SewerBackup" in flow
"identity fraud"            Find "IdentityFraud" in flow — likely an Option file
target_function_hint        Direct match on function name in flow
(unknown term)              Grep the shared code file(s) for the term
```

3.2. For each matched function, read its body and extract metadata:

```python
def analyze_function(lines, func_start, func_end, func_name):
    """Analyze a function body for downstream agent consumption.

    Returns structured metadata about the function.
    """
    body = lines[func_start:func_end]
    body_text = "\n".join(body)

    # Count Array6 occurrences — three categories per CLAUDE.md:
    # 1. Rate value: varRates = Array6(...) → MODIFY
    # 2. Test: IsItemInArray(x, Array6(...)) → NEVER MODIFY
    # 3. Enum collection: varCovTypes = Array6(TBWApplication.BasePremEnum...) → NEVER MODIFY

    # All Array6 assignments
    all_array6_assigns = re.findall(
        r'(\w+)\s*=\s*Array6\s*\(([^)]*)\)', body_text, re.IGNORECASE
    )
    array6_rate = 0
    array6_enum = 0
    for var_name, args in all_array6_assigns:
        # Enum/constant collections contain member access (letter.letter) in arguments
        # e.g., TBWApplication.BasePremEnum.bpeTPLBI
        # Decimal numbers (324.29) have digit.digit — NOT member access
        if re.search(r'[A-Za-z_]\.[A-Za-z_]', args):
            array6_enum += 1
        else:
            array6_rate += 1

    # Count Array6 test usages (NOT rate values)
    array6_test = len(re.findall(
        r'IsItemInArray\s*\([^,]+,\s*Array6\s*\(', body_text, re.IGNORECASE
    ))

    # Count Select Case blocks
    select_cases = len(re.findall(
        r'Select\s+Case\b', body_text, re.IGNORECASE
    ))
    # Count Case branches (excluding Case Else)
    case_branches = len(re.findall(
        r'^\s*Case\s+(?!Else\b)', body_text, re.MULTILINE | re.IGNORECASE
    ))

    # Identify sub-calls within the function
    sub_calls = extract_call_sequence(lines, func_start, func_end)

    # Detect return type from function signature
    # Handle multi-line declarations: scan from func_start until we find ") As Type"
    return_type = "Sub"  # Default for Sub procedures
    for k in range(func_start, min(func_start + 5, func_end)):
        return_match = re.search(r'\)\s*As\s+(\w+)', lines[k])
        if return_match:
            return_type = return_match.group(1)
            break

    return {
        "function_name": func_name,
        "line_start": func_start + 1,   # 1-indexed (output is always 1-indexed)
        "function_length": func_end - func_start,
        "returns": return_type,
        "array6_count": array6_rate,
        "array6_test_count": array6_test,
        "select_case_count": select_cases,
        "case_branches": case_branches,
        "calls": [c["name"] for c in sub_calls],
    }
```

3.3. Identify related functions — functions adjacent to the target that share the
     same business domain (e.g., `GetLiabilityExtensionPremiums` is related to
     `GetLiabilityBundlePremiums`):

```python
def find_related_functions(func_index, target_name, category_keywords):
    """Find functions related to the target by name similarity.

    category_keywords: words extracted from the target name
      e.g., "GetLiabilityBundlePremiums" → ["Liability"]
    """
    related = []
    for func in func_index:
        if func["name"] == target_name:
            continue
        for keyword in category_keywords:
            if keyword.lower() in func["name"].lower():
                related.append({
                    "name": func["name"],
                    "relationship": "same_category",
                    "line_start": func["line_start"],
                    "note": f"Also contains '{keyword}' — may need same change"
                })
                break
    return related
```

3.4. For endorsement/option change requests, read the CalcOption dispatch file and extract
     the routing table:

```python
def extract_dispatch_table(calcopt_lines):
    """Extract CalcOption category → function mapping.

    CalcOption uses Select Case blocks to route option codes to functions.
    Args: calcopt_lines — list[str], 0-indexed file lines.
    Returns dict: {category: [{code, function, line}]}
    """
    dispatch = {}
    current_category = None
    for i, line in enumerate(calcopt_lines):
        stripped = line.strip()

        # Reset category on new Select Case block (prevents carry-over)
        if re.match(r'Select\s+Case\b', stripped, re.IGNORECASE):
            current_category = None

        # Detect category sections — ONLY from comment-only lines
        # (prevents false triggers from inline mentions of "endorsement")
        if stripped.startswith("'"):
            upper = stripped.upper()
            if "ENDORSEMENT" in upper or "EXTENSION" in upper:
                current_category = "ENDORSEMENTEXTENSION"
            elif "LIABILITY" in upper:
                current_category = "LIABILITY"
            elif "PROPERTY" in upper:
                current_category = "PROPERTY"

        # Detect Case → function call mappings
        # Handles: Case 5000, Case "Identity Fraud", Case "Policy Limits"
        case_match = re.match(r'Case\s+(?:"([^"]+)"|(\d+))', stripped)
        if case_match and current_category:
            code = case_match.group(1) or case_match.group(2)  # String or numeric
            # Next non-blank, non-comment line is typically the function call
            for j in range(i + 1, min(i + 5, len(calcopt_lines))):
                next_line = calcopt_lines[j].strip()
                if not next_line or next_line.startswith("'"):
                    continue  # Skip blank lines and comments
                call_match = re.search(r'(\w+)\s*\(', next_line)
                if call_match:
                    if current_category not in dispatch:
                        dispatch[current_category] = []
                    dispatch[current_category].append({
                        "code": code if isinstance(code, str) and not code.isdigit() else int(code),
                        "function": call_match.group(1),
                        "line": i + 1,
                    })
                    break
    return dispatch
```

3.5. For Auto LOBs, identify vehicle-type-specific functions:

```python
def find_vehicle_type_functions(func_index):
    """Find per-vehicle-type base premium functions.

    Auto LOBs have GetBasePrem_{VehicleType} or GetBasePremium_{VehicleType}.
    Returns list of {vehicle_type, function_name, line_start}.
    """
    vehicle_funcs = []
    pattern = re.compile(
        r'GetBase(?:Prem(?:ium)?|Rate)_(\w+)',
        re.IGNORECASE
    )
    for func in func_index:
        match = pattern.match(func["name"])
        if match:
            vehicle_funcs.append({
                "vehicle_type": match.group(1),
                "function_name": func["name"],
                "line_start": func["line_start"],
            })
    return vehicle_funcs
```

---

### Step 4: BUILD THE CODE MAP

Assemble all findings into `analysis/code_discovery.yaml`.

4.1. Structure the output:

```yaml
# File: analysis/code_discovery.yaml
# Generated by Discovery Agent — DO NOT EDIT MANUALLY
discovery_timestamp: "{ISO 8601}"
province: "{province_code}"
lobs: ["{LOB1}", "{LOB2}", ...]
lob_category: "{hab|auto|mixed}"

entry_point:
  file: "{path to CalcMain.vb relative to codebase root}"
  main_function: "{name of main function}"
  total_steps: {number of function calls in main function}

calculation_flow:
  - step: 1
    function: "{function_name}"
    file: "{path to Code/ file}"
    purpose: "{brief purpose inferred from function name}"
    note: "{optional note — e.g., DAT file lookup}"
  # ... one entry per function call from CalcMain, in order

request_targets:
  cr-001:
    title: "{change request title from Intake}"
    resolved: true                     # false if function could not be found
    resolved_function: "{exact function name found in code}"
    resolved_file: "{exact path to Code/ file}"
    function_line_start: {1-indexed line number}
    function_length: {number of lines}
    returns: "{return type — Short, Double, Sub, etc.}"
    called_by: ["{function that calls this one}"]
    calls: ["{sub-functions called by this function}"]
    contains:
      array6_count: {count of rate-value Array6 usages}
      array6_test_count: {count of test Array6 usages — NOT rate values}
      select_case_count: {count of Select Case blocks}
      case_branches: {total Case branch count}
    related_functions:
      - name: "{related function name}"
        relationship: "same_category"
        line_start: {1-indexed line number}
        note: "{why this is related}"
    code_snippet: |
      ' First 30 lines of the function body
      ' (enough for downstream agents to understand structure)

  cr-002:
    # ... same structure per change request

  cr-003:    # Example of an unresolved request
    title: "{request title}"
    resolved: false
    resolved_function: null
    resolved_file: null
    search_attempted: "{what was searched for}"
    suggestion: "{grep suggestion for manual investigation}"

# Only present if endorsement/option change requests exist
dispatch_map:
  "{PROV}_{LOB}":
    categories:
      ENDORSEMENTEXTENSION:
        - code: {option_code}
          function: "{function_name}"
      # ...

# For downstream Change Engine — peer function templates
peer_functions:
  "{target_function_name}":
    - name: "{peer function name}"
      file: "{file path}"
      line_start: {line number}
      similarity: "{what makes this a good template}"

# Only present for Auto LOBs
vehicle_types:
  - vehicle_type: "{PPV|Motorcycle|Motorhome|...}"
    function_name: "{GetBasePrem_PPV}"
    line_start: {line number}
```

4.2. Write the file to `analysis/code_discovery.yaml` in the workstream directory.

4.3. Return a completion summary to the orchestrator:

```
Discovery complete:
  Entry point: {main_function} in {CalcMain path}
  Calculation flow: {N} functions traced
  Request targets resolved: {N}/{total requests}
    CR-001: {title} → {function} in {file}
    CR-002: {title} → {function} in {file}
  Unresolved requests: {list, if any — with grep suggestions}
  Related functions flagged: {N}
  Peer templates found: {N}
```

---

## Graceful Degradation

If any step fails, the agent continues with partial results:

| Failure | Impact | Recovery |
|---------|--------|----------|
| CalcMain.vb not found | No calculation_flow | Request targets still resolved via grep |
| .vbproj parse fails | No file categorization | Use config.yaml naming patterns |
| Function not found for CR | request_targets entry has `resolved: false` | Decomposer falls back to heuristics |
| CalcOption not readable | No dispatch_map | Decomposer uses pattern matching |
| Empty code_discovery.yaml | All downstream agents degrade gracefully | Each agent has existing fallback logic |
| Partial write / malformed YAML | Consumers' `load_yaml` fails | Consumers wrap in try/except, treat as absent |
| Agent process crashes mid-run | File may be absent or partial | Orchestrator checks file existence; if absent, sets status "skipped" |

**Critical rule:** NEVER block the pipeline. If Discovery produces partial results,
downstream agents use what they can and fall back to existing behavior for the rest.

---

## What Makes This Carrier-Agnostic

The agent does NOT hardcode function names. It follows a universal framework:

1. **Find CalcMain** → from target_folders path (works for any carrier)
2. **Extract call sequence** → regex for function calls (any TBW CalcMain)
3. **Resolve files** → .vbproj tells which Code/ file each function lives in
4. **Read and trace** → follow calls, read bodies (universal)
5. **Match change requests to functions** → by name patterns, grep, or CalcOption dispatch

Different carriers have different names but the same discovery process.
