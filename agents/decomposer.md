# Agent: Decomposer

## Purpose

Break each SRD into atomic operations with a dependency graph. Identify which files
each operation touches. Handle shared modules correctly for multi-LOB tickets by
ensuring shared modules are edited ONCE, not once per LOB.

**Core philosophy: ONE operation = ONE change to ONE function in ONE file.**
When a single SRD spans multiple functions or files, the Decomposer produces
multiple operations. The Decomposer identifies FILES, not line numbers -- that
precision is the Analyzer's job.

## Pipeline Position

```
[INPUT] --> Intake --> Discovery --> DECOMPOSER --> Analyzer --> Planner --> [GATE 1] --> Modifiers --> Reviewer --> [GATE 2]
                                     ^^^^^^^^^^
```

- **Upstream:** Intake agent (provides `parsed/change_spec.yaml` + `parsed/srds/srd-NNN.yaml`),
  Discovery agent (provides `analysis/code_discovery.yaml` — optional, graceful degradation)
- **Downstream:** Analyzer agent (consumes `analysis/dependency_graph.yaml` + `analysis/operations/op-{SRD}-{NN}.yaml`)

## Input Schema

```yaml
# Reads: parsed/change_spec.yaml (full schema defined in intake.md)
# Reads: parsed/srds/srd-NNN.yaml (one per SRD)
# Reads: target folder .vbproj files (to identify Code/ file references)
# Reads: config.yaml (for naming patterns, hab LOB lists, hab flags)
```

### change_spec.yaml Fields Used by Decomposer

```yaml
carrier: "Portage Mutual"
province: "SK"
province_name: "Saskatchewan"         # Human-readable, used in reporting
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
lob_category: "hab"                   # "hab" | "auto" | "mixed" (from Intake Step 2.3)
effective_date: "20260101"
ticket_ref: "DevOps 24778"           # Optional

target_folders:
  - path: "Saskatchewan/Home/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  # ... one per LOB in the workflow

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

srds:
  - id: "srd-001"
    title: "..."
    type: "base_rate_increase"
    # ... (abbreviated; full SRD in parsed/srds/)
```

### Individual SRD Fields (parsed/srds/srd-NNN.yaml)

The Decomposer reads these fields from each SRD file:

```yaml
id: "srd-NNN"
title: "..."
type: "base_rate_increase|factor_table_change|included_limits|new_endorsement_flat|new_liability_option|new_coverage_type|eligibility_rules|UNKNOWN"
complexity: "SIMPLE|MEDIUM|COMPLEX"
method: "multiply|explicit"           # Only for rate changes
scope: "all_territories|specific_territories"
lob_scope: "all|specific"
target_lobs: [...]                    # Only if lob_scope = "specific"
srd_count: 5                          # Total number of SRDs (for validation)
dat_file_warning: true|false
ambiguity_flag: true|false
ambiguity_note: "..."                 # Present when ambiguity_flag=true (reason for ambiguity)
source_text: "..."

# Pattern-specific fields (varies by type):
factor: 1.05                          # base_rate_increase
rounding: "auto"                      # base_rate_increase (Analyzer resolves later)
rounding_hint: "banker"               # Optional hint from Intake (pass through to op-{SRD}-{NN})
case_value: 5000                      # factor_table_change
old_value: -0.20                      # factor_table_change
new_value: -0.22                      # factor_table_change
limit_name: "Medical Payments"        # included_limits
old_limit: 5000.0                     # included_limits
new_limit: 10000.0                    # included_limits
target_function: null                 # Intake sets null; Decomposer infers
target_function_hint: "SetDisSur_*"   # Optional developer hint
endorsement_name: "..."               # new_endorsement_flat
option_code: 9999                     # new_endorsement_flat
premium: 75.0                         # new_endorsement_flat
category: "ENDORSEMENTEXTENSION"      # new_endorsement_flat
liability_name: "RentedDwelling"      # new_liability_option
premium_array: [0, 0, 0, 0, 324, 462] # new_liability_option
coverage_type_name: "Elite Comp."     # new_coverage_type
constant_name: "ELITECOMP"            # new_coverage_type
classifications: ["PREFERRED","STANDARD"]  # new_coverage_type
dat_ids: {Preferred: 9501, Standard: 9502} # new_coverage_type
rules: [...]                          # eligibility_rules
```

## Output Schema

### dependency_graph.yaml

```yaml
# File: analysis/dependency_graph.yaml

workflow_id: "20260101-SK-Hab-rate-update"
decomposer_version: "1.0"
decomposed_at: "2026-02-27T10:00:00"
total_operations: 6
total_out_of_scope: 1                  # SRDs with dat_file_warning = true

# SRDs marked out of scope (tracked but no operations generated)
out_of_scope:
  - srd: "srd-001"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"

# Shared module operations (done ONCE, affects all LOBs that compile the file)
shared_operations:
  op-002-01:
    srd: "srd-002"
    description: "Change $5000 deductible factor from -0.20 to -0.22"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    agent: "rate-modifier"
    depends_on: []

  op-003-01:
    srd: "srd-003"
    description: "Change $2500 deductible factor from -0.15 to -0.17"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    agent: "rate-modifier"
    depends_on: []

  op-004-01:
    srd: "srd-004"
    description: "Multiply liability bundle premiums by 1.03"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityBundlePremiums"
    agent: "rate-modifier"
    depends_on: []

  op-004-02:
    srd: "srd-004"
    description: "Multiply liability extension premiums by 1.03"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityExtensionPremiums"
    agent: "rate-modifier"
    depends_on: []

# LOB-specific operations (one per target folder per change)
lob_operations:
  op-005-01:
    srd: "srd-005"
    description: "Add DAT IDs to ResourceID.vb"
    file: "Saskatchewan/Home/20260101/ResourceID.vb"
    file_type: "lob_specific"
    agent: "logic-modifier"
    depends_on: []

  op-005-02:
    srd: "srd-005"
    description: "Add DAT IDs to ResourceID.vb"
    file: "Saskatchewan/Condo/20260101/ResourceID.vb"
    file_type: "lob_specific"
    agent: "logic-modifier"
    depends_on: []

# Partial approval constraints: which SRDs are coupled by inter-SRD dependencies.
# If SRD X is rejected at Gate 1, these constraints show which other SRDs are
# blocked as a consequence. Only populated when inter-SRD dependencies exist.
partial_approval_constraints: []        # Empty in this example (no inter-SRD deps)
# Non-empty example (see Example D):
#   - srd: "srd-003"
#     requires_srd: "srd-001"
#     reason: "op-003-01 (eligibility rule) depends on op-001-01 (constant definition)"
#     blocking_operations: ["op-003-01"]
#     required_operations: ["op-001-01"]

# Topological order for execution (respects depends_on)
execution_order:
  - "op-002-01"
  - "op-003-01"
  - "op-004-01"
  - "op-004-02"
  - "op-005-01"    # Can run in parallel with op-005-02
  - "op-005-02"    # Can run in parallel with op-005-01
```

### Individual Operation Files (analysis/operations/op-{SRD}-{NN}.yaml)

```yaml
# File: analysis/operations/op-002-01.yaml
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
```

```yaml
# File: analysis/operations/op-004-01.yaml
id: "op-004-01"
srd: "srd-004"
title: "Multiply liability bundle premiums by 1.03"
description: |
  In function GetLiabilityBundlePremiums, find all Array6() calls assigned
  to a variable (LHS of =). Multiply each numeric argument by 1.03.
  NOTE: Some Array6 values in this function contain decimals (e.g., 324.29,
  462.32) -- rounding mode must be determined by the Analyzer after
  inspecting actual values.
  IMPORTANT: Do NOT modify Array6 calls inside IsItemInArray() -- those are
  membership tests, not rate values.
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
  rounding: "auto"
```

```yaml
# File: analysis/operations/op-005-01.yaml (LOB-specific, one of many)
id: "op-005-01"
srd: "srd-005"
title: "Add Elite Comp DAT IDs to Home ResourceID.vb"
description: |
  Add DAT resource ID constants for the Elite Comp coverage type to
  ResourceID.vb in the Home version folder. Add constants for each
  classification (Preferred, Standard).
file: "Saskatchewan/Home/20260101/ResourceID.vb"
file_type: "lob_specific"
function: null
agent: "logic-modifier"
depends_on: []
blocked_by: []
pattern: "new_coverage_type"
parameters:
  coverage_type_name: "Elite Comp."
  constant_name: "ELITECOMP"
  classifications: ["PREFERRED", "STANDARD"]
  dat_ids:
    Preferred: 9501
    Standard: 9502
```

---

## EXECUTION STEPS

These are the step-by-step instructions for decomposing SRDs into atomic operations.
Follow them in order. Each step has clear inputs, actions, and outputs.

### Prerequisites

Before starting, confirm the following exist and are readable:

1. The workflow directory at `.iq-workstreams/changes/{workstream-name}/`
2. The `parsed/change_spec.yaml` inside that directory (from Intake)
3. The `parsed/srds/` directory with individual SRD files (from Intake)
4. The `.iq-workstreams/config.yaml` (for carrier info, province codes, hab flags)
5. The `.iq-update/patterns/*.yaml` files (for pattern-to-operation mapping guidance)
6. The target folder .vbproj files listed in change_spec.yaml

If any of these are missing, STOP and report:
```
[Decomposer] Cannot proceed -- missing required file: {path}
              Was Intake completed? Check manifest.yaml for intake.status = "completed".
```

### Step 1: Load Context from Intake Output

**Action:** Read the Intake output and build the working context.

