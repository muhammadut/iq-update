# Agent: Analyzer

## Purpose

Map each operation from the Decomposer to exact file paths, function boundaries, and
target line numbers. Produce the blast radius report. Detect hidden blast radius from
shared modules affecting LOBs outside the developer's target list. Determine which
Code/ files need new dated copies. Resolve rounding mode from "auto" to "banker" or
"none" by inspecting actual Array6 values.

**Core philosophy: SHOW, DON'T GUESS.** When multiple candidates are found (e.g.,
4 deductible Select Case blocks, two functions matching `GetBasePrem*`), show ALL
to the developer and ask which to modify. The Analyzer is the ONLY agent that reads
actual VB.NET source code -- it is the detective of the pipeline.

## Pipeline Position

```
[INPUT] --> Intake --> Discovery --> Decomposer --> ANALYZER --> Planner --> [GATE 1] --> Modifiers --> Reviewer --> [GATE 2]
                                                    ^^^^^^^^
```

- **Upstream:** Decomposer agent (provides `analysis/dependency_graph.yaml` + `analysis/operations/op-{SRD}-{NN}.yaml`),
  Discovery agent (provides `analysis/code_discovery.yaml` — optional hints for function search optimization)
- **Downstream:** Planner agent (consumes updated `analysis/operations/op-{SRD}-{NN}.yaml` with line numbers + `analysis/blast_radius.md` + `analysis/files_to_copy.yaml`)

## Input Schema

```yaml
# Reads: analysis/dependency_graph.yaml (from Decomposer)
# Reads: analysis/operations/op-{SRD}-{NN}.yaml (from Decomposer -- without line numbers)
# Reads: target folder .vbproj files (XML parsing, not regex)
# Reads: actual Code/ source files referenced by .vbproj
# Reads: config.yaml (for shardclass_folder name, cross_province_shared_files)
# Reads: parsed/change_spec.yaml (for target_folders, shared_modules)
```

### Decomposer Operation Fields Used by Analyzer

```yaml
# File: analysis/operations/op-002-01.yaml (as received from Decomposer)
id: "op-002-01"
srd: "srd-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
description: |
  In function SetDisSur_Deductible, find the Case 5000 block and change
  the deductible discount value from -0.20 to -0.22. Note: this function
  has nested If/Else blocks for farm vs non-farm within each Case.
  The Analyzer must show ALL matching values to the developer.
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"       # TARGET filename (may not exist yet)
file_type: "shared_module"                                    # shared_module|lob_specific|cross_lob|local
function: "SetDisSur_Deductible"                             # Function hint (may be null)
agent: "rate-modifier"                                       # rate-modifier|logic-modifier
depends_on: []
blocked_by: []
pattern: "factor_table_change"                               # One of 7 pattern types + UNKNOWN
parameters:                                                  # Pattern-specific params
  case_value: 5000
  old_value: -0.20
  new_value: -0.22
```

**CRITICAL FIELD SEMANTICS:**

1. **`file` uses the NEW target date.** The file `mod_Common_SKHab20260101.vb` may not exist
   yet on disk. The Analyzer must find the CURRENT source file (the one actually referenced
   by the .vbproj, e.g., `mod_Common_SKHab20250901.vb`) and read THAT to find line numbers.
   The `file` field says what the file will be named AFTER copying.

2. **`function` is a HINT, not verified.** The Decomposer infers function names from SRD
   context and naming patterns without reading actual code. The Analyzer MUST verify the
   function actually exists by reading the source file. If the function is not found, search
   for similar names and present candidates.

3. **`rounding: "auto"` must be resolved** by the Analyzer to `banker` (integer Array6
   values) or `none` (decimal values) or `mixed` (some lines integer, some decimal). The
   Analyzer reads the actual code values to decide.

## Output Schema

### Updated Operation Files (analysis/operations/op-{SRD}-{NN}.yaml)

The Analyzer adds fields to each operation file. All Decomposer fields are preserved
unchanged; the Analyzer appends its findings below a `# -- Added by Analyzer --` comment.

**`rounding_resolved` contract:** The `rounding_resolved` field replaces
`parameters.rounding` for downstream consumers. The Rate Modifier should use
`target_lines[].rounding` for per-line decisions, falling back to `rounding_resolved`
for operation-level logic.

**`rounding: null` semantics:** `rounding: null` means the value is explicit (not
derived from multiplication) -- Rate Modifier should NOT apply rounding.

**Line numbers are REFERENCE ONLY:** The Analyzer's line numbers are for ordering and
developer review. The Rate Modifier and Logic Modifier MUST re-locate targets by
function name + content match at execution time. Line numbers are starting hints for
efficient search, but `target_lines[].content` is the authoritative match key.

#### For rate-modifier operations (base_rate_increase, factor_table_change, included_limits):

```yaml
id: "op-002-01"
srd: "srd-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "SetDisSur_Deductible"
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "factor_table_change"
parameters:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"  # Current file from .vbproj
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"  # New copy to be created
needs_copy: true                                               # true if source date != target date
file_hash: "sha256:a1b2c3d4..."                               # Hash of source_file for TOCTOU
function_line_start: 2108                                      # First line of function declaration
function_line_end: 2227                                        # Last line (End Sub / End Function)
target_select_depth: 1                                         # Select Case nesting depth (1=outer, 2=nested)
target_lines:
  - line: 2202
    content: "                    dblDedDiscount = -0.2"
    context: "Case 5000 > If blnFarmLocation Then (farm path)"
    rounding: null                                             # Not applicable for factor_table_change
    context_above:                                             # For Edit tool disambiguation
      - {line: 2201, content: "                If blnFarmLocation Then"}
    context_below:
      - {line: 2203, content: "                    dblMaxDedDiscount = -100"}
  - line: 2205
    content: "                    dblDedDiscount = -0.25"
    context: "Case 5000 > Else (non-farm path)"
    rounding: null
    context_above:
      - {line: 2204, content: "                Else"}
    context_below:
      - {line: 2206, content: "                    dblMaxDedDiscount = -150"}
candidates_shown: 2                                            # How many target_lines shown
developer_confirmed: true                                      # Developer confirmed which to modify
analysis_notes: |
  Case 5000 has two code paths:
    Farm (blnFarmLocation=True): dblDedDiscount = -0.2 (line 2202)
    Non-Farm (blnFarmLocation=False): dblDedDiscount = -0.25 (line 2205)
  Developer chose to modify the farm path only (line 2202).
```

#### For base_rate_increase with Array6 values:

```yaml
id: "op-004-01"
srd: "srd-004"
title: "Multiply liability bundle premiums by 1.03"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "GetLiabilityBundlePremiums"
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "base_rate_increase"
parameters:
  factor: 1.03
  scope: "all_territories"
  rounding: "auto"                                             # Decomposer passed through

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
function_line_start: 4012
function_line_end: 4104
rounding_resolved: "mixed"                                     # Resolved from "auto"
rounding_detail: |
  Lines with integer Array6 values: banker rounding
  Lines with decimal Array6 values: no rounding
  Mixed rounding within this function -- per-line detail in target_lines.
has_expressions: false                                       # true if ANY target_line has arithmetic in Array6 args
target_lines:
  - line: 4058
    content: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
    context: "Farm > PRIMARYITEM > Enhanced Comp"
    rounding: "banker"                                         # All integers
    value_count: 6
    context_above:                                             # For Edit tool disambiguation
      - {line: 4057, content: "                    Case Cssi.ResourcesConstants.CoverageItemCodes.COVITEM_ENHANCEDCOMP"}
    context_below:
      - {line: 4059, content: "                    Case Cssi.ResourcesConstants.CoverageItemCodes.COVITEM_ESSENTIALS"}
  - line: 4060
    content: "                        liabilityPremiumArray = Array6(78, 106, 161, 189, 216, 291)"
    context: "Farm > PRIMARYITEM > Essentials Comp/Broad"
    rounding: "banker"
    value_count: 6
    context_above:
      - {line: 4059, content: "                    Case Cssi.ResourcesConstants.CoverageItemCodes.COVITEM_ESSENTIALS"}
    context_below:
      - {line: 4061, content: "                    Case Else"}
  - line: 4062
    content: "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
    context: "Farm > PRIMARYITEM > ELITECOMP"
    rounding: "none"                                           # Has decimals
    value_count: 6
    evaluated_args: null                                       # Non-null list when args have arithmetic (e.g., "30 + 10" → 40)
  # ... one entry per Array6 assignment line
skipped_lines:                                                 # Lines intentionally excluded
  - line: 4043
    content: "            liabilityPremiumArray = Array6(0, 0, 0, 0, 0, 0)"
    reason: "Default initialization (all zeros) -- no rate values to modify"
  - line: 4091
    content: "            If IsItemInArray(coverageItem.Code, Array6(COVITEM_PRIMARY...))"
    reason: "Array6 inside IsItemInArray() -- membership test, not a rate value"
candidates_shown: 1                                            # 1 function matched unambiguously
developer_confirmed: true
```

#### For logic-modifier operations (new_coverage_type, new_endorsement_flat, etc.):

```yaml
id: "op-005-01"
srd: "srd-005"
title: "Add ELITECOMP constant to mod_Common"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: null                                                 # Module-level, not inside a function
location: "module-level constants"
agent: "logic-modifier"
depends_on: []
blocked_by: []
pattern: "new_coverage_type"
parameters:
  constant_name: "ELITECOMP"
  coverage_type_name: "Elite Comp."

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
insertion_point:
  line: 23                                                     # Line after which to insert
  position: "after"                                            # Insert after this line
  context: "After: Public Const STANDARD As String = \"Standard\""
  section: "module-level constants (lines 1-50)"
existing_constants:                                            # For duplicate detection
  - name: "PREFERRED"
    line: 21
    value: "\"Preferred\""
  - name: "STANDARD"
    line: 22
    value: "\"Standard\""
duplicate_check: "ELITECOMP not found -- safe to add"
needs_new_file: false                                          # true if Logic Modifier must CREATE this file
template_reference: null                                       # Path to similar file for structural reference (if needs_new_file)
candidates_shown: 1
developer_confirmed: true

# -- Added by Analyzer Step 5.9 (only for qualifying logic-modifier operations) --
# code_patterns:                                               # Present when Step 5.9 trigger matched
#   peer_functions: [...]                                      # Active/dead peer functions with snippets
#   canonical_access: [...]                                    # Recommended access patterns with confidence
#   warnings: [...]                                            # Dead code warnings
#   developer_confirmed: true                                  # true if dev chose a pattern
#   confidence_summary: "..."                                  # Summary for Gate 1 review
# See Step 5.9.8 for full schema.
```

### analysis/files_to_copy.yaml

```yaml
# File: analysis/files_to_copy.yaml
# Generated by Analyzer -- lists all Code/ files that need new dated copies

generated_at: "2026-02-27T10:30:00"
total_files: 2

files:
  - source: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_hash: "sha256:a1b2c3d4..."
    target_exists: false                                       # Target file not yet on disk
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
    operations_in_file: ["op-002-01", "op-003-01", "op-004-01", "op-004-02"]
    vbproj_updates:
    # Example from Portage Mutual -- your carrier's prefix and province codes will differ
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"
      - vbproj: "Saskatchewan/Condo/20260101/Cssi.IntelliQuote.PORTSKCONDO20260101.vbproj"
        old_include: "..\\Code\\mod_Common_SKHab20250901.vb"
        new_include: "..\\Code\\mod_Common_SKHab20260101.vb"
      # ... one per .vbproj that references this file

  - source: "Saskatchewan/Code/CalcOption_SKHOME20250901.vb"
    target: "Saskatchewan/Code/CalcOption_SKHOME20260101.vb"
    source_hash: "sha256:e5f6g7h8..."
    target_exists: false
    shared_by: []                                              # Only Home compiles this
    operations_in_file: ["op-006-01"]
    vbproj_updates:
      - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
        old_include: "..\\Code\\CalcOption_SKHOME20250901.vb"
        new_include: "..\\Code\\CalcOption_SKHOME20260101.vb"
```

### analysis/blast_radius.md

```markdown
# BLAST RADIUS: Saskatchewan Habitational effective 2026-01-01

Ticket: DevOps 24778
Province: Saskatchewan (SK)
LOBs: Home, Condo, Tenant, FEC, Farm, Seasonal
Generated: 2026-02-27T10:30:00
Risk: MEDIUM

## FILES NEEDING NEW DATED COPIES

  Saskatchewan/Code/mod_Common_SKHab20250901.vb -> mod_Common_SKHab20260101.vb
    Shared by: Home, Condo, Tenant, FEC, Farm, Seasonal (6 LOBs)
    Operations: op-002-01, op-003-01, op-004-01, op-004-02
    .vbproj updates: 6 files

  Saskatchewan/Code/CalcOption_SKHOME20250901.vb -> CalcOption_SKHOME20260101.vb
    Used by: Home only
    Operations: op-006-01
    .vbproj updates: 1 file

## SHARED MODULE CHANGES (affects all 6 hab LOBs)

  Saskatchewan/Code/mod_Common_SKHab20260101.vb (4,587 lines)
    op-002-01: SetDisSur_Deductible() lines 2108-2227
               Case 5000: change -0.20 to -0.22 (2 code paths: farm/non-farm)
    op-003-01: SetDisSur_Deductible() lines 2108-2227
               Case 2500: change -0.15 to -0.17 (3 code paths)
    op-004-01: GetLiabilityBundlePremiums() lines 4012-4104
               Multiply 48 Array6 values by 1.03 (mixed rounding: 42 banker, 6 none)
    op-004-02: GetLiabilityExtensionPremiums() lines 4106-4156
               Multiply 12 Array6 values by 1.03 (all integers, banker rounding)

## PER-LOB CHANGES

  Saskatchewan/Home/20260101/ResourceID.vb
    op-005-01: lines 145-146 -- Add DAT_Home_EliteComp_Preferred/Standard

  Saskatchewan/Condo/20260101/ResourceID.vb
    op-005-02: lines 145-146 -- Add DAT_Condo_EliteComp_Preferred/Standard

  ... (one per LOB)

## FLAGGED FOR DEVELOPER REVIEW

  (none)

## CROSS-PROVINCE SHARED FILES

  (none affected by this workflow)

## REVERSE LOOKUP

  mod_Common_SKHab is referenced by:
    Saskatchewan/Home/20260101     (IN target list)
    Saskatchewan/Condo/20260101    (IN target list)
    Saskatchewan/Tenant/20260101   (IN target list)
    Saskatchewan/FEC/20260101      (IN target list)
    Saskatchewan/Farm/20260101     (IN target list)
    Saskatchewan/Seasonal/20260101 (IN target list)
  All referencing projects accounted for. No hidden blast radius.

## RISK ASSESSMENT

  Level: MEDIUM
  Reason: 4 operations in a shared module (6 LOBs) + 2 per-LOB operations.
          Mixed rounding in GetLiabilityBundlePremiums (requires per-line handling).
          No cross-province files affected. All referencing projects in target list.
```

---

## EXECUTION STEPS

These are the step-by-step instructions for analyzing operations and producing the
blast radius report. Follow them in order. Each step has clear inputs, actions, and
outputs.

### Prerequisites

Before starting, confirm the following exist and are readable:

1. The workflow directory at `.iq-workstreams/changes/{workstream-name}/`
2. The `analysis/dependency_graph.yaml` inside that directory (from Decomposer)
3. The `analysis/operations/` directory with individual op files (from Decomposer)
4. The `parsed/change_spec.yaml` (for target_folders, shared_modules)
5. The `.iq-workstreams/config.yaml` (for shardclass_folder, cross_province_shared_files)
6. The target folder .vbproj files listed in change_spec.yaml

If any of these are missing, STOP and report:
```
[Analyzer] Cannot proceed -- missing required file: {path}
            Was the Decomposer completed? Check manifest.yaml for decomposer.status = "completed".
```

### Step 1: Load Context

**Action:** Read all Decomposer output and build the working context.

1.1. Read `analysis/dependency_graph.yaml`. Extract:
   - `execution_order` (list of operation IDs -- the Analyzer processes in this order)
   - `shared_operations` and `lob_operations` (for quick lookup of operation metadata)
   - `out_of_scope` (skip these SRDs entirely)

1.2. Read `parsed/change_spec.yaml`. Extract:
   - `province` (e.g., "SK")
   - `province_name` (e.g., "Saskatchewan")
   - `effective_date` (e.g., "20260101")
   - `target_folders[]` (path + vbproj for each LOB)
   - `shared_modules[]` (files shared across LOBs)

1.3. Read `.iq-workstreams/config.yaml`. Extract:
   - `provinces.{province_code}.shardclass_folder` (e.g., "SHARDCLASS" or "SharedClass")
   - `cross_province_shared_files` (list of files that must NEVER be auto-modified)

1.4. Read each operation file from `analysis/operations/op-*.yaml`. Store in memory
indexed by operation ID. Verify each file has the required Decomposer fields:
`id`, `srd`, `file`, `pattern`, `agent`.

1.5. If any operation has `needs_review: true` and `file: null`, set it aside for
developer guidance in Step 10.

### Step 2: Parse .vbproj Files and Build the File Reference Map

**Action:** Read each target folder's .vbproj to discover which Code/ files each project
compiles. Build a map from Code/ filenames to the .vbproj files that compile them.

2.1. For each entry in `target_folders`, locate the .vbproj file on disk. The path
is relative to the codebase root:

```python
import os
import xml.etree.ElementTree as ET

codebase_root = manifest["codebase_root"]  # Discovered at runtime from manifest.yaml
vbproj_path = os.path.join(codebase_root, target_folder["path"], target_folder["vbproj"])
```

If the .vbproj file does not exist, STOP and report:
```
[Analyzer] ERROR: .vbproj file not found: {vbproj_path}
            Was IQWiz run to create this version folder?
```

2.2. Parse the .vbproj as XML.

**CRITICAL: Use an XML parser, NOT regex.** The .vbproj is MSBuild XML with
multiple `<ItemGroup>` blocks containing `<Compile Include="...">` elements.

```python
tree = ET.parse(vbproj_path)
root = tree.getroot()

# MSBuild uses a namespace -- strip it for easier element access
ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"

compile_includes = []
for item_group in root.findall(f"{ns}ItemGroup"):
    for compile_elem in item_group.findall(f"{ns}Compile"):
        include_path = compile_elem.get("Include")
        if include_path:
            # Check for Condition attribute (flag for developer review)
            condition = compile_elem.get("Condition")
            # Ignore <Link> child elements (cosmetic display names)
            compile_includes.append({
                "include": include_path,
                "condition": condition,
                "vbproj": vbproj_path,
                "lob": target_folder["lob"]
            })
```

**IMPORTANT:** The .vbproj XML uses the MSBuild namespace
`http://schemas.microsoft.com/developer/msbuild/2003`. All element lookups must
include this namespace prefix, or use a namespace-stripping approach. Without this,
`findall("ItemGroup")` returns nothing.

