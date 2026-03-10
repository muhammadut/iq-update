# Agent: Decomposer

## Purpose

Transform change requests into executable intents by matching ticket requirements
to analyzed code. Each intent says "change this function to do X" with a capability
tag and all the context the Change Engine needs to make the edit.

**Core philosophy: ONE intent = ONE change to ONE function in ONE file.**
When a single change request spans multiple functions or files, the Decomposer
produces multiple intents. The Decomposer does NOT classify changes into predefined
types -- it reads the code (via Analyzer output), reads the ticket requirement
(via Intake output), and reasons about what needs to change.

## Pipeline Position

```
[INPUT] --> Intake --> Discovery --> Analyzer --> DECOMPOSER --> Planner --> [GATE 1]
                                                 ^^^^^^^^^^
```

- **Upstream:**
  - Intake agent (provides `parsed/change_requests.yaml` + `parsed/requests/cr-NNN.yaml`)
  - Discovery agent (provides `analysis/code_discovery.yaml` -- function-to-file mappings)
  - Analyzer agent (provides `analysis/analyzer_output/` -- function bodies, FUBs, line numbers, branch trees, hazards)
- **Downstream:** Planner agent (consumes `analysis/intent_graph.yaml`)

**Key difference from old pipeline:** The Decomposer runs AFTER the Analyzer. It
receives verified code understanding -- exact function bodies, line numbers, branch
trees, hazards. It does not guess about code; it reads what the Analyzer already found.

## Input Schema

```yaml
# Reads: parsed/change_requests.yaml (from Intake -- full schema in intake.md)
# Reads: parsed/requests/cr-NNN.yaml (one per change request -- from Intake)
# Reads: analysis/code_discovery.yaml (from Discovery -- CalcMain flow, function->file mappings)
# Reads: analysis/analyzer_output/ (from Analyzer -- function analysis, FUBs, line numbers)
# Reads: target folder .vbproj files (to identify Code/ file references)
# Reads: .iq-workstreams/config.yaml (for naming patterns, hab LOB lists, hab flags)
```

### change_requests.yaml Fields Used by Decomposer

```yaml
carrier: "Portage Mutual"
province: "SK"
province_name: "Saskatchewan"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
lob_category: "hab"                    # "hab" | "auto" | "mixed"
effective_date: "20260101"
ticket_ref: "DevOps 24778"            # Optional
request_count: 4

target_folders:
  - path: "Saskatchewan/Home/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  # ... one per LOB

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

requests:
  - id: "cr-001"
    title: "..."
    # ... (abbreviated; full CR in parsed/requests/)
```

### Individual CR Fields (parsed/requests/cr-NNN.yaml)

The Decomposer reads these fields from each change request file:

```yaml
id: "cr-NNN"
title: "Increase liability premiums by 3%"
description: "All liability bundle premiums should increase by 3% across all territories"
source_text: "Increase all liability premiums by 3%"
source_location: "comment by John Smith on 2026-01-15"  # Where in the ticket this came from
evidence_refs: ["ticket description item 2", "att-03"]   # References to screenshots/attachments

extracted:                              # Concrete values from the ticket text
  percentage: 3.0                       # Optional
  factor: 1.03                          # Optional
  method: "multiply"                    # "multiply" | "explicit" | null
  scope: "all_territories"              # "all_territories" | "specific_territories" | null
  lob_scope: "all"                      # "all" | "specific"
  target_lobs: null                     # Only if lob_scope = "specific"
  case_value: null                      # For factor table changes
  old_value: null                       # For explicit replacements
  new_value: null                       # For explicit replacements
  target_function_hint: null            # Developer-provided function name
  target_file_hint: null                # Developer-provided file name

domain_hints:
  keyword_matches: ["liability", "premium", "increase"]
  glossary_match: "GetLiabilityBundlePremiums"
  glossary_confidence: "high"
  involves_rates: true
  involves_percentages: true
  involves_new_code: false
  rounding_hint: null

dat_file_warning: false
ambiguity_flag: false
complexity_estimate: "SIMPLE"
```

### analysis/code_discovery.yaml (from Discovery)

```yaml
# Key fields used by Decomposer:
calculation_flow:                       # Ordered call graph from CalcMain
  - function: "TotPrem"
    file: "CalcMain.vb"
    calls: [...]

cr_targets:                             # Discovery's best guess: CR -> function mapping
  cr-001:
    resolved_function: "GetLiabilityBundlePremiums"
    resolved_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    related_functions:
      - name: "GetLiabilityExtensionPremiums"
        note: "Same liability category -- may need same change"
    contains:
      array6_count: 14
      select_case_count: 3

dispatch_map: {}                        # CalcOption routing tables
peer_functions: {}                      # Functions similar to targets
```

### analysis/analyzer_output/ (from Analyzer)

The Analyzer produces per-CR analysis files. The Decomposer reads these
to get verified code understanding:

```yaml
# Example: analysis/analyzer_output/cr-001-analysis.yaml
cr: "cr-001"
title: "Increase liability premiums by 3%"
analyzed_at: "2026-03-03T10:00:00"
functions_analyzed:
  - function: "GetLiabilityBundlePremiums"
    file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    function_line_start: 3850
    function_line_end: 4100
    return_type: "Double"
    fub:
      branch_tree:
        - type: "Select Case"
          variable: "policyCategory"
          cases:
            - label: "Case 1"
              line: 3870
      hazards:
        - "mixed_rounding"
        - "dual_use_array6"
      adjacent_context:
        above: "End Function ' GetLiabilityExtensionWatercraftPremiums"
        below: "Public Function GetLiabilityExtensionPremiums..."
      nearby_functions:
        - name: "GetLiabilityExtensionPremiums"
          line_start: 4110
          line_end: 4300
    target_lines:
      - line: 3870
        content: "                Case 1 : varRates = Array6(512.59, 28.73, 463.03)"
        context: "Territory 1 Home"
        rounding: "none"
        value_count: 3
  - line: 3880
    content: "                Case 2 : varRates = Array6(612, 32, 553)"
    context: "Territory 2 Home"
    rounding: "banker"                  # Integer values
    value_count: 3
  # ... more target lines

skipped_lines:
  - line: 4055
    content: "                If IsItemInArray(..., Array6(...))"
    reason: "Array6 in IsItemInArray -- membership test, not rate value"

# File copy information
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
```

## Output Schema

### analysis/intent_graph.yaml

This is the single output artifact. All intents live in one file.

```yaml
# File: analysis/intent_graph.yaml

workflow_id: "20260101-SK-Hab-rate-update"
decomposer_version: "2.0"
decomposed_at: "2026-03-03T10:00:00"
total_intents: 4
total_out_of_scope: 1

# CRs marked out of scope (tracked but no intents generated)
out_of_scope:
  - cr: "cr-003"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"

intents:
  - id: "intent-001"
    cr: "cr-001"                        # Links back to change request
    title: "Increase liability bundle premiums by 3%"
    description: "Multiply all rate-value Array6 arguments by 1.03"
    capability: "value_editing"         # value_editing | structure_insertion | file_creation | flow_modification
    strategy_hint: "array6-multiply"    # Optional -- reference to old pattern docs
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityBundlePremiums"
    depends_on: []
    confidence: 0.95
    open_questions: []

    # Evidence traceability (carried from CR)
    source_text: "Increase all liability premiums by 3%"    # From CR source_text
    source_location: "ticket description item 4"            # From CR source_location
    evidence_refs: ["ticket description item 4"]            # References to evidence
    assumptions: []                                          # Assumptions made during decomposition
    done_when: "All Array6 rate values multiplied by 1.03"  # Verification criteria

    # Analyzer-enriched fields (passed through from analyzer_output)
    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    needs_copy: true
    file_hash: "sha256:a1b2c3d4..."
    function_line_start: 3850
    function_line_end: 4100
    target_lines:
      - line: 3870
        content: "                Case 1 : varRates = Array6(512.59, 28.73, 463.03)"
        context: "Territory 1 Home"
        rounding: "none"
        value_count: 3
      # ... more target lines
    parameters:
      factor: 1.03
      scope: "all_territories"
      rounding: "auto"
    peer_examples: []

  - id: "intent-002"
    cr: "cr-002"
    title: "Change $5000 deductible factor from -0.20 to -0.22"
    description: "Modify the $5000 deductible discount factor in SetDisSur_Deductible"
    capability: "value_editing"
    strategy_hint: "factor-table"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    depends_on: []
    confidence: 0.95
    open_questions: []

    # Evidence traceability (carried from CR)
    source_text: "Change $5000 deductible factor from -0.20 to -0.22"
    source_location: "ticket description item 2"
    evidence_refs: ["ticket description item 2"]
    assumptions: []
    done_when: "Case 5000 dblDedDiscount changed from -0.2 to -0.22"

    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    needs_copy: true
    file_hash: "sha256:a1b2c3d4..."
    function_line_start: 2100
    function_line_end: 2250
    target_lines:
      - line: 2202
        content: "                Case 5000 : dblDedDiscount = -0.2"
        context: "Case 5000 deductible"
        rounding: null
        value_count: 1
    parameters:
      old_value: -0.20
      new_value: -0.22
    peer_examples: []

# Partial approval constraints: which CRs are coupled by inter-CR dependencies.
partial_approval_constraints: []
# Non-empty example:
#   - cr: "cr-003"
#     requires_cr: "cr-001"
#     reason: "intent-003 depends on intent-001"
#     blocking_intents: ["intent-003"]
#     required_intents: ["intent-001"]

# Topological order for execution (respects depends_on)
execution_order:
  - "intent-001"
  - "intent-002"
  - "intent-003"
  - "intent-004"
```