1.1. Read `parsed/change_spec.yaml`. Extract:
   - `province` (e.g., "SK")
   - `province_name` (e.g., "Saskatchewan")
   - `lobs` (e.g., ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"])
   - `lob_category` (e.g., "hab" -- used in Step 5 to determine decomposition context)
   - `effective_date` (e.g., "20260101")
   - `target_folders` (list of path + vbproj entries)
   - `shared_modules` (list of shared files and which LOBs use them)
   - `srds` (summary list -- IDs and types)

1.2. Read `config.yaml` from `.iq-workstreams/`. Extract:
   - `provinces.{province_code}.lobs[]` with `is_hab` flags
   - `provinces.{province_code}.hab_code` (e.g., "SKHab")
   - `naming` patterns for file classification

1.3. Build the **LOB context table** -- one row per target folder:

```
LOB CONTEXT TABLE
------------------------------------------------------------
Example: Portage Mutual Saskatchewan Habitational (6 LOBs)
LOB         Path                         vbproj                                          is_hab
Home        Saskatchewan/Home/20260101   Cssi.IntelliQuote.PORTSKHOME20260101.vbproj     true
Condo       Saskatchewan/Condo/20260101  Cssi.IntelliQuote.PORTSKCONDO20260101.vbproj    true
Tenant      Saskatchewan/Tenant/20260101 Cssi.IntelliQuote.PORTSKTENANT20260101.vbproj   true
FEC         Saskatchewan/FEC/20260101    Cssi.IntelliQuote.PORTSKFEC20260101.vbproj       true
Farm        Saskatchewan/Farm/20260101   Cssi.IntelliQuote.PORTSKFARM20260101.vbproj      true
Seasonal    Saskatchewan/Seasonal/20260101 Cssi.IntelliQuote.PORTSKSEASONAL20260101.vbproj true
```

1.4. Read each individual SRD file from `parsed/srds/srd-NNN.yaml`. Store in memory.

1.5. If `srd_count` in change_spec is 0, report and complete:
```
[Decomposer] No SRDs to decompose. Intake produced 0 change items.
              Nothing to do -- workflow complete at Decomposer stage.
```
Write a minimal dependency_graph.yaml (total_operations: 0) and exit.

### Step 2: Parse .vbproj Files to Build the File Reference Map

**Action:** Read each target folder's .vbproj to know which Code/ files each project
compiles.

2.1. For each entry in `target_folders`, read the .vbproj as XML.

**CRITICAL: Use an XML parser, NOT regex.** The .vbproj is MSBuild XML.
In Python: `import xml.etree.ElementTree as ET`

2.2. Extract all `<Compile Include="...">` elements from the .vbproj. Record each
Include path and normalize it (resolve `..\..\` relative paths against the
version folder location to get the absolute path within the codebase).

**Use Python for path resolution** when the Include path contains `..` -- do NOT
attempt to mentally resolve relative paths (error-prone string manipulation):

```python
import os
vbproj_dir = os.path.dirname(os.path.abspath(vbproj_path))
resolved = os.path.normpath(os.path.join(vbproj_dir, include_path))
```

This handles arbitrary nesting depth (`..\..\`, `..\..\..\`, etc.) correctly.

The six source types found in .vbproj files:

```
SOURCE TYPES IN .VBPROJ
------------------------------------------------------------
Type                    Example Include Path                              Action
Local files             CalcMain.vb, ResourceID.vb                        Classify as local
Province Code/ files    ..\..\Code\mod_Common_SKHab20260101.vb            Classify per rules
SHARDCLASS files        ..\..\SHARDCLASS\cMessage.vb                      Classify as shardclass
Hub-level files         ..\..\..\Hub\modAttachScheduledArticleToDwellings.vb  Ignore (not editable)
Cross-province Code/    ..\..\..\Code\PORTCommonHeat.vb                   NEVER modify
Shared engine files     ..\..\..\..\Shared Files for Nodes\cCalcEngine.vb Ignore (not editable)
```

Some `<Compile>` elements have `<Link>` child elements -- these are cosmetic display
names for Visual Studio. Ignore `<Link>` values; use the `Include` attribute path.

2.3. Build the **File Reference Map** -- for each Code/ file, record which .vbproj(s)
compile it:

```
FILE REFERENCE MAP
------------------------------------------------------------
Code/ File                                          Compiled By
mod_Common_SKHab20260101.vb                         Home, Condo, Tenant, FEC, Farm, Seasonal
CalcOption_SKHOME20260101.vb                        Home
CalcOption_SKCONDO20260101.vb                       Condo
Option_SewerBackup_SKHome20231001.vb                Home, Condo   (cross-LOB!)
Liab_RentedDwelling_SKHome20260101.vb               Home, Condo   (cross-LOB!)
Option_RentedCondo_SKCondo20220502.vb               Home, Condo   (cross-LOB!)
modFloatersAndScheduledArticles_SKHAB20220502.vb    Home, Condo, Tenant, FEC, Farm, Seasonal
```

2.4. Classify each referenced file using the File Classification Rules (Step 3).

2.5. Cross-reference with `shared_modules` from change_spec.yaml. Any file listed
there should already be classified as `shared_module`. If there is a mismatch
(e.g., change_spec says shared but .vbproj says only one LOB compiles it), flag
for developer review.

2.6. **Date consistency validation (multi-folder workflows only).** When there are
2+ target folders (e.g., multi-LOB hab workflows), extract the date portions from
all Code/ file references across all .vbproj files and compare:

```python
import re
from collections import defaultdict

# date_sets[lob] = set of dates found in that LOB's .vbproj Code/ references
date_sets = defaultdict(set)
for lob, vbproj_refs in file_reference_map_by_lob.items():
    for ref in vbproj_refs:
        # Extract YYYYMMDD date from filename (e.g., mod_Common_SKHab20260101.vb -> 20260101)
        match = re.search(r'(\d{8})\.vb$', ref)
        if match:
            date_sets[lob].add(match.group(1))
```

If the sets of referenced dates vary significantly between LOBs, warn:

```
[Decomposer] WARNING: .vbproj files reference inconsistent Code/ file dates.
             {LOB1} references dates {X, Y}, while {LOB2} references {X, Z}.
             This may indicate IQWiz was run at different times or with different
             settings. Verify the target folders are correctly configured.
```

Minor variation is expected (e.g., one LOB has an extra endorsement file with an
older date). Only warn when the core shared file dates differ between LOBs.

### Step 3: Classify Files

**Action:** Assign a file_type to every Code/ file referenced by the target .vbproj
files. Apply these rules in priority order (first match wins):

#### File Classification Rules

```
RULE 1: Cross-Province Shared (NEVER MODIFY)
  Match: file path resolves to the codebase-root Code/ directory
         (e.g., Code/PORTCommonHeat.vb, Code/mod_VICCAuto.vb)
         NOT the province-level Code/ directory
  Result: file_type = "cross_province_shared"
  Action: NEVER generate operations for these files. If an SRD seems to
          target one, flag for developer review.

RULE 2: Shared Hab Module
  Match: filename matches one of:
         - mod_Common_{Prov}Hab{Date}.vb
         - modFloatersAndScheduledArticles_{PROV}HAB{Date}.vb
         OR file is listed in change_spec.yaml shared_modules[]
  Result: file_type = "shared_module"
  Verify: Should appear in 2+ .vbproj File Reference Maps

RULE 3: Shared Auto Module
  Match: filename matches:
         - mod_Algorithms_{Prov}Auto{Date}.vb
         - mod_DisSur_{Prov}Auto{Date}.vb
  Result: file_type = "shared_module" (if compiled by multiple projects)
          OR file_type = "lob_specific" (if compiled by only Auto project)

RULE 4: LOB-Specific CalcOption File
  Match: filename matches CalcOption_{PROV}{LOB}{Date}.vb
  Result: file_type = "lob_specific"
  Note: Only one .vbproj compiles this file.

RULE 5: Cross-LOB Option/Liab File
  Match: filename matches:
         - Option_{Name}_{Prov}{LOB}{Date}.vb
         - Liab_{Name}_{Prov}{LOB}{Date}.vb
         AND the File Reference Map shows 2+ LOB projects compile it
  Result: file_type = "cross_lob"
  Note: File is named for one LOB but compiled by another. E.g.,
        Option_Bicycle_SKHome20220502.vb compiled by both Home and Condo.
        The Decomposer records this; the Analyzer runs full reverse lookup.

RULE 6: Single-LOB Option/Liab File
  Match: same filename patterns as Rule 5 but only 1 .vbproj compiles it
  Result: file_type = "lob_specific"

RULE 7: Local File (in version folder)
  Match: file is inside the version folder itself (not Code/ or SHARDCLASS/)
         Examples: ResourceID.vb, CalcMain.vb, TbwApplicationTypeFactory.vb
  Result: file_type = "local"

RULE 8: SHARDCLASS File
  Match: file is in SHARDCLASS/ (or SharedClass/ for Nova Scotia)
  Result: file_type = "shardclass"
  Note: Treat similarly to shared_module -- may be compiled by multiple LOBs.
        Flag for developer review if an operation would modify these.
```

3.1. Store the classification for each file in the working context. This is used
throughout the remaining steps to determine shared_operations vs lob_operations.

### Step 4: Filter Out-of-Scope SRDs

**Action:** Separate SRDs that cannot be processed from those that can.

4.1. For each SRD, check `dat_file_warning`:
   - If `dat_file_warning: true` --> mark as **OUT_OF_SCOPE**
   - If `dat_file_warning: false` --> proceed to decomposition

4.2. Record out-of-scope SRDs for the dependency graph:

```yaml
out_of_scope:
  - srd: "srd-001"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files, not VB code"
```

4.3. Report to the developer:

```
[Decomposer] Filtered 1 out-of-scope SRD(s):
             SRD-001: "[DAT FILE] Increase hab dwelling base rates by 5%"
             Reason: Hab dwelling base rates are in external DAT files, not VB source code.
             This SRD is tracked in the manifest but will have no executable operations.

             Proceeding with {N} in-scope SRDs.
```

4.4. If ALL SRDs are out of scope, report and complete:

```
[Decomposer] All {N} SRDs are out of scope (DAT file changes).
              No operations to generate. Workflow complete at Decomposer stage.
```

Write dependency_graph.yaml with total_operations: 0 and the out_of_scope list, then exit.

### Step 5: Decompose Each In-Scope SRD into Operations

**Action:** For each in-scope SRD, apply the SRD-type-specific decomposition rules
to produce one or more atomic operations.

Use **hierarchical operation IDs** in the format `op-{SRD_NUM}-{LOCAL_INDEX}`.
The SRD number comes from the SRD ID (e.g., srd-002 --> `op-002-XX`), and the
local index starts at 01 within each SRD. Examples:
- SRD srd-001 produces: op-001-01, op-001-02, op-001-03
- SRD srd-002 produces: op-002-01, op-002-02

This makes ID generation locally scoped to each SRD -- no global counter to lose
track of across long generation runs.

#### 5.0 Load Discovery Output and Codebase Profile (Optional)

Before decomposing SRDs, load the Discovery Agent's code map (if available) and
relevant sections from the Codebase Knowledge Base.

**5.0a Load Discovery (code_discovery.yaml):**

```python
import os

workstream_dir = f".iq-workstreams/changes/{workstream_name}"
discovery_path = os.path.join(workstream_dir, "analysis/code_discovery.yaml")
discovery = {}

if file_exists(discovery_path):
    try:
        discovery = load_yaml(discovery_path)
    except Exception:
        discovery = {}  # Malformed YAML — treat as absent, fall through to heuristics
    # Build lookup: SRD ID → resolved target (skip unresolved entries)
    discovery_targets = {}
    for srd_id, target in discovery.get("srd_targets", {}).items():
        if target.get("resolved_function"):  # Only use entries that resolved
            discovery_targets[srd_id] = target
    discovery_dispatch = discovery.get("dispatch_map", {})
    discovery_peers = discovery.get("peer_functions", {})
else:
    discovery_targets = {}
    discovery_dispatch = {}
    discovery_peers = {}
```

When `code_discovery.yaml` exists, use it to replace guesswork:
- **USE `resolved_function`** instead of inferring function names from SRD titles
- **USE `resolved_file`** instead of guessing files from naming patterns
- **USE `related_functions`** to flag multi-function changes the SRD might imply
- **USE `dispatch_map`** for endorsement category determination (instead of pattern matching)
- **USE `contains.array6_count` / `select_case_count`** for complexity estimation

If `code_discovery.yaml` does not exist, all decomposition rules fall through to
their existing heuristic behavior (graceful degradation — no discovery data needed).

**5.0b Load Codebase Profile (codebase-profile.yaml):**

```python
profile_path = ".iq-workstreams/codebase-profile.yaml"
dispatch_tables = {}
vehicle_profiles = {}

if file_exists(profile_path):
    prov = change_spec["province"]           # e.g., "SK"
    lob_category = change_spec["lob_category"]  # "hab" | "auto" | "mixed"

    # Load dispatch tables for target province+LOB combinations
    for lob in change_spec["lobs"]:
        key = f"{prov}_{lob.upper()}"        # e.g., "SK_HOME"
        section = load_yaml_section(profile_path, f"dispatch_tables.{key}")
        if section:
            dispatch_tables[key] = section

    # Load vehicle type profiles (Auto LOBs only)
    if lob_category in ("auto", "mixed"):
        for lob in change_spec["lobs"]:
            if lob.upper() == "AUTO":
                key = f"{prov}_AUTO"
                section = load_yaml_section(profile_path, f"vehicle_type_profiles.{key}")
                if section:
                    vehicle_profiles[key] = section
```

If `codebase-profile.yaml` does not exist or relevant sections are empty, all
decomposition rules fall through to their existing behavior (no profile data needed).

**Priority and merging:** Discovery output (code_discovery.yaml) takes precedence
over Codebase Profile (codebase-profile.yaml) when both provide the same information.
Discovery is per-run verified data; the profile is a persistent cache that may be stale.

Merge `discovery_dispatch` into `dispatch_tables` so existing Step 5.1.4 code
uses Discovery's freshly-traced dispatch data when available:

```python
# Discovery dispatch overrides profile dispatch (per province+LOB key)
for key, dispatch_data in discovery_dispatch.items():
    dispatch_tables[key] = dispatch_data  # Fresh data wins over stale profile
```

#### 5.0c Apply Discovery Overrides (Per-SRD)

Before applying heuristic decomposition rules, check if Discovery resolved this
SRD to an exact function. If so, use the verified data instead of guessing.

```python
def apply_discovery_override(srd, discovery_targets):
    """Override SRD hints with Discovery-verified data when available.

    Mutates srd dict in place: sets target_function_hint and target_file_hint
    to Discovery's resolved values. Downstream decomposition rules should
    check these hints FIRST before falling back to keyword inference.
    """
    srd_id = srd["id"]  # e.g., "srd-001"
    if srd_id not in discovery_targets:
        return  # No discovery data — heuristics will handle this SRD

    target = discovery_targets[srd_id]
    srd["target_function_hint"] = target["resolved_function"]
    srd["target_file_hint"] = target["resolved_file"]
    srd["discovery_contains"] = target.get("contains", {})

    # Flag related functions that may need the same change
    related = target.get("related_functions", [])
    if related:
        srd["related_function_hints"] = [
            {"name": r["name"], "note": r.get("note", "")} for r in related
        ]

# Apply to each SRD before decomposition
for srd in srds:
    apply_discovery_override(srd, discovery_targets)
```

After this step, the SRD type decomposition rules in Step 5.1 should check
`srd.get("target_function_hint")` FIRST. If set, use it as the primary target
instead of keyword-based inference. If not set, fall through to existing heuristics.

#### 5.1 SRD Type Decomposition Rules

Apply the matching rule set based on the SRD `type` field.

---

##### 5.1.1 base_rate_increase

**Input:** SRD with `type: "base_rate_increase"`, `method: "multiply"`, `factor: N`

**Decomposition logic:**

1. **Check Discovery hint FIRST.** If `target_function_hint` is set on the SRD
   (from Step 5.0c), use it as the primary search target. Also check
   `related_function_hints` for additional functions that may need the same change.

2. **If no hint, infer from SRD title and scope.** The SRD title gives clues:
   - "liability premiums" --> target functions containing "Liability" in the name
     (e.g., GetLiabilityBundlePremiums, GetLiabilityExtensionPremiums,
     GetLiabilityExtensionWatercraftPremiums)
   - "base rates" in auto --> target functions containing "BaseRate" or "BasePrem"
     in mod_Algorithms (e.g., GetBaseRate_Auto)
   - "sewer backup" --> GetSewerBackupPremium
   - "base rates" or "base premiums" in hab --> likely DAT file (should have been
     caught by dat_file_warning, but if it was not, flag now)

3. **Create ONE operation per target function.** A single SRD like "increase all
   liability premiums by 3%" may produce multiple operations if there are multiple
   liability functions (e.g., GetLiabilityBundlePremiums AND
   GetLiabilityExtensionPremiums AND GetLiabilityExtensionWatercraftPremiums).

3b. **Vehicle type fan-out (Auto only).** If the SRD targets an Auto LOB with
   scope "all" or "all_vehicles" (or no explicit vehicle type), AND `vehicle_profiles`
   were loaded in Step 5.0, enumerate all vehicle types and create one operation per
   vehicle type entry function:

   ```python
   prov = change_spec["province"]
   key = f"{prov}_AUTO"
   if key in vehicle_profiles and srd.get("scope") in ("all", "all_vehicles", None):
       for vtype in vehicle_profiles[key]["types"]:
           create_operation(
               target_function=vtype["entry_function"],
               title=f"Multiply {vtype['name']} base rate by {factor}",
               # ... standard fields
           )
   else:
       # No profile or specific vehicle type named → single operation (existing behavior)
       create_operation(target_function=inferred_function, ...)
   ```

   Without vehicle profiles, the Decomposer creates a single operation targeting
   `mod_Algorithms` broadly (the Analyzer resolves specific functions). With profiles,
   each vehicle type gets its own operation, enabling parallel capsule execution.

4. For each operation, determine the file:
   - Look up the function name pattern in the File Reference Map
   - If the function is in a `shared_module` file --> classify as shared_operation
   - If the function is in a `lob_specific` file --> classify as lob_operation

5. Set `agent: "rate-modifier"` for all base_rate_increase operations.

6. Pass `rounding: "auto"` through unchanged -- the Analyzer resolves this after
   reading actual values (integers get banker rounding, decimals get none).

**Output per operation:**

```yaml
id: "op-{SRD_NUM}-{NN}"
srd: "srd-{SRD_NUM}"
title: "Multiply {function_name} Array6 values by {factor}"
description: |
  In function {function_name}, find all Array6() calls assigned to a variable
  (LHS of =). Multiply each numeric argument by {factor}.
  IMPORTANT: Do NOT modify Array6 calls inside IsItemInArray() or other
  non-assignment contexts -- those are membership tests, not rate values.
file: "{file_path}"
file_type: "{shared_module|lob_specific}"
function: "{function_name}"
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "base_rate_increase"
parameters:
  factor: {factor}
  scope: "{scope}"
  rounding: "auto"
  rounding_hint: "{rounding_hint}"      # Only if present on SRD; omit if not set
```

**When the Decomposer cannot determine the exact function name:**

If the SRD title is broad (e.g., "increase all rates by 5%") and the Decomposer
cannot determine which specific function(s) to target, it MUST ask the developer:

```
[Decomposer] SRD-{NNN} says "{title}". In this codebase, the shared module
             {file} typically contains several rate functions. Based on the
             naming patterns, candidates include:

             1. GetLiabilityBundlePremiums -- liability premium Array6 tables
             2. GetLiabilityExtensionPremiums -- extension premium Array6 tables
             3. GetSewerBackupPremium -- sewer backup premium Array6 tables
             4. SetDisSur_Deductible -- deductible factor tables

             Which function(s) should this increase apply to?
             (Enter numbers, e.g., "1, 2" or "all")
```

The Decomposer lists candidate function names inferred from naming conventions
and config.yaml patterns. It does NOT read file contents -- function existence
verification is the Analyzer's job.

---

##### 5.1.2 factor_table_change

**Input:** SRD with `type: "factor_table_change"`, `case_value`, `old_value`, `new_value`

**Decomposition logic:**

1. Determine the target function:
   - If `target_function_hint` is set --> use it
   - If `case_value` suggests deductible amounts (200, 500, 750, 1000, 2500, 5000)
     --> likely `SetDisSur_Deductible` or similar
   - If the SRD title mentions "age discount" --> `SetDisc_Age`
   - If the SRD title mentions "claims discount" --> `SetDisc_Claims`
   - If the SRD title mentions "new home discount" --> `SetDisc_NewHome`
   - If uncertain, flag for developer (see below)

2. **Create ONE operation per SRD.** One case_value change = one operation.

3. Determine the file:
   - Factor functions are typically in mod_Common (shared_module for hab)
   - Or in mod_Algorithms / mod_DisSur (for auto)

4. Set `agent: "rate-modifier"`.

5. **Flag nested conditionals:** Factor tables like SetDisSur_Deductible have
   If/Else blocks inside each Case (e.g., farm vs non-farm paths with different
   values). Add a note in the operation description:

```yaml
description: |
  In function SetDisSur_Deductible, find Case {case_value} and change
  the discount value from {old_value} to {new_value}.
  NOTE: Factor tables in this codebase commonly have nested If/Else blocks
  within each Case (e.g., farm vs non-farm). The Analyzer must show ALL
  matching values within Case {case_value} to the developer for confirmation.
```

**When the function cannot be determined:**

```
[Decomposer] SRD-{NNN} targets a factor table value (Case {case_value}: {old_value} -> {new_value})
             but I cannot determine which function this belongs to.

             Which function contains this factor table?
             (Examples in this codebase: SetDisSur_Deductible, SetDisc_Age,
              SetDisc_Claims, SetDisc_NewHome)
```

**Output per operation:**

```yaml
id: "op-{SRD_NUM}-{NN}"
srd: "srd-{SRD_NUM}"
title: "Change {case_description} from {old_value} to {new_value}"
description: "..."
file: "{file_path}"
file_type: "shared_module"
function: "{function_name}"
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "factor_table_change"
parameters:
  case_value: {case_value}
  old_value: {old_value}
  new_value: {new_value}
```

---

##### 5.1.3 included_limits

**Input:** SRD with `type: "included_limits"`, `limit_name`, `old_limit`, `new_limit`

**Decomposition logic:**

1. Included limits are typically in CalcOption_{PROV}{LOB}{Date}.vb files
   or in mod_Common shared modules.

2. If the limit applies to all LOBs (lob_scope = "all"):
   - Check if the limit logic is in a shared module --> 1 shared_operation
   - If the limit logic is in per-LOB CalcOption files --> 1 lob_operation per LOB

3. If the limit applies to specific LOBs (lob_scope = "specific"):
   - Only generate operations for the target_lobs

4. Set `agent: "rate-modifier"`.

**Output per operation:**

```yaml
id: "op-{SRD_NUM}-{NN}"
srd: "srd-{SRD_NUM}"
title: "Change {limit_name} from {old_limit} to {new_limit}"
description: |
  Find the {limit_name} value and change from {old_limit} to {new_limit}.
  The Analyzer will locate the exact variable or constant.
file: "{file_path}"
file_type: "{shared_module|lob_specific}"
function: null                          # Analyzer determines
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "included_limits"
parameters:
  limit_name: "{limit_name}"
  old_limit: {old_limit}
  new_limit: {new_limit}
```

---

##### 5.1.4 new_endorsement_flat

**Input:** SRD with `type: "new_endorsement_flat"`, `endorsement_name`, `option_code`,
`premium`, `category`

**Dispatch table pre-check (from Step 5.0):**

Before decomposing, check the dispatch table to determine context:

```python
for lob in change_spec["lobs"]:
    key = f"{prov}_{lob.upper()}"
    if key in dispatch_tables:
        table = dispatch_tables[key]
        # Check if this option code already exists
        existing = None
        for cat_name, entries in table.get("categories", {}).items():
            for entry in entries:
                if entry["code"] == srd["option_code"]:
                    existing = {"category": cat_name, "function": entry["function"]}
                    break

        if existing:
            # Code already exists → this is a MODIFY, not CREATE
            # Adjust operation type: modify existing handler, don't create new
            log(f"[Decomposer] Option code {srd['option_code']} already exists in "
                f"{key} as {existing['function']} (category: {existing['category']})")
        else:
            # New code → determine best category from SRD or infer from dispatch
            # Find adjacent codes in the same category for template selection
            if srd.get("category") and srd["category"] in table.get("categories", {}):
                adjacent = table["categories"][srd["category"]][-3:]  # Last 3 entries
                log(f"[Decomposer] Adjacent entries in {srd['category']}: "
                    f"{[e['function'] for e in adjacent]}")
```

If dispatch tables are not available, fall through to existing behavior (no pre-check).

**Decomposition logic:**

This is a MEDIUM complexity pattern that requires both logic changes (new code
structure) and rate values (premium amount). Decompose into 2 operations per
target LOB:

1. **Operation A: Add endorsement logic** (logic-modifier)
   - Add the endorsement handler to the appropriate Option_*.vb or CalcOption_*.vb
   - This may mean creating a new Option_{Name}_{Prov}{LOB}{Date}.vb file
     or adding a Case block to an existing CalcOption file
   - file_type: "lob_specific" (one per target LOB)

2. **Operation B: Add CalcOption routing** (logic-modifier)
   - Add the Case block in CalcOption_{PROV}{LOB}{Date}.vb that routes to the
     endorsement handler
   - file_type: "lob_specific" (one per target LOB)

3. Dependencies: Operation A does NOT depend on B or vice versa if they are in
   different files. If both are in the same CalcOption file, B depends on A.

4. If `lob_scope: "all"`, repeat Operations A and B for EACH target LOB.
   If `lob_scope: "specific"`, only for target_lobs.

**Output per LOB (2 operations):**

```yaml
# Operation A: Add endorsement handler
id: "op-{SRD_NUM}-{NN}"
srd: "srd-{SRD_NUM}"
title: "Add {endorsement_name} endorsement handler for {LOB}"
description: |
  Add the {endorsement_name} endorsement handler with flat premium of {premium}.
  This involves either creating a new Option file or adding to CalcOption.
  Category: {category}. Option code: {option_code}.
file: "{CalcOption or Option file path}"
file_type: "lob_specific"
function: null                          # New function or existing routing
agent: "logic-modifier"
depends_on: []
blocked_by: []
pattern: "new_endorsement_flat"
parameters:
  endorsement_name: "{endorsement_name}"
  option_code: {option_code}
  premium: {premium}
  category: "{category}"

# Operation B: Add CalcOption routing
id: "op-{SRD_NUM}-{NN+1}"
srd: "srd-{SRD_NUM}"
title: "Add CalcOption routing for {endorsement_name} in {LOB}"
description: |
  Add a Case block in the CalcOption file that routes to the
  {endorsement_name} handler.
file: "{CalcOption file path}"
file_type: "lob_specific"
function: null
agent: "logic-modifier"
depends_on: ["op-{SRD_NUM}-{NN}"]      # A before B if same file
blocked_by: []
pattern: "new_endorsement_flat"
parameters:
  endorsement_name: "{endorsement_name}"
  option_code: {option_code}
```

---

##### 5.1.5 new_liability_option

**Input:** SRD with `type: "new_liability_option"`, `liability_name`, `premium_array`

**Dispatch table pre-check:** Same pattern as 5.1.4 — check if the liability option
code already exists in the dispatch table's LIABILITY category. If found, this is
a modify operation (update existing premium array). If not found, this is a create
operation. Use adjacent entries in the LIABILITY category as templates for the new
handler structure.

**Decomposition logic:**

1. **Operation A: Add liability premium array** (rate-modifier)
   - Add the Array6 premium row to the appropriate Liab_{Name}_{Prov}{LOB}{Date}.vb
     file or to the liability section of mod_Common
   - If in mod_Common --> shared_operation (done once)
   - If in a new Liab_*.vb file --> lob_specific (may be cross-LOB)

2. **Operation B: Add CalcOption routing** (logic-modifier)
   - Add the routing case in CalcOption that directs to the new liability handler
   - file_type: lob_specific, one per target LOB

3. Dependencies: A before B (the premium array must exist before routing references it)

**Output:**

```yaml
# Operation A: Add premium array (shared or per-LOB depending on location)
id: "op-{SRD_NUM}-{NN}"
srd: "srd-{SRD_NUM}"
title: "Add {liability_name} liability premium array"
description: |
  Add Array6 premium array for {liability_name}: {premium_array}.
  The Analyzer will determine whether this goes in mod_Common or a
  new Liab_*.vb file based on existing codebase patterns.
file: "{file_path}"
file_type: "{shared_module|lob_specific|cross_lob}"
function: null                          # New or existing function
agent: "rate-modifier"
depends_on: []
blocked_by: []
pattern: "new_liability_option"
parameters:
  liability_name: "{liability_name}"
  premium_array: {premium_array}

# Operation B: Add routing (per LOB)
id: "op-{SRD_NUM}-{NN+1}"
srd: "srd-{SRD_NUM}"
title: "Add CalcOption routing for {liability_name} in {LOB}"
description: |
  Add a routing case for the {liability_name} liability option
  in the CalcOption file.
file: "{CalcOption file path}"
file_type: "lob_specific"
function: null
agent: "logic-modifier"
depends_on: ["op-{SRD_NUM}-{NN}"]
blocked_by: []
pattern: "new_liability_option"
parameters:
  liability_name: "{liability_name}"
```

---

##### 5.1.6 new_coverage_type

**Input:** SRD with `type: "new_coverage_type"`, `coverage_type_name`, `constant_name`,
`classifications`, `dat_ids`

**Decomposition logic:**

This is the most complex decomposition. A new coverage type requires 3-4+ operations
with strict dependencies:

1. **Operation A: Add Const to mod_Common** (logic-modifier, shared)
   - Add `Public Const {constant_name} As String = "{coverage_type_name}"` to the
     module-level constants section of mod_Common
   - file_type: shared_module
   - depends_on: [] (this is the root operation)

2. **Operation B: Add rate table routing** (logic-modifier, shared)
   - Add a Case block in the rate table selection function (e.g., GetRateTableID
     or SetClassification) that routes on the new constant
   - file_type: shared_module (same file as A)
   - depends_on: [A] -- the constant must be defined before it can be referenced

3. **Operation C: Add DAT IDs to ResourceID.vb** (logic-modifier, per LOB)
   - Add DAT resource ID constants for each classification
   - file_type: local (ResourceID.vb is in the version folder)
   - depends_on: [] (independent of A and B -- DAT IDs are just integer constants)
   - Repeat for EACH target LOB

4. **Operation D: Add eligibility/validation** (logic-modifier, shared) -- OPTIONAL
   - Only if the SRD includes `rules` or if a companion eligibility_rules SRD exists
   - depends_on: [A] -- validation references the constant
   - See eligibility_rules decomposition (5.1.7)

**Output (4+ operations for a 6-LOB hab workflow):**

```yaml
# A: Add constant (shared, root)
id: "op-{SRD_NUM}-01"
srd: "srd-{SRD_NUM}"
title: "Add {constant_name} constant to mod_Common"
description: |
  Add Public Const {constant_name} As String = "{coverage_type_name}"
  to the module-level constants section of mod_Common.
file: "{mod_Common file}"
file_type: "shared_module"
function: null                          # Module-level, not inside a function
location: "module-level constants"      # When function is null, location provides a
                                        # descriptive placement hint for the Analyzer
                                        # (e.g., "module-level constants", "end of module")
agent: "logic-modifier"
depends_on: []
blocked_by: []
pattern: "new_coverage_type"
parameters:
  constant_name: "{constant_name}"
  coverage_type_name: "{coverage_type_name}"

# B: Add rate table routing (shared, depends on A)
id: "op-{SRD_NUM}-02"
srd: "srd-{SRD_NUM}"
title: "Add {coverage_type_name} rate table selection"
description: |
  Add Case block for {constant_name} in the rate table selection function.
  Route each classification to the appropriate DAT file ID.
file: "{mod_Common file}"
file_type: "shared_module"
function: "GetRateTableID"              # Or similar -- Analyzer confirms
agent: "logic-modifier"
depends_on: ["op-{SRD_NUM}-01"]        # Must define constant first
blocked_by: []
pattern: "new_coverage_type"
parameters:
  constant_name: "{constant_name}"
  classifications: {classifications}
  dat_ids: {dat_ids}

# C: Add DAT IDs (per LOB, independent)
# Repeat for each target LOB, incrementing the local index:
id: "op-{SRD_NUM}-03"
srd: "srd-{SRD_NUM}"
title: "Add {coverage_type_name} DAT IDs to {LOB} ResourceID.vb"
description: |
  Add DAT resource ID constants for {coverage_type_name}:
  {classifications} with IDs {dat_ids}.
file: "{Province}/{LOB}/{Date}/ResourceID.vb"
file_type: "local"
function: null
agent: "logic-modifier"
depends_on: []                          # Independent of A and B
blocked_by: []
pattern: "new_coverage_type"
parameters:
  coverage_type_name: "{coverage_type_name}"
  classifications: {classifications}
  dat_ids: {dat_ids}
```

---

##### 5.1.7 eligibility_rules

**Input:** SRD with `type: "eligibility_rules"`, `rules: [...]`

**Decomposition logic:**

1. Eligibility rules typically go into validation functions in mod_Common or
   CalcMain.vb. The exact function depends on the rule type.

2. If the rule references a constant that is being added by another SRD in this
   workflow (e.g., the ELITECOMP constant from a new_coverage_type SRD):
   - Create an inter-SRD dependency (see Step 6)
   - The eligibility operation depends on the constant-adding operation

3. If the rule requires new alert constants:
   - **Operation A: Add alert constant(s)** (logic-modifier)
   - **Operation B: Add validation logic** (logic-modifier)
   - depends_on: A before B

4. If no new constants are needed:
   - **Single operation** for adding the validation logic
   - Agent: logic-modifier

5. Determine file location:
   - If validation logic is in mod_Common --> shared_operation (done once)
   - If validation logic is in CalcMain.vb --> lob_operation (one per LOB)

**Output:**

```yaml
id: "op-{SRD_NUM}-{NN}"
srd: "srd-{SRD_NUM}"
title: "Add eligibility rule: {rule_summary}"
description: |
  Add validation logic: {condition_description}.
  Enforcement: {enforcement}.
  Alert message: "{alert_message}".
file: "{file_path}"
file_type: "{shared_module|lob_specific}"
function: null                          # Analyzer determines target function
agent: "logic-modifier"
depends_on: {inter_srd_dependencies}
blocked_by: []
pattern: "eligibility_rules"
parameters:
  rules: {rules_from_srd}
```

---

##### 5.1.8 UNKNOWN Type SRDs

**Input:** SRD with `type: "UNKNOWN"`

**Decomposition logic:**

1. Create a single operation marked as `needs_review: true`.
2. Set `agent: "logic-modifier"` (conservative default -- logic-modifier handles
   complex cases).
3. Include all available context from the SRD in the operation description.
4. The Analyzer will need developer guidance to determine the target file and
   function.

**Output:**

```yaml
id: "op-{SRD_NUM}-01"
srd: "srd-{SRD_NUM}"
title: "[REVIEW NEEDED] {srd_title}"
description: |
  This SRD could not be classified into a known pattern type.
  Original request: "{source_text}"

  The developer must provide guidance on:
  1. Which file(s) to modify
  2. Which function(s) to modify
  3. What specific changes to make
file: null                              # Unknown -- developer must specify
file_type: null
function: null
agent: "logic-modifier"
depends_on: []
blocked_by: []
pattern: "UNKNOWN"
needs_review: true
parameters: {}
```

Report to the developer:

```
[Decomposer] SRD-{NNN} has type UNKNOWN and could not be decomposed automatically.
             Original text: "{source_text}"

             I have created a placeholder operation (op-{SRD_NUM}-01) that needs your input:
             1. Which file should this change target?
             2. Which function within that file?
             3. Should this be handled by rate-modifier or logic-modifier?

             Once you provide this information, I will update the operation.
```

#### Optional Field: access_needs (All Logic-Modifier Patterns)

When decomposing a logic-modifier operation whose SRD description implies runtime
data access (collections, object properties, framework method calls), the Decomposer
SHOULD add an `access_needs` field to the operation YAML. This is a classification
signal that triggers the Analyzer's Code Pattern Discovery step (Step 5.9).

**When to add access_needs:**
- The SRD description mentions accessing claims, vehicles, coverage items, or alerts
- The operation requires iterating over a collection (e.g., "count NAF claims per vehicle")
- The operation calls framework methods not defined in the source code
- The SRD uses terms like "check if", "validate that", "count", "for each"

**When NOT to add access_needs:**
- Pure constant insertion (e.g., `Public Const ELITECOMP = "Elite Comp."`)
- Pure Case block insertion with hardcoded values
- DAT ID additions to ResourceID.vb
- Operations where the Decomposer is confident no runtime object access is needed

**Schema:**

```yaml
access_needs:                         # Optional — triggers Analyzer Step 5.9
  - id: "{short_identifier}"         # e.g., "claims_vehicle_count"
    description: "{what needs to be accessed}"  # e.g., "Count NAF claims per vehicle"
    data_object: "{category}"         # claims | coverage_item | alert | vehicle | premium | other
    access_type: "{how it's accessed}" # iteration | property | method_call | field_access
```

This is a **classification signal**, not discovery. The Decomposer does NOT search
the codebase for patterns — that is the Analyzer's job. The Decomposer merely flags
"this operation will need runtime data access" so the Analyzer knows to run Step 5.9.

**Example — eligibility_rules operation needing claims access:**

```yaml
id: "op-008-01"
srd: "srd-008"
title: "Add NAF claims count eligibility rule"
# ... standard fields ...
pattern: "eligibility_rules"
parameters:
  rules: [...]
access_needs:
  - id: "claims_vehicle_count"
    description: "Count NAF claims per vehicle"
    data_object: "claims"
    access_type: "iteration"
```

---

### Step 5.5: Validate Decomposition Completeness

**Action:** Before building the dependency graph, validate that all operations are
well-formed. Catching malformed operations here prevents cascading failures in
Steps 6-8.

Run these checks across all generated operations:

```
CHECK 1: Every non-OUT_OF_SCOPE SRD produced at least one operation.
  For each in-scope SRD:
    Count operations with srd == this SRD's id
    If count == 0:
      ERROR: "SRD-{NNN} is in-scope but produced 0 operations.
              This indicates a bug in the decomposition logic for type '{type}'."

CHECK 2: Every operation has required fields.
  For each operation:
    Required fields: id, srd, pattern, agent, file OR (file: null AND needs_review: true)
    If any required field is missing:
      ERROR: "Operation {id} is missing required field '{field}'."

CHECK 3: Agent values are valid.
  For each operation:
    If agent not in ["rate-modifier", "logic-modifier"]:
      ERROR: "Operation {id} has invalid agent '{agent}'.
              Must be 'rate-modifier' or 'logic-modifier'."

CHECK 4: No duplicate operation IDs.
  Collect all operation IDs into a list.
  If any ID appears more than once:
    ERROR: "Duplicate operation ID: {id}. IDs must be unique."

CHECK 5: Hierarchical ID format is correct.
  For each operation:
    ID should match pattern: op-{SRD_NUM}-{NN}
    The SRD_NUM portion should match the operation's srd field.
    If mismatch:
      ERROR: "Operation {id} has SRD mismatch: ID suggests SRD-{X}
              but srd field says SRD-{Y}."
```

If ANY check fails, STOP and report the specific error(s) before proceeding to
Step 6. Fix the decomposition output and re-validate.

If all checks pass, report:
```
[Decomposer] Validation passed: {N} operations across {M} SRDs, all well-formed.
```

---

### Step 6: Build Inter-SRD Dependencies

**Action:** After decomposing all SRDs into operations, scan for dependencies
BETWEEN operations from different SRDs.

6.1. **Constant-reference dependencies.** If one SRD adds a constant (e.g.,
new_coverage_type adds ELITECOMP) and another SRD references that constant
(e.g., eligibility_rules checks `CoverageType = ELITECOMP`):
   - The eligibility operations depend on the constant-adding operation
   - Add the constant-adding operation's ID to the eligibility operation's `depends_on`

6.2. **Same-function operations from different SRDs.** If two operations from
different SRDs target the same function in the same file:
   - They are NOT dependent on each other (they can run in any order)
   - BUT the Planner will sequence them bottom-to-top within the file
   - The Decomposer notes the shared file/function in both operations so the
     Planner can sequence them correctly

6.3. **Same-file operations from different SRDs.** If operations from different SRDs
target the same file but different functions:
   - No dependency at the Decomposer level
   - The Planner will enforce bottom-to-top ordering within the file

6.4. **Scan algorithm:**

```
For each operation O in all_operations:
  For each other operation P in all_operations (P != O):
    IF O.pattern == "new_coverage_type" AND O adds a constant:
      IF P references that constant (check P.parameters for the constant name):
        Add O.id to P.depends_on   (in P's op-{SRD}-{NN}.yaml file)
        Add P.id to O.blocked_by   (in O's op-{SRD}-{NN}.yaml file -- inverse tracking)

    IF O creates a new function AND P calls that function:
      Add O.id to P.depends_on

    IF O creates a new file AND P modifies that file:
      Add O.id to P.depends_on

NOTE: depends_on and blocked_by are updated in the individual op-{SRD}-{NN}.yaml files.
The dependency_graph.yaml summary only tracks depends_on (not blocked_by) since
blocked_by can be derived from the depends_on graph.
```

6.5. **Systematic conflict detection.** Instead of relying on noticing conflicts
while scanning, use an explicit group-and-compare algorithm:

```
ALGORITHM: Conflict Detection
--------------------------------------
1. Build a conflict key for each operation:
   - If the operation has a case_value:
     key = (file, function, case_value)
   - Else:
     key = (file, function, pattern)

2. Group operations by their conflict key.

3. For each group with 2+ operations from DIFFERENT SRDs:
   a. Compare the target values (new_value, factor, premium, etc.)
   b. If values differ --> TRUE CONFLICT. Report:

      [Decomposer] CONFLICT: Two SRDs target the same value:
                   {op_A.id} (SRD-{X}): {description_A} -> {value_A}
                   {op_B.id} (SRD-{Y}): {description_B} -> {value_B}

                   Key: ({file}, {function}, {case_value_or_pattern})

                   These cannot both be applied. Which value should be used?
                     a) {value_A} (from SRD-{X})
                     b) {value_B} (from SRD-{Y})
                     c) A different value (please specify)

      Wait for developer resolution before continuing.

   c. If values are identical --> DUPLICATE. Flag as warning:

      [Decomposer] WARNING: Duplicate operations from different SRDs:
                   {op_A.id} and {op_B.id} both do the same thing.
                   Keeping only {op_A.id} (from the earlier SRD).

      Remove the duplicate operation.

4. Operations from the SAME SRD targeting the same key are NOT conflicts
   (the SRD decomposition intentionally created them).
```

6.6. **Circular dependency check.** After building all dependencies, verify
there are no cycles:

```
Run topological sort on the dependency graph.
If a cycle is detected:
  STOP and report the cycle to the developer:

  [Decomposer] ERROR: Circular dependency detected in operation graph:
               op-{A} depends on op-{B} which depends on op-{A}

               This should not happen with correctly structured SRDs.
               Please review the change spec and clarify the dependency order.
```

### Step 7: Assign Operations to Shared vs LOB Buckets

**Action:** Sort all operations into `shared_operations` and `lob_operations`
based on their file_type.

7.1. **Shared operations** (edited ONCE, affects all LOBs that compile the file):
   - file_type = "shared_module"
   - These go into `shared_operations` in dependency_graph.yaml

7.2. **LOB operations** (one per target LOB):
   - file_type = "lob_specific" or "local"
   - These go into `lob_operations` in dependency_graph.yaml

7.3. **Cross-LOB operations** (file is named for one LOB but compiled by others):
   - file_type = "cross_lob"
   - These go into `shared_operations` (treated like shared because modifying
     the file affects multiple LOBs)
   - Add a note: `cross_lob_warning: "File named for {LOB_A} but also compiled by {LOB_B}"`

7.4. **SHARDCLASS operations:**
   - file_type = "shardclass"
   - Place in `shared_operations` if compiled by 2+ LOBs
   - Add a note: `shardclass_warning: "Shared helper class -- verify all dependent LOBs"`

7.5. **Unknown/null file_type:**
   - Place in `lob_operations` as a conservative default
   - Set `needs_review: true`

### Step 8: Compute Topological Execution Order

**Action:** Produce the `execution_order` list that respects all `depends_on`
relationships. **Use a Python script** for deterministic correctness -- do NOT
attempt to mentally execute a graph algorithm.

8.1. Collect all operation IDs and their `depends_on` lists from the op-{SRD}-{NN}.yaml
files written in Step 9.3 (or from the in-memory data structures if writing all at once).

8.2. **Write and run a temporary Python script** to perform topological sort:

```python
# File: analysis/_topo_sort.py (temporary -- delete after use)
import os, glob

# ------- Load dependency data from op files -------
# Read depends_on from each op-*.yaml file.
# We parse just the 'id' and 'depends_on' fields with simple string matching
# to avoid requiring PyYAML.

ops = {}          # id -> {"depends_on": [...], "file_type": "...", "file": "...", "srd": "..."}
op_dir = os.path.join(os.path.dirname(__file__), "operations")
for path in sorted(glob.glob(os.path.join(op_dir, "op-*.yaml"))):
    op_id = None
    deps = []
    file_type = ""
    file_path = ""
    srd = ""
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("id:"):
                op_id = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            elif stripped.startswith("depends_on:"):
                rest = stripped.split(":", 1)[1].strip()
                if rest.startswith("["):
                    # Inline list: ["op-001-01", "op-001-02"]
                    items = rest.strip("[]").split(",")
                    deps = [i.strip().strip('"').strip("'") for i in items if i.strip()]
                # else: empty or block form -- handled below
            elif stripped.startswith("- ") and not deps and op_id:
                # Block-form depends_on continuation
                val = stripped[2:].strip().strip('"').strip("'")
                if val.startswith("op-"):
                    deps.append(val)
            elif stripped.startswith("file_type:"):
                file_type = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            elif stripped.startswith("file:"):
                file_path = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            elif stripped.startswith("srd:"):
                srd = stripped.split(":", 1)[1].strip().strip('"').strip("'")
    if op_id:
        ops[op_id] = {"depends_on": deps, "file_type": file_type, "file": file_path, "srd": srd}

# ------- Kahn's Algorithm -------
from collections import deque

in_degree = {op: 0 for op in ops}
dependents = {op: [] for op in ops}     # op -> list of ops that depend on it

for op, data in ops.items():
    for dep in data["depends_on"]:
        if dep in ops:
            in_degree[op] += 1
            dependents[dep].append(op)

# Tie-breaking: shared before lob, then alphabetical by file, then by SRD order
def sort_key(op_id):
    d = ops[op_id]
    is_shared = 0 if d["file_type"] in ("shared_module", "cross_lob", "shardclass") else 1
    return (is_shared, d["file"], d["srd"], op_id)

queue = deque(sorted([op for op, deg in in_degree.items() if deg == 0], key=sort_key))
order = []

while queue:
    op = queue.popleft()
    order.append(op)
    for dep_op in sorted(dependents[op], key=sort_key):
        in_degree[dep_op] -= 1
        if in_degree[dep_op] == 0:
            queue.append(dep_op)
    # Re-sort queue to maintain tie-breaking after new additions
    queue = deque(sorted(queue, key=sort_key))

if len(order) != len(ops):
    processed = set(order)
    cycle_ops = [op for op in ops if op not in processed]
    print(f"ERROR: Circular dependency detected involving: {cycle_ops}")
else:
    print("execution_order:")
    for op in order:
        print(f'  - "{op}"')
```

Run the script:
```bash
python analysis/_topo_sort.py
```

8.3. Copy the printed `execution_order` list into dependency_graph.yaml.

8.4. **Delete the temporary script** after use:
```bash
rm analysis/_topo_sort.py
```

8.5. If the script reports a circular dependency error, STOP and report to the
developer (this should have been caught in Step 6, but the script serves as a
safety net).

8.6. **Build partial_approval_constraints.** Scan the dependency graph for inter-SRD
dependencies and record which SRDs are coupled for Gate 1 partial approval:

```
For each operation O where O.depends_on is non-empty:
  For each dependency D in O.depends_on:
    If O.srd != D.srd:
      Add a constraint entry:
        srd: O.srd
        requires_srd: D.srd
        reason: "{O.id} ({O.title}) depends on {D.id} ({D.title})"
        blocking_operations: [O.id]
        required_operations: [D.id]

Deduplicate: if multiple operations from the same SRD pair create constraints,
merge them into a single entry with combined blocking_operations and
required_operations lists.
```

Write the `partial_approval_constraints` list to dependency_graph.yaml. If there
are no inter-SRD dependencies, write an empty list.

### Step 9: Write Output Files

**Action:** Write all Decomposer output files to the `analysis/` directory.

9.1. **Ensure directory structure exists:**
```
.iq-workstreams/changes/{workstream}/analysis/
.iq-workstreams/changes/{workstream}/analysis/operations/
```

9.2. **Write `analysis/dependency_graph.yaml`:**

Assemble the complete dependency graph with:
- Header (workflow_id, decomposer_version, decomposed_at, total_operations, total_out_of_scope)
- out_of_scope list (SRDs with dat_file_warning)
- shared_operations map
- lob_operations map
- partial_approval_constraints list (from Step 8.6)
- execution_order list

9.3. **Write individual operation files** to `analysis/operations/op-{SRD}-{NN}.yaml`:

One file per operation with the full schema as shown in the Output Schema section.

9.4. **Validate all written YAML files:**

PyYAML is not in the Python standard library, so use a fallback if it is not installed:

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
        # PyYAML not installed -- do basic structure check
        with open(filepath) as f:
            content = f.read()
        if content.strip() and not content.strip().startswith('{'):
            print(f'  {os.path.basename(filepath)}: YAML basic structure OK (install PyYAML for full validation)')
        else:
            print(f'  WARNING: {os.path.basename(filepath)} may not be valid YAML')
    except yaml.YAMLError as e:
        print(f'  YAML ERROR in {os.path.basename(filepath)}: {e}')
        sys.exit(1)

print('Validating dependency_graph.yaml...')
validate_yaml('analysis/dependency_graph.yaml')

print('Validating operation files...')
for f in sorted(glob.glob('analysis/operations/op-*.yaml')):
    validate_yaml(f)

print('All files validated.')
"
```

If validation fails, fix and re-write. Do NOT proceed with malformed YAML.

9.5. **Do NOT update `manifest.yaml`** — the orchestrator handles manifest updates
after each agent completes (see skills/iq-plan/SKILL.md Manifest Update Protocol). The summary
counts (total_operations, shared_operations, lob_operations, out_of_scope) are
derivable from the operation files and dependency_graph.yaml you already wrote.
SRD status transitions (OUT_OF_SCOPE, ANALYZING) are set by the orchestrator.

### Step 10: Present Results to Developer

**Action:** Show the developer a formatted summary of all operations for awareness
(NOT approval -- approval happens at Gate 1 after the Planner builds the full plan).

10.1. Present the summary:

```
[Decomposer] Decomposed {N} SRDs into {M} operations:

  OUT OF SCOPE (tracked, no operations):
    SRD-001: [DAT FILE] Increase hab dwelling base rates by 5%

  SHARED OPERATIONS (edit once, affects all hab LOBs):
    op-002-01: rate-modifier -- Change $5000 deductible in SetDisSur_Deductible
               File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)
    op-003-01: rate-modifier -- Change $2500 deductible in SetDisSur_Deductible
               File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)
    op-004-01: rate-modifier -- Multiply GetLiabilityBundlePremiums by 1.03
               File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)
    op-004-02: rate-modifier -- Multiply GetLiabilityExtensionPremiums by 1.03
               File: mod_Common_SKHab20260101.vb (shared by 6 LOBs)

  LOB OPERATIONS (per target folder):
    op-005-01: logic-modifier -- Add Elite Comp DAT IDs to Home/ResourceID.vb
    op-005-02: logic-modifier -- Add Elite Comp DAT IDs to Condo/ResourceID.vb

  Dependencies:
    (None)

  Totals: {M} operations ({S} shared, {L} LOB-specific, {O} out-of-scope)
          Agents: {R} rate-modifier, {L} logic-modifier
          Review needed: {N}

  Next: Analyzer will map each operation to exact file:line positions.
```

10.2. Report completion:

```
[Decomposer] COMPLETE. Wrote {M} operations to analysis/.
             - analysis/dependency_graph.yaml (master graph)
             - analysis/operations/op-{SRD}-{NN}.yaml (one per operation)
             - {O} SRD(s) out of scope (DAT file)
             - {N} operation(s) flagged for review

             Next: Analyzer agent will locate exact line numbers and blast radius.
```

---

## WORKED EXAMPLES

These examples demonstrate the full Decomposer flow for common scenarios.

### Example A: Simple SK Hab Factor + Liability Changes

**Input from Intake (change_spec.yaml):**

```yaml
province: "SK"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
effective_date: "20260101"
srd_count: 4

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

srds:
  - id: "srd-001"
    type: "base_rate_increase"
    dat_file_warning: true              # Hab dwelling base rates = DAT file
  - id: "srd-002"
    type: "factor_table_change"
    case_value: 5000
    old_value: -0.20
    new_value: -0.22
  - id: "srd-003"
    type: "factor_table_change"
    case_value: 2500
    old_value: -0.15
    new_value: -0.17
  - id: "srd-004"
    type: "base_rate_increase"
    method: "multiply"
    factor: 1.03
    scope: "all_territories"
    rounding: "auto"
    dat_file_warning: false
    # Title: "Increase hab liability premiums by 3%"
```

**Step 4 -- Filter out-of-scope:**
- SRD-001: dat_file_warning = true --> OUT_OF_SCOPE

**Step 5 -- Decompose SRD-002:**
- Type: factor_table_change
- case_value: 5000 (deductible amount) --> function pattern: SetDisSur_Deductible
- File: mod_Common_SKHab20260101.vb --> file_type: shared_module
- Agent: rate-modifier
- --> op-002-01

**Step 5 -- Decompose SRD-003:**
- Type: factor_table_change
- case_value: 2500 --> same function pattern: SetDisSur_Deductible
- File: mod_Common_SKHab20260101.vb --> file_type: shared_module
- Agent: rate-modifier
- --> op-003-01

**Step 5 -- Decompose SRD-004:**
- Type: base_rate_increase, title says "liability premiums"
- Target functions: GetLiabilityBundlePremiums, GetLiabilityExtensionPremiums
  (two functions = two operations)
- File: mod_Common_SKHab20260101.vb --> file_type: shared_module for both
- Agent: rate-modifier for both
- --> op-004-01 (GetLiabilityBundlePremiums), op-004-02 (GetLiabilityExtensionPremiums)

**Step 6 -- Inter-SRD dependencies:**
- No cross-SRD dependencies. op-002-01 and op-003-01 target the same function
  (SetDisSur_Deductible) but are independent operations on different Case values.

**Step 7 -- Bucket assignment:**
- All 4 operations are shared_operations (all in mod_Common)
- No lob_operations

**Step 8 -- Topological order:**
- All operations have depends_on: [] so order is: op-002-01, op-003-01, op-004-01, op-004-02

**Final output (dependency_graph.yaml):**

```yaml
workflow_id: "20260101-SK-Hab-deductible-liability"
decomposer_version: "1.0"
decomposed_at: "2026-02-27T10:00:00"
total_operations: 4
total_out_of_scope: 1

out_of_scope:
  - srd: "srd-001"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    reason: "dat_file_warning: Hab dwelling base rates are in DAT files"

shared_operations:
  op-002-01:
    srd: "srd-002"
    description: "Change $5000 deductible factor from -0.20 to -0.22"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    agent: "rate-modifier"
    depends_on: []

  op-003-01:
    srd: "srd-003"
    description: "Change $2500 deductible factor from -0.15 to -0.17"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "SetDisSur_Deductible"
    agent: "rate-modifier"
    depends_on: []

  op-004-01:
    srd: "srd-004"
    description: "Multiply liability bundle premiums by 1.03"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityBundlePremiums"
    agent: "rate-modifier"
    depends_on: []

  op-004-02:
    srd: "srd-004"
    description: "Multiply liability extension premiums by 1.03"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetLiabilityExtensionPremiums"
    agent: "rate-modifier"
    depends_on: []

lob_operations: {}

execution_order:
  - "op-002-01"
  - "op-003-01"
  - "op-004-01"
  - "op-004-02"
```

### Example B: New Coverage Type (Complex, Multi-File)

**Input from Intake:** 1 SRD of type "new_coverage_type"

```yaml
province: "SK"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
srd_count: 1

srds:
  - id: "srd-001"
    type: "new_coverage_type"
    complexity: "COMPLEX"
    coverage_type_name: "Elite Comp."
    constant_name: "ELITECOMP"
    classifications: ["PREFERRED", "STANDARD"]
    dat_ids:
      Preferred: 9501
      Standard: 9502
    lob_scope: "all"                    # 6 hab LOBs
```

**Step 5 -- Decompose SRD-001 using new_coverage_type rules:**

Operation A: Add ELITECOMP constant to mod_Common
- file: mod_Common_SKHab20260101.vb, file_type: shared_module
- agent: logic-modifier, depends_on: []
- --> op-001-01

Operation B: Add rate table routing in mod_Common
- file: mod_Common_SKHab20260101.vb, file_type: shared_module
- agent: logic-modifier, depends_on: ["op-001-01"]
- --> op-001-02

Operations C1-C6: Add DAT IDs to ResourceID.vb (one per LOB)
- file: {Province}/{LOB}/{Date}/ResourceID.vb, file_type: local
- agent: logic-modifier, depends_on: []
- --> op-001-03 (Home), op-001-04 (Condo), op-001-05 (Tenant),
      op-001-06 (FEC), op-001-07 (Farm), op-001-08 (Seasonal)

**Step 6 -- Dependencies:**
- op-001-02 depends on op-001-01 (constant before reference)
- op-001-03 through op-001-08 are independent of all other ops

**Step 7 -- Buckets:**
- shared_operations: op-001-01, op-001-02
- lob_operations: op-001-03 through op-001-08

**Step 8 -- Topological order:**
```
op-001-01  (no deps -- root)
op-001-02  (depends on op-001-01)
op-001-03  (no deps, parallel with op-001-04 through op-001-08)
op-001-04  (no deps)
op-001-05  (no deps)
op-001-06  (no deps)
op-001-07  (no deps)
op-001-08  (no deps)
```

**Final output (8 operations):**

```yaml
workflow_id: "20260101-SK-Hab-elite-comp"
total_operations: 8
total_out_of_scope: 0

shared_operations:
  op-001-01:
    srd: "srd-001"
    description: "Add ELITECOMP constant to mod_Common"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: null
    agent: "logic-modifier"
    depends_on: []

  op-001-02:
    srd: "srd-001"
    description: "Add Elite Comp rate table routing"
    file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    file_type: "shared_module"
    function: "GetRateTableID"
    agent: "logic-modifier"
    depends_on: ["op-001-01"]

lob_operations:
  op-001-03:
    srd: "srd-001"
    description: "Add Elite Comp DAT IDs to Home ResourceID.vb"
    file: "Saskatchewan/Home/20260101/ResourceID.vb"
    file_type: "local"
    agent: "logic-modifier"
    depends_on: []

  op-001-04:
    srd: "srd-001"
    description: "Add Elite Comp DAT IDs to Condo ResourceID.vb"
    file: "Saskatchewan/Condo/20260101/ResourceID.vb"
    file_type: "local"
    agent: "logic-modifier"
    depends_on: []

  op-001-05:
    srd: "srd-001"
    description: "Add Elite Comp DAT IDs to Tenant ResourceID.vb"
    file: "Saskatchewan/Tenant/20260101/ResourceID.vb"
    file_type: "local"
    agent: "logic-modifier"
    depends_on: []

  op-001-06:
    srd: "srd-001"
    description: "Add Elite Comp DAT IDs to FEC ResourceID.vb"
    file: "Saskatchewan/FEC/20260101/ResourceID.vb"
    file_type: "local"
    agent: "logic-modifier"
    depends_on: []

  op-001-07:
    srd: "srd-001"
    description: "Add Elite Comp DAT IDs to Farm ResourceID.vb"
    file: "Saskatchewan/Farm/20260101/ResourceID.vb"
    file_type: "local"
    agent: "logic-modifier"
    depends_on: []

  op-001-08:
    srd: "srd-001"
    description: "Add Elite Comp DAT IDs to Seasonal ResourceID.vb"
    file: "Saskatchewan/Seasonal/20260101/ResourceID.vb"
    file_type: "local"
    agent: "logic-modifier"
    depends_on: []

execution_order:
  - "op-001-01"
  - "op-001-02"
  - "op-001-03"
  - "op-001-04"
  - "op-001-05"
  - "op-001-06"
  - "op-001-07"
  - "op-001-08"
```

### Example C: AB Auto Base Rate Increase (Single LOB)

**Input from Intake:**

```yaml
province: "AB"
lobs: ["Auto"]
effective_date: "20260101"
srd_count: 1

target_folders:
  - path: "Alberta/Auto/20260101"
    vbproj: "Cssi.IntelliQuote.PORTABAUTO20260101.vbproj"

shared_modules: []                      # Auto typically has no shared hab modules

srds:
  - id: "srd-001"
    type: "base_rate_increase"
    method: "multiply"
    factor: 1.05
    scope: "all_territories"
    rounding: "auto"
    dat_file_warning: false             # Auto base rates are in VB code
```

**Step 2 -- Parse .vbproj:**
- Read PORTABAUTO20260101.vbproj
- Find Compile Include for mod_Algorithms_ABAuto20260101.vb

**Step 5 -- Decompose SRD-001:**
- Type: base_rate_increase, auto context
- Target function: GetBaseRate_Auto (or similar) in mod_Algorithms
- File: Alberta/Code/mod_Algorithms_ABAuto20260101.vb
- file_type: lob_specific (only Auto compiles this)
- Agent: rate-modifier
- --> op-001-01

**Final output (1 operation):**

```yaml
workflow_id: "20260101-AB-Auto-base-rate"
total_operations: 1
total_out_of_scope: 0

shared_operations: {}

lob_operations:
  op-001-01:
    srd: "srd-001"
    description: "Multiply AB Auto base rate Array6 values by 1.05"
    file: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
    file_type: "lob_specific"
    function: "GetBaseRate_Auto"
    agent: "rate-modifier"
    depends_on: []

execution_order:
  - "op-001-01"
```

### Example D: Mixed Complexity with Inter-SRD Dependencies

**Input from Intake:** 3 SRDs where the third depends on the first

```yaml
province: "SK"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
srd_count: 3

srds:
  - id: "srd-001"
    type: "new_coverage_type"
    complexity: "COMPLEX"
    coverage_type_name: "Elite Comp."
    constant_name: "ELITECOMP"
    classifications: ["PREFERRED", "STANDARD"]
    dat_ids: {Preferred: 9501, Standard: 9502}

  - id: "srd-002"
    type: "factor_table_change"
    case_value: 5000
    old_value: -0.20
    new_value: -0.22

  - id: "srd-003"
    type: "eligibility_rules"
    complexity: "COMPLEX"
    rules:
      - condition: "CoverageType = ELITECOMP"
        enforcement: "Minimum dwelling $500,000"
        alert_message: "Elite Comp requires minimum $500K dwelling"
```

**Decomposition:**

SRD-001 (new_coverage_type):
- op-001-01: Add ELITECOMP constant (shared, logic-modifier)
- op-001-02: Add rate table routing (shared, logic-modifier, depends: [op-001-01])
- op-001-03 through op-001-08: Add DAT IDs per LOB (local, logic-modifier)

SRD-002 (factor_table_change):
- op-002-01: Change $5000 deductible (shared, rate-modifier)

SRD-003 (eligibility_rules):
- op-003-01: Add eligibility validation for ELITECOMP (shared, logic-modifier)

**Step 6 -- Inter-SRD dependency detection:**
- op-003-01 references ELITECOMP (from SRD-003 rules, condition field)
- op-001-01 defines ELITECOMP (from SRD-001)
- Therefore: op-003-01 depends_on: ["op-001-01"]

**Dependency graph:**

```
op-001-01 (add constant)
  |--- op-001-02 (rate table routing, depends on op-001-01)
  |--- op-003-01 (eligibility rule, depends on op-001-01)
op-001-03..op-001-08 (DAT IDs, independent)
op-002-01 (deductible factor, independent)
```

**Step 8.6 -- Partial approval constraints:**

```yaml
partial_approval_constraints:
  - srd: "srd-003"
    requires_srd: "srd-001"
    reason: "op-003-01 (eligibility rule) depends on op-001-01 (constant definition)"
    blocking_operations: ["op-003-01"]
    required_operations: ["op-001-01"]
```

**This matters for partial approval:** If the developer approves SRD-002 but rejects
SRD-001, only op-002-01 can execute. If SRD-003 is approved but SRD-001 is rejected,
op-003-01 CANNOT execute because it depends on op-001-01. The Planner reads the
`partial_approval_constraints` list to enforce this at Gate 1.

The Decomposer flags this:

```
[Decomposer] Dependency note: SRD-003 (eligibility rules) references the ELITECOMP
             constant defined by SRD-001 (new coverage type). If SRD-001 is rejected
             at Gate 1, SRD-003 cannot proceed either.
```

---

## SPECIAL CASES

### Case 1: Two SRDs Target the Same Function with Different Case Values

**Scenario:** SRD-002 changes Case 5000, SRD-003 changes Case 2500, both in
SetDisSur_Deductible.

**Handling:** These produce separate operations (op-002-01 and op-003-01) targeting the
same function. They are NOT dependent on each other because they modify different
Case branches. The Planner will sequence them bottom-to-top within the file.

The Decomposer does NOT flag this as a conflict. Two operations in the same
function with different Case values are normal.

### Case 2: Two SRDs Target the Same Value (True Conflict)

**Scenario:** SRD-002 says change Case 5000 to -0.22, SRD-005 says change
Case 5000 to -0.25.

**Handling:** The Decomposer detects this conflict during the systematic conflict
detection in Step 6.5 by grouping operations by their conflict key tuple
(file, function, case_value). When two operations from different SRDs share the
same key with different target values, STOP and ask:

```
[Decomposer] CONFLICT: Two SRDs target the same value:
             SRD-002: Case 5000 in SetDisSur_Deductible -> -0.22
             SRD-005: Case 5000 in SetDisSur_Deductible -> -0.25

             These cannot both be applied. Which value should be used?
               a) -0.22 (from SRD-002)
               b) -0.25 (from SRD-005)
               c) A different value (please specify)
```

Wait for developer resolution before continuing.

### Case 3: Cross-LOB File Compilation

**Scenario:** An operation targets Liab_RentedDwelling_SKHome20260101.vb, which
is compiled by both SK Home AND SK Condo .vbproj files.

**Handling:** The Decomposer classifies this as `file_type: "cross_lob"` and places
it in shared_operations with a warning:

```yaml
op-005-01:
  file: "Saskatchewan/Code/Liab_RentedDwelling_SKHome20260101.vb"
  file_type: "cross_lob"
  cross_lob_warning: "File named for Home but also compiled by Condo"
  agent: "rate-modifier"
```

The Analyzer will run a full reverse lookup to identify all affected projects.

### Case 4: SRD Targets Function That Might Not Exist

**Scenario:** SRD says "update SetDisSur_Deductible" but the function name varies
by province (e.g., might be "SetDeductibleDiscount" in Alberta).

**Handling:** The Decomposer records the function name from the SRD and adds a note:

```yaml
function: "SetDisSur_Deductible"        # From SRD hint; Analyzer verifies existence
```

The Analyzer is responsible for verifying function existence and showing alternatives
if the exact name is not found. The Decomposer does NOT validate function names
against actual code -- it uses naming patterns and config.yaml hints.

### Case 5: One SRD Produces Many Operations (10+)

**Scenario:** new_coverage_type SRD for a 6-LOB hab workflow produces 8 operations
(2 shared + 6 per-LOB).

**Handling:** This is normal. The Decomposer generates all operations without
prompting the developer. The Planner will group them into readable phases.

If the operation count exceeds 20 for a single SRD, flag for developer awareness:

```
[Decomposer] Note: SRD-{NNN} decomposed into {N} operations (complex change).
             This is expected for new_coverage_type with {L} LOBs.
```

### Case 6: LOB-Scope = Specific (Not All LOBs)

**Scenario:** SRD has `lob_scope: "specific"`, `target_lobs: ["Home", "Condo"]`
in a 6-LOB hab workflow.

**Handling:**
- Shared module operations are STILL shared (affect all LOBs that compile the file).
  Generate normally.
- LOB-specific operations are generated ONLY for the target_lobs (Home, Condo).
- If a shared module operation is needed only for the specific LOBs but the module
  is compiled by all 6 LOBs, flag for developer:

```
[Decomposer] SRD-{NNN} targets only Home and Condo, but the target file
             (mod_Common_SKHab20260101.vb) is shared by all 6 hab LOBs.
             Changes to this file will affect ALL LOBs, not just Home and Condo.
             Proceed? (The change will be visible to Tenant, FEC, Farm, Seasonal too)
```

### Case 7: Empty SRD List After Filtering

**Scenario:** All SRDs are dat_file_warning = true.

**Handling:** See Step 4.4 -- report "all out of scope" and write a minimal
dependency_graph.yaml with total_operations: 0.

### Case 8: SRD with ambiguity_flag = true

**Scenario:** SRD-003 has `ambiguity_flag: true`, `ambiguity_note: "Source says
'approximately 5%'. Using exactly 1.05."`.

**Handling:** The Decomposer passes the ambiguity through to the operation:

```yaml
op-003-01:
  parameters:
    factor: 1.05
    ambiguity_note: "Source says 'approximately 5%'. Using exactly 1.05."
```

The ambiguity was already reviewed by the developer at Intake. The Decomposer
does NOT re-ask about it. The Planner will show the before/after values at Gate 1,
giving the developer another chance to review.

### Case 9: Broad SRD ("Increase All Liability Premiums")

**Scenario:** SRD says "increase all liability premiums by 3%" and the codebase has
multiple liability functions: GetLiabilityBundlePremiums,
GetLiabilityExtensionPremiums, GetLiabilityExtensionWatercraftPremiums.

**Handling:** The Decomposer creates SEPARATE operations for each function:
- op-001-01: Multiply GetLiabilityBundlePremiums by 1.03
- op-001-02: Multiply GetLiabilityExtensionPremiums by 1.03
- op-001-03: Multiply GetLiabilityExtensionWatercraftPremiums by 1.03

Each is an independent shared_operation in the same file. The Decomposer
determines the list of target functions using naming patterns from config.yaml.
Function verification is delegated to the Analyzer.

**If uncertain which functions to target,** the Decomposer asks the developer
(see Step 5.1.1 "When the Decomposer cannot determine the exact function name").

### Case 10: Nested If/Else in Factor Tables

**Scenario:** SRD says "change $5000 deductible factor from -0.20 to -0.22" but
SetDisSur_Deductible has nested If/Else for farm vs non-farm:

```vb
Case 5000
    If IsFarm Then
        dblDedDiscount = -0.25        ' Farm value
    Else
        dblDedDiscount = -0.20        ' Non-farm value
    End If
```

**Handling:** The Decomposer does NOT resolve this ambiguity -- it does not read
actual code. Instead, it adds a note to the operation description:

```yaml
description: |
  In SetDisSur_Deductible, change Case 5000 discount from -0.20 to -0.22.
  NOTE: Factor tables in this codebase commonly have nested If/Else blocks
  (e.g., farm vs non-farm paths). The Analyzer must show ALL matching
  values within Case 5000 to the developer for confirmation.
```

The Analyzer is responsible for discovering the nested structure and presenting
ALL candidate values to the developer (show-don't-guess principle).

---

## KEY RESPONSIBILITIES (Summary)

1. **Read Intake output:** Parse change_spec.yaml and individual SRD files
2. **Parse .vbproj files as XML:** Build the File Reference Map showing which
   Code/ files each project compiles (use Python for `..` path resolution)
3. **Validate date consistency:** For multi-LOB workflows, check Code/ file dates
   across .vbproj files for consistency (Step 2.6)
4. **Classify files:** Apply the File Classification Rules to determine shared_module,
   lob_specific, cross_lob, local, shardclass, or cross_province_shared
5. **Filter out-of-scope SRDs:** dat_file_warning = true --> OUT_OF_SCOPE
6. **Decompose each SRD:** Apply type-specific rules to produce atomic operations
   (using hierarchical op-{SRD}-{NN} IDs scoped per SRD)
7. **Validate decomposition:** Check completeness -- required fields, agent values,
   no duplicates, every in-scope SRD produced operations (Step 5.5)
8. **Build dependency graph:** Intra-SRD dependencies (constant before usage) and
   inter-SRD dependencies (eligibility rule references new constant)
9. **Detect conflicts systematically:** Group operations by key tuple, compare
   values from different SRDs (Step 6.5)
10. **Assign agents:** rate-modifier for numeric value changes, logic-modifier for
    structural code changes
11. **Compute execution order:** Topological sort via Python script (Step 8)
12. **Build partial approval constraints:** Surface inter-SRD couplings for Gate 1
    (Step 8.6)
13. **Write output files:** dependency_graph.yaml + individual op-{SRD}-{NN}.yaml files
14. **Pass rounding: "auto" through unchanged** -- Analyzer resolves later
15. **Handle cross-LOB files:** Detect and flag files compiled by multiple LOBs
16. **Handle UNKNOWN SRDs:** Create placeholder with needs_review = true

## Agent Assignment Quick Reference

| What the operation does | Agent |
|------------------------|-------|
| Multiply Array6 values by a factor | rate-modifier |
| Change a Select Case value (old --> new) | rate-modifier |
| Change a Const value | rate-modifier |
| Change an included limit value | rate-modifier |
| Add a new Array6 premium row | rate-modifier |
| Add a new Const declaration | logic-modifier |
| Add a new Select Case branch | logic-modifier |
| Add a new function | logic-modifier |
| Add CalcOption routing (new Case block) | logic-modifier |
| Add DAT IDs to ResourceID.vb | logic-modifier |
| Add validation/eligibility logic | logic-modifier |
| Add alert message constants | logic-modifier |

**Rule of thumb:** rate-modifier = changing existing numeric values.
logic-modifier = adding new code structure.

## Boundary with Analyzer

The Decomposer and Analyzer have a clean boundary:

| Responsibility | Decomposer | Analyzer |
|---------------|:----------:|:--------:|
| Identify target files | YES | Verifies |
| Classify file types (shared, LOB, etc.) | YES | Verifies |
| Determine target function names | Best guess from patterns | Confirms by reading code |
| Determine exact line numbers | NO | YES |
| Resolve rounding: "auto" | Passes through | Resolves to banker/none |
| Detect cross-LOB file refs | Flags from .vbproj parsing | Full reverse lookup |
| Show candidates to developer | NO (does not read code) | YES (reads actual code) |
| Build dependency graph | YES | Preserves |
| Determine file copy needs | NO | YES |
| Build blast radius report | NO | YES |

## Error Handling

### Missing Files

```
[Decomposer] ERROR: Cannot read .vbproj file:
             {path}

             This file is listed in change_spec.yaml target_folders but does not
             exist on disk. Was IQWiz run to create this version folder?
```

### Malformed .vbproj

```
[Decomposer] ERROR: Cannot parse .vbproj as XML:
             {path}
             Error: {xml_error}

             This file may be corrupted. Check the file in a text editor.
```

### Invalid SRD YAML

```
[Decomposer] ERROR: Cannot read SRD file:
             {path}
             Error: {yaml_error}

             The Intake agent may have written malformed YAML.
             Run Intake again or fix the file manually.
```

### No Target Folders

```
[Decomposer] ERROR: change_spec.yaml has empty target_folders list.
             At least one target folder is required.
             Was /iq-plan configured correctly?
```

### Unsupported SRD Type

If the SRD has a type value that is not one of the 7 known patterns and is not
UNKNOWN, treat it as UNKNOWN and proceed with the UNKNOWN decomposition rules
(Section 5.1.8).

---

## NOT YET IMPLEMENTED (Future Enhancements)

- **Auto-discovery of function names from file contents:** Currently the Decomposer
  uses naming patterns. Future versions could scan Code/ files for function
  declarations to build a more accurate target list.
- **Batch conflict detection:** IMPLEMENTED in Step 6.5 -- systematic group-and-compare
  algorithm detects conflicts across the entire operation set after decomposition.
- **Operation merge optimization:** Two operations targeting the same function could
  be merged into a single operation with multiple parameter sets (currently kept
  separate for simplicity and auditability).

<!-- IMPLEMENTATION: Phase 04 -->