2.3. For each `<Compile Include>` path, resolve the relative path to an absolute path:

```python
vbproj_dir = os.path.dirname(os.path.abspath(vbproj_path))
resolved = os.path.normpath(os.path.join(vbproj_dir, include_path))
# Convert to forward-slash codebase-relative path
relative_to_root = os.path.relpath(resolved, codebase_root).replace("\\", "/")
```

2.4. Classify each resolved file using the File Classification Rules:

```
CLASSIFICATION RULES (first match wins)
------------------------------------------------------------

RULE 1: Cross-Province Shared (NEVER MODIFY)
  Match: resolved path starts with "{codebase_root}/Code/"
         (NOT "{codebase_root}/{Province}/Code/")
  Pattern: Include contains "..\..\..\Code\" (3+ levels up)
  Examples: Code/PORTCommonHeat.vb, Code/mod_VICCAuto.vb
  Result: classification = "cross_province_shared"
  Action: NEVER generate line numbers for these. If an operation targets one, flag.

RULE 2: Shared Engine File (NEVER MODIFY)
  Match: resolved path contains "Shared Files for Nodes/"
  Pattern: Include contains "..\..\..\..\Shared Files for Nodes\"
  Result: classification = "engine_shared"
  Action: Ignore completely. Not editable by the plugin.

RULE 3: Hub-Level File (NEVER MODIFY)
  Match: resolved path contains "/Hub/"
  Pattern: Include contains "..\..\..\Hub\"
  Result: classification = "hub_shared"
  Action: Ignore. Not editable by the plugin.

RULE 4: SHARDCLASS File
  Match: resolved path contains "/SHARDCLASS/" or "/SharedClass/"
  Pattern: Include contains "..\..\SHARDCLASS\" or "..\..\SharedClass\"
  Result: classification = "shardclass"
  Action: Include in blast radius. Flag if operations would modify.

RULE 5: Province Code/ File
  Match: resolved path is in "{Province}/Code/"
  Pattern: Include contains "..\..\Code\" (2 levels up from version folder)
  Result: classification = depends on further analysis (shared_module, lob_specific, cross_lob)
  Action: This is where most operations target. See Step 2.5 for sub-classification.

RULE 6: Local File
  Match: resolved path is inside the version folder itself
  Pattern: Include has no ".." prefix (e.g., "CalcMain.vb", "ResourceID.vb")
  Result: classification = "local"
  Action: Direct edits in the version folder.
```

2.5. Sub-classify Province Code/ files by checking the File Reference Map:

For each Province Code/ file, check how many .vbproj files compile it:

```python
from collections import defaultdict

# file_refs[code_file] = set of LOBs that compile it
file_refs = defaultdict(set)
for entry in all_compile_includes:
    if entry["classification"] == "province_code":
        file_refs[entry["relative_to_root"]].add(entry["lob"])
```

Apply sub-classification:
```
- File in shared_modules list from change_spec.yaml --> "shared_module"
- File compiled by 2+ LOBs AND matches mod_Common_*Hab* or modFloaters* --> "shared_module"
- File compiled by 2+ LOBs AND matches Option_* or Liab_* --> "cross_lob"
- File compiled by 1 LOB only --> "lob_specific"
```

2.6. Build the **File Reference Map** -- the master data structure:

```
FILE REFERENCE MAP
------------------------------------------------------------
Code/ File                                  Classification     Compiled By
mod_Common_SKHab20250901.vb                 shared_module      Home, Condo, Tenant, FEC, Farm, Seasonal
CalcOption_SKHOME20250901.vb                lob_specific       Home
CalcOption_SKCONDO20250901.vb               lob_specific       Condo
Option_Bicycle_SKHome20220502.vb            cross_lob          Home, Condo
Liab_RentedDwelling_SKHome20240801.vb       cross_lob          Home, Condo
modFloatersAndScheduledArticles_SKHAB20220502.vb  shared_module  Home, Condo, Tenant, FEC, Farm, Seasonal
Code/PORTCommonHeat.vb                      cross_province     Home, Condo, Tenant, FEC, Farm, Seasonal
```

2.7. If any `<Compile>` element has a `Condition` attribute, flag it:

```
[Analyzer] WARNING: Conditional compilation detected in {vbproj}:
            <Compile Include="{path}" Condition="{condition}"/>
            This file may only be compiled in certain build configurations.
            Please verify whether this file is active in the current build.
```

2.8. **Extract date from each Code/ filename.** For determining source vs target files:

```python
import re

def extract_date(filename):
    """Extract YYYYMMDD date from a VB filename."""
    match = re.search(r'(\d{8})\.vb$', filename)
    return match.group(1) if match else None
```

### Step 3: Resolve Source Files for Each Operation

**Action:** For each operation, find the ACTUAL source file currently referenced by the
.vbproj. The Decomposer's `file` field uses the target date, but the real file on disk
may have an older date.

3.1. For each operation, extract the base name pattern from the `file` field:

```python
def get_file_pattern(target_filename, effective_date):
    """
    Convert target filename to a pattern for matching against .vbproj references.

    Example:
      target: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
      effective_date: "20260101"
      pattern: "mod_Common_SKHab"  (the part before the date)
    """
    basename = os.path.basename(target_filename)  # mod_Common_SKHab20260101.vb
    # Remove date + .vb extension
    pattern = re.sub(r'\d{8}\.vb$', '', basename)  # mod_Common_SKHab
    return pattern
```

3.2. Search the File Reference Map for a file matching that pattern:

```python
def find_source_file(file_pattern, file_reference_map):
    """Find the current file in .vbproj that matches the base pattern."""
    matches = []
    for code_file in file_reference_map:
        basename = os.path.basename(code_file)
        file_base = re.sub(r'\d{8}\.vb$', '', basename)
        if file_base == file_pattern:
            matches.append(code_file)
    return matches
```

If 0 matches: The file is not in any .vbproj. This means either:
- The Decomposer has a wrong file name --> STOP, report error
- The file is a new file to be created (for logic-modifier operations)

If 1 match: This is the source file. Record it.

If 2+ matches: Multiple date versions exist for the same base file. Pick the one
with the most recent date that is NOT the target date. Report all matches.

3.3. Compare source file date to target date:

```python
source_date = extract_date(source_file)  # e.g., "20250901"
target_date = effective_date             # e.g., "20260101"

needs_copy = (source_date != target_date)
```

3.4. Update the operation with source file information:

```yaml
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
```

3.5. **Compute the source file hash** for TOCTOU protection:

```python
import hashlib

def hash_file(filepath):
    """SHA-256 hash of file contents for TOCTOU protection."""
    with open(filepath, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()
```

Record `file_hash` in the operation. This hash will be checked again before the
Rate Modifier or Logic Modifier writes changes. If the hash differs, the file was
modified between analysis and execution -- ABORT that operation.

3.6. **Check if target file already exists on disk:**

- If target file does NOT exist: normal case, `needs_copy: true`
- If target file DOES exist AND matches source hash: safe (untouched copy exists,
  `needs_copy: false` since copy already done)
- If target file DOES exist AND hash DIFFERS from source: someone already modified it.
  Warn the developer:

```
[Analyzer] WARNING: Target file already exists with DIFFERENT content:
            Target: {target_file}
            Source hash: {source_hash}
            Target hash: {target_hash}

            Options:
              a) Use existing target file (keep someone else's changes)
              b) Overwrite target with fresh copy of source
              c) Abort -- investigate before proceeding
```

### Step 4: Read Source Files and Find Functions

**Action:** Read each source file and locate the functions referenced by operations.

**4.0 Load Discovery Hints (Optional)**

Before searching from scratch, check if the Discovery Agent produced a code map:

```python
import os

workstream_dir = f".iq-workstreams/changes/{workstream_name}"
discovery_path = os.path.join(workstream_dir, "analysis/code_discovery.yaml")
discovery_hints = {}

if file_exists(discovery_path):
    try:
        discovery = load_yaml(discovery_path)
    except Exception:
        discovery = {}  # Malformed YAML — treat as absent, fall through to full search
    for srd_id, target in discovery.get("srd_targets", {}).items():
        if target.get("resolved_function"):
            discovery_hints[srd_id] = {
                "source_file_hint": target["resolved_file"],
                "function_name_hint": target["resolved_function"],
                "function_line_hint": target.get("function_line_start"),
                "function_length_hint": target.get("function_length"),
                "returns_hint": target.get("returns"),
                "peer_functions": target.get("related_functions", []),
            }
    # Discovery peer_functions feed into Step 5.10.5 (FUB nearby_functions).
    # Stored here, then merged into collect_nearby_functions() in Step 5.10.
    discovery_peers = discovery.get("peer_functions", {})
else:
    discovery_peers = {}

# Make discovery_peers available to Step 5.10 FUB generation.
# When collect_nearby_functions() runs for a target function, check
# discovery_peers[target_function_name] for additional peer entries.
# These supplement (not replace) the pattern-library-based nearby search.
# Each discovery peer entry has: name, file, line_start, similarity.
# Convert to nearby_functions format: add call_sites=None, status="ACTIVE"
# so they integrate with the existing FUB schema.
```

When Discovery hints exist for an operation's SRD:
- **Start** the function search at `function_line_hint` (skip full-file scan)
- **Verify** by reading actual code (trust but verify — Discovery may be stale)
- **Use** `peer_functions` as additional input for Step 5.10.5 (FUB nearby_functions)
- If the hint doesn't match (function moved or renamed), fall through to full search

When Discovery hints do NOT exist: search from scratch (existing behavior, unchanged).

**Large file guidance:** For files exceeding 2,000 lines, read in focused chunks: first
build the function index from function/sub declarations (scan for `Function|Sub` lines),
then read only the target function's line range. Avoid loading entire 4,500-line files
into context at once.

4.1. Group operations by source file to avoid reading the same file multiple times.

```python
from collections import defaultdict

ops_by_file = defaultdict(list)
for op in operations:
    ops_by_file[op["source_file"]].append(op)
```

4.2. For each source file, read the entire file into memory.

**Safe arithmetic evaluator** (used instead of raw `eval()` for defense-in-depth):

```python
import ast

def safe_eval_arithmetic(expr_str):
    """Evaluate a simple arithmetic expression using AST whitelisting.

    Only allows: numeric literals, +, -, *, /, unary +/-.
    Rejects function calls, attribute access, imports, etc.
    Raises ValueError if the expression contains disallowed nodes.
    """
    tree = ast.parse(expr_str, mode='eval')
    ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                     ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"Disallowed AST node: {type(node).__name__}")
    return eval(compile(tree, "<safe_eval>", "eval"))
```

```python
def read_source_file(filepath):
    """Read VB.NET source file, return list of (line_number, content) tuples."""
    codebase_root = manifest["codebase_root"]  # Discovered at runtime from manifest.yaml
    full_path = os.path.join(codebase_root, filepath)
    with open(full_path, "r", encoding="utf-8-sig") as f:  # utf-8-sig handles BOM
        lines = f.readlines()
    return [(i + 1, line.rstrip("\n\r")) for i, line in enumerate(lines)]
```

**NOTE:** VB.NET files from Visual Studio often have a UTF-8 BOM (Byte Order Mark).
Use `utf-8-sig` encoding to handle this transparently.

4.3. **Build a function index** for the file. Scan for all `Sub` and `Function`
declarations and their matching `End Sub` / `End Function`:

```python
def build_function_index(lines):
    """
    Find all function/sub boundaries in a VB.NET file.

    Returns: list of {name, type, line_start, line_end, param_types, return_type}
    """
    import re
    functions = []
    # Match: [Private|Public|Friend] [Shared] [Sub|Function] Name(...)
    func_pattern = re.compile(
        r'^\s*(Private|Public|Friend)?\s*(Shared)?\s*(Sub|Function)\s+(\w+)',
        re.IGNORECASE
    )
    end_pattern = re.compile(
        r'^\s*End\s+(Sub|Function)',
        re.IGNORECASE
    )
    # Parse parameter types from declaration: ByVal/ByRef name As Type
    param_pattern = re.compile(
        r'(?:ByVal|ByRef)?\s*(\w+)\s+As\s+(\w+)',
        re.IGNORECASE
    )
    # Parse return type: ) As Type
    return_type_pattern = re.compile(
        r'\)\s*As\s+(\w+)',
        re.IGNORECASE
    )

    # NOTE: VB.NET line continuation (`_` at end of line) could cause multi-line
    # function declarations to be missed. In the current Portage Mutual codebase,
    # this has not been observed for Sub/Function declarations, but if the function
    # index misses a function, check for line continuations. Defensive approach:
    # if a line ends with ` _`, concatenate it with the next line before matching.

    stack = []  # For nested functions (rare in VB.NET modules but defensive)
    for line_num, content in lines:
        # Skip commented lines (VB.NET: ' apostrophe or REM keyword)
        stripped = content.lstrip()
        if stripped.startswith("'") or stripped.upper().startswith("REM "):
            continue

        func_match = func_pattern.match(content)
        if func_match:
            # Extract param_types from the signature
            param_types = [
                {"name": m.group(1), "type": m.group(2)}
                for m in param_pattern.finditer(content)
            ]
            # Extract return_type (Function only)
            func_type = func_match.group(3)  # "Sub" or "Function"
            return_type = None
            if func_type.lower() == "function":
                rt_match = return_type_pattern.search(content)
                return_type = rt_match.group(1) if rt_match else "Variant"

            stack.append({
                "name": func_match.group(4),
                "type": func_type,
                "line_start": line_num,
                "line_end": None,
                "param_types": param_types,
                "return_type": return_type,
            })

        end_match = end_pattern.match(content)
        if end_match and stack:
            func = stack.pop()
            func["line_end"] = line_num
            functions.append(func)

    return functions
```

4.4. **Find the target function** for each operation:

**Discovery hint fast path:** Before searching the full function index, check if
Discovery provided a line hint for this operation's SRD:

```python
def try_discovery_hint(op, function_index, discovery_hints):
    """Try to resolve function via Discovery hint before full search.

    Returns: matching function dict, or None (fall through to full search).
    """
    srd_id = op.get("srd")
    if not srd_id or srd_id not in discovery_hints:
        return None

    hint = discovery_hints[srd_id]
    hint_name = hint.get("function_name_hint")
    hint_line = hint.get("function_line_hint")

    if not hint_name:
        return None

    # Verify the hint matches the operation's expected function name
    op_function = op.get("function", "")
    if op_function and op_function.lower() != hint_name.lower():
        # Operation targets a different function than Discovery resolved
        # (e.g., Decomposer split into sub-operations) — skip hint
        return None

    # Check if the function index has this function at the expected line
    for func in function_index:
        if func["name"].lower() == hint_name.lower():
            if hint_line and abs(func["line_start"] - hint_line) <= 5:
                # Line matches within tolerance — high confidence
                return func
            elif not hint_line:
                # No line hint but name matches — use it
                return func
    return None  # Hint stale or moved — fall through to full search
```

For each operation, call `try_discovery_hint()` first. If it returns a match,
skip the full `find_function()` search. If it returns None, proceed normally.

For operations where `function` is not null, search the function index:

```python
def find_function(function_index, function_hint):
    """
    Find a function by name. Supports exact match and pattern match.

    Returns: list of matching functions (may be 0, 1, or many)
    """
    import re
    # Try exact match first
    exact = [f for f in function_index if f["name"] == function_hint]
    if exact:
        return exact

    # Try case-insensitive exact match
    exact_ci = [f for f in function_index if f["name"].lower() == function_hint.lower()]
    if exact_ci:
        return exact_ci

    # Try pattern match (function_hint may contain wildcards)
    # Convert hint to regex: "GetBasePrem*" -> "GetBasePrem.*"
    pattern = function_hint.replace("*", ".*")
    regex = re.compile(f"^{pattern}$", re.IGNORECASE)
    pattern_matches = [f for f in function_index if regex.match(f["name"])]
    return pattern_matches
```

4.5. **Handle search results:**

**0 matches (function not found):**
Show similar function names and ask the developer:

```
[Analyzer] Function not found: "{function_hint}" in {source_file}

            Searched {len(function_index)} functions. Similar names:
              1. SetDisSur_Deductible (line 2108)       -- closest match
              2. SetDisc_Claims (line 1602)
              3. SetDisc_Age (line 1694)
              4. SetDisc_NewHome (line 1780)

            Which function should operation {op_id} target?
            (Enter a number, or type the function name)
```

Use a simple edit-distance or prefix-match heuristic to rank candidates.

**1 match (unambiguous):**
Record the function boundaries and proceed to Step 5.

**2+ matches (ambiguous):**
Show all matches and ask the developer:

```
[Analyzer] Multiple functions match pattern "{function_hint}" in {source_file}:

            1. GetBasePrem_FarmMobileFEC (lines 2974-3050)
            2. GetBasePrem_FarmMobileHome (lines 3052-3112)
            3. GetBasePrem_HabMobileHome (lines 3210-3385)
            4. GetBasePremium_Home (lines 3387-3543)         -- uses DAT files, no Array6
            5. GetBasePremiumTenantHab (lines 4291-4369)     -- uses DAT files, no Array6

            Which function(s) should operation {op_id} target?
            (Enter numbers, e.g., "1, 2" or "all")

            NOTE: Functions 4 and 5 use GetPremFromResourceFile() for base rates
            (DAT file lookups, not Array6 in code). They likely cannot be modified
            by rate-modifier.
```

4.5.1. **Partial Module fallback: project-wide function search.**

VB.NET uses `Partial Public Module` which splits a module's code across multiple
source files. Example: `CalcOption_SKHOME20260101.vb` calls `Option_Bicycle()`, but
that function lives in `Option_Bicycle_SKHome20220502.vb` — a separate Code/ file
compiled into the same project via the .vbproj.

**If Step 4.5 yields 0 matches** (function not found in the specified file), BEFORE
prompting the developer, perform a project-wide search:

```python
def search_project_for_function(function_hint, source_file, file_reference_map):
    """
    Fallback search: scan ALL .vb files in the same .vbproj for the function.
    Triggered when function not found in the Decomposer's suggested file.

    file_reference_map: dict of {relative_path: absolute_path} from the .vbproj
    """
    found_in = []
    for rel_path, abs_path in file_reference_map.items():
        if rel_path == source_file:
            continue  # Already searched this one
        try:
            lines = read_source_file(rel_path)
            index = build_function_index(lines)
            matches = find_function(index, function_hint)
            if matches:
                found_in.append({
                    "file": rel_path,
                    "functions": matches
                })
        except Exception:
            continue  # Skip unreadable files
    return found_in
```

If the project-wide search finds the function in a DIFFERENT file:
```
[Analyzer] Function "{function_hint}" not found in {source_file}.
           Found in {alt_file} (Partial Module -- same project).
           Redirecting operation {op_id} to {alt_file}.
           (source_file updated in operation YAML)
```