---

## EXECUTION STEPS

These are the step-by-step instructions for transforming change requests into
executable intents. Follow them in order.

### Prerequisites

Before starting, confirm the following exist and are readable:

1. The workflow directory at `.iq-workstreams/changes/{workstream-name}/`
2. The `parsed/change_requests.yaml` inside that directory (from Intake)
3. The `parsed/requests/` directory with individual CR files (from Intake)
4. The `analysis/code_discovery.yaml` (from Discovery -- optional but expected)
5. The `analysis/analyzer_output/` directory with function analysis files (from Analyzer)
6. The `.iq-workstreams/config.yaml` (for carrier info, province codes, hab flags)
7. The target folder .vbproj files listed in change_requests.yaml

If `parsed/change_requests.yaml` or `analysis/analyzer_output/` are missing, STOP:
```
[Decomposer] Cannot proceed -- missing required file: {path}
             Were Intake and Analyzer completed?
             Check manifest.yaml for intake.status and analyzer.status.
```

If `analysis/code_discovery.yaml` is missing, log a warning and proceed -- Discovery
output is used for function resolution but the Decomposer can match CRs to Analyzer
output using domain hints and keyword matching as a fallback.

### Step 1: Load Context

**Action:** Read all upstream outputs and build the working context.

1.1. Read `parsed/change_requests.yaml`. Extract:
   - `province`, `province_name`, `lobs`, `lob_category`, `effective_date`
   - `target_folders` (list of path + vbproj entries)
   - `shared_modules` (list of shared files and which LOBs use them)
   - `requests` (summary list -- IDs and titles)

1.2. Read `config.yaml` from `.iq-workstreams/`. Extract:
   - `provinces.{province_code}.lobs[]` with `is_hab` flags
   - `provinces.{province_code}.hab_code` (e.g., "SKHab")
   - `naming` patterns for file classification

1.3. Read each individual CR file from `parsed/requests/cr-NNN.yaml`. Store in memory.

1.4. If `request_count` is 0, report and complete:
```
[Decomposer] No change requests to process. Intake produced 0 items.
             Nothing to do -- workflow complete at Decomposer stage.
```
Write a minimal intent_graph.yaml (total_intents: 0) and exit.

### Step 2: Load Discovery Output

**Action:** Load the Discovery agent's code map for function-to-file resolution.

2.1. Read `analysis/code_discovery.yaml`:

```python
import os

workstream_dir = f".iq-workstreams/changes/{workstream_name}"
discovery_path = os.path.join(workstream_dir, "analysis/code_discovery.yaml")
discovery = {}

if file_exists(discovery_path):
    try:
        discovery = load_yaml(discovery_path)
    except Exception:
        discovery = {}  # Malformed YAML -- treat as absent

    # Build lookup: CR ID -> resolved target
    discovery_targets = {}
    for cr_id, target in discovery.get("request_targets", {}).items():
        if target.get("resolved_function"):
            discovery_targets[cr_id] = target

    discovery_dispatch = discovery.get("dispatch_map", {})
    discovery_peers = discovery.get("peer_functions", {})
else:
    discovery_targets = {}
    discovery_dispatch = {}
    discovery_peers = {}
```

### Step 3: Load Analyzer Output

**Action:** Load the Analyzer's function-level analysis for every analyzed function.

3.1. Scan `analysis/analyzer_output/` for all `.yaml` files. Build an index:

```python
analyzer_index = {}  # function_name -> analyzer data dict

analyzer_dir = os.path.join(workstream_dir, "analysis/analyzer_output")
if os.path.isdir(analyzer_dir):
    for filename in os.listdir(analyzer_dir):
        if filename.endswith(".yaml"):
            try:
                data = load_yaml(os.path.join(analyzer_dir, filename))
                # Analyzer output is per-CR with functions_analyzed[] array
                for func_entry in data.get("functions_analyzed", []):
                    func_name = func_entry.get("function")
                    if func_name:
                        analyzer_index[func_name] = func_entry
            except Exception:
                pass  # Skip malformed files
```

3.2. Also build secondary indexes for efficient lookup:

```python
# file -> [function_names] index (for matching CRs to files)
file_to_functions = {}
for func_name, data in analyzer_index.items():
    src_file = data.get("source_file", data.get("file", ""))
    file_to_functions.setdefault(src_file, []).append(func_name)

# keyword -> [function_names] index (for matching CRs by domain hints)
keyword_to_functions = {}
for func_name, data in analyzer_index.items():
    # Index by lowercase function name segments
    parts = re.split(r'(?=[A-Z])|_', func_name)
    for part in parts:
        if part and len(part) > 2:
            keyword_to_functions.setdefault(part.lower(), []).append(func_name)
```

### Step 4: Parse .vbproj Files to Build the File Reference Map

**Action:** Read each target folder's .vbproj to know which Code/ files each project
compiles. This logic is IDENTICAL to what the old decomposer did -- kept because
it is essential for shared module deduplication and file classification.

4.1. For each entry in `target_folders`, read the .vbproj as XML.

**CRITICAL: Use an XML parser, NOT regex.** The .vbproj is MSBuild XML.

4.2. Extract all `<Compile Include="...">` elements. Normalize paths:

```python
import os
import xml.etree.ElementTree as ET

def parse_vbproj(vbproj_path):
    """Extract Compile Include paths from a .vbproj file."""
    tree = ET.parse(vbproj_path)
    root = tree.getroot()
    ns = {"ms": "http://schemas.microsoft.com/developer/msbuild/2003"}
    includes = []
    for compile_elem in root.findall(".//ms:Compile", ns):
        include = compile_elem.get("Include")
        if include:
            vbproj_dir = os.path.dirname(os.path.abspath(vbproj_path))
            resolved = os.path.normpath(os.path.join(vbproj_dir, include))
            includes.append(resolved)
    return includes
```

4.3. Build the **File Reference Map** -- for each Code/ file, record which .vbproj(s)
compile it.

4.4. Classify each referenced file using the File Classification Rules (Step 5).

4.5. Cross-reference with `shared_modules` from change_requests.yaml. Flag mismatches.

### Step 5: Classify Files

**Action:** Assign a file_type to every Code/ file referenced by target .vbproj files.

#### File Classification Rules (priority order -- first match wins)

```
RULE 1: Cross-Province Shared (NEVER MODIFY)
  Match: file path resolves to the codebase-root Code/ directory
         (NOT the province-level Code/ directory)
  Result: file_type = "cross_province_shared"
  Action: NEVER generate intents for these files.

RULE 2: Shared Hab Module
  Match: filename matches mod_Common_{Prov}Hab{Date}.vb
         OR modFloatersAndScheduledArticles_{PROV}HAB{Date}.vb
         OR file is listed in change_requests.yaml shared_modules[]
  Result: file_type = "shared_module"
  Verify: Should appear in 2+ .vbproj File Reference Maps

RULE 3: Shared Auto Module
  Match: filename matches mod_Algorithms_{Prov}Auto{Date}.vb
         OR mod_DisSur_{Prov}Auto{Date}.vb
  Result: file_type = "shared_module" (if compiled by multiple projects)
          OR file_type = "lob_specific" (if only one project compiles it)

RULE 4: LOB-Specific CalcOption File
  Match: filename matches CalcOption_{PROV}{LOB}{Date}.vb
  Result: file_type = "lob_specific"

RULE 5: Cross-LOB Option/Liab File
  Match: Option_{Name}_{Prov}{LOB}{Date}.vb or Liab_{Name}_{Prov}{LOB}{Date}.vb
         AND 2+ LOB projects compile it
  Result: file_type = "cross_lob"

RULE 6: Single-LOB Option/Liab File
  Match: same patterns as Rule 5 but only 1 .vbproj compiles it
  Result: file_type = "lob_specific"

RULE 7: Local File (in version folder)
  Match: file is inside the version folder itself (not Code/ or SHARDCLASS/)
  Result: file_type = "local"

RULE 8: SHARDCLASS File
  Match: file is in SHARDCLASS/ (or SharedClass/ for Nova Scotia)
  Result: file_type = "shardclass"
```

### Step 6: Filter Out-of-Scope CRs

**Action:** Separate CRs that cannot be processed.

6.1. For each CR, check `dat_file_warning`:
   - If `dat_file_warning: true` --> mark as **OUT_OF_SCOPE**
   - If `dat_file_warning: false` --> proceed

6.2. Record out-of-scope CRs:

```yaml
out_of_scope:
  - cr: "cr-003"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"
```

6.3. Report:
```
[Decomposer] Filtered {N} out-of-scope CR(s):
             CR-003: "[DAT FILE] Increase hab dwelling base rates by 5%"
             Reason: Hab dwelling base rates are in external DAT files.

             Proceeding with {M} in-scope CRs.
```

6.4. If ALL CRs are out of scope, write minimal intent_graph.yaml and exit.

### Step 7: Match Each CR to Analyzed Functions

**Action:** For each in-scope CR, find the analyzed function(s) it targets. This is
the core of the new Decomposer -- it matches ticket requirements to code understanding.

The matching uses three data sources in priority order:

1. **Discovery targets** (highest confidence -- Discovery traced CalcMain and resolved)
2. **Analyzer index** (verified function analysis with exact lines and FUBs)
3. **Domain hint matching** (keyword matching from Intake's glossary/domain hints)

#### 7.1 Match Algorithm

For each in-scope CR:

```python
def match_cr_to_functions(cr, discovery_targets, analyzer_index, keyword_to_functions):
    """Find all analyzed functions that a change request targets.

    Returns a list of (function_name, analyzer_data, match_source) tuples.
    """
    matches = []
    cr_id = cr["id"]

    # Priority 1: Discovery resolved this CR to a specific function
    if cr_id in discovery_targets:
        target = discovery_targets[cr_id]
        func_name = target["resolved_function"]
        if func_name in analyzer_index:
            matches.append((func_name, analyzer_index[func_name], "discovery"))

        # Also check related functions from Discovery
        for related in target.get("related_functions", []):
            rname = related["name"]
            if rname in analyzer_index:
                matches.append((rname, analyzer_index[rname], "discovery_related"))

    # Priority 2: Developer provided a function hint in the CR
    if not matches and cr.get("extracted", {}).get("target_function_hint"):
        hint = cr["extracted"]["target_function_hint"]
        # Exact match
        if hint in analyzer_index:
            matches.append((hint, analyzer_index[hint], "developer_hint"))
        else:
            # Wildcard match (e.g., "SetDisSur_*")
            for func_name in analyzer_index:
                if fnmatch.fnmatch(func_name, hint):
                    matches.append((func_name, analyzer_index[func_name], "developer_hint_wildcard"))

    # Priority 3: Glossary match from Intake domain hints
    if not matches and cr.get("domain_hints", {}).get("glossary_match"):
        gm = cr["domain_hints"]["glossary_match"]
        if gm in analyzer_index:
            matches.append((gm, analyzer_index[gm], "glossary"))

    # Priority 4: Keyword matching against Analyzer function names
    if not matches:
        keywords = cr.get("domain_hints", {}).get("keyword_matches", [])
        candidates = set()
        for kw in keywords:
            for func_name in keyword_to_functions.get(kw.lower(), []):
                candidates.add(func_name)
        # Score candidates by number of matching keywords
        scored = []
        for func_name in candidates:
            func_lower = func_name.lower()
            score = sum(1 for kw in keywords if kw.lower() in func_lower)
            scored.append((score, func_name))
        scored.sort(reverse=True)
        for score, func_name in scored:
            if score >= 1:
                matches.append((func_name, analyzer_index[func_name], "keyword"))

    return matches
```

#### 7.2 Handle Unresolved CRs

If a CR matches ZERO analyzed functions:

```
[Decomposer] CR-{NNN}: "{title}"
             Could not find a matching analyzed function. Discovery and Analyzer
             did not identify a target for this change.

             Possible reasons:
             1. The function was not in the CalcMain call chain
             2. The function name is non-standard
             3. The change targets a file not yet analyzed

             Which function should this CR target?
             (Or type "skip" to mark as needs_review)
```

If the developer names a function, check if it exists in the Analyzer output.
If not, create the intent with `confidence: 0.3` and `open_questions` noting
the function was not found by the Analyzer.

#### 7.3 Handle Multi-Function CRs

If a CR matches MULTIPLE analyzed functions (e.g., "increase all liability premiums"
matches GetLiabilityBundlePremiums AND GetLiabilityExtensionPremiums):

- Create ONE intent per matched function
- All intents reference the same `cr` ID
- The developer can reject individual intents at Gate 1

If the match source is "keyword" (lowest confidence) and there are many matches,
present them to the developer:

```
[Decomposer] CR-{NNN} "{title}" may target multiple functions:

  1. GetLiabilityBundlePremiums (mod_Common_SKHab, line 3850)
     14 Array6 lines across 12 Case branches
  2. GetLiabilityExtensionPremiums (mod_Common_SKHab, line 4110)
     8 Array6 lines across 8 Case branches
  3. GetLiabilityExtensionWatercraftPremiums (mod_Common_SKHab, line 4310)
     6 Array6 lines across 6 Case branches

  Which function(s) should this change apply to?
  (Enter numbers, e.g., "1, 2" or "all")
```

### Step 8: Form Intents

**Action:** For each CR-to-function match, create an intent with all the fields
the Change Engine needs.

#### 8.1 Determine Capability

The `capability` field describes WHAT KIND of change this is, not a specific
template. Determine it from the CR's extracted values and the Analyzer's findings:

```python
def determine_capability(cr, analyzer_data):
    """Determine the capability tag for an intent.

    Capabilities:
    - value_editing: Changing existing values in existing code
    - structure_insertion: Adding new code blocks to existing files
    - file_creation: Creating new files
    - flow_modification: Changing control flow (if/else, loops, case routing)
    """
    extracted = cr.get("extracted", {})
    domain = cr.get("domain_hints", {})

    # Value changes: has old->new values, or a multiplication factor
    if extracted.get("factor") or extracted.get("old_value") is not None:
        return "value_editing"

    # New code: domain hints say new code needed, or keywords suggest it
    if domain.get("involves_new_code"):
        # Does the analyzer data show this function exists yet?
        if analyzer_data is None:
            return "file_creation"
        else:
            return "structure_insertion"

    # Explicit method signals
    if extracted.get("method") == "multiply":
        return "value_editing"
    if extracted.get("method") == "explicit":
        return "value_editing"

    # Default: if the function exists and we're changing it, it's value_editing
    # If the function doesn't exist, it's structure_insertion
    if analyzer_data:
        return "value_editing"
    else:
        return "structure_insertion"
```

#### 8.2 Determine Strategy Hint (Optional)

The `strategy_hint` is an optional reference to old pattern documentation. It tells
the Change Engine "we've seen something like this before, here's how it was done."
This is INFORMATIONAL, not prescriptive.

```python
def determine_strategy_hint(cr, capability, analyzer_data):
    """Optional: suggest a strategy from the old pattern docs.

    Returns a string (strategy name) or None.
    """
    extracted = cr.get("extracted", {})

    if capability == "value_editing":
        # Check if the target has Array6 lines
        if analyzer_data and any("Array6" in str(t.get("content", ""))
                                  for t in analyzer_data.get("target_lines", [])):
            if extracted.get("factor"):
                return "array6-multiply"
            elif extracted.get("old_value") is not None:
                return "factor-table"
        # Const value changes
        if analyzer_data and analyzer_data.get("fub", {}).get("hazards"):
            if "const_rate_values" in analyzer_data["fub"]["hazards"]:
                return "constant-value"
        # Generic factor table
        if extracted.get("case_value") is not None:
            return "factor-table"
        return None

    if capability == "structure_insertion":
        kw = cr.get("domain_hints", {}).get("keyword_matches", [])
        if "endorsement" in kw:
            return "new-endorsement"
        if "coverage" in kw:
            return "case-block-insertion"
        if "eligibility" in kw or "validation" in kw:
            return "validation-function"
        return None

    return None
```

#### 8.3 Build the Intent

For each (cr, function_name, analyzer_data, match_source) tuple:

```python
def build_intent(intent_id, cr, func_name, analyzer_data, match_source,
                 file_classification, effective_date):
    """Build a single intent from a CR + analyzed function.

    All Analyzer fields are passed through directly -- the Decomposer does NOT
    recompute line numbers or FUBs.
    """
    extracted = cr.get("extracted", {})

    capability = determine_capability(cr, analyzer_data)
    strategy_hint = determine_strategy_hint(cr, capability, analyzer_data)

    # Determine confidence based on match source and data completeness
    confidence = compute_confidence(match_source, analyzer_data, cr)

    # Build the intent
    intent = {
        "id": intent_id,
        "cr": cr["id"],
        "title": cr["title"],
        "description": cr.get("description", cr["title"]),
        "capability": capability,
        "strategy_hint": strategy_hint,
        "file": analyzer_data.get("target_file", analyzer_data.get("file", "")),
        "file_type": file_classification.get(
            analyzer_data.get("source_file", ""), "unknown"
        ),
        "function": func_name,
        "depends_on": [],
        "confidence": confidence,
        "open_questions": [],

        # Evidence traceability (carried from CR)
        # These fields maintain the chain from ticket -> CR -> intent so that
        # the Planner and Reviewer can trace every code change back to its
        # business justification.
        "source_text": cr.get("source_text", cr.get("title", "")),
        "source_location": cr.get("source_location", ""),
        "evidence_refs": cr.get("evidence_refs", []),
        "assumptions": [],  # Populated below if Decomposer makes assumptions
        "done_when": build_done_when(cr, capability, func_name, extracted),

        # Analyzer pass-through fields
        "source_file": analyzer_data.get("source_file"),
        "target_file": analyzer_data.get("target_file"),
        "needs_copy": analyzer_data.get("needs_copy", False),
        "file_hash": analyzer_data.get("file_hash"),
        "function_line_start": analyzer_data.get("function_line_start"),
        "function_line_end": analyzer_data.get("function_line_end"),
        "target_lines": analyzer_data.get("target_lines", []),
        "parameters": build_parameters(cr, capability),
        "peer_examples": [],
    }

    # Add open questions from ambiguity
    if cr.get("ambiguity_flag"):
        intent["open_questions"].append(cr.get("ambiguity_note", "Ambiguous CR"))

    # Add open questions from missing values
    if capability == "structure_insertion" and not extracted.get("premium"):
        if "premium" in cr.get("description", "").lower():
            intent["open_questions"].append(
                f"Premium amount not specified for {cr['title']}"
            )

    return intent


def build_parameters(cr, capability):
    """Extract the relevant parameters from the CR for this capability."""
    extracted = cr.get("extracted", {})
    params = {}

    if capability == "value_editing":
        if extracted.get("factor"):
            params["factor"] = extracted["factor"]
            params["scope"] = extracted.get("scope", "all_territories")
            params["rounding"] = "auto"
            rounding_hint = cr.get("domain_hints", {}).get("rounding_hint")
            if rounding_hint:
                params["rounding_hint"] = rounding_hint
        if extracted.get("old_value") is not None:
            params["old_value"] = extracted["old_value"]
            params["new_value"] = extracted.get("new_value")
        if extracted.get("case_value") is not None:
            params["case_value"] = extracted["case_value"]

    elif capability in ("structure_insertion", "file_creation"):
        # Pass through all extracted values -- the Change Engine decides what to use
        for key, val in extracted.items():
            if val is not None and key not in ("method", "scope", "lob_scope"):
                params[key] = val

    elif capability == "flow_modification":
        for key, val in extracted.items():
            if val is not None:
                params[key] = val

    return params


def compute_confidence(match_source, analyzer_data, cr):
    """Compute confidence score based on how well the CR matches the code."""
    base = {
        "discovery": 0.95,
        "discovery_related": 0.85,
        "developer_hint": 0.90,
        "developer_hint_wildcard": 0.80,
        "glossary": 0.85,
        "keyword": 0.60,
    }.get(match_source, 0.50)

    # Boost if Analyzer has target_lines (high precision)
    if analyzer_data and analyzer_data.get("target_lines"):
        base = min(base + 0.05, 0.99)

    # Reduce if CR has ambiguity
    if cr.get("ambiguity_flag"):
        base = max(base - 0.15, 0.30)

    # Reduce if Analyzer data is minimal
    if analyzer_data and not analyzer_data.get("fub"):
        base = max(base - 0.10, 0.30)

    return round(base, 2)


def build_done_when(cr, capability, func_name, extracted):
    """Build a human-readable verification criteria string for the intent.

    The done_when field tells the Reviewer exactly what to check to confirm
    the change was applied correctly.
    """
    if capability == "value_editing":
        if extracted.get("factor"):
            return f"All rate values in {func_name} multiplied by {extracted['factor']}"
        elif extracted.get("old_value") is not None and extracted.get("new_value") is not None:
            return f"{func_name}: value changed from {extracted['old_value']} to {extracted['new_value']}"
        else:
            return f"Values in {func_name} updated per CR specification"

    elif capability == "structure_insertion":
        return f"New code block inserted in {func_name} as specified"

    elif capability == "file_creation":
        return f"New file created with required content"

    else:
        return f"Change applied to {func_name} per CR specification"
```

**Recording assumptions:** When the Decomposer makes a decision that is not
explicitly stated in the CR, it MUST record it in the intent's `assumptions`
list. Examples:
- `"CR says 'all liability premiums' -- interpreting as GetLiabilityBundlePremiums only (not Extension)"`
- `"CR does not specify rounding -- using auto (match existing pattern)"`
- `"Applying to all territories (CR says 'increase' without territory restriction)"`

These assumptions flow through to the Planner's execution plan and the Reviewer's
validation checklist, so the developer can catch incorrect interpretations at Gate 1.

#### 8.4 Intent ID Assignment

Use sequential IDs: `intent-001`, `intent-002`, etc. Zero-padded to 3 digits.
Intent IDs are flat and sequential because one CR can produce intents across
different functions with no natural nesting.

### Step 8.5: Caller Analysis — Produce Additional Intents for Caller Fixes

**Action:** Check each intent's Analyzer output for `caller_analysis` warnings.
When the Analyzer detected that a caller OVERWRITES the return value of a target
function, the Decomposer MUST produce an additional intent to fix the caller.

This step prevents the bug where the pipeline correctly identifies a defect in a
function but misses that the caller's post-processing renders the fix ineffective.

#### 8.5.1 Check for Caller Warnings

For each intent, check if the Analyzer output includes `caller_analysis`:

```python
def check_caller_warnings(intents, analyzer_outputs):
    """Scan Analyzer outputs for caller_analysis with HIGH risk.

    When found, produce an additional intent to fix the caller function.
    """
    additional_intents = []
    next_id = max_intent_id(intents) + 1

    for intent in intents:
        cr_id = intent["cr"]
        # caller_analysis is a ROOT-LEVEL key in the CR analysis file
        # (cr-NNN-analysis.yaml), NOT inside functions_analyzed[].
        # Look it up by CR ID, not by function name.
        cr_analysis = analyzer_outputs.get(cr_id, {})
        caller = cr_analysis.get("caller_analysis", {})

        if not caller or caller.get("overall_risk") != "HIGH":
            continue

        # HIGH risk means: caller unconditionally overwrites the return value
        # The target function fix is correct, but the caller needs fixing too
        competing_writes = caller.get("competing_writes", [])
        code_smells = caller.get("code_smells", [])

        # Build an additional intent for the caller fix
        caller_intent = build_caller_fix_intent(
            intent_id=f"intent-{next_id:03d}",
            original_intent=intent,
            caller_analysis=caller,
            competing_writes=competing_writes,
            code_smells=code_smells,
        )
        additional_intents.append(caller_intent)
        next_id += 1

        # The caller fix depends on the original intent
        caller_intent["depends_on"].append(intent["id"])

        # Flag the original intent
        intent["has_caller_fix"] = caller_intent["id"]

    return additional_intents
```

#### 8.5.2 Build the Caller Fix Intent

```python
def build_caller_fix_intent(intent_id, original_intent, caller_analysis,
                             competing_writes, code_smells):
    """Build an intent to fix the caller that overwrites a return value.

    capability: 'flow_modification' — we're changing control flow (removing
    or conditionalizing an unconditional overwrite).
    """
    caller_func = caller_analysis["caller_function"]
    result_var = caller_analysis["result_variable"]

    # Build description from the competing writes
    overwrite_lines = [cw["content"].strip() for cw in competing_writes]
    smell_descriptions = [cs["note"] for cs in code_smells]

    description_parts = [
        f"Caller '{caller_func}' unconditionally overwrites '{result_var}' "
        f"after calling '{original_intent['function']}'.",
    ]
    if overwrite_lines:
        description_parts.append(
            f"Competing write(s): {'; '.join(overwrite_lines)}"
        )
    if smell_descriptions:
        description_parts.append(
            f"Code smells: {'; '.join(smell_descriptions)}"
        )

    return {
        "id": intent_id,
        "cr": original_intent["cr"],
        "title": f"Fix caller '{caller_func}' — remove overwrite of "
                 f"'{result_var}' returned by '{original_intent['function']}'",
        "description": " ".join(description_parts),
        "capability": "flow_modification",
        "strategy_hint": None,
        "file": caller_analysis.get("caller_file",
                                     original_intent["file"]),
        "file_type": original_intent["file_type"],
        "function": caller_func,
        "depends_on": [],
        "confidence": 0.80,
        "open_questions": [
            f"Caller '{caller_func}' overwrites the return value of "
            f"'{original_intent['function']}'. The overwrite at "
            f"line(s) {', '.join(str(cw['line']) for cw in competing_writes)} "
            f"needs to be removed or conditionalized. Please confirm the "
            f"correct fix approach."
        ],
        "source_text": original_intent.get("source_text", ""),
        "source_location": "Analyzer caller_analysis (auto-detected)",
        "evidence_refs": [f"caller_analysis for {original_intent['function']}"],
        "assumptions": [
            f"Auto-generated: Analyzer detected that {caller_func} overwrites "
            f"the result of {original_intent['function']}. Without fixing the "
            f"caller, the original change has no effect."
        ],
        "done_when": (
            f"'{result_var}' in '{caller_func}' is no longer unconditionally "
            f"overwritten after the call to '{original_intent['function']}'"
        ),
        "source_file": caller_analysis.get("caller_file",
                                            original_intent.get("source_file")),
        "target_file": caller_analysis.get("caller_file",
                                            original_intent.get("target_file")),
        "needs_copy": original_intent.get("needs_copy", False),
        "file_hash": None,  # Planner will compute
        "function_line_start": caller_analysis.get("call_site_line"),
        "function_line_end": None,  # Planner will determine from full read
        "target_lines": [
            {
                "line": cw["line"],
                "content": cw["content"],
                "context": f"Competing write — overwrites {result_var}",
                "rounding": None,
                "value_count": 0,
            }
            for cw in competing_writes
        ],
        "parameters": {
            "result_variable": result_var,
            "competing_writes": competing_writes,
            "code_smells": code_smells,
            "original_function": original_intent["function"],
        },
        "caller_analysis_source": True,  # Flag: this intent was auto-generated
    }
```

#### 8.5.3 Merge Additional Intents

```python
# After building all regular intents in Step 8:
caller_fix_intents = check_caller_warnings(intents, analyzer_outputs)

if caller_fix_intents:
    intents.extend(caller_fix_intents)

    # Log prominently
    for cfi in caller_fix_intents:
        print(f"[Decomposer] ⚠ AUTO-GENERATED INTENT {cfi['id']}: "
              f"Caller fix for {cfi['function']}")
        print(f"             Original: {cfi['parameters']['original_function']} "
              f"return value is overwritten")
        print(f"             This intent has an OPEN QUESTION for developer review")

# ALSO propagate caller_analysis_risk onto ALL intents (not just HIGH).
# This lets the Planner's Step 9.7 belt-and-suspenders check work,
# and surfaces MEDIUM risk as a warning even when no auto-fix is created.
for intent in intents:
    if intent.get("caller_analysis_source"):
        continue  # Skip auto-generated caller-fix intents
    cr_id = intent["cr"]
    cr_analysis = analyzer_outputs.get(cr_id, {})
    caller = cr_analysis.get("caller_analysis", {})
    if caller.get("overall_risk"):
        intent["caller_analysis_risk"] = caller["overall_risk"]
```

**CRITICAL:** When `caller_analysis.overall_risk == "HIGH"`, the Decomposer MUST
produce this additional intent. Failing to do so means the original fix will have
NO EFFECT at runtime — the caller will overwrite the corrected return value.

### Step 9: Handle Shared Module Deduplication

**Action:** Ensure shared modules are edited ONCE, not per LOB.

9.1. Group intents by `(file, function)` tuple.

9.2. For each group where `file_type == "shared_module"`:
   - Keep exactly ONE intent for the shared function
   - Record which LOBs are affected: `shared_by: ["Home", "Condo", ...]`
   - The Change Engine edits the file once; all LOBs that compile it get the change

```python
def deduplicate_shared_intents(intents, shared_modules):
    """Remove duplicate intents for shared modules.

    If the matching process created multiple intents for the same function
    in a shared module (one per LOB), keep only the first and annotate it
    with shared_by.
    """
    seen = {}  # (file, function) -> intent_id
    to_remove = []

    for intent in intents:
        if intent["file_type"] != "shared_module":
            continue
        key = (intent["file"], intent["function"])
        if key in seen:
            to_remove.append(intent["id"])
        else:
            seen[key] = intent["id"]
            # Annotate with shared_by from shared_modules list
            for sm in shared_modules:
                if sm["file"] in (intent.get("source_file", ""), intent.get("target_file", "")):
                    intent["shared_by"] = sm["shared_by"]
                    break

    return [i for i in intents if i["id"] not in to_remove]
```

### Step 10: Handle Multi-LOB Expansion

**Action:** For LOB-specific changes, expand intents to cover all target LOBs.

10.1. For CRs with `lob_scope: "all"` that target LOB-specific files:
   - Create one intent per target LOB
   - Each intent targets the LOB's specific file (e.g., ResourceID.vb in each version folder)
   - Use the Analyzer output for the specific LOB if available, or the template from
     any analyzed LOB

10.2. For CRs with `lob_scope: "specific"`:
   - Only generate intents for `target_lobs`

10.3. If a shared module operation is needed only for specific LOBs but the module
is compiled by all LOBs, flag:

```
[Decomposer] CR-{NNN} targets only {target_lobs}, but the target file
             ({file}) is shared by all {N} LOBs.
             Changes to this file will affect ALL LOBs.
             Proceed?
```

### Step 11: Build Dependency Graph

**Action:** Detect dependencies between intents and compute topological order.

#### 11.1 Intra-CR Dependencies

When a single CR produces multiple intents (e.g., add a constant AND add routing
that references it):

```python
def detect_intra_cr_deps(intents):
    """Find dependencies between intents from the same CR.

    Rules:
    - If intent A creates a constant and intent B references it: A before B
    - If intent A creates a function and intent B calls it: A before B
    - If intent A creates a file and intent B modifies it: A before B
    """
    cr_groups = {}
    for intent in intents:
        cr_groups.setdefault(intent["cr"], []).append(intent)

    for cr_id, group in cr_groups.items():
        for a in group:
            for b in group:
                if a["id"] == b["id"]:
                    continue
                # Constant creation before reference
                if (a["capability"] == "structure_insertion" and
                    a.get("parameters", {}).get("constant_name")):
                    const_name = a["parameters"]["constant_name"]
                    if const_name in str(b.get("parameters", {})):
                        if a["id"] not in b["depends_on"]:
                            b["depends_on"].append(a["id"])

                # File creation before modification
                if a["capability"] == "file_creation":
                    if a["file"] == b["file"] and b["capability"] != "file_creation":
                        if a["id"] not in b["depends_on"]:
                            b["depends_on"].append(a["id"])
```

#### 11.2 Inter-CR Dependencies

Same logic but across CRs:

```python
def detect_inter_cr_deps(intents):
    """Find dependencies between intents from different CRs.

    Same rules as intra-CR, but also builds partial_approval_constraints.
    """
    constraints = []
    for a in intents:
        for b in intents:
            if a["id"] == b["id"] or a["cr"] == b["cr"]:
                continue
            # Constant creation before reference (cross-CR)
            if (a["capability"] == "structure_insertion" and
                a.get("parameters", {}).get("constant_name")):
                const_name = a["parameters"]["constant_name"]
                if const_name in str(b.get("parameters", {})):
                    if a["id"] not in b["depends_on"]:
                        b["depends_on"].append(a["id"])
                    constraints.append({
                        "cr": b["cr"],
                        "requires_cr": a["cr"],
                        "reason": f"{b['id']} depends on {a['id']}",
                        "blocking_intents": [b["id"]],
                        "required_intents": [a["id"]],
                    })
    return constraints
```

#### 11.3 Conflict Detection

Detect when multiple intents from different CRs target the same code:

```python
def detect_conflicts(intents):
    """Detect conflicting intents using group-and-compare.

    Conflict key = (file, function, case_value or None).
    Two intents from different CRs sharing a key with different target values
    are a TRUE CONFLICT requiring developer resolution.
    """
    groups = {}
    for intent in intents:
        case_val = intent.get("parameters", {}).get("case_value")
        key = (intent["file"], intent["function"], case_val)
        groups.setdefault(key, []).append(intent)

    conflicts = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        # Only flag cross-CR conflicts (same CR is intentional)
        cr_ids = set(i["cr"] for i in group)
        if len(cr_ids) < 2:
            continue

        # Compare target values
        for i, a in enumerate(group):
            for b in group[i+1:]:
                if a["cr"] == b["cr"]:
                    continue
                a_vals = (a.get("parameters", {}).get("new_value"),
                          a.get("parameters", {}).get("factor"))
                b_vals = (b.get("parameters", {}).get("new_value"),
                          b.get("parameters", {}).get("factor"))
                if a_vals != b_vals:
                    conflicts.append((a, b, key))
                elif a_vals == b_vals:
                    # Duplicate -- keep earlier intent
                    conflicts.append((a, b, key, "duplicate"))

    return conflicts
```

When conflicts are found, STOP and ask the developer:

```
[Decomposer] CONFLICT: Two CRs target the same value:
             {intent_A.id} (CR-{X}): {description_A} -> {value_A}
             {intent_B.id} (CR-{Y}): {description_B} -> {value_B}

             Key: ({file}, {function}, {case_value})

             These cannot both be applied. Which value should be used?
               a) {value_A} (from CR-{X})
               b) {value_B} (from CR-{Y})
               c) A different value (please specify)
```

#### 11.4 Circular Dependency Check

```python
def check_cycles(intents):
    """Verify no circular dependencies exist using topological sort."""
    # Kahn's algorithm
    from collections import deque

    in_degree = {i["id"]: 0 for i in intents}
    dependents = {i["id"]: [] for i in intents}

    for intent in intents:
        for dep in intent["depends_on"]:
            if dep in in_degree:
                in_degree[intent["id"]] += 1
                dependents[dep].append(intent["id"])

    queue = deque(sorted(k for k, v in in_degree.items() if v == 0))
    order = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for dep in sorted(dependents[node]):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if len(order) != len(intents):
        cycle_ids = [i["id"] for i in intents if i["id"] not in set(order)]
        return None, cycle_ids  # Cycle detected

    return order, None
```

### Step 12: Compute Topological Execution Order

**Action:** Produce the `execution_order` list respecting all `depends_on` edges.

12.1. Use Kahn's algorithm (Step 11.4) to compute the order.

12.2. Tie-breaking rules (when multiple intents have no remaining dependencies):
   - Shared modules before LOB-specific files
   - Same file: sort by function_line_start descending (bottom-to-top)
   - Different files: alphabetical by file path
   - Same file and line: alphabetical by intent ID

```python
def sort_key(intent_id, intents_by_id):
    """Tie-breaking key for topological sort."""
    intent = intents_by_id[intent_id]
    is_shared = 0 if intent["file_type"] in ("shared_module", "cross_lob") else 1
    line = -(intent.get("function_line_start") or 0)  # Negative for descending
    return (is_shared, intent.get("file", ""), line, intent_id)
```

12.3. If the topological sort detects a cycle, STOP:

```
[Decomposer] ERROR: Circular dependency detected:
             {cycle_ids}

             This should not happen. Please review the change requests.
```

### Step 13: Compute Confidence Scores and Collect Open Questions

**Action:** Final pass to adjust confidence and collect all open questions.

13.1. For each intent, collect open questions from:
   - CR ambiguity flags (`ambiguity_note`)
   - Missing parameter values (e.g., premium not specified)
   - Low-confidence matches (keyword-only, no Discovery/Analyzer confirmation)
   - Analyzer hazards that need developer attention

13.2. Adjust confidence based on open questions:
   - Each unanswered question reduces confidence by 0.10 (minimum 0.30)
   - High-hazard functions (e.g., mixed_rounding, dual_use_array6) reduce by 0.05

### Step 14: Write intent_graph.yaml

**Action:** Write the complete intent graph to the analysis/ directory.

14.1. Ensure directory exists:
```
.iq-workstreams/changes/{workstream}/analysis/
```

14.2. Assemble and write `analysis/intent_graph.yaml`:

```yaml
workflow_id: "{workflow_id}"
decomposer_version: "2.0"
decomposed_at: "{ISO timestamp}"
total_intents: {count}
total_out_of_scope: {count}

out_of_scope:
  # ... CRs with dat_file_warning

intents:
  # ... all intents with full schemas

partial_approval_constraints:
  # ... inter-CR couplings

execution_order:
  # ... topological order
```

14.3. Validate YAML:

```bash
{python_cmd} -c "import yaml; yaml.safe_load(open('analysis/intent_graph.yaml')); print('OK')"
```

If PyYAML is not installed, do a basic structure check (file is non-empty, starts
with a key-value pair).

14.4. **Do NOT update `manifest.yaml`** -- the orchestrator handles that.

### Step 15: Present Results to Developer

**Action:** Show a formatted summary.

15.1. Present:

```
[Decomposer] Formed {N} intents from {M} change requests:

  OUT OF SCOPE (tracked, no intents):
    CR-003: [DAT FILE] Increase hab dwelling base rates by 5%

  INTENTS:
    intent-001: value_editing -- Multiply GetLiabilityBundlePremiums by 1.03
                File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)
                Lines: 3850-4100, 14 target lines
                Confidence: 0.95
                Strategy hint: array6-multiply

    intent-002: value_editing -- Change $5000 deductible in SetDisSur_Deductible
                File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)
                Line: 2202, 1 target line
                Confidence: 0.95
                Strategy hint: factor-table

    intent-003: value_editing -- Multiply GetLiabilityExtensionPremiums by 1.03
                File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)
                Lines: 4110-4300, 8 target lines
                Confidence: 0.85 (discovered via related function)
                Strategy hint: array6-multiply

    intent-004: structure_insertion -- Add $50K sewer backup tier
                File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)
                Line: ~5200
                Confidence: 0.70
                Open questions:
                  - "Premium amount for $50K tier not specified"
                  - "Insert before or after $25K case?"

  Dependencies: (none)

  Totals: {N} intents ({V} value_editing, {S} structure_insertion,
           {F} file_creation, {W} flow_modification)
          {O} out-of-scope, {Q} open questions

  Next: Planner will build the execution plan for Gate 1 approval.
```

15.2. Report completion:

```
[Decomposer] COMPLETE. Wrote {N} intents to analysis/intent_graph.yaml.
             {O} CR(s) out of scope (DAT file)
             {Q} open question(s) for developer at Gate 1

             Next: Planner agent builds the execution plan.
```

---

## WORKED EXAMPLES

### Example A: Simple SK Hab Factor + Liability Changes

**Input from Intake (change_requests.yaml):**

```yaml
province: "SK"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
effective_date: "20260101"
request_count: 4

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

requests:
  - id: "cr-001"
    title: "[DAT FILE] Increase dwelling base rates by 5%"
    dat_file_warning: true
  - id: "cr-002"
    title: "Change $5000 deductible factor from -0.20 to -0.22"
    extracted: {case_value: 5000, old_value: -0.20, new_value: -0.22, method: "explicit"}
  - id: "cr-003"
    title: "Change $2500 deductible factor from -0.15 to -0.17"
    extracted: {case_value: 2500, old_value: -0.15, new_value: -0.17, method: "explicit"}
  - id: "cr-004"
    title: "Increase liability premiums by 3%"
    extracted: {factor: 1.03, method: "multiply", scope: "all_territories"}
    domain_hints: {glossary_match: "GetLiabilityBundlePremiums", involves_rates: true}
```

**Discovery output:** Resolved cr-004 to GetLiabilityBundlePremiums with related
function GetLiabilityExtensionPremiums.

**Analyzer output:** Full function analysis for SetDisSur_Deductible (lines 2100-2250),
GetLiabilityBundlePremiums (lines 3850-4100), GetLiabilityExtensionPremiums
(lines 4110-4300).

**Step 6 -- Filter:** CR-001 is out-of-scope (DAT file).

**Step 7 -- Match:**
- CR-002 -> SetDisSur_Deductible (keyword match: "deductible")
- CR-003 -> SetDisSur_Deductible (keyword match: "deductible")
- CR-004 -> GetLiabilityBundlePremiums (discovery) + GetLiabilityExtensionPremiums (related)

**Step 8 -- Form intents:**
- intent-001: value_editing, SetDisSur_Deductible, Case 5000 (from CR-002)
- intent-002: value_editing, SetDisSur_Deductible, Case 2500 (from CR-003)
- intent-003: value_editing, GetLiabilityBundlePremiums, multiply 1.03 (from CR-004)
- intent-004: value_editing, GetLiabilityExtensionPremiums, multiply 1.03 (from CR-004)

**Step 9 -- Dedup:** All in shared module -- one intent per function (correct, no dups).

**Step 11 -- Dependencies:** None between these intents.

**Final output:**

```yaml
workflow_id: "20260101-SK-Hab-deductible-liability"
decomposer_version: "2.0"
total_intents: 4
total_out_of_scope: 1

out_of_scope:
  - cr: "cr-001"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning"

intents:
  - id: "intent-001"
    cr: "cr-002"
    title: "Change $5000 deductible factor from -0.20 to -0.22"
    capability: "value_editing"
    strategy_hint: "factor-table"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    depends_on: []
    confidence: 0.95
    open_questions: []
    # Analyzer pass-through...
    function_line_start: 2100
    function_line_end: 2250
    target_lines:
      - line: 2202
        content: "                Case 5000 : dblDedDiscount = -0.2"
    parameters: {case_value: 5000, old_value: -0.20, new_value: -0.22}

  - id: "intent-002"
    cr: "cr-003"
    title: "Change $2500 deductible factor from -0.15 to -0.17"
    capability: "value_editing"
    strategy_hint: "factor-table"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    depends_on: []
    confidence: 0.95
    open_questions: []
    function_line_start: 2100
    function_line_end: 2250
    target_lines:
      - line: 2180
        content: "                Case 2500 : dblDedDiscount = -0.15"
    parameters: {case_value: 2500, old_value: -0.15, new_value: -0.17}

  - id: "intent-003"
    cr: "cr-004"
    title: "Multiply liability bundle premiums by 1.03"
    capability: "value_editing"
    strategy_hint: "array6-multiply"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityBundlePremiums"
    depends_on: []
    confidence: 0.95
    open_questions: []
    function_line_start: 3850
    function_line_end: 4100
    target_lines: [...]  # 14 Array6 lines
    parameters: {factor: 1.03, scope: "all_territories", rounding: "auto"}

  - id: "intent-004"
    cr: "cr-004"
    title: "Multiply liability extension premiums by 1.03"
    capability: "value_editing"
    strategy_hint: "array6-multiply"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityExtensionPremiums"
    depends_on: []
    confidence: 0.85
    open_questions: []
    function_line_start: 4110
    function_line_end: 4300
    target_lines: [...]  # 8 Array6 lines
    parameters: {factor: 1.03, scope: "all_territories", rounding: "auto"}

partial_approval_constraints: []

execution_order:
  - "intent-001"
  - "intent-002"
  - "intent-003"
  - "intent-004"
```

### Example B: Bug Fix Ticket (No Classification Needed)

**Input from Intake:**

```yaml
requests:
  - id: "cr-001"
    title: "Fix missing $25K Seasonal case in GetSewerBackupPremium"
    description: |
      GetSewerBackupPremium is missing the $25K coverage branch for Seasonal
      policy category. Falls through to Case Else (returns 0). Should return
      same premium as Home ($89).
    extracted:
      target_function_hint: "GetSewerBackupPremium"
      case_value: 25000
      new_value: 89
      lob_scope: "specific"
      target_lobs: ["Seasonal"]
    domain_hints:
      glossary_match: "GetSewerBackupPremium"
      involves_new_code: true
```

**Analyzer output:** GetSewerBackupPremium analyzed at lines 5200-5400. Branch tree
shows existing cases for 10000, 20000, 25000 (but 25000 missing Seasonal branch).
FUB shows nested Select Case: outer = policyCategory, inner = sewerBackupCoverage.

**Step 7 -- Match:** CR-001 -> GetSewerBackupPremium (developer hint + glossary match).

**Step 8 -- Form intent:**

```yaml
- id: "intent-001"
  cr: "cr-001"
  title: "Fix missing $25K Seasonal case in GetSewerBackupPremium"
  capability: "structure_insertion"
  strategy_hint: "case-block-insertion"
  file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
  file_type: "shared_module"
  function: "GetSewerBackupPremium"
  depends_on: []
  confidence: 0.90
  open_questions: []
  function_line_start: 5200
  function_line_end: 5400
  target_lines: []      # Insertion, not modification
  parameters:
    case_value: 25000
    new_value: 89
    target_lobs: ["Seasonal"]
  peer_examples:
    - "Case 25000 in Home branch -- structure to follow"
```

This intent was formed WITHOUT any classification gate. The old pipeline would
have been stuck trying to fit a bug fix into one of 7 template types. The new
pipeline reads the code, sees what's missing, and forms an intent.

### Example C: Complex Multi-File Change with Dependencies

**Input from Intake:** 2 CRs -- one adds a constant, one adds routing that uses it.

```yaml
requests:
  - id: "cr-001"
    title: "Add Elite Comp coverage type"
    extracted:
      constant_name: "ELITECOMP"
      coverage_type_name: "Elite Comp."
      classifications: ["PREFERRED", "STANDARD"]
      dat_ids: {Preferred: 9501, Standard: 9502}
    domain_hints:
      involves_new_code: true

  - id: "cr-002"
    title: "Add Elite Comp eligibility rule"
    extracted:
      rules: [{condition: "CoverageType = ELITECOMP", enforcement: "Min $500K dwelling"}]
    domain_hints:
      involves_new_code: true
```

**Step 8 -- Form intents:**

```yaml
intents:
  - id: "intent-001"
    cr: "cr-001"
    title: "Add ELITECOMP constant to mod_Common"
    capability: "structure_insertion"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: null        # Module-level
    depends_on: []

  - id: "intent-002"
    cr: "cr-001"
    title: "Add Elite Comp rate table routing"
    capability: "flow_modification"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetRateTableID"
    depends_on: ["intent-001"]    # Constant must exist first

  - id: "intent-003"
    cr: "cr-001"
    title: "Add Elite Comp DAT IDs to Home ResourceID.vb"
    capability: "structure_insertion"
    file: "Saskatchewan/Home/20260101/ResourceID.vb"
    file_type: "local"
    depends_on: []

  # intent-004 through intent-008: DAT IDs for remaining 5 LOBs

  - id: "intent-009"
    cr: "cr-002"
    title: "Add Elite Comp eligibility validation"
    capability: "flow_modification"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    depends_on: ["intent-001"]    # References ELITECOMP constant

partial_approval_constraints:
  - cr: "cr-002"
    requires_cr: "cr-001"
    reason: "intent-009 references ELITECOMP defined by intent-001"
    blocking_intents: ["intent-009"]
    required_intents: ["intent-001"]
```

### Example D: AB Auto Base Rate Increase (Single LOB)

**Input from Intake:**

```yaml
province: "AB"
lobs: ["Auto"]
effective_date: "20260101"
request_count: 1

requests:
  - id: "cr-001"
    title: "Increase AB Auto base rates by 5%"
    extracted: {factor: 1.05, method: "multiply", scope: "all_territories"}
    domain_hints: {involves_rates: true}
```

**Analyzer output:** GetBaseRate_Auto at lines 200-450 in mod_Algorithms_ABAuto.

**Result:**

```yaml
total_intents: 1

intents:
  - id: "intent-001"
    cr: "cr-001"
    title: "Multiply AB Auto base rates by 1.05"
    capability: "value_editing"
    strategy_hint: "array6-multiply"
    file: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
    file_type: "lob_specific"
    function: "GetBaseRate_Auto"
    depends_on: []
    confidence: 0.95
    function_line_start: 200
    function_line_end: 450
    parameters: {factor: 1.05, scope: "all_territories", rounding: "auto"}

execution_order: ["intent-001"]
```

---

## SPECIAL CASES

### Case 1: Two CRs Target the Same Function with Different Case Values

**Scenario:** CR-002 changes Case 5000, CR-003 changes Case 2500, both resolved to
SetDisSur_Deductible by the Analyzer.

**Handling:** Separate intents (intent-001 and intent-002) targeting the same function.
NOT a conflict -- different Case values are independent edits. The Planner sequences
them bottom-to-top within the file.

### Case 2: Two CRs Target the Same Value (True Conflict)

**Scenario:** CR-002 says change Case 5000 to -0.22, CR-005 says change Case 5000 to -0.25.

**Handling:** Detected by conflict detection in Step 11.3. STOP and ask the developer.
The Decomposer will not proceed until the conflict is resolved.

### Case 3: Cross-LOB File Compilation

**Scenario:** An intent targets Liab_RentedDwelling_SKHome20260101.vb, which the
.vbproj parsing shows is compiled by both Home AND Condo.

**Handling:** Classify as `file_type: "cross_lob"`. Place with shared intents.
Add `cross_lob_warning` to the intent.

### Case 4: CR Matches No Analyzed Function

**Scenario:** CR says "update the multi-vehicle discount logic" but no function
matching "multi-vehicle" was found by the Analyzer.

**Handling:** See Step 7.2. Ask the developer for the function name. If they provide
one, create the intent with `confidence: 0.30` and flag `open_questions` noting
the function was not analyzed.

### Case 5: One CR Produces Many Intents (10+)

**Scenario:** "Add Elite Comp coverage" for a 6-LOB hab workflow produces 9 intents
(3 shared + 6 per-LOB DAT IDs).

**Handling:** Normal. Report the count to the developer:

```
[Decomposer] CR-001 decomposed into 9 intents (complex multi-file change).
```

### Case 6: LOB-Scope = Specific (Not All LOBs)

**Scenario:** CR has `lob_scope: "specific"`, `target_lobs: ["Home", "Condo"]`.

**Handling:**
- Shared module intents: generated as normal (affect all LOBs that compile the file).
  Flag the scope mismatch to the developer.
- LOB-specific intents: only for target_lobs.

### Case 7: CR with ambiguity_flag = true

**Scenario:** CR has `ambiguity_flag: true`, `ambiguity_note: "Premium amount not specified"`.

**Handling:** Pass the ambiguity through to the intent's `open_questions`. The
ambiguity was noted by Intake; the Planner will present it to the developer at Gate 1.
The Decomposer does NOT re-ask.

### Case 8: Broad CR ("Increase All Liability Premiums")

**Scenario:** CR says "increase all liability premiums by 3%" and Discovery + Analyzer
found 3 liability functions.

**Handling:** Create separate intents per function (Step 7.3). All link back to the
same CR. If the match came from keyword matching (low confidence), present candidates
to the developer for confirmation.

### Case 9: Nested If/Else in Factor Tables

**Scenario:** CR says "change $5000 deductible factor" but the Analyzer found nested
If/Else (farm vs non-farm) inside Case 5000.

**Handling:** The Analyzer already identified this -- the FUB's branch_tree shows
the nesting, and target_lines includes all candidate values. The Decomposer passes
this through. The intent includes ALL target lines from the Analyzer. The Change
Engine or the developer decides which branch(es) to modify.

### Case 10: Change Targets a Function Not in CalcMain Flow

**Scenario:** CR references a utility function that Discovery did not trace
(not in CalcMain call chain) but the Analyzer found it via .vbproj scanning.

**Handling:** If the function is in the Analyzer output, match normally. If not,
fall through to developer interaction (Step 7.2). The Decomposer does not restrict
itself to Discovery's call chain -- any analyzed function is a valid target.

---

## KEY RESPONSIBILITIES (Summary)

1. **Load all upstream outputs:** Intake CRs, Discovery code map, Analyzer function analysis
2. **Parse .vbproj files as XML:** Build the File Reference Map (same as before)
3. **Classify files:** Apply File Classification Rules for shared/LOB/cross-LOB typing
4. **Filter out-of-scope CRs:** dat_file_warning = true -> OUT_OF_SCOPE
5. **Match CRs to analyzed functions:** Priority: Discovery > developer hint > glossary > keywords
6. **Form intents:** One intent per function per CR, with capability tag and strategy hint
7. **Pass through Analyzer data:** target_lines, FUBs, line numbers, hazards -- no recomputation
8. **Deduplicate shared modules:** One intent per shared function, not per LOB
9. **Expand LOB-specific intents:** One per target LOB for local files
10. **Build dependency graph:** Constant-before-reference, file-creation-before-modification
11. **Detect conflicts:** Group-and-compare across CRs
12. **Compute execution order:** Topological sort with tie-breaking
13. **Build partial approval constraints:** Surface inter-CR couplings for Gate 1
14. **Write intent_graph.yaml:** Single output artifact
15. **Handle unknown/unmatched CRs:** Create low-confidence intents with open_questions, ask developer

## Capability Quick Reference

| What the intent does | Capability |
|---------------------|-----------|
| Multiply Array6 values by a factor | value_editing |
| Change a Select Case value (old -> new) | value_editing |
| Change a Const value | value_editing |
| Change an included limit value | value_editing |
| Add a new Array6 premium row | structure_insertion |
| Add a new Const declaration | structure_insertion |
| Add a new Select Case branch | structure_insertion |
| Add DAT IDs to ResourceID.vb | structure_insertion |
| Create a new Option_*.vb or Liab_*.vb file | file_creation |
| Add CalcOption routing (new Case block) | flow_modification |
| Add validation/eligibility logic | flow_modification |
| Modify If/Else control flow | flow_modification |

**Rule of thumb:** value_editing = changing existing values in existing code.
structure_insertion = adding new blocks to existing files. file_creation = new files.
flow_modification = changing how the code routes/decides.

## Boundary with Analyzer (New vs Old)

| Responsibility | Old Decomposer | New Decomposer | Analyzer |
|---------------|:--------------:|:--------------:|:--------:|
| Identify target functions | Guess from patterns | Match from Analyzer output | Provides verified analysis |
| Determine exact line numbers | NO | Pass through from Analyzer | YES |
| Read actual VB.NET code | NO | NO (reads Analyzer output) | YES |
| Classify operation types | YES (10 types) | NO (uses capabilities) | N/A |
| Resolve rounding | Passes "auto" | Passes through Analyzer's resolution | Resolves to banker/none/mixed |
| Build dependency graph | YES | YES (same) | N/A |
| Detect cross-LOB refs | From .vbproj | From .vbproj (same) | Full reverse lookup |
| Show candidates to developer | NO | YES (from Analyzer data) | Provides candidates |

The key difference: the OLD Decomposer guessed about code based on naming patterns.
The NEW Decomposer reads verified Analyzer output. It knows exactly which functions
exist, what they contain, and where the target lines are. No guessing.

## Error Handling

### Missing Analyzer Output

```
[Decomposer] ERROR: No Analyzer output found in analysis/analyzer_output/.
             Was the Analyzer run? Check manifest.yaml for analyzer.status.
```

### Missing .vbproj Files

```
[Decomposer] ERROR: Cannot read .vbproj file: {path}
             This file is listed in change_requests.yaml target_folders but
             does not exist on disk. Was IQWiz run?
```

### Malformed .vbproj

```
[Decomposer] ERROR: Cannot parse .vbproj as XML: {path}
             Error: {xml_error}
```

### Invalid CR YAML

```
[Decomposer] ERROR: Cannot read CR file: {path}
             Error: {yaml_error}
             The Intake agent may have written malformed YAML.
```

### No Target Folders

```
[Decomposer] ERROR: change_requests.yaml has empty target_folders list.
             At least one target folder is required.
```

---

## GRACEFUL DEGRADATION

The Decomposer handles missing upstream data gracefully:

| Missing Data | Fallback |
|-------------|----------|
| code_discovery.yaml absent | Skip Discovery matching, rely on Analyzer index + domain hints |
| analyzer_output/ empty | STOP -- cannot form intents without code understanding |
| Specific function not in Analyzer | Ask developer for function name, create low-confidence intent |
| config.yaml missing | STOP -- need carrier configuration |
| codebase-profile.yaml absent | Skip glossary/dispatch enrichment, proceed with basic matching |

<!-- IMPLEMENTATION: Vision Rewrite Phase 1 -->