Update the operation's `source_file` field and proceed. Log the redirect in
`analysis_notes`. If the function is found in MULTIPLE files (unlikely but
possible with overloaded names), present all candidates to the developer.

If the project-wide search also yields 0 matches, THEN show similar names as
in Step 4.5 "0 matches" case.

**Cost guard:** Project-wide search reads function declarations only (not full file
bodies). For a typical .vbproj with 15-25 Compile Include entries, this adds
~2-3 seconds and ~5,000-10,000 tokens. Only triggered for 0-match cases.

4.6. For operations where `function` IS null (module-level operations like adding
constants), skip function search. Instead, find the appropriate insertion area:

- For `location: "module-level constants"`: find the last `Public Const` or
  `Private Const` line before the first `Sub` or `Function` declaration.
- For `location: "end of module"`: find the `End Module` line.

### Step 5: Search Within Functions for Target Lines

**Action:** For each operation, apply the pattern-specific search strategy within the
confirmed function boundaries to find the exact lines to modify.

#### 5.1 Pattern: base_rate_increase

**Goal:** Find all Array6 assignments (rate values) within the function.

**IMPORTANT: Auto base rates are scalar, not Array6.** In Auto LOBs (mod_Algorithms),
base rates use simple scalar assignments (`baseRate = 66.48`), NOT Array6. If the
function has 0 Array6 assignments but contains `baseRate = {number}` patterns
inside Select Case blocks, inform the developer:

```
[Analyzer] Function "{function_name}" has 0 Array6 assignments.
           Found {N} scalar base rate assignments (baseRate = {value}).
           Auto LOB base rates use scalar assignments, not Array6 tables.
           To modify these, the operation should use pattern "factor_table_change"
           targeting individual Case values (e.g., baseRate = 66.48 -> 69.80).
```

This is not a failure — it's a pattern mismatch. The developer should re-classify
the operation or the Intake should have set the pattern differently. Do NOT
attempt to modify scalar assignments with the Array6 multiplication logic.

**WARNING: Multi-line Array6 calls.** VB.NET allows line continuation with ` _`
(space-underscore) at end of line. An Array6 call may span multiple lines:
```vb
varRates = Array6(105.01, 103.74, _
                  311.9, 375.17)
```
The regex `Array6\(([^)]+)\)` will NOT match these. The `find_array6_assignments`
function below handles this with explicit line-continuation joining. If joining is
not feasible for a given call, the line is added to `skipped_lines` with reason
`"Array6 with unclosed parenthesis -- possible multi-line call, manual review needed"`.

5.1.1. Extract the function body (lines between `function_line_start` and
`function_line_end`):

```python
def get_function_body(all_lines, func):
    """Get lines within function boundaries."""
    return [(num, content) for num, content in all_lines
            if func["line_start"] <= num <= func["line_end"]]
```

5.1.2. Find all Array6 assignment lines:

```python
def extract_array6_args(content):
    """
    Extract Array6 arguments using parenthesis-depth-aware parsing.
    Handles nested parens like CInt(30 + 10) or Math.Round(x).

    The naive regex Array6\(([^)]+)\) stops at the first ), which truncates
    args containing nested function calls. This helper walks forward from
    the opening ( counting depth until it returns to zero.

    Returns: args string (without outer parens) or None if unbalanced.
    """
    idx = content.find("Array6(")
    if idx < 0:
        return None
    start = idx + len("Array6(")  # index after the opening (
    depth = 1
    pos = start
    while pos < len(content) and depth > 0:
        if content[pos] == "(":
            depth += 1
        elif content[pos] == ")":
            depth -= 1
        pos += 1
    if depth != 0:
        return None  # Unbalanced -- possible multi-line or malformed
    return content[start:pos - 1]  # Everything between outer ( and )


def join_continued_lines(function_body, start_idx):
    """
    Join VB.NET line-continuation lines starting at start_idx.
    Returns (joined_content, span_end_idx) where span_end_idx is the last
    index consumed from function_body.

    Handles TWO continuation styles:
    1. Explicit: trailing " _" (traditional VB.NET)
    2. Implicit (VB.NET 10+): line ends with a binary operator, comma, or open paren
       Examples:
         If x + y +       <-- implicit continuation (trailing +)
            z > 0 Then
         Array6(1, 2,     <-- implicit continuation (trailing ,)
            3, 4)
    """
    import re
    joined = function_body[start_idx][1].rstrip()
    end_idx = start_idx

    # Implicit continuation tokens: binary operators, comma, open paren
    implicit_pattern = re.compile(
        r'(\+|-|\*|/|\\|&|,|\(|'
        r'\b(And|Or|OrElse|AndAlso|Xor|Mod|Like|Is|IsNot)\s*)$',
        re.IGNORECASE
    )

    while end_idx + 1 < len(function_body):
        # Check for explicit continuation
        if joined.endswith(" _"):
            joined = joined[:-2]  # Remove trailing " _"
            end_idx += 1
            joined += " " + function_body[end_idx][1].strip()
            continue

        # Check for implicit continuation (VB.NET 10+)
        stripped = joined.rstrip()
        if implicit_pattern.search(stripped):
            end_idx += 1
            joined = stripped + " " + function_body[end_idx][1].strip()
            continue

        break  # No continuation detected

    return joined, end_idx


def find_array6_assignments(function_body):
    """
    Find Array6() calls that are rate value assignments (LHS of =).
    EXCLUDE Array6 inside IsItemInArray() or other non-assignment contexts.
    Handles multi-line Array6 calls (VB.NET line continuation with " _").
    Handles nested parentheses in arguments like CInt(30 + 10).
    """
    import re
    targets = []
    skipped = []

    i = 0
    while i < len(function_body):
        line_num, content = function_body[i]
        stripped = content.lstrip()

        # Skip commented lines (VB.NET: ' apostrophe or REM keyword)
        if stripped.startswith("'") or stripped.upper().startswith("REM "):
            i += 1
            continue

        # Check if line contains Array6
        if "Array6(" not in content:
            i += 1
            continue

        # RULE: Array6 inside IsItemInArray() = membership test, NOT a rate
        if "IsItemInArray" in content:
            skipped.append({
                "line": line_num,
                "content": content.rstrip(),
                "reason": "Array6 inside IsItemInArray() -- membership test, not a rate value"
            })
            i += 1
            continue

        # RULE: Array6 as argument to another function (not a variable assignment).
        # Example: FindHeatingSystem(p_obj, , Array6(HF_ELECTRIC, HF_GAS))
        # Detect by checking: if Array6( appears BUT there is no `= Array6(` pattern,
        # AND the Array6 is nested inside another function call's parentheses.
        # Note: The assignment check below (line ~1006) catches this as "non-assignment
        # context" and skips it. This explicit check provides a clearer skip reason.
        if "Array6(" in content and not re.search(r'\w+\s*=\s*Array6\(', content):
            # Array6 used as function argument, loop collection, or other non-assignment
            skipped.append({
                "line": line_num,
                "content": content.rstrip(),
                "reason": "Array6 in non-assignment context (function argument or expression) -- not a rate value"
            })
            i += 1
            continue

        # Try to extract args from this line (handles nested parens)
        working_content = content
        span_end = i

        # Check for multi-line continuation: if Array6( is present but
        # extract_array6_args returns None, the parens may span multiple lines
        args_str = extract_array6_args(working_content)
        if args_str is None and content.rstrip().endswith(" _"):
            # Join continuation lines and retry
            working_content, span_end = join_continued_lines(function_body, i)
            args_str = extract_array6_args(working_content)

        if args_str is None:
            # Still can't parse -- add to skipped
            skipped.append({
                "line": line_num,
                "content": content.rstrip(),
                "reason": "Array6 with unclosed parenthesis -- possible multi-line call, manual review needed"
            })
            i = span_end + 1
            continue

        # RULE: Array6 assigned to a variable (LHS of =) = rate value
        # Pattern: identifier = Array6(...)
        if re.search(r'\w+\s*=\s*Array6\(', working_content):
            args = [a.strip() for a in args_str.split(",")]

            # RULE: Array6 with ALL non-numeric arguments = enum/constant collection,
            # NOT a rate value. Example:
            #   varCovTypes = Array6(TBWApplication.BasePremEnum.bpeTPLBI, ...)
            # These are iteration collections or lookup keys, not rate tables.
            # Detect: if EVERY argument contains a dot (qualified enum name) or is
            # a non-numeric identifier (no digits), skip the line.
            all_non_numeric = all(
                not re.match(r'^-?[\d.]+$', a.strip()) and  # Not a plain number
                not re.match(r'^[\d+\-*/.()\s]+$', a.strip())  # Not arithmetic
                for a in args if a.strip()
            )
            if all_non_numeric and args:
                skipped.append({
                    "line": line_num,
                    "content": content.rstrip(),
                    "reason": "Array6 arguments are all non-numeric (enum/constant collection) -- not rate values"
                })
                i = span_end + 1
                continue

            # Sanity check (Fix 16): balanced parens, no empty args, reasonable count
            issues = []
            if any(a == "" for a in args):
                issues.append("empty argument (consecutive commas)")
            if len(args) > 20:
                issues.append(f"unusually high arg count ({len(args)})")
            # Check balanced parens in each arg
            for a in args:
                if a.count("(") != a.count(")"):
                    issues.append(f"unbalanced parens in arg '{a}'")
                    break

            entry = {
                "line": line_num,
                "content": content.rstrip() if span_end == i else working_content,
                "args": args,
                "value_count": len(args)
            }

            # DISAMBIGUATION CONTEXT: Capture 1-2 surrounding lines for Edit tool
            # uniqueness. When the same Array6 content appears on multiple lines
            # within the same function (e.g., `Array6(0, 0, 0, 0, 324.29, 462.32)`
            # at BOTH line 4055 and 4079 in GetLiabilityBundlePremiums), the Edit
            # tool needs surrounding context to produce a unique old_string.
            #
            # Rule: capture the 1 line above and 1 line below the target line
            # (within function boundaries). Workers use these as multi-line
            # old_string to disambiguate identical content lines.
            ctx_above = []
            ctx_below = []
            for fb_idx, (fb_num, fb_content) in enumerate(function_body):
                if fb_num == line_num:
                    # 1 line above (within function)
                    if fb_idx > 0:
                        above_num, above_content = function_body[fb_idx - 1]
                        ctx_above.append({"line": above_num, "content": above_content.rstrip()})
                    # 1 line below (within function)
                    if fb_idx + 1 < len(function_body):
                        below_num, below_content = function_body[fb_idx + 1]
                        ctx_below.append({"line": below_num, "content": below_content.rstrip()})
                    break
            entry["context_above"] = ctx_above
            entry["context_below"] = ctx_below

            # Check for arithmetic expressions and precompute evaluated_args
            has_expr = any(re.search(r'[+\-*/]', a) for a in args
                          if not a.lstrip().startswith("-"))  # Don't flag negative numbers
            if has_expr:
                entry["has_expressions"] = True
                try:
                    # Evaluate simple arithmetic only (no function calls)
                    evaluated = []
                    for a in args:
                        clean = a.strip()
                        if re.match(r'^[\d+\-*/.()\s]+$', clean):
                            # Use AST-based safe eval (same as rate-modifier's
                            # safe_eval_arithmetic) instead of raw eval() for
                            # defense-in-depth. Whitelists only numeric nodes
                            # and arithmetic operators.
                            evaluated.append(round(safe_eval_arithmetic(clean), 4))
                        else:
                            evaluated.append(clean)  # Keep as-is if contains function calls
                    entry["evaluated_args"] = evaluated
                except Exception:
                    pass  # If eval fails, omit evaluated_args -- manual review

            if issues:
                entry["sanity_warnings"] = issues
                # Record in analysis_notes but don't block
            targets.append(entry)
        else:
            # Array6 in some other context (rare) -- flag for review
            skipped.append({
                "line": line_num,
                "content": content.rstrip(),
                "reason": "Array6 in non-assignment context -- review manually"
            })

        i = span_end + 1

    return targets, skipped
```

5.1.3. **Filter out default initializations** (all-zero Array6 calls):

```python
def is_default_init(args):
    """Check if Array6 is all zeros (default init, not a real rate)."""
    return all(a.strip() == "0" for a in args)
```

Lines with all-zero Array6 go into `skipped_lines` with reason
`"Default initialization (all zeros) -- no rate values to modify"`.

5.1.4. **Determine the context** for each target line. Walk backwards from the
target line to find the enclosing Select Case and If/Else structure.

**NOTE:** This context is best-effort cosmetic display only -- it is never used for
matching or decision-making. The context string is shown to the developer for
orientation but is not relied upon by downstream agents. Full nesting-depth tracking
is intentionally omitted here because the cost outweighs the benefit for a display-only
field.

```python
def determine_context(all_lines, target_line_num, func_start):
    """
    Walk backwards from target line to build the nesting context.

    Returns string like: "Farm > PRIMARYITEM > Enhanced Comp"
    """
    # Build line-number -> content lookup for direct access
    # (avoids fragile index arithmetic on the tuple list)
    line_map = {num: content for num, content in all_lines}

    context_parts = []
    for line_num in range(target_line_num - 1, func_start - 1, -1):
        content = line_map.get(line_num, "")
        stripped = content.strip()

        if stripped.startswith("Case ") and not stripped.startswith("Case Else"):
            context_parts.insert(0, stripped)
        elif stripped.startswith("Select Case"):
            context_parts.insert(0, stripped)
        elif stripped.startswith("If ") or stripped.startswith("ElseIf "):
            context_parts.insert(0, stripped.split(" Then")[0])
        elif stripped == "Else":
            context_parts.insert(0, "Else")

    return " > ".join(context_parts[-3:])  # Last 3 levels of nesting
```

5.1.5. **Determine rounding per line** (see Step 6 for the full algorithm).

5.1.6. Record all findings in the operation's `target_lines` and `skipped_lines` arrays.

#### 5.2 Pattern: factor_table_change

**Goal:** Find the specific `Case {value}` block and all values within it.

5.2.1. Within the function body, find the target Case block:

**IMPORTANT: Nested Select Case depth tracking.** A function may contain nested
Select Case blocks (e.g., `Select Case territory` inside `Case "Home"`). Without
depth tracking, `Case 5000` inside an inner Select Case would falsely match when
searching at the outer level. The fix: only match `Case {value}` when
`select_depth == 1` (the outermost Select Case level for the target search).

**Example of the false-match scenario:**
```vb
Select Case coverageType           ' <-- depth 1 (target level)
    Case "Home"
        Select Case deductible     ' <-- depth 2 (inner, NOT target)
            Case 5000              ' <-- FALSE MATCH if depth not tracked
                dblDiscount = -0.20
        End Select                 ' <-- back to depth 1
    Case 5000                      ' <-- TRUE MATCH at depth 1
        dblFactor = 1.05
End Select
```

```python
def find_case_block(function_body, case_value, target_select_depth=1):
    """
    Find a Case block matching the given value.

    BEWARE: A function can have MULTIPLE Select Case blocks,
    and the same Case value might appear in different blocks.
    Find ALL matches. Only match at select_depth == target_select_depth
    to find the correct nesting level.

    Args:
        function_body: list of (line_num, content) tuples
        case_value: the Case value to find
        target_select_depth: which Select Case nesting level to match at.
            Default 1 = outermost Select Case.
            Set to 2 for nested Select Case targets (e.g., when the target
            Case is inside an inner Select Case within an outer Select Case).
            The Analyzer auto-detects this from the function structure.

    DEPTH DETECTION RULE (for Analyzer):
    When the Decomposer specifies a case_value AND the function has nested
    Select Case blocks, the Analyzer MUST determine the correct depth:
    1. Search ALL depths for the case_value
    2. If found at exactly ONE depth -> use that depth
    3. If found at MULTIPLE depths -> present ALL to developer, record
       the confirmed depth as `target_select_depth` in the operation YAML
    4. If NOT found at any depth -> report FUNCTION_MATCH_FAILED
    """
    import re
    matches = []
    case_else_blocks = []
    select_depth = 0
    current_select_var = None

    # Build dict for forward scanning (avoids fragile index arithmetic)
    line_list = list(function_body)  # Preserve ordering for forward scan
    line_idx = {num: idx for idx, (num, _) in enumerate(line_list)}

    for line_num, content in line_list:
        stripped = content.strip()
        # Skip commented lines (VB.NET: ' apostrophe or REM keyword)
        if stripped.startswith("'") or stripped.upper().startswith("REM "):
            continue

        if stripped.startswith("Select Case"):
            select_depth += 1
            if select_depth == target_select_depth:
                current_select_var = stripped

        elif stripped.startswith("End Select"):
            select_depth -= 1

        # Only match Case at the target depth level
        # Build match patterns for multiple VB.NET Case syntaxes:
        #   Case 5000            -- exact numeric value
        #   Case "5000"          -- string-quoted numeric (common for coverage amounts)
        #   Case 0 To 25         -- range (matches if case_value is the start value)
        #   Case Is <= 3000      -- comparison operator
        #   Case "val1", "val2"  -- multi-value (matches if case_value is ANY value)
        elif select_depth == target_select_depth and (
            re.match(rf'^Case\s+{re.escape(str(case_value))}\s*($|:|\s)', stripped) or
            re.match(rf'^Case\s+"{re.escape(str(case_value))}"\s*($|:|\s|,)', stripped) or
            re.match(rf'^Case\s+{re.escape(str(case_value))}\s+To\s+', stripped) or
            re.match(rf'^Case\s+\w+\s+To\s+{re.escape(str(case_value))}\s*($|:|\s)', stripped) or
            re.match(rf'^Case\s+Is\s*[<>=!]+\s*{re.escape(str(case_value))}\s*($|:|\s)', stripped) or
            ('"' + str(case_value) + '"' in stripped and stripped.startswith("Case "))
        ):
            # Found a matching Case -- handles exact, string-quoted, range, comparison,
            # and multi-value patterns. The regex ensures Case 5000 won't false-match Case 50000.
            case_start = line_num
            # Scan forward to find end of this Case block
            # (next Case at same depth, or End Select)
            case_lines = []
            inner_depth = 0
            start_idx = line_idx[line_num]
            for j in range(start_idx, len(line_list)):
                ln, ct = line_list[j]
                st = ct.strip()
                if ln == case_start:
                    case_lines.append((ln, ct))
                    continue
                # Track nested Select Case within this Case block
                if st.startswith("Select Case"):
                    inner_depth += 1
                elif st.startswith("End Select"):
                    if inner_depth > 0:
                        inner_depth -= 1
                        case_lines.append((ln, ct))
                        continue
                    else:
                        break  # End of our target Select Case
                if inner_depth == 0 and (st.startswith("Case ") or st.startswith("Case Else")):
                    break
                case_lines.append((ln, ct))

            matches.append({
                "case_start": case_start,
                "case_lines": case_lines,
                "select_context": current_select_var
            })

        # Track Case Else blocks at target depth (for fallback if no exact match)
        elif select_depth == target_select_depth and stripped.startswith("Case Else"):
            case_else_start = line_num
            case_else_lines = []
            start_idx = line_idx[line_num]
            for j in range(start_idx, len(line_list)):
                ln, ct = line_list[j]
                st = ct.strip()
                if ln == case_else_start:
                    case_else_lines.append((ln, ct))
                    continue
                if st.startswith("End Select"):
                    break
                case_else_lines.append((ln, ct))
            case_else_blocks.append({
                "case_start": case_else_start,
                "case_lines": case_else_lines,
                "select_context": current_select_var
            })

    # If no exact Case match found, check for Case Else as fallback
    if not matches and case_else_blocks:
        for block in case_else_blocks:
            block["is_case_else"] = True
            block["note"] = (
                f"No explicit Case {case_value} found, but Case Else at line "
                f"{block['case_start']} would handle this value. Is this the target?"
            )
        return case_else_blocks

    return matches
```

5.2.2. Within each Case block, find all value assignments:

```python
def find_values_in_case_block(case_lines):
    """
    Extract all value assignments within a Case block.
    Handles nested If/Else (farm vs non-farm paths).
    """
    import re
    values = []
    current_condition = None

    for line_num, content in case_lines:
        stripped = content.strip()
        # Skip commented lines (VB.NET: ' apostrophe or REM keyword)
        if stripped.startswith("'") or stripped.upper().startswith("REM "):
            continue

        # Track If/Else conditions
        if stripped.startswith("If "):
            current_condition = stripped.split(" Then")[0]
        elif stripped == "Else":
            current_condition = "Else"
        elif stripped.startswith("ElseIf "):
            current_condition = stripped.split(" Then")[0]
        elif stripped.startswith("End If"):
            current_condition = None

        # Find value assignments: variable = value
        assign_match = re.match(r'\s*(\w+)\s*=\s*(-?[\d.]+)', stripped)
        if assign_match:
            values.append({
                "line": line_num,
                "content": content.rstrip(),
                "variable": assign_match.group(1),
                "value": float(assign_match.group(2)),
                "condition": current_condition,
                "context": f"Case {case_value}" + (f" > {current_condition}" if current_condition else "")
            })

    return values
```

5.2.3. **Show ALL values to the developer** (show-don't-guess):

```
[Analyzer] Operation {op_id}: Case {case_value} in {function_name} has {N} value assignments:

            1. Line {L1}: {variable} = {value1}
               Context: Case 5000 > If blnFarmLocation Then (farm path)

            2. Line {L2}: {variable} = {value2}
               Context: Case 5000 > Else (non-farm path)

            The SRD says change from {old_value} to {new_value}.
            Value 1 ({value1}) matches old_value.
            Value 2 ({value2}) does NOT match old_value.

            Which value(s) should be changed?
              a) Only line {L1} (farm path, matches old_value)
              b) Only line {L2} (non-farm path)
              c) Both lines
              d) None (skip this operation)
```

5.2.4. **Special case: old_value not found.** If none of the values in the Case block
match the operation's `old_value`, report:

```
[Analyzer] WARNING: Operation {op_id} expects old_value={old_value} in Case {case_value}
            of {function_name}, but the actual values found are:
              Line {L1}: {variable} = {actual_value_1} (context: farm path)
              Line {L2}: {variable} = {actual_value_2} (context: non-farm path)

            None match {old_value}. Possible reasons:
              - The value was already changed in a previous update
              - The SRD references a different Case value
              - The function has been restructured

            How to proceed?
              a) Update the old_value to {actual_value_1} and continue
              b) Update the old_value to {actual_value_2} and continue
              c) Skip this operation
              d) I'll investigate manually
```

#### 5.3 Pattern: included_limits

**Goal:** Find the variable or constant containing the limit value.

5.3.1. If the operation has a `function` hint, search within that function.
Otherwise, search the entire file for the limit variable/constant.

5.3.2. Search for both patterns:
- `Const {limit_name} = {old_limit}` (constant declaration)
- `{limit_name} = {old_limit}` (variable assignment)
- Also search for the raw value `{old_limit}` near context keywords

5.3.3. Present findings with context to the developer.

#### 5.4 Pattern: new_endorsement_flat

**Goal:** Find the CalcOption routing function and determine insertion point for a
new Case block.

5.4.1. Read the CalcOption file for the target LOB. The CalcOption file is a giant
Select Case router:

```vb
Select Case TheCategory
    Case Cssi.ResourcesConstants.CategoryCodes.CATEGORY_MISCPROPERTY
        Select Case TheOptionCode
            Case 1    'Antennae (Television)
                dblPrem = Option_AntennaeRadio()
            Case 2    'Bicycle
                dblPrem = Option_Bicycle()
            ...
```

5.4.2. Find the main routing Select Case (typically `Select Case TheOptionCode`
or `Select Case TheCategory` followed by nested `Select Case TheOptionCode`).

5.4.3. Determine the insertion point: the last existing `Case` before `End Select`
in the appropriate category section.

5.4.4. Record as `insertion_point` with `position: "before"` (before `End Select`).

5.4.5. Check if the option_code already exists in the routing:

```
[Analyzer] Duplicate check: Option code {option_code} in {calcoption_file}
            Result: NOT FOUND -- safe to add
```

or:

```
[Analyzer] WARNING: Option code {option_code} ALREADY EXISTS at line {L} in {calcoption_file}.
            Existing handler: {existing_handler}
            This may be an update to an existing endorsement, not a new one.
            Proceed with adding a duplicate, or modify the existing handler?
```

#### 5.5 Pattern: new_liability_option

**Goal:** Find where to add the liability premium array and the routing Case.

5.5.1. Search for existing Liab_*.vb files in the File Reference Map that match the
pattern for this LOB. Determine if the new liability should go in an existing file
or require a new file.

Existing Liab files are self-contained modules with a simple structure:

```vb
Partial Public Module modLiab_RentedDwelling
    Function Liab_RentedDwelling() As Short
        ' ... validation and setup ...
        Select Case liabilityAmount
            Case 500000 : premium = 11
            Case 1000000 : premium = 13
            Case 2000000 : premium = 15
            ...
        End Select
        Liab_RentedDwelling = premium
    End Function
End Module
```

5.5.2. If the liability function already exists (updating premiums), use
base_rate_increase search to find the Array6 lines.

5.5.3. If creating a new Liab_*.vb file, record `needs_new_file: true` and provide
a template reference from an existing Liab_*.vb in the same LOB.

5.5.4. For CalcOption routing, follow the same insertion logic as new_endorsement_flat
(Step 5.4).

#### 5.6 Pattern: new_coverage_type

**Goal:** Multiple sub-operations -- handle each per its location field.

5.6.1. **Add constant:** Find the module-level constants area (Step 4.6). Check for
duplicate constants. Record insertion point after the last existing constant.

Module-level constants in mod_Common look like:

```vb
Public Const PREFERRED As String = "Preferred"
Public Const STANDARD As String = "Standard"
```

Check for duplicates: if ELITECOMP already exists, report it and skip.

5.6.2. **Add rate table routing:** Find the routing function (e.g., `GetRateTableID`
or `SetClassification`). Find the existing Select Case block for coverage types.
Determine insertion point for the new Case.

5.6.3. **Add DAT IDs:** Read the target LOB's `ResourceID.vb`. Find the last constant
declaration. Record insertion point.

```vb
Public Const DAT_Home_EliteComp_Preferred = 28
Public Const DAT_Home_EliteComp_Standard = 29
```

5.6.4. For each sub-operation, check for existing duplicates before recommending
insertion.

#### 5.7 Pattern: eligibility_rules

**Goal:** Find the validation function and determine insertion point.

5.7.1. Search for validation functions matching the rule context:
- If the rule references a coverage type, search for validation functions in mod_Common
  (e.g., `ValidateCommon`, `ValidateData_Home`)
- If the rule targets per-LOB validation, search `CalcMain.vb` in the version folder

5.7.2. Determine the insertion point within the validation function.

5.7.3. Check if similar validation logic already exists (duplicate detection).

#### 5.8 Pattern: UNKNOWN

**Goal:** Present the operation details and ask the developer for guidance.

```
[Analyzer] Operation {op_id} has pattern UNKNOWN. Cannot auto-analyze.
            SRD: {srd_id} -- "{srd_title}"
            Description: {description}

            I need your guidance:
            1. Which file should this target? (current guess: {file})
            2. Which function? (current guess: {function})
            3. What should I search for?

            I can search for any text pattern in the target file(s).
            Type a search term and I'll show matches.
```

#### Deferred Confirmation Handling (All Patterns)

When the developer defers a confirmation prompt (responds with "I'll come back to
this", "skip for now", "defer", or similar), do NOT block the entire analysis. Instead:

- Mark the operation as `developer_confirmed: false, status: "pending_confirmation"`
- Continue processing remaining operations
- At Step 14 (final summary), list ALL pending operations under a dedicated section:

```
PENDING CONFIRMATION ({N} operations):
  {op_id}: {title} -- awaiting developer selection
  {op_id}: {title} -- awaiting developer selection
```

The Planner CANNOT proceed until all operations are either:
- `developer_confirmed: true` (developer made a selection)
- `developer_confirmed: false, status: "deferred"` (developer explicitly deferred
  this operation -- it will be excluded from the execution plan)

### Step 5.9: Code Pattern Discovery

**Action:** For qualifying logic-modifier operations, discover established code
patterns in the codebase so the Logic Modifier uses proven, active approaches
instead of inventing new ones or mimicking dead code.

**Why this step exists:** Without pattern discovery, the Logic Modifier sees dead
functions and active functions as equally valid — leading to bugs like ticket 25545
where `CountNAFClaims_Vehicle` (0 callers, dead code) was used instead of the
established `allIQCovItem.GetClaimsVehicles` (12+ callers). This step uses the
Pattern Library (from /iq-init) for instant call-count lookups and reads code
snippets from active functions to build a "Pattern Brief" for the operation YAML.

**Pattern guard — Trigger Table:**

```
TRIGGER TABLE
─────────────────────────────────────────────────────────
Pattern                    Trigger?   Reason
─────────────────────────────────────────────────────────
base_rate_increase         NO         Value substitution (rate-modifier)
factor_table_change        NO         Value substitution (rate-modifier)
included_limits            NO         Value substitution (rate-modifier)
new_coverage_type          MAYBE      Only if it involves function calls
eligibility_rules          YES        Accesses runtime objects
alert_message              YES        Calls alert functions
new_endorsement_flat       YES        Must follow existing file structure
new_liability_option       YES        Accesses liability collections
UNKNOWN                    YES        Always discover when uncertain
─────────────────────────────────────────────────────────
```

**Additional triggers:** Step 5.9 also triggers when:
- The Decomposer set `access_needs[]` on the operation (any pattern)
- The operation description contains keywords: "claims", "vehicle", "alert",
  "coverage item", "premium calculation", "collection", "accessor"

If the operation does NOT match any trigger, skip Step 5.9 entirely (no performance
cost for simple rate-modifier operations).

#### 5.9.7 CHECK INVESTIGATION FINDINGS (runs FIRST despite numbering)

Before any searching, check for saved `/iq-investigate` findings:

```
.iq-workstreams/changes/{workstream}/investigation/finding-*.yaml
```

If a finding matches the operation's access need (by keyword or data_object match),
use it directly — the developer already validated this pattern. Record:
```yaml
code_patterns:
  source: "investigation"
  finding_ref: "finding-001.yaml"
  # ... rest of code_patterns populated from the finding
```

If no investigation findings match, proceed to Steps 5.9.1-5.9.6.

#### 5.9.1 IDENTIFY ACCESS NEEDS

Determine what runtime data access patterns this operation requires. Sources in
priority order:

a) **`access_needs[]` from Decomposer** (if present on the operation YAML):
   ```yaml
   access_needs:
     - id: "claims_vehicle_count"
       description: "Count NAF claims per vehicle"
       data_object: "claims"
       access_type: "iteration"
   ```

b) **Inferred from pattern type:**
   - `eligibility_rules` → coverage items, field access
   - `alert_message` → alert functions (AlertHab/AlertAuto)
   - `new_endorsement_flat` → premium calculation, option routing
   - `new_liability_option` → liability collections, Array6 premium tables

c) **Keywords from operation description:** Scan the operation `description` and
   `title` fields for keywords: "claims", "vehicle", "alert", "coverage",
   "premium", "liability", "deductible", "discount", "surcharge", "endorsement".

If no access needs are identified from any source, skip the rest of Step 5.9.

#### 5.9.2 LOOKUP PATTERN LIBRARY

For each identified access need, query `.iq-workstreams/pattern-library.yaml`:

1. **Accessor index lookup:** `accessor_index[keyword]` → ranked list of accessor
   patterns with call counts. Example: `accessor_index["claims"]` returns
   `allIQCovItem.GetClaimsVehicles (12 callers)` and `p_objVehicle.Claims (0 callers)`.

2. **Function name lookup:** `functions[name]` → call_sites + status + file + line.
   Used to check if a function referenced in the operation description is DEAD or ACTIVE.

3. **Status filter:** Separate results into ACTIVE/HIGH_USE (safe to use) and
   DEAD (0 call sites — warn, never recommend).

**Fallback:** If `pattern-library.yaml` does not exist (old carrier that hasn't
re-run /iq-init), fall back to direct file scanning:
- Grep the target file and 2-3 related Code/ files for the access need keywords
- Count call sites manually
- This is slower but still works. Log:
  ```
  NOTE: Pattern Library not found — falling back to direct file scan.
  Run /iq-init --refresh to build the Pattern Library for faster analysis.
  ```

#### 5.9.3 FIND PEER FUNCTIONS

In the target file's function index (already built in Step 4.3), find functions that
are "peers" of the operation's target:

1. **Similar name prefix:** If target function is `CountNAFClaims`, search for
   functions matching `Count*Claims*`, `*NAF*`, or `*Claims*Vehicle*`

2. **Same parameter types:** Functions with the same first parameter type (e.g.,
   `ICoverageItem`, `IVehicle`) — these likely access the same runtime objects

3. **Keywords from operation description:** Functions whose name or body contains
   the access need keywords

Cross-reference each peer function with the Pattern Library for call counts.
Sort by `call_sites` descending — HIGH_USE peers are the best style references.

#### 5.9.4 EXTRACT CODE SNIPPETS

For each peer function with `call_sites > 0` (ACTIVE or HIGH_USE):
- Read the full function body from the source file
- If the function is longer than 30 lines, truncate to the first 30 lines with
  a note: `"(truncated at 30 lines — full function is {N} lines)"`
- Include: function signature, key access patterns (the lines that match the
  access need), return statement style
- Record as a `peer_functions` entry in the operation YAML

For dead-code functions (`call_sites == 0`):
- Include ONLY the signature + a 1-line "DEAD CODE" warning
- Do NOT include the full body — this prevents the Logic Modifier from copying
  dead code patterns
- Record with `dead_code: true`

#### 5.9.5 CANONICAL PATTERN SELECTION

Evaluate the discovered patterns and assign a confidence level:

**HIGH confidence** (proceed silently):
- The accessor_index has a clear winner: 3+ call sites, no close second (nearest
  competitor has <50% of the winner's call sites)
- Record as canonical. The Analyzer does NOT ask the developer.

**MEDIUM confidence** (include in Gate 1 review):
- 2+ active patterns with similar call counts (within 50% of each other)
- Record BOTH patterns. The developer sees them at Gate 1 and picks one.

**LOW confidence** (BLOCK: ask developer):
- Zero active patterns found for the access need
- Record as `"not_found"`. The Analyzer pauses and asks the developer:
  ```
  [Analyzer] No established pattern found for: "{access_need_description}"

  I searched for {keyword} patterns in the Pattern Library and target file
  but found no active functions that demonstrate this access pattern.

  Options:
  1. Provide the pattern manually (paste code or describe)
  2. Run /iq-investigate to explore the codebase
  3. Defer this operation (exclude from plan)
  ```

**Dead code warning** (always emitted):
- If any function near the operation target has `call_sites == 0`, emit:
  ```
  WARNING: {FunctionName} (line {N}) has 0 call sites — flagged as DEAD CODE.
  Do NOT use patterns from this function.
  ```

#### 5.9.6 DEVELOPER CONFIRMATION (when needed)

Only triggered for MEDIUM or LOW confidence. Presents patterns for selection:

```
┌─────────────────────────────────────────────────┐
│ [Analyzer] Pattern Discovery for {op_id}        │
│                                                  │
│ Need: "{access_need_description}"                │
│                                                  │
│ PATTERN A (RECOMMENDED — {N} active call sites): │
│   {accessor_pattern}                             │
│   Used in: {function1}, {function2}...           │
│   Snippet:                                       │
│     {2-4 lines of code showing the pattern}      │
│                                                  │
│ PATTERN B (WARNING — 0 call sites, DEAD CODE):   │
│   {dead_accessor_pattern}                        │
│   Used in: {dead_function} (DEAD)                │
│                                                  │
│ Which pattern? [A] / B / provide your own        │
└─────────────────────────────────────────────────┘
```

**Batching:** If multiple operations in the same workstream need the same access
pattern (e.g., two operations both need claims access), confirm ONCE and apply the
developer's choice to all matching operations.

#### 5.9.8 WRITE TO OPERATION YAML

Add the `code_patterns` section to the operation YAML file. All Decomposer and
prior Analyzer fields are preserved; `code_patterns` is appended below.

```yaml
# -- Added by Analyzer Step 5.9 --
code_patterns:
  peer_functions:
    - name: "{FunctionName}"
      file: "{relative file path}"
      line_start: {N}
      line_end: {N}
      call_sites: {N}
      dead_code: false
      snippet: |
        {Full function body or truncated excerpt}
      relevance: "{Why this function is relevant to the operation}"

    - name: "{DeadFunctionName}"
      file: "{relative file path}"
      line_start: {N}
      call_sites: 0
      dead_code: true
      snippet: "{Signature only} — DEAD CODE, 0 call sites"
      relevance: "{Why this is near the target — DO NOT USE}"

  canonical_access:
    - need: "{access_need_id}"
      pattern: "{established accessor pattern}"
      call_sites: {N}
      confidence: "{high|medium|low}"
      example_function: "{FunctionName that demonstrates this pattern}"
      example_snippet: |
        {2-5 lines showing the canonical way to do this}

  warnings:
    - "{FunctionName} (line {N}) has 0 call sites — flagged as DEAD CODE"

  developer_confirmed: {true|false}
  confidence_summary: "{N} canonical pattern(s) found, {HIGH|MEDIUM|LOW} confidence"
```

**If Step 5.9 was skipped** (operation did not match trigger table), the
`code_patterns` section is simply absent from the operation YAML. Downstream
consumers (Logic Modifier) handle this gracefully — see Logic Modifier core.md
ESTABLISHED PATTERN PREFERENCE rule.

#### Context Cost of Step 5.9

| Activity | Tool Calls | Time |
|----------|-----------|------|
| Read Pattern Library (already on disk) | 1 | ~1 sec |
| Read peer function bodies (from target file, already in memory) | 0 | negligible |
| Cross-file snippet extraction (1-3 active functions) | 1-3 | ~30 sec |
| Developer confirmation (only if MEDIUM/LOW) | 0-1 | ~30 sec |
| **Total incremental cost** | **2-5** | **~1-2 min** |

Step 5.9 is applied ONLY to qualifying operations (~1-3 per workstream, not all
10-20). Rate-modifier operations (base_rate_increase, factor_table_change) are
never triggered, so there is zero performance regression for typical tickets.

### Step 5.10: Generate Function Understanding Blocks (FUBs)

**Action:** For every operation that targets a function (`function is not null AND
function_line_start is not null`), generate a Function Understanding Block (FUB).
FUBs transform the Analyzer's "phone book" output (function name + line numbers)
into a "how-to guide" (branch tree + hazards + adjacent context) that workers can
use to understand function structure before modifying it.

**Trigger:** Broader than Step 5.9 — fires for BOTH rate-modifier and logic-modifier
operations. Any operation with a known target function gets a FUB.

**Cost guard:** Only generates FUBs for functions that workers will actually modify.
Typical workstream: 3-8 unique functions. At ~600-800 tokens per FUB, total cost is
1,800-6,400 tokens — well within the context budget.

#### 5.10.1 READ FUNCTION BODY

Extract the full text of the target function from the source file between
`function_line_start` and `function_line_end` (already in memory from Steps 4/5 —
no additional tool calls needed).

```python
def extract_function_body(lines, func_start, func_end):
    """Extract function body lines from the already-loaded file.

    Args:
        lines: list of (line_number, content) tuples from read_source_file()
        func_start: 1-based line number of function declaration
        func_end: 1-based line number of End Function/Sub

    Returns: list of (line_number, content) tuples for the function body
    """
    return [(ln, content) for ln, content in lines
            if func_start <= ln <= func_end]
```

#### 5.10.2 BUILD BRANCH TREE

Walk the function body and produce a compressed structural outline. This captures
the nesting structure (Select Case, If/ElseIf/Else) without the full source code,
giving workers a map of where to insert or modify code.

```python
import re

def build_branch_tree(func_body):
    """Build a compressed structural outline of a VB.NET function.

    Tracks: Select Case/End Select, If/ElseIf/Else/End If
    Records: nesting depth, switch variable, case values
    For each leaf: line range, content type, 1-line summary
    Truncation: top 3 levels max. If deeper, add "... ({N} more branches)"

    Token cost: ~200-400 tokens per function

    Returns: list of branch nodes (YAML-serializable)
    """
    tree = []
    stack = []   # Track nesting: [{type, variable, line, depth, branches}]

    select_case_re = re.compile(
        r'^\s*Select\s+Case\s+(.+)', re.IGNORECASE
    )
    case_re = re.compile(
        r'^\s*Case\s+(?!Else\b)(.+)', re.IGNORECASE
    )
    case_else_re = re.compile(
        r'^\s*Case\s+Else', re.IGNORECASE
    )
    end_select_re = re.compile(
        r'^\s*End\s+Select', re.IGNORECASE
    )
    if_re = re.compile(
        r'^\s*If\s+(.+?)\s+Then\s*$', re.IGNORECASE  # Block If only (not single-line)
    )
    elseif_re = re.compile(
        r'^\s*ElseIf\s+(.+?)\s+Then', re.IGNORECASE
    )
    else_re = re.compile(
        r'^\s*Else\s*$', re.IGNORECASE
    )
    end_if_re = re.compile(
        r'^\s*End\s+If', re.IGNORECASE
    )
    # Leaf content classifiers
    array6_re = re.compile(r'Array6\s*\(', re.IGNORECASE)

    current_depth = 0
    MAX_DEPTH = 3   # Truncate beyond depth 3

    for line_num, content in func_body:
        stripped = content.strip()
        if stripped.startswith("'"):
            continue  # Skip comments

        # --- Select Case ---
        m = select_case_re.match(content)
        if m:
            current_depth += 1
            node = {
                "type": "Select Case",
                "variable": m.group(1).strip(),
                "line": line_num,
                "depth": current_depth,
                "branches": []
            }
            if current_depth <= MAX_DEPTH:
                stack.append(node)
            else:
                # Track for counting but don't expand
                stack.append({"_overflow": True, "_count": 0, "depth": current_depth})
            continue

        m = end_select_re.match(content)
        if m and stack:
            closed = stack.pop()
            current_depth -= 1
            if closed.get("_overflow"):
                # Add overflow summary to parent
                if stack and not stack[-1].get("_overflow"):
                    parent = stack[-1]
                    target = parent.get("branches", parent.get("children", []))
                    target.append({
                        "line": line_num,
                        "leaf": f"... ({closed['_count']} nested branches omitted)"
                    })
            elif current_depth == 0:
                tree.append(closed)
            elif stack and not stack[-1].get("_overflow"):
                parent = stack[-1]
                target = parent.get("branches", parent.get("children", []))
                target.append(closed)
            continue

        m = case_re.match(content) or case_else_re.match(content)
        if m and stack and not stack[-1].get("_overflow"):
            case_val = m.group(1).strip() if hasattr(m, 'group') and m.lastindex else "Else"
            # Classify leaf content (look ahead up to 10 lines for content type)
            leaf_summary = classify_case_leaf(func_body, line_num)
            branch_entry = {
                "case": case_val,
                "line": line_num,
            }
            if leaf_summary:
                branch_entry["leaf"] = leaf_summary
            stack[-1]["branches"].append(branch_entry)
        elif m and stack and stack[-1].get("_overflow"):
            stack[-1]["_count"] += 1
            continue

        # --- If/ElseIf/Else/End If ---
        m = if_re.match(content)
        if m:
            current_depth += 1
            node = {
                "type": "If",
                "condition": m.group(1).strip()[:80],  # Truncate long conditions
                "line": line_num,
                "depth": current_depth,
                "children": []
            }
            if current_depth <= MAX_DEPTH:
                stack.append(node)
            else:
                stack.append({"_overflow": True, "_count": 0, "depth": current_depth})
            continue

        m = end_if_re.match(content)
        if m and stack:
            closed = stack.pop()
            current_depth -= 1
            if closed.get("_overflow"):
                if stack and not stack[-1].get("_overflow"):
                    parent = stack[-1]
                    target = parent.get("branches", parent.get("children", []))
                    target.append({
                        "line": line_num,
                        "leaf": f"... ({closed['_count']} nested branches omitted)"
                    })
            elif current_depth == 0:
                tree.append(closed)
            elif stack and not stack[-1].get("_overflow"):
                parent = stack[-1]
                target = parent.get("branches", parent.get("children", []))
                target.append(closed)
            continue

    return tree


def classify_case_leaf(func_body, case_line):
    """Look ahead from a Case line to classify its content.

    Returns a 1-line summary: e.g., "Array6 assignment (6 values)",
    "assignment statement", "function call", or None.
    """
    import re
    array6_re = re.compile(r'Array6\s*\(', re.IGNORECASE)
    for ln, content in func_body:
        if ln <= case_line:
            continue
        if ln > case_line + 10:
            break
        stripped = content.strip()
        if not stripped or stripped.startswith("'"):
            continue
        # Stop if we hit another Case or End Select
        if re.match(r'^\s*(Case\s|End\s+Select)', content, re.IGNORECASE):
            break
        if array6_re.search(content):
            # Count Array6 args
            paren_content = content[content.index("(") + 1:]
            arg_count = paren_content.count(",") + 1
            return f"Array6 assignment ({arg_count} values)"
        if "=" in stripped and not stripped.startswith("If"):
            return "assignment statement"
        if "(" in stripped:
            return "function call"
    return None
```

**Output schema for branch_tree:**

```yaml
branch_tree:
  - type: "Select Case"
    variable: "coverageType"
    line: 4015
    depth: 1
    branches:
      - case: "PREFERRED"
        line: 4016
        children:
          - type: "Select Case"
            variable: "territory"
            line: 4018
            depth: 2
            branches:
              - case: "1"
                line: 4020
                leaf: "Array6 assignment (6 values)"
              - case: "2"
                line: 4025
                leaf: "Array6 assignment (6 values)"
      - case: "Else"
        line: 4050
        leaf: "assignment statement"
```

#### 5.10.2b VALIDATE BRANCH TREE

After building the branch tree, run a lightweight sanity check. If validation fails,
the FUB includes `branch_tree_warnings` so workers know the tree may be unreliable.

```python
def validate_branch_tree(tree, func_body, func_start, func_end):
    """Sanity-check the branch tree after generation.

    Returns: (is_valid, warnings)
    """
    warnings = []

    # Check 1: Non-trivial functions should have branch nodes
    non_comment_lines = [ln for ln, c in func_body if not c.strip().startswith("'") and c.strip()]
    if len(non_comment_lines) > 20 and not tree:
        warnings.append(
            f"No branch nodes found in {len(non_comment_lines)}-line function — "
            "verify function boundaries or check for single-line If patterns"
        )

    # Check 2: Line references should be within function range
    def check_lines(nodes):
        for node in nodes:
            if isinstance(node, dict) and not node.get("_overflow"):
                line = node.get("line", 0)
                if line and (line < func_start or line > func_end):
                    warnings.append(
                        f"Branch tree line {line} outside function range "
                        f"{func_start}-{func_end}"
                    )
                for child in node.get("branches", []) + node.get("children", []):
                    if isinstance(child, dict):
                        check_lines([child])
    check_lines(tree)

    return len(warnings) == 0, warnings
```

If `validate_branch_tree` returns warnings, include them in the FUB:

```yaml
fub:
  branch_tree: [...]
  branch_tree_warnings:    # Only present when validation found issues
    - "No branch nodes found in 45-line function — verify function boundaries"
```

Workers receiving a FUB with `branch_tree_warnings` should rely more heavily on
`adjacent_context` and less on the branch_tree structure.

#### 5.10.3 DETECT HAZARDS

Scan the function body for known hazards that affect how workers should handle the
operation. Each hazard is a string tag; the FUB carries a list of active hazards.

```python
def detect_hazards(func_body, function_name, pattern_library):
    """Scan function body for known hazards.

    Args:
        func_body: list of (line_number, content) tuples
        function_name: name of the target function
        pattern_library: loaded pattern-library.yaml (for dead-code proximity check)

    Returns: list of hazard tag strings

    Token cost: ~50-100 tokens.
    """
    import re
    hazards = []

    has_integer_array6 = False
    has_decimal_array6 = False
    has_expressions = False
    has_multiline_array6 = False
    has_rate_array6 = False       # varRates = Array6(...)
    has_test_array6 = False       # IsItemInArray(Array6(...))
    max_nesting = 0
    has_const_rates = False

    array6_re = re.compile(r'Array6\s*\(', re.IGNORECASE)
    assign_array6_re = re.compile(r'=\s*Array6\s*\(', re.IGNORECASE)
    test_array6_re = re.compile(r'IsItemInArray\s*\([^,]*,\s*Array6\s*\(', re.IGNORECASE)
    const_re = re.compile(r'^\s*Const\s+\w+\s*=\s*[\d.]+', re.IGNORECASE)
    nesting_depth = 0

    for line_num, content in func_body:
        stripped = content.strip()
        if stripped.startswith("'"):
            continue

        # Track nesting depth
        if re.match(r'^\s*(Select\s+Case|If\s+.+\s+Then\s*$)', content, re.IGNORECASE):
            nesting_depth += 1
            max_nesting = max(max_nesting, nesting_depth)
        if re.match(r'^\s*(End\s+Select|End\s+If)', content, re.IGNORECASE):
            nesting_depth -= 1

        # Array6 analysis
        if array6_re.search(content):
            if assign_array6_re.search(content):
                has_rate_array6 = True
            if test_array6_re.search(content):
                has_test_array6 = True

            # Check for integer vs decimal values
            paren_start = content.index("Array6") + content[content.index("Array6"):].index("(")
            args_str = content[paren_start + 1:]
            if ")" in args_str:
                args_str = args_str[:args_str.index(")")]
            args = [a.strip() for a in args_str.split(",") if a.strip()]
            for arg in args:
                if re.search(r'[+\-*/]', arg) and not arg.startswith("-"):
                    has_expressions = True
                try:
                    val = float(arg.replace(" ", ""))
                    if "." in arg and val != int(val):
                        has_decimal_array6 = True
                    elif val == int(val):
                        has_integer_array6 = True
                except ValueError:
                    pass  # Non-numeric arg

        # Multi-line Array6 (line continuation)
        if array6_re.search(content) and stripped.endswith("_"):
            has_multiline_array6 = True

        # Const rate values
        if const_re.match(content):
            has_const_rates = True

    # Build hazard list
    if has_integer_array6 and has_decimal_array6:
        hazards.append("mixed_rounding")
    if has_expressions:
        hazards.append("arithmetic_expressions")
    if has_multiline_array6:
        hazards.append("multi_line_array6")
    if has_rate_array6 and has_test_array6:
        hazards.append("dual_use_array6")
    if max_nesting >= 3:
        hazards.append("nested_depth_3plus")
    if has_const_rates:
        hazards.append("const_rate_values")

    # Dead code proximity check (query Pattern Library)
    if pattern_library:
        all_funcs = pattern_library.get("functions", {})
        # Check if any function within ±5 positions in the file has 0 call sites
        func_entry = all_funcs.get(function_name, {})
        target_line = func_entry.get("line", 0)
        for name, entry in all_funcs.items():
            if name == function_name:
                continue
            if entry.get("call_sites", 1) == 0:
                entry_line = entry.get("line", 0)
                if abs(entry_line - target_line) < 200:  # proximity by line distance
                    hazards.append("dead_code_nearby")
                    break

    return hazards
```

#### 5.10.4 EXTRACT ADJACENT CONTEXT

Capture lines immediately surrounding the operation's target location. This helps
workers validate that the insertion/modification point hasn't drifted.

```python
def extract_adjacent_context(lines, target_line, agent_type):
    """Extract lines above and below the target line.

    - Logic-modifier ops: 5 lines above + 5 lines below insertion_point
    - Rate-modifier ops: 3 lines above + 3 lines below first target_line

    Token cost: ~100-200 tokens.

    Returns: {above: [{line, content}], below: [{line, content}]}
    """
    if agent_type == "logic-modifier":
        radius = 5
    else:
        radius = 3

    above = []
    below = []

    for ln, content in lines:
        if target_line - radius <= ln < target_line:
            above.append({"line": ln, "content": content.rstrip()})
        elif target_line < ln <= target_line + radius:
            below.append({"line": ln, "content": content.rstrip()})

    return {"above": above, "below": below}
```

#### 5.10.5 COLLECT NEARBY FUNCTION STATUS

Provide lightweight alive/dead signals for functions near the target. If Step 5.9
already ran for this operation, reference its output instead of duplicating data.

```python
def collect_nearby_functions(function_name, func_line_start, function_index,
                             pattern_library, step_5_9_ran):
    """Collect status of functions near the target.

    If Step 5.9 ran: set canonical_patterns_ref = "code_patterns" (pointer,
    no duplication — the FUB references the code_patterns section in the same
    operation YAML).

    If Step 5.9 did NOT run: lightweight Pattern Library lookup for target
    function + 2 nearest by line proximity. Record call_sites + status only
    (no snippets, no function bodies).

    Token cost: ~50-100 tokens.

    Returns: (canonical_patterns_ref, nearby_functions_list)
    """
    canonical_ref = "code_patterns" if step_5_9_ran else None

    nearby = []
    if not step_5_9_ran and pattern_library:
        all_funcs = pattern_library.get("functions", {})
        # Sort all functions by distance from target
        candidates = []
        for name, entry in all_funcs.items():
            entry_line = entry.get("line", 0)
            dist = abs(entry_line - func_line_start)
            candidates.append((dist, name, entry))

        candidates.sort(key=lambda x: x[0])
        # Take the target function + 2 nearest
        for dist, name, entry in candidates[:3]:
            nearby.append({
                "name": name,
                "call_sites": entry.get("call_sites", 0),
                "status": entry.get("status", "ACTIVE"),
                "line_start": entry.get("line", 0),
            })

    return canonical_ref, nearby
```

#### 5.10.6 ASSEMBLE FUB

Combine all sub-step outputs into a single Function Understanding Block and write
it into the operation YAML alongside existing Analyzer fields.

```yaml
# Appended to each operation YAML (analysis/operations/op-{SRD}-{NN}.yaml):
fub:
  function: "GetLiabilityBundlePremiums"
  file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
  line_start: 4012
  line_end: 4104
  param_types:
    - {name: "covItem", type: "ICoverageItem"}
    - {name: "territory", type: "Integer"}
  return_type: "Short"
  total_lines: 93
  branch_tree:                    # From 5.10.2
    - type: "Select Case"
      variable: "coverageType"
      line: 4015
      depth: 1
      branches:
        - case: "PREFERRED"
          line: 4016
          children:
            - type: "Select Case"
              variable: "territory"
              line: 4018
              depth: 2
              branches:
                - case: "1"
                  line: 4020
                  leaf: "Array6 assignment (6 values)"
                - case: "2"
                  line: 4025
                  leaf: "Array6 assignment (6 values)"
  hazards: ["mixed_rounding", "dual_use_array6"]     # From 5.10.3
  adjacent_context:                                   # From 5.10.4
    above: [{line: 4055, content: "Case \"ELITECOMP\""}]
    below: [{line: 4059, content: "Case Else"}]
  canonical_patterns_ref: "code_patterns"             # From 5.10.5 (or null)
  nearby_functions:                                   # From 5.10.5
    - {name: "CountNAFClaims", call_sites: 5, status: "HIGH_USE", line_start: 3200}
    - {name: "CountNAFClaims_Vehicle", call_sites: 0, status: "DEAD", line_start: 3250}
```

#### 5.10.7 DEDUPLICATION

Multiple operations targeting the SAME function in the SAME file share a single FUB.
The FIRST operation processed gets the full FUB block. Subsequent operations targeting
the same function get a lightweight pointer:

```yaml
# On the first operation (e.g., op-004-01):
fub:
  function: "GetBasePremium_Home"
  # ... full FUB as above ...

# On subsequent operations in the same function (e.g., op-004-02):
fub_ref: "op-004-01"    # "FUB is in this op's YAML"
adjacent_context_override:  # This op's OWN adjacent context (different target line)
  above: [{line: 4085, content: "..."}]
  below: [{line: 4089, content: "..."}]
```

When the capsule builder resolves `fub_ref`, it should use `adjacent_context_override`
(if present) instead of the shared FUB's `adjacent_context`. The override ensures
each operation gets adjacent context around ITS target line, not the first operation's.

```python
def generate_fubs_for_operations(operations, lines_by_file, function_indices,
                                 pattern_library):
    """Generate FUBs for all operations, with deduplication.

    Args:
        operations: list of operation dicts (already enriched by Steps 4-5.9)
        lines_by_file: dict of file -> [(line_num, content)] (already in memory)
        function_indices: dict of file -> build_function_index() result
        pattern_library: loaded pattern-library.yaml

    Returns: dict of op_id -> fub_data (or fub_ref string)
    """
    fub_cache = {}   # key = (file, function_name) -> op_id that owns the FUB

    for op in operations:
        func_name = op.get("function")
        func_start = op.get("function_line_start")
        func_end = op.get("function_line_end")
        target_file = op.get("source_file") or op.get("target_file")

        # Skip operations without function targets
        if not func_name or not func_start:
            continue

        cache_key = (target_file, func_name)

        # DEDUPLICATION: if FUB already generated for this function, use reference
        # BUT: adjacent_context is per-operation (different target lines within
        # the same function), so compute and store it as an override.
        if cache_key in fub_cache:
            op["fub_ref"] = fub_cache[cache_key]
            # Compute this op's own adjacent_context (different target line)
            op_target_line = op.get("insertion_point", {}).get("line") or \
                             (op.get("target_lines", [{}])[0].get("line") if op.get("target_lines") else func_start)
            op_agent_type = op.get("agent", "rate-modifier")
            op_adjacent = extract_adjacent_context(file_lines, op_target_line, op_agent_type)
            op["adjacent_context_override"] = op_adjacent
            continue

        # Generate full FUB
        file_lines = lines_by_file.get(target_file, [])
        func_index = function_indices.get(target_file, [])

        # 5.10.1: Extract function body
        func_body = extract_function_body(file_lines, func_start, func_end)

        # 5.10.2: Build branch tree
        branch_tree = build_branch_tree(func_body)

        # 5.10.3: Detect hazards
        hazards = detect_hazards(func_body, func_name, pattern_library)

        # 5.10.4: Extract adjacent context
        target_line = op.get("insertion_point", {}).get("line") or \
                      (op.get("target_lines", [{}])[0].get("line") if op.get("target_lines") else func_start)
        agent_type = op.get("agent", "rate-modifier")
        adjacent = extract_adjacent_context(file_lines, target_line, agent_type)

        # 5.10.5: Collect nearby function status
        step_5_9_ran = bool(op.get("code_patterns"))
        canonical_ref, nearby = collect_nearby_functions(
            func_name, func_start, func_index, pattern_library, step_5_9_ran
        )

        # Get param_types and return_type from function index
        func_entry = next((f for f in func_index
                           if f["name"] == func_name), {})
        param_types = func_entry.get("param_types", [])
        return_type = func_entry.get("return_type")

        # 5.10.6: Assemble FUB
        op["fub"] = {
            "function": func_name,
            "file": target_file,
            "line_start": func_start,
            "line_end": func_end,
            "param_types": param_types,
            "return_type": return_type,
            "total_lines": (func_end - func_start + 1) if func_end else None,
            "branch_tree": branch_tree,
            "hazards": hazards,
            "adjacent_context": adjacent,
            "canonical_patterns_ref": canonical_ref,
            "nearby_functions": nearby,
        }

        # 5.10.7: Register in dedup cache
        fub_cache[cache_key] = op["id"]

    return  # operations are modified in-place
```

#### Context Cost of Step 5.10

| Activity | Tool Calls | Time |
|----------|-----------|------|
| Function body (already in memory) | 0 | negligible |
| Branch tree (pure logic) | 0 | negligible |
| Hazard scan (Pattern Library lookup, 2-3 names) | 1 | ~1 sec |
| Adjacent context (already in memory) | 0 | negligible |
| Nearby functions (Pattern Library lookup) | 0-1 | ~1 sec |
| **Total per function** | **1-2** | **~2-3 sec** |
| **Total per workstream (3-8 functions)** | **3-16** | **~10-30 sec** |

Zero developer interaction. Fully automated. FUB deduplication ensures the cost
scales with unique functions, not total operations.

**If Step 5.10 encounters an error** (e.g., function body cannot be extracted,
Pattern Library is missing), it degrades gracefully: the FUB is omitted and the
operation proceeds without it. The capsule builder defaults to Tier 2 behavior
(current system) when no FUB is present.

### Step 5.11: Enrich Codebase Profile

**Action:** While function bodies are already in memory from Steps 4-5.10, extract
reusable knowledge and persist it to `codebase-profile.yaml`. This step is free
in terms of tool calls (data already loaded) and makes the profile richer with
every /iq-plan run.

**Trigger:** Runs for every operation that has a resolved target function. Skipped
entirely if `codebase-profile.yaml` does not exist (profile must be initialized by
/iq-init first).

#### 5.11.1 FACTOR CARDINALITY

For each operation that targets a function containing Select Case blocks (already
parsed for FUBs in Step 5.10.2), extract and persist cardinality metadata:

```python
def extract_factor_cardinality(function_name, function_body, branch_tree):
    """Extract Case branch counts from the function's branch tree.

    Returns list of cardinality entries (one per Select Case block in the function).
    """
    cardinalities = []
    for node in branch_tree:
        if node["type"] == "Select Case":
            case_values = [c for c in node.get("children", []) if c["type"] == "Case"]
            cardinalities.append({
                "function": function_name,
                "case_variable": node.get("variable", "unknown"),
                "count": len(case_values),
                "min": min((c.get("value") for c in case_values if c.get("value")), default=None),
                "max": max((c.get("value") for c in case_values if c.get("value")), default=None),
                "value_type": "numeric" if all(
                    isinstance(c.get("value"), (int, float)) for c in case_values if c.get("value")
                ) else "mixed",
                "has_case_else": any(c["type"] == "Case Else" for c in node.get("children", [])),
            })
    return cardinalities
```

Write discovered cardinalities to `factor_cardinality` section:

```yaml
factor_cardinality:
  SetDisSur_Deductible:
    - case_variable: "deductible"
      count: 8
      min: 200
      max: 25000
      value_type: "numeric"
      has_case_else: true
      provenance: "analyzer"
      discovered_at: "2026-03-03T14:30:00Z"

  GetRateGroupDifferential:
    - case_variable: "rateGroup"
      count: 99
      min: 1
      max: 99
      value_type: "numeric"
      has_case_else: false
      provenance: "analyzer"
      discovered_at: "2026-03-03T14:30:00Z"
```

#### 5.11.2 RULE DEPENDENCY DETECTION

Scan function bodies for patterns that indicate business rule relationships:

```python
def detect_rule_dependencies(function_name, function_body, all_function_names):
    """Detect function pairs that have business rule dependencies.

    Patterns detected:
    1. Validate* + Get*/Set* with same domain noun → validation dependency
       Example: ValidateSewerBackup + GetSewerBackupPremium
    2. Set*Defaults + Validate* → setup/validation pair
       Example: SetSewerBackupDefaults + ValidateSewerBackup
    3. Direct function calls within function body → call dependency
       Example: GetWaterDamagePremium calls GetSewerBackupPremium
    4. Shared variable names across functions → data dependency
       Example: Both use 'sewerBackupCoverage' as parameter
    """
    dependencies = []

    # Pattern 1: Validate + Get/Set with same noun
    if function_name.startswith("Validate"):
        noun = function_name.replace("Validate", "")
        for other in all_function_names:
            if other != function_name and noun in other:
                dependencies.append({
                    "name": f"validation_{noun.lower()}",
                    "functions": [function_name, other],
                    "relationship": "validation_dependency",
                    "impact": f"Changes to {other} may require updating {function_name}"
                })

    # Pattern 3: Direct call detection
    for other in all_function_names:
        if other != function_name and other in function_body:
            dependencies.append({
                "name": f"call_{function_name}_to_{other}",
                "functions": [function_name, other],
                "relationship": "call_dependency",
                "impact": f"{function_name} calls {other} — changes may propagate"
            })

    return dependencies
```

Write discovered dependencies to `rule_dependencies` section:

```yaml
rule_dependencies:
  - name: "water_sewer_backup"
    functions: ["GetWaterDamagePremium", "GetSewerBackupPremium"]
    relationship: "call_dependency"
    impact: "Water Coverage calls Sewer Backup — changes may propagate"
    provenance: "analyzer"
    discovered_at: "2026-03-03T14:30:00Z"

  - name: "validation_sewerbackup"
    functions: ["ValidateSewerBackup", "GetSewerBackupPremium"]
    relationship: "validation_dependency"
    impact: "Changes to GetSewerBackupPremium may require updating ValidateSewerBackup"
    provenance: "analyzer"
    discovered_at: "2026-03-03T14:30:00Z"
```

#### 5.11.3 PROVENANCE AND MERGE RULES

All enriched entries receive `provenance: "analyzer"` and `discovered_at: "{timestamp}"`.

**Merge rules when writing to codebase-profile.yaml:**
- Existing entries with `provenance: "investigation"` or `provenance: "init"` are
  NEVER overwritten — they are more authoritative (developer-validated or structurally
  derived).
- Existing entries with `provenance: "analyzer"` are updated with the latest data
  (same source, newer observation).
- New entries are appended.
- Use read-modify-write with the Grep tool to find existing entries before writing.

#### Context Cost of Step 5.11

| Activity | Tool Calls | Time |
|----------|-----------|------|
| Factor cardinality (from branch_tree) | 0 | negligible (already in memory) |
| Rule dependency (string matching) | 0 | negligible (already in memory) |
| Profile write (Grep + Edit) | 2-3 | ~2-3 sec |
| **Total per workstream** | **2-3** | **~2-3 sec** |

Zero developer interaction. Fully automated. Only writes if new knowledge was
discovered. If codebase-profile.yaml does not exist, the entire step is skipped.

---

### Step 6: Resolve Rounding Mode

**Action:** For operations with `rounding: "auto"` (base_rate_increase pattern),
inspect the actual Array6 values to determine the correct rounding mode.

**Pattern guard:** Step 6 applies ONLY to operations with `pattern: "base_rate_increase"`
and `parameters.rounding: "auto"`. Skip all other patterns -- they do not use Array6
multiplication and rounding resolution is not applicable.

6.0. **Check for `rounding_hint` from the Decomposer.** The Intake agent may have
attached a `rounding_hint` field (e.g., `rounding_hint: "banker"`) to the operation
parameters. If present, use it as a cross-check AFTER the value-based analysis in
Steps 6.1-6.3:

- If `rounding_hint` matches `rounding_resolved`: confirmed, proceed silently.
- If `rounding_hint` disagrees with `rounding_resolved`: flag for developer review:

```
[Analyzer] Rounding cross-check MISMATCH for {op_id}:
            Intake hint: {rounding_hint}
            Value-based analysis: {rounding_resolved}

            The Intake agent suggested "{rounding_hint}" rounding, but the actual
            Array6 values indicate "{rounding_resolved}". Using value-based result.
            Please confirm this is correct.
```

  When a mismatch occurs and the developer confirms a choice, record in
  `analysis_notes`: `"Rounding hint was '{hint}' but value-based analysis found
  '{result}'. Developer confirmed {choice}."`

- If `rounding_hint` is absent: rely solely on value-based analysis (the normal case).

6.1. For each target line identified in Step 5.1, extract the Array6 arguments:

```python
def classify_rounding(args):
    """
    Determine rounding mode from Array6 argument values.

    Returns: "banker" (all integers), "none" (any decimal), or "skip" (all zeros)
    """
    has_decimal = False
    all_zero = True

    for arg in args:
        arg = arg.strip()
        # Skip non-numeric args (rare but possible)
        try:
            val = float(arg)
        except ValueError:
            return "review"  # Contains non-numeric -- needs developer review

        if val != 0:
            all_zero = False
        if "." in arg and float(arg) != int(float(arg)):
            has_decimal = True

    if all_zero:
        return "skip"      # All zeros -- no rounding needed (will be 0 * factor = 0)
    elif has_decimal:
        return "none"      # Has decimals -- multiply and keep decimals
    else:
        return "banker"    # All integers -- use banker rounding after multiply
```

**Secondary signal -- variable type:** As a secondary check, inspect the variable
being assigned. `Integer`/`Short` typed variables confirm banker rounding.
`Double`/`Decimal` may keep precision. In practice, most rate code uses Variant/Object
types (like `varRates`), so value inspection (primary method above) takes precedence.
The variable type check is only used to cross-validate ambiguous cases.

6.2. Aggregate per-operation rounding:

```
ROUNDING AGGREGATION
------------------------------------------------------------

If ALL target_lines have rounding = "banker":
    operation.rounding_resolved = "banker"

If ALL target_lines have rounding = "none":
    operation.rounding_resolved = "none"

If target_lines have a MIX of "banker" and "none":
    operation.rounding_resolved = "mixed"
    Include per-line rounding in target_lines[].rounding

If any target_line has rounding = "review":
    operation.rounding_resolved = "review"
    Flag for developer
```

6.3. Report rounding resolution to the developer:

```
[Analyzer] Rounding resolution for {op_id} ({function_name}):
            {N} Array6 lines found:
              {M} lines with integer values -> banker rounding
              {K} lines with decimal values -> no rounding
              {J} lines all zeros -> skip (multiply has no effect)

            Operation-level rounding: {rounding_resolved}
```

6.4. **Real-world mixed rounding example** (from GetLiabilityBundlePremiums):

```
Lines with integer Array6 values (rounding: banker):
  Line 4058: Array6(0, 78, 161, 189, 213, 291)          -- Enhanced Comp
  Line 4060: Array6(78, 106, 161, 189, 216, 291)        -- Essentials Comp/Broad
  Line 4064: Array6(41, 66, 99, 124, 149, 274)          -- another coverage

Lines with decimal Array6 values (rounding: none):
  Line 4062: Array6(0, 0, 0, 0, 324.29, 462.32)         -- ELITECOMP

Resolved rounding: "mixed" (per-line detail attached to each target_line)
```

### Step 7: Run Reverse Lookup for Hidden Blast Radius

**Action:** For each shared module targeted by operations, scan ALL .vbproj files in
the province to find references that are NOT in the developer's target list.

**NOTE:** This step MUST run BEFORE building files_to_copy.yaml (Step 8), because the
reverse lookup discovers additional .vbproj files that need reference updates. Those
additional .vbproj files must be included in the files_to_copy vbproj_updates list.

7.1. Identify all shared modules that have operations:

```python
shared_targets = set()
for op in operations:
    if op["file_type"] in ("shared_module", "cross_lob"):
        shared_targets.add(op["source_file"])
```

7.2. Glob for ALL .vbproj files in the province:

```python
import glob

province_path = os.path.join(codebase_root, province_name)
all_vbproj = glob.glob(
    os.path.join(province_path, "**", f"Cssi.IntelliQuote.{config['carrier_prefix']}*.vbproj"),
    recursive=True
)
```

7.3. Parse each .vbproj and check for references to the shared modules:

```python
reverse_refs = defaultdict(list)  # shared_module -> list of vbproj paths that reference it

for vbproj in all_vbproj:
    tree = ET.parse(vbproj)
    root = tree.getroot()
    ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"

    for item_group in root.findall(f"{ns}ItemGroup"):
        for compile_elem in item_group.findall(f"{ns}Compile"):
            include_path = compile_elem.get("Include")
            if include_path:
                resolved = os.path.normpath(os.path.join(os.path.dirname(vbproj), include_path))
                relative = os.path.relpath(resolved, codebase_root).replace("\\", "/")
                for shared_module in shared_targets:
                    if os.path.basename(relative) == os.path.basename(shared_module):
                        reverse_refs[shared_module].append(vbproj)
```

7.4. Compare reverse lookup results against target_folders:

```python
target_vbprojs = set()
for tf in target_folders:
    target_vbprojs.add(
        os.path.normpath(os.path.join(codebase_root, tf["path"], tf["vbproj"]))
    )

for shared_module, referencing_vbprojs in reverse_refs.items():
    for vbproj in referencing_vbprojs:
        if os.path.normpath(vbproj) not in target_vbprojs:
            # HIDDEN BLAST RADIUS -- this project will be affected but
            # is not in the developer's target list
            warnings.append({
                "type": "hidden_blast_radius",
                "shared_module": shared_module,
                "affected_vbproj": vbproj,
                "message": f"{shared_module} is also compiled by {vbproj}, "
                           f"which is NOT in the target folders."
            })
```

7.5. Report hidden blast radius to the developer:

```
[Analyzer] REVERSE LOOKUP WARNING: Shared module mod_Common_SKHab is referenced by
            projects NOT in your target list:

            Saskatchewan/Seasonal/20260101/Cssi.IntelliQuote.PORTSKSEASONAL20260101.vbproj

            Changes to mod_Common_SKHab will affect this project too.
            Options:
              a) Add this project to the target list (recommended)
              b) Acknowledge and proceed (changes will still affect this project)
              c) Abort -- need to reconsider the scope
```

If ALL referencing projects are in the target list, report:
```
[Analyzer] Reverse lookup complete: All {N} projects referencing {shared_module}
            are in the target list. No hidden blast radius.
```

### Step 8: Build files_to_copy.yaml

**Action:** Assemble the list of Code/ files that need new dated copies, with the
.vbproj reference updates for each. This step runs AFTER the reverse lookup (Step 7)
so that additional .vbproj files discovered by the reverse lookup are included in the
vbproj_updates list.

8.1. Collect all unique source -> target file mappings from operations:

```python
files_to_copy = {}  # key = source_file, value = {target, operations, shared_by, vbproj_updates}

for op in operations:
    if op.get("needs_copy"):
        source = op["source_file"]
        if source not in files_to_copy:
            files_to_copy[source] = {
                "source": source,
                "target": op["target_file"],
                "source_hash": op["file_hash"],
                "target_exists": os.path.exists(os.path.join(codebase_root, op["target_file"])),
                "shared_by": list(file_refs.get(source, set())),
                "operations_in_file": [],
                "vbproj_updates": []
            }
        files_to_copy[source]["operations_in_file"].append(op["id"])
```

8.2. For each file to copy, find ALL .vbproj files that reference the source file
and build the `vbproj_updates` list. **Include .vbproj files discovered by the reverse
lookup in Step 7** -- if a shared module is referenced by .vbproj files OUTSIDE the
target folders, those .vbproj files also need reference updates:

```python
for source_file, entry in files_to_copy.items():
    source_basename = os.path.basename(source_file)
    target_basename = os.path.basename(entry["target"])

    # Use all_vbproj_includes (from Step 2) PLUS reverse_refs (from Step 7)
    # to build the complete list of .vbproj files needing updates
    for vbproj_path, includes in all_vbproj_includes.items():
        for include_entry in includes:
            if os.path.basename(include_entry["resolved"]) == source_basename:
                # Build the new Include path by replacing the date
                old_include = include_entry["include"]
                new_include = old_include.replace(source_basename, target_basename)
                entry["vbproj_updates"].append({
                    "vbproj": vbproj_path,
                    "old_include": old_include,
                    "new_include": new_include
                })
```

8.3. Write `analysis/files_to_copy.yaml` with the complete list.

### Step 9: Check for Cross-Province Shared Files

**Action:** Verify that no operation targets a cross-province shared file.

9.1. For each operation, check if the resolved source file is a cross-province shared
file (classification = "cross_province_shared" from Step 2.4):

```python
cross_province_files = config.get("cross_province_shared_files", [])  # Discovered by /iq-init

for op in operations:
    for cpf in cross_province_files:
        if cpf in op["source_file"]:
            errors.append({
                "type": "cross_province_violation",
                "operation": op["id"],
                "file": op["source_file"],
                "message": f"Operation {op['id']} targets cross-province shared file "
                           f"{cpf}. These files must NEVER be auto-modified."
            })
```

9.2. If any violations found, report and REFUSE to assign line numbers:

```
[Analyzer] ERROR: Operation {op_id} targets a cross-province shared file:
            {source_file}

            Cross-province shared files (listed in config.yaml cross_province_shared_files,
            e.g., Code/PORTCommonHeat.vb for Portage Mutual) are used by ALL provinces
            and must NEVER be automatically modified.

            This operation has been flagged as BLOCKED. The developer must either:
              a) Modify this file manually outside the plugin
              b) Remove this operation from the workflow
```

### Step 10: Handle Review-Needed Operations

**Action:** For operations with `needs_review: true` or `file: null`, present the
operation to the developer and request guidance.

10.1. For each operation with `needs_review: true`:

```
[Analyzer] Operation {op_id} needs your input before I can analyze it.

            SRD: {srd_id} -- "{title}"
            Pattern: {pattern}
            Description:
              {description}

            Currently missing:
              - File: {file or "not specified"}
              - Function: {function or "not specified"}

            Please provide:
            1. Which file should this change target?
            2. Which function within that file?
            3. Any additional context for finding the right code location?
```

10.2. After receiving developer input, re-run the search steps (Steps 3-6) for the
updated operation.

### Step 11: Include SHARDCLASS Files in Blast Radius

**Action:** Check if any SHARDCLASS (or SharedClass) files are affected.

11.1. Determine the correct directory name:

```python
shardclass_folder = config.get("shardclass_folder", "SHARDCLASS")
# Nova Scotia uses "SharedClass" -- config.yaml should specify this
```

11.2. Check if any operations reference SHARDCLASS files (classification = "shardclass"
from Step 2.4).

11.3. If operations touch SHARDCLASS files, include them in the blast radius with a
warning:

```
[Analyzer] SHARDCLASS file in scope: {shardclass_file}
            This shared helper class is compiled by {N} LOBs.
            Changes will affect all dependent LOBs.
```

### Step 11.5: Rule Dependency Blast Radius Check

**Action:** Before computing the blast radius report, check `rule_dependencies` in
`codebase-profile.yaml` for related functions that are NOT in the target list.

```python
profile_path = ".iq-workstreams/codebase-profile.yaml"
deps = load_yaml_section(profile_path, "rule_dependencies")
target_functions = set(op.get("function") for op in operations if op.get("function"))

blast_radius_notes = []
if deps:
    for dep in deps:
        dep_functions = set(dep.get("functions", []))
        # If ANY function in this dependency is in our target set...
        overlap = dep_functions & target_functions
        if overlap:
            # ...check if ALL functions are in our target set
            missing = dep_functions - target_functions
            if missing:
                for related_fn in missing:
                    blast_radius_notes.append(
                        f"WARNING: {related_fn} is linked to "
                        f"{', '.join(overlap)} via '{dep['name']}' "
                        f"({dep.get('relationship', 'unknown')}) — "
                        f"review for consistency. {dep.get('impact', '')}"
                    )
```

If notes are generated, include them in the blast radius report (Step 12) under a
"Rule Dependency Warnings" heading. If `codebase-profile.yaml` or `rule_dependencies`
does not exist, skip silently.

### Step 12: Generate Blast Radius Report

**Action:** Assemble the `analysis/blast_radius.md` report.

12.1. Calculate the risk level:

```
RISK LEVEL CALCULATION
------------------------------------------------------------

Start at LOW.

Upgrade to MEDIUM if ANY of:
  - 3+ operations in a shared module
  - Any cross_lob files affected
  - Any SHARDCLASS files affected
  - Mixed rounding in any operation
  - Any operation flagged for developer review

Upgrade to HIGH if ANY of:
  - Cross-province shared file warnings
  - Hidden blast radius (reverse lookup found unaccounted projects)
  - 10+ operations total
  - Any operation targeting a file with 3,000+ lines
  - Rule dependency warnings from Step 11.5 (related functions not in target list)
```

12.2. Write the blast radius report using this template:

```markdown
# BLAST RADIUS: {Province_Name} {LOB_Category} effective {YYYY-MM-DD}

Ticket: {ticket_ref}
Province: {province_name} ({province_code})
LOBs: {lob_list}
Generated: {timestamp}
Risk: {risk_level}

## FILES NEEDING NEW DATED COPIES

  {For each entry in files_to_copy.yaml:}
  {source_file} -> {target_basename}
    {If shared:} Shared by: {shared_by_list} ({count} LOBs)
    Operations: {operation_list}
    .vbproj updates: {count} files

## SHARED MODULE CHANGES (affects {N} LOBs)

  {For each shared_module with operations:}
  {target_file} ({line_count} lines)
    {For each operation:}
    {op_id}: {function_name}() lines {start}-{end}
             {description_of_changes}

## PER-LOB CHANGES

  {For each LOB-specific file with operations:}
  {file_path}
    {op_id}: lines {start}-{end} -- {description}

## FLAGGED FOR DEVELOPER REVIEW

  {For each warning/flag:}
  - {warning_message}

  {If no flags:}
  (none)

## CROSS-PROVINCE SHARED FILES

  {For each cross-province warning:}
  - {file}: {warning}

  {If none:}
  (none affected by this workflow)

## REVERSE LOOKUP

  {For each shared module:}
  {module_name} is referenced by:
    {For each referencing project:}
    {project_path}  ({IN target list / NOT in target list - WARNING})
  {Summary: All accounted / N unaccounted}

## RULE DEPENDENCY WARNINGS

  {For each blast_radius_note from Step 11.5:}
  - {warning_message}

  {If none:}
  (no rule dependencies triggered)

## RISK ASSESSMENT

  Level: {risk_level}
  Reason: {explanation of why this risk level was assigned}
```

### Step 13: Write Output Files and Update Manifest

**Action:** Write all Analyzer output files.

13.1. **Update each operation file** in `analysis/operations/op-{SRD}-{NN}.yaml`:
Append the `# -- Added by Analyzer --` section with source_file, target_file,
needs_copy, file_hash, function boundaries, target_lines, rounding, etc.

**Bubble up `has_expressions` to operation level:** If ANY entry in `target_lines`
has `has_expressions: true`, also set `has_expressions: true` at the operation level
(alongside source_file, target_file, etc.). This allows the Planner to check for
arithmetic expressions at the operation level without iterating target_lines.
```yaml
# Operation-level bubble-up (in addition to per-target_line):
has_expressions: true    # Set if any target_lines[].has_expressions is true
```

13.2. **Write `analysis/files_to_copy.yaml`** (Step 8).

13.3. **Write `analysis/blast_radius.md`** (Step 12).

13.4. **File hash handoff:** The Analyzer writes `file_hash` in each operation file.
The Planner collects these hashes and writes `execution/file_hashes.yaml` at plan
approval time. If a file's hash has changed between the Analyzer run and plan approval,
the Planner forces re-analysis of affected operations before proceeding.

13.5. **Validate all written YAML files:**

```bash
python -c "
import sys, os, glob

def validate_yaml(filepath):
    try:
        import yaml
        with open(filepath) as f:
            yaml.safe_load(f)
        print(f'  {os.path.basename(filepath)}: YAML valid')
    except ImportError:
        with open(filepath) as f:
            content = f.read()
        if content.strip() and not content.strip().startswith('{'):
            print(f'  {os.path.basename(filepath)}: basic structure OK')
        else:
            print(f'  WARNING: {os.path.basename(filepath)} may not be valid YAML')
    except yaml.YAMLError as e:
        print(f'  YAML ERROR in {os.path.basename(filepath)}: {e}')
        sys.exit(1)

print('Validating files_to_copy.yaml...')
validate_yaml('analysis/files_to_copy.yaml')

print('Validating updated operation files...')
for f in sorted(glob.glob('analysis/operations/op-*.yaml')):
    validate_yaml(f)

print('All files validated.')
"
```

13.6. **Do NOT update `manifest.yaml`** — the orchestrator handles manifest updates
after each agent completes (see skills/iq-plan/SKILL.md Manifest Update Protocol). The summary
counts (operations_analyzed, files_to_copy, warnings) are derivable from the
enriched op-*.yaml files and files_to_copy.yaml you already wrote. SRD status
transitions are set by the orchestrator — agents do not set SRD statuses.

### Step 14: Present Results to Developer

**Action:** Show the developer a summary of the analysis.

14.1. Present the summary:

```
[Analyzer] Analysis complete for {workflow_id}:

  FILES TO COPY: {N}
    {For each file:}
    {source} -> {target_basename} ({shared_by_count} LOBs)

  OPERATIONS MAPPED: {M} of {total}
    {For each operation:}
    {op_id}: {function_name}() in {file_basename}, lines {start}-{end}
             {target_line_count} target line(s), rounding: {rounding_resolved}

  DEVELOPER CONFIRMATIONS NEEDED: {K}
    {Any pending confirmations}

  PENDING CONFIRMATION: {P}
    {For each operation with developer_confirmed == false:}
    {op_id}: {title} -- awaiting developer selection
    NOTE: Planner cannot proceed until all pending operations are resolved or deferred.

  REVERSE LOOKUP: {status}
    {All accounted / N warnings}

  RISK LEVEL: {risk_level}

  Full report: analysis/blast_radius.md
  Files to copy: analysis/files_to_copy.yaml
```

14.2. Report completion:

```
[Analyzer] COMPLETE. Updated {M} operation files in analysis/operations/.
            - analysis/files_to_copy.yaml ({N} files)
            - analysis/blast_radius.md (risk: {risk_level})
            - {K} developer confirmations recorded

            Next: Planner agent will build the execution plan for Gate 1 approval.
```

---

## WORKED EXAMPLES

These examples demonstrate the full Analyzer flow for common scenarios.

### Example A: Factor Table Change -- Nested If/Else Discovery

**Input operation (from Decomposer):**

```yaml
id: "op-002-01"
srd: "srd-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "SetDisSur_Deductible"
agent: "rate-modifier"
pattern: "factor_table_change"
parameters:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22
```

**Step 2 -- Parse .vbproj:**
- Read PORTSKHOME20260101.vbproj
- Find `<Compile Include="..\..\Code\mod_Common_SKHab20250901.vb">`
- Resolve to `Saskatchewan/Code/mod_Common_SKHab20250901.vb`

**Step 3 -- Resolve source file:**
- Target date: 20260101, Source date: 20250901
- `needs_copy: true`
- Hash source file for TOCTOU

**Step 4 -- Find function:**
- Build function index for mod_Common_SKHab20250901.vb (4,587 lines)
- Search for "SetDisSur_Deductible"
- Found: lines 2108-2227 (120 lines)
- 1 match = unambiguous, proceed

**Step 5 -- Find Case 5000:**
- Search within lines 2108-2227 for `Case 5000`
- Found at line 2199
- Extract Case block (lines 2199-2206):

```vb
' Line 2199: Case 5000
' Line 2200:     If blnFarmLocation Then
' Line 2201:         'RJB 20200713 IQPORT-5336
' Line 2202:         dblDedDiscount = -0.2
' Line 2203:     Else
' Line 2204:         'RJB 20191201 IQPORT-4732 changed from 20% to 25%
' Line 2205:         dblDedDiscount = -0.25
' Line 2206:     End If
```

- Line 2201 and 2204 are comments -- SKIPPED
- Line 2202: `dblDedDiscount = -0.2` -- matches old_value (-0.20)
- Line 2205: `dblDedDiscount = -0.25` -- does NOT match old_value

**Show to developer:**

```
[Analyzer] Operation op-002-01: Case 5000 in SetDisSur_Deductible has 2 value assignments:

            1. Line 2202: dblDedDiscount = -0.2
               Context: Case 5000 > If blnFarmLocation Then (farm path)
               MATCHES old_value (-0.20)

            2. Line 2205: dblDedDiscount = -0.25
               Context: Case 5000 > Else (non-farm path)
               Does NOT match old_value (-0.20)

            The SRD says change from -0.20 to -0.22.
            Which value(s) should be changed?
              a) Only line 2202 (farm path, matches old_value)
              b) Only line 2205 (non-farm path)
              c) Both lines
              d) None (skip this operation)
```

**Developer selects (a).**

**Updated operation file:**

```yaml
id: "op-002-01"
srd: "srd-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
description: |
  In function SetDisSur_Deductible, find the Case 5000 block and change
  the deductible discount value from -0.20 to -0.22. Note: this function
  has nested If/Else blocks for farm vs non-farm within each Case.
  The Analyzer must show ALL matching values to the developer.
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "SetDisSur_Deductible"
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "factor_table_change"
parameters:
  case_value: 5000
  old_value: -0.20
  new_value: -0.22

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
function_line_start: 2108
function_line_end: 2227
target_lines:
  - line: 2202
    content: "                    dblDedDiscount = -0.2"
    context: "Case 5000 > If blnFarmLocation Then (farm path)"
    rounding: null
candidates_shown: 2
developer_confirmed: true
analysis_notes: |
  Case 5000 has two code paths:
    Farm (blnFarmLocation=True): dblDedDiscount = -0.2 (line 2202) -- SELECTED
    Non-Farm (blnFarmLocation=False): dblDedDiscount = -0.25 (line 2205) -- not selected
  Developer chose farm path only.
```

---

### Example B: Array6 Rate Increase with Mixed Rounding

**Input operation (from Decomposer):**

```yaml
id: "op-004-01"
srd: "srd-004"
title: "Multiply liability bundle premiums by 1.03"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "GetLiabilityBundlePremiums"
agent: "rate-modifier"
pattern: "base_rate_increase"
parameters:
  factor: 1.03
  scope: "all_territories"
  rounding: "auto"
```

**Step 4 -- Find function:**
- Search for "GetLiabilityBundlePremiums" in function index
- Found: lines 4012-4104 (93 lines)
- 1 match = unambiguous

**Step 5 -- Find Array6 assignments:**
- Scan lines 4012-4104 for `= Array6(`
- Found 48 Array6 assignment lines
- Skipped:
  - Line 4043: `liabilityPremiumArray = Array6(0, 0, 0, 0, 0, 0)` -- all zeros
  - Line 4091: `IsItemInArray(code, Array6(COVITEM_PRIMARY...))` -- membership test

**Step 6 -- Rounding resolution:**
- 42 lines: all integer values --> rounding: "banker"
- 6 lines: contain decimal values (324.29, 462.32) --> rounding: "none"
- Operation-level: "mixed"

**Report to developer:**

```
[Analyzer] Rounding resolution for op-004-01 (GetLiabilityBundlePremiums):
            48 Array6 assignment lines found:
              42 lines with integer values -> banker rounding (round to nearest cent)
              6 lines with decimal values -> no rounding (keep full precision)
              1 line all zeros -> skip (0 * 1.03 = 0)
              1 line skipped: membership test (IsItemInArray)

            Operation-level rounding: MIXED (per-line rounding in target_lines)
```

**Updated operation (abbreviated):**

```yaml
# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
function_line_start: 4012
function_line_end: 4104
rounding_resolved: "mixed"
rounding_detail: |
  42 lines integer values -> banker
  6 lines decimal values -> none
target_lines:
  - line: 4058
    content: "                        liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)"
    context: "Farm > PRIMARYITEM > Enhanced Comp"
    rounding: "banker"
    value_count: 6
  - line: 4062
    content: "                        liabilityPremiumArray = Array6(0, 0, 0, 0, 324.29, 462.32)"
    context: "Farm > PRIMARYITEM > ELITECOMP"
    rounding: "none"
    value_count: 6
  # ... 46 more entries
skipped_lines:
  - line: 4043
    content: "            liabilityPremiumArray = Array6(0, 0, 0, 0, 0, 0)"
    reason: "Default initialization (all zeros)"
  - line: 4091
    content: "            If IsItemInArray(coverageItem.Code, Array6(...))"
    reason: "Membership test (IsItemInArray), not a rate value"
candidates_shown: 1
developer_confirmed: true
```

---

### Example C: AB Auto Base Rate -- Function Name Variation

**Input operation (from Decomposer):**

```yaml
id: "op-001-01"
srd: "srd-001"
title: "Multiply AB Auto base rate Array6 values by 1.05"
file: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
file_type: "lob_specific"
function: "GetBaseRate_Auto"
agent: "rate-modifier"
pattern: "base_rate_increase"
parameters:
  factor: 1.05
  scope: "all_territories"
  rounding: "auto"
```

**Step 4 -- Find function:**
- Search for "GetBaseRate_Auto" in mod_Algorithms_ABAuto20250101.vb
- 0 matches!
- Search with pattern "GetBaseRate*": 0 matches
- Search with broader pattern "GetFactor*BaseRate*":
  - Found: GetFactor_BaseRate (lines 1201-1235)
- Search with broader pattern "*BaseRate*":
  - Found: GetFactor_BaseRate (lines 1201-1235)
  - Found: SetFactor_BaseRateGroup (lines 1240-1288)

**Show to developer:**

```
[Analyzer] Function "GetBaseRate_Auto" not found in mod_Algorithms_ABAuto20250101.vb

            Searched 47 functions. Closest matches:
              1. GetFactor_BaseRate (lines 1201-1235) -- contains territory Array6 tables
              2. SetFactor_BaseRateGroup (lines 1240-1288) -- contains class Array6 tables

            Which function should op-001-01 target?
            (Enter a number, or type the function name)
```

**Developer selects (1) -- GetFactor_BaseRate.**

**Step 5 -- Find Array6 in GetFactor_BaseRate:**

```vb
Select Case oCurrentInscoCovItem.Fields.Item(...LOCFACTOR).Value
    Case TERRITORY01 : varRates = Array6(105.01, 103.74, 311.9, 375.17, 23.85, 1793.39, 63.15, 216.44)
    Case TERRITORY02 : varRates = Array6(75.65, 149.74, 376.73, 541.46, 38.23, 1256.05, 44.23, 168.22)
    Case TERRITORY03 : varRates = Array6(78.59, 152.91, 257.86, 552.93, 30.51, 1121.19, 39.48, 155.89)
    Case TERRITORY04 : varRates = Array6(105.01, 76.1, 394.17, 275.2, 22.03, 1839.17, 64.76, 225.91)
End Select
```

- 4 territory lines, each with 8 decimal values
- All values have decimals --> rounding: "none"

---

### Example D: Multiple Select Case Blocks in One Function

**Input operation (from Decomposer):**

```yaml
id: "op-010-01"
srd: "srd-010"
title: "Multiply snowmobile deductible factors by 1.02"
file: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
function: "GetBasePrem_Snowmobile"
pattern: "base_rate_increase"
parameters:
  factor: 1.02
  scope: "all_territories"
  rounding: "auto"
```

**Step 4 -- Find function:**
- Found: GetBasePrem_Snowmobile (lines 812-937) -- 126 lines

**Step 5 -- Find Array6 assignments:**
- This function has 4 DIFFERENT Select Case blocks!
- Block 1 (liability constants): no Array6
- Block 2 (coverage type premiums): inline `baseRate = 15.66` (not Array6)
- Block 3 (deductible factors): `varRates = Array6(1, 0.9, 0.92, 0.92)` etc.
- Block 4 (purchase price groups): `varRates = Array6(1, 1, 1, 1)` etc.
  - PLUS `excessRates = Array6(1, 0.41, 0.44, 0.44)` on an adjacent line!

**Show to developer (4 blocks, show ALL):**

```
[Analyzer] Operation op-010-01: GetBasePrem_Snowmobile has 4 Select Case blocks
            with Array6 assignments.

            Block 3 (lines 870-890): Deductible factors
              Line 871: varRates = Array6(1, 1, 1, 1)            Case 0
              Line 872: varRates = Array6(1, 0.9, 0.92, 0.92)    Case 250
              Line 873: varRates = Array6(1, 0.85, 0.87, 0.87)   Case 500
              Line 874: varRates = Array6(1, 0.8, 0.82, 0.82)    Case 1000

            Block 4 (lines 895-930): Purchase price rate groups
              Line 896: varRates = Array6(1, 1, 1, 1)            Case Is <= 3000
              Line 897: varRates = Array6(2, 1.365, 1.365, 1.365)  Case Is <= 4000
              ...
              Line 920: varRates = Array6(18, 6.74, 7.04, 7.04)  Case Else (varRates)
              Line 921: excessRates = Array6(1, 0.41, 0.44, 0.44) Case Else (excessRates)

            The SRD says "multiply deductible factors by 1.02".
            Which block(s) should be modified?
              a) Block 3 only (deductible factors)
              b) Block 4 only (purchase price groups)
              c) Both blocks
              d) Let me specify exact lines
```

---

### Example E: Reverse Lookup Finds Hidden Blast Radius

**Scenario:** Developer targets Home and Condo only, but mod_Common is shared by 6 LOBs.

**Step 7 -- Reverse lookup:**
- Glob for `Saskatchewan/**/Cssi.IntelliQuote.PORT*.vbproj`
- Parse each and check for references to mod_Common_SKHab
- Found references in:
  - Saskatchewan/Home/20260101/ -- IN target list
  - Saskatchewan/Condo/20260101/ -- IN target list
  - Saskatchewan/Tenant/20260101/ -- NOT in target list!
  - Saskatchewan/FEC/20260101/ -- NOT in target list!
  - Saskatchewan/Farm/20260101/ -- NOT in target list!
  - Saskatchewan/Seasonal/20260101/ -- NOT in target list!

**Report:**

```
[Analyzer] REVERSE LOOKUP WARNING: mod_Common_SKHab is referenced by 4 projects
            NOT in your target list:

            1. Saskatchewan/Tenant/20260101/Cssi.IntelliQuote.PORTSKTENANT20260101.vbproj
            2. Saskatchewan/FEC/20260101/Cssi.IntelliQuote.PORTSKFEC20260101.vbproj
            3. Saskatchewan/Farm/20260101/Cssi.IntelliQuote.PORTSKFARM20260101.vbproj
            4. Saskatchewan/Seasonal/20260101/Cssi.IntelliQuote.PORTSKSEASONAL20260101.vbproj

            Changes to mod_Common_SKHab will affect ALL 6 projects, not just Home and Condo.

            Options:
              a) Add all 4 missing projects to the target list (recommended for hab workflows)
              b) Acknowledge and proceed (changes will still propagate)
              c) Abort -- need to reconsider the scope
```

---

### Example F: DAT File Detection in GetBasePremium_Home

**Scenario:** An operation targets GetBasePremium_Home to multiply base rates by 5%.

**Step 4 -- Find function:**
- Found: GetBasePremium_Home (lines 3387-3543)

**Step 5 -- Search for Array6 assignments:**
- Scan lines 3387-3543 for `= Array6(`
- Only Array6 found is inside `IsItemInArray()` calls -- skipped as membership tests
- Search for `GetPremFromResourceFile` -- FOUND multiple calls
- This function uses DAT file lookups for base rates, NOT inline Array6 values

**Report:**

```
[Analyzer] WARNING: Operation {op_id} targets GetBasePremium_Home, but this function
            uses DAT file lookups (GetPremFromResourceFile) for base rate values.

            The base rate values are NOT in VB source code -- they are in external
            DAT files loaded at runtime. This plugin cannot edit DAT files.

            Found: 0 rate-bearing Array6 assignments
            Found: 8 GetPremFromResourceFile() calls

            This operation should have been flagged as dat_file_warning by Intake.
            Options:
              a) Mark as OUT_OF_SCOPE (skip this operation)
              b) Override -- I know the rates are in code (explain where)
```

---

## SPECIAL CASES

### Case 1: Select Case with Range Expressions

**Scenario:** The Select Case uses range syntax rather than single values:

```vb
Select Case horsePower
    Case 0 To 25  : liabilityPremiumArray = Array6(0, 0, 0, 0, 0, 0)
    Case 26 To 50 : liabilityPremiumArray = Array6(10, 12, 14, 16, 18, 36)
    Case Is > 100 : liabilityPremiumArray = Array6(41, 49, 57, 65, 73, 146)
End Select
```

**Handling:** The Analyzer must recognize `Case X To Y` and `Case Is > X` patterns.
When the Decomposer specifies `case_value: 50`, search for both `Case 50` and ranges
that include 50 (`Case 26 To 50`). Show all matches and let the developer confirm.

### Case 2: Two Arrays on Adjacent Lines (Same Case Block)

**Scenario:**

```vb
Case Else
    varRates = Array6(18, 6.74, 7.04, 7.04)
    excessRates = Array6(1, 0.41, 0.44, 0.44)
```

**Handling:** Both lines are Array6 assignments in the same Case block but target
DIFFERENT variables. The Analyzer lists both as separate target_lines. The SRD context
determines which to modify (or both, if the SRD says "all rates").

### Case 3: Array6 with Arithmetic Expressions

**Scenario:** Some Array6 arguments contain arithmetic:

```vb
varRates = Array6(30 + 10, 25.5, 40, 50)
```

**Handling:** The Analyzer flags `has_expressions: true` and precomputes
`evaluated_args` by evaluating simple VB.NET arithmetic (addition, subtraction).
The Rate Modifier uses `evaluated_args` (if present) instead of parsing VB.NET
arithmetic at execution time. If evaluation fails for any argument, fall back to
flagging for manual review. Record:

```yaml
target_lines:
  - line: 1234
    content: "varRates = Array6(30 + 10, 25.5, 40, 50)"
    context: "..."
    has_expressions: true
    evaluated_args: [40, 25.5, 40, 50]
    analysis_notes: "Array6 contains arithmetic expression '30 + 10', evaluated to 40."
```

The Rate Modifier uses `evaluated_args` for value comparison and change calculation,
then replaces the entire expression with the computed result in the output.

### Case 4: Source File Already at Target Date

**Scenario:** The .vbproj already references `mod_Common_SKHab20260101.vb` (IQWiz
already updated the reference, or a previous plugin run already created the copy).

**Handling:**
- `source_file` = `target_file` (same date)
- `needs_copy: false`
- Read the existing file at the target date
- Proceed with line number discovery normally

### Case 5: Multiple Operations in the Same Function

**Scenario:** Two operations (op-002-01 and op-003-01) both target `SetDisSur_Deductible`
but for different Case values (5000 and 2500).

**Handling:** The Analyzer finds function boundaries ONCE (lines 2108-2227). For each
operation, it searches within those same boundaries for the specific Case value. Each
operation gets its own `target_lines` pointing to different lines within the same
function. The Planner will sequence them bottom-to-top (Case 5000 on line 2199 runs
before Case 2500 on line 2178).

### Case 6: Cross-LOB File Discovery

**Scenario:** The operation targets `Option_SewerBackup_SKHome20231001.vb`, which
the File Reference Map shows is compiled by BOTH Home and Condo.

**Handling:** Record the cross-LOB nature in the blast radius:

```yaml
cross_lob_warning: "Option_SewerBackup_SKHome20231001.vb is named for Home but also compiled by Condo"
```

If the operation needs a new dated copy, the .vbproj updates must include BOTH the
Home and Condo .vbproj files. The files_to_copy.yaml entry includes both:

```yaml
vbproj_updates:
  - vbproj: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
    old_include: "..\\Code\\Option_SewerBackup_SKHome20231001.vb"
    new_include: "..\\Code\\Option_SewerBackup_SKHome20260101.vb"
  - vbproj: "Saskatchewan/Condo/20260101/Cssi.IntelliQuote.PORTSKCONDO20260101.vbproj"
    old_include: "..\\Code\\Option_SewerBackup_SKHome20231001.vb"
    new_include: "..\\Code\\Option_SewerBackup_SKHome20260101.vb"
```

### Case 7: File Referenced by .vbproj but Missing from Disk

**Scenario:** The .vbproj contains `<Compile Include="..\..\Code\SomeFile20260101.vb">`
but the file does not exist on disk.

**Handling:** Flag as error. The file may not have been copied by IQWiz yet, or the
.vbproj may be stale.

```
[Analyzer] ERROR: File referenced by .vbproj but not found on disk:
            .vbproj: {vbproj_path}
            Reference: {include_path}
            Resolved to: {resolved_path}

            This file is expected to exist but is missing. Possible causes:
              - IQWiz has not been run yet for this version folder
              - The .vbproj was manually edited with a wrong path
              - The file was deleted or renamed

            Cannot analyze operations targeting this file until it exists.
```

### Case 8: Nova Scotia SharedClass/ Directory

**Scenario:** An operation targets a Nova Scotia hab workflow. The SHARDCLASS folder
is named "SharedClass" instead of "SHARDCLASS".

**Handling:** Read `config.yaml` for the `shardclass_folder` value for this province.
Use the configured name in all SHARDCLASS-related searches.

```python
province_config = config["provinces"][province_code]
shardclass_name = province_config.get("shardclass_folder", "SHARDCLASS")
# For NS: shardclass_name = "SharedClass"
```

### Case 9: Const Declaration Rate Values

**Scenario:** A rate value is stored as a `Const` rather than in a Select Case or Array6.

```vb
Const ACCIDENTBASE = 200
```

**Handling:** Search for `Const {name}` patterns within the appropriate scope. For
module-level constants (before the first Sub/Function), search lines 1 through the
first function declaration. Record the line number and current value.

```yaml
target_lines:
  - line: 15
    content: "    Const ACCIDENTBASE = 200"
    context: "Module-level constant declaration"
    rounding: null
```

### Case 10: Operation Targets a New File (Logic Modifier Creates It)

**Scenario:** An operation for `new_endorsement_flat` targets a new
`Option_NewEndorsement_SKHome20260101.vb` that does not yet exist in any .vbproj.

**Handling:**
- `source_file: null` (no existing file)
- `target_file: "Saskatchewan/Code/Option_NewEndorsement_SKHome20260101.vb"`
- `needs_copy: false` (no copy, the Logic Modifier will CREATE this file)
- `needs_new_file: true`
- Provide a template reference from an existing similar file:

```yaml
template_reference: "Saskatchewan/Code/Option_Bicycle_SKHome20220502.vb"
template_reason: "Similar endorsement option file in the same LOB"
```

The Logic Modifier uses the template as a structural guide for the new file.

---

## KEY RESPONSIBILITIES (Summary)

1. **Parse .vbproj files as XML** using Python's `xml.etree.ElementTree` with the
   MSBuild namespace. Extract all `<Compile Include>` paths. Handle multiple
   `<ItemGroup>` blocks. Ignore `<Link>` child elements.

2. **Build the File Reference Map** showing which Code/ files each project compiles.
   Classify each file (shared_module, lob_specific, cross_lob, local, shardclass,
   cross_province_shared, engine_shared, hub_shared).

3. **Resolve source files** from target filenames. The Decomposer's `file` field uses
   the target date; the Analyzer finds the actual file referenced by the .vbproj
   (which may have an older date).

4. **Compute file hashes** for TOCTOU protection. Record SHA-256 hash of each source
   file. Rate Modifier / Logic Modifier will re-check before writing.

5. **Build a function index** for each source file. Find all Sub/Function declarations
   and their matching End Sub/End Function boundaries.

6. **Find target functions** using pattern-based search. Handle exact match, case-
   insensitive match, and wildcard pattern match. Present candidates when ambiguous.
   Flag DAT-file functions (GetPremFromResourceFile users) as non-editable.

7. **Apply pattern-specific search** within function boundaries:
   - base_rate_increase: find `= Array6(...)` assignments, filter out `IsItemInArray`
     and default initializations
   - factor_table_change: find `Case {value}`, extract ALL value assignments including
     nested If/Else branches
   - included_limits: find variable/constant declarations with limit values
   - new_endorsement_flat: find CalcOption routing and insertion point
   - new_liability_option: find liability function and insertion point
   - new_coverage_type: find constants section, routing function, ResourceID.vb
   - eligibility_rules: find validation function and insertion point

8. **Resolve rounding from "auto"** by inspecting actual Array6 values:
   - All integers --> "banker"
   - Any decimal --> "none"
   - Mixed across lines --> "mixed" with per-line detail

9. **Run reverse lookup** scanning ALL .vbproj files in the province to detect
   hidden blast radius from shared modules. This MUST run before building
   files_to_copy.yaml so that additional .vbproj references are included.

10. **Build files_to_copy.yaml** listing source -> target file copies with .vbproj
    update instructions for each (including references found by reverse lookup).

11. **Check for cross-province shared files** and REFUSE to assign line numbers if
    an operation targets one.

12. **Include SHARDCLASS/SharedClass** files in blast radius analysis. Use the correct
    directory name from config.yaml (NS uses "SharedClass").

13. **Generate blast_radius.md** report with risk assessment, file copies, shared
    module changes, per-LOB changes, flags, and reverse lookup results.

14. **Show, don't guess** -- present ALL candidates to the developer when multiple
    matches are found. Never silently pick one.

15. **Skip commented lines** (starting with `'` or `REM`). VB.NET comments start
    with `'` (apostrophe) or `REM`. Both must be skipped. Never report a commented
    line as a target for modification.

16. **Handle multi-block Select Case functions** -- a single function can have 4+
    Select Case blocks. Show ALL blocks with Array6 assignments and let the developer
    specify which to modify.

## Boundary with Decomposer and Planner

| Responsibility | Decomposer | Analyzer | Planner |
|---------------|:----------:|:--------:|:-------:|
| Identify target files | YES | Verifies | Uses |
| Classify file types | YES | Verifies | Uses |
| Determine function names | Best guess | Confirms by reading code | Uses |
| Determine exact line numbers | NO | YES | Uses for ordering |
| Resolve rounding: "auto" | Passes through | Resolves to banker/none/mixed | Uses |
| Detect cross-LOB file refs | Flags from .vbproj | Full reverse lookup | Reports |
| Show candidates to developer | NO (does not read code) | YES (reads actual code) | NO |
| Build dependency graph | YES | Preserves | Uses for ordering |
| Determine file copy needs | NO | YES (files_to_copy.yaml) | Builds copy phase |
| Build blast radius report | NO | YES (blast_radius.md) | Includes in plan |
| Sequence operations bottom-to-top | NO | Provides line numbers | YES (orders by line) |
| Build approval document | NO | NO | YES |

## Error Handling

### Missing .vbproj File

```
[Analyzer] ERROR: .vbproj file not found:
            {path}

            This file is listed in change_spec.yaml target_folders but does not
            exist on disk. Was IQWiz run to create this version folder?
```

### Malformed .vbproj XML

```
[Analyzer] ERROR: Cannot parse .vbproj as XML:
            {path}
            Error: {xml_error}

            This file may be corrupted. Check the file in a text editor.
```

### Source File Not Found

```
[Analyzer] ERROR: Cannot find source file for operation {op_id}:
            Expected pattern: {file_pattern}
            Searched in File Reference Map ({N} Code/ files)

            No file matches. Either:
              - The Decomposer has a wrong file name
              - The .vbproj references have changed since Decomposer ran
              - This is a new file that needs to be created
```

### Function Not Found

```
[Analyzer] WARNING: Function "{function_hint}" not found in {source_file}

            Searched {N} functions. Similar names:
              {candidates}

            Which function should operation {op_id} target?
```

### Hash Mismatch (TOCTOU Violation)

```
[Analyzer] ERROR: File hash changed between analysis steps!
            File: {source_file}
            Expected: {original_hash}
            Current:  {new_hash}

            Someone modified this file while the Analyzer was running.
            Re-run the Analyzer to get fresh line numbers.
```

### No Rate Values Found in Function

```
[Analyzer] WARNING: No rate-bearing Array6 assignments found in {function_name}
            (lines {start}-{end}).

            Possible reasons:
              - Function uses GetPremFromResourceFile() (DAT file rates)
              - Rate values are in a different function
              - Rate values use a format other than Array6

            Found instead:
              - {N} GetPremFromResourceFile() calls
              - {M} non-Array6 assignments
              - {K} Array6 calls inside IsItemInArray (membership tests)
```

---

## NOT YET IMPLEMENTED (Future Enhancements)

- **AST-based parsing:** Currently uses regex-based function detection. A full VB.NET
  AST parser would handle edge cases like multi-line function signatures, `#Region`
  directives, and `Implements` clauses more robustly.
- **Incremental re-analysis:** Currently re-reads all files from scratch. Future
  versions could cache the function index and only re-analyze files that changed.
- **Automatic old_value verification:** Currently shows candidates and asks the
  developer. Future versions could auto-match when exactly one value matches old_value.
- **Cross-file function call tracing:** Currently analyzes each file in isolation.
  Future versions could trace function calls across files to detect indirect impacts.

<!-- IMPLEMENTATION: Phase 05 -->
