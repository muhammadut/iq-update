---
name: iq-init
description: Initialize the IQ Rate Update plugin for a TBW carrier folder. Scans provinces, LOBs, and naming patterns into config.yaml.
user-invocable: true
---

# Skill: /iq-init

## Purpose

Initialize the `.iq-workstreams/` working directory in a TBW carrier folder.
Scans the carrier folder structure, auto-detects all provinces and LOBs, then
generates (or updates) a lightweight `config.yaml` cheat sheet that all downstream
agents depend on.

config.yaml is NOT an inventory of every file and version -- it is a structural
map. It tells agents WHERE things are and HOW they are named, not WHAT exists.
Agents discover specific versions and files from .vbproj at runtime.

This is the FIRST command a developer runs. It must be bulletproof, educational, and
set the stage for everything that follows.

## Trigger

Slash command: `/iq-init`

## Inputs

None. Everything is auto-detected from the carrier folder structure.

| Input | Source | Required | Description |
|-------|--------|----------|-------------|
| Carrier folder | Current working directory | YES | Must be a TBW carrier folder (contains province-named subdirectories) |

No required arguments. Optional: `/iq-init --refresh` to force rebuild of
pattern-library.yaml and codebase-profile.yaml even if they already exist.
Without `--refresh`, existing artifacts are kept and only missing ones are created.

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| config.yaml | `.iq-workstreams/config.yaml` | Lightweight cheat sheet: provinces, LOBs, naming patterns, paths |
| pattern-library.yaml | `.iq-workstreams/pattern-library.yaml` | Function registry with call counts for dead-code detection and pattern discovery |
| Summary report | Console output | What was found, what was created, next steps |

## Idempotency

Running `/iq-init` multiple times is safe:
- **First run:** Creates `.iq-workstreams/` and writes `config.yaml`
- **Subsequent runs:** Scans fresh, MERGES into existing `config.yaml`:
  - New provinces/LOBs are ADDED
  - Removed provinces/LOBs are FLAGGED with a warning (not deleted)
  - Cross-province shared files list is refreshed
  - Existing workflow directories under `.iq-workstreams/` are NEVER deleted
  - The `_meta.last_scanned` timestamp is updated

---

## Execution Steps

When the developer types `/iq-init`, execute these steps IN ORDER. If any step fails,
report the error and continue to the next step (Snyk-style resilience -- never crash
the whole init because one province is malformed).

**EXECUTION GUARDRAILS:**
- Do NOT spawn sub-agents for /iq-init steps. Execute all steps sequentially in the current context.
- Do NOT use `sleep` for any reason. If a tool call fails, log the error and move to the next step.
- Do NOT retry failed operations in a loop. Try once, report the result, move on.

### Step 0: Validate Preconditions

1. Determine the carrier root directory. Use the current working directory.
2. **Discover the plugin root** — the plugin may be installed locally OR via marketplace:

   **Search order:**
   a. Check `{carrier_root}/.iq-update/CLAUDE.md` (local development install)
   b. If not found, scan for marketplace cache: look for a directory matching
      `~/.claude/plugins/cache/*/iq-update/*/CLAUDE.md` (use Glob tool)
   c. If neither found, STOP:
      ```
      ERROR: The .iq-update/ plugin is not installed.
      Install via Claude Code marketplace or copy .iq-update/ to this folder.
      ```

   **Persist the result** as `plugin_root` in config.yaml (see template below).
   Report what was found:
   ```
   Plugin root:  ✓ {path}  [local | marketplace]
   ```

   **IMPORTANT:** Throughout this skill and all agent specs, `.iq-update/` is shorthand
   for `{plugin_root}/`. Always resolve paths using the discovered plugin root, NOT
   by assuming `.iq-update/` exists in the carrier root.
3. Check if `.iq-workstreams/config.yaml` already exists:
   - If YES: this is a RE-INIT (merge mode). Note this for Step 4.
   - If NO: this is a FRESH INIT.
4. **Preflight dependency checks.** Verify required tools are available:

   **Python discovery (try in order, use first that succeeds):**
   ```bash
   # 1. Check config.yaml for cached python_cmd (from previous /iq-init)
   # 2. Try: python --version 2>/dev/null
   # 3. Try: python3 --version 2>/dev/null
   # 4. Try: py -3 --version 2>/dev/null          # Windows Python Launcher
   # 5. Try: conda run -n rival_plugin python --version 2>/dev/null  # Conda env
   ```
   Once found, verify PyYAML is installed: `{python_cmd} -c "import yaml; print(yaml.__version__)"`.
   If PyYAML is missing, WARN — the plugin will work for `/iq-plan` but `/iq-execute`
   and `/iq-review` will STOP because validators require PyYAML. Install it early.

   **Persist the discovered Python command** to config.yaml as `python_cmd` (see template below).
   This prevents every downstream skill from re-discovering the Python path.

   ```bash
   # Other dependencies — discover full paths
   bash_path=$(which bash 2>/dev/null)
   bash --version 2>/dev/null
   jq_path=$(which jq 2>/dev/null)
   jq --version 2>/dev/null
   curl_path=$(which curl 2>/dev/null)
   curl --version 2>/dev/null
   ```

   **If `jq` is missing**, attempt automatic installation before giving up:
   1. Check if `winget` is available (`winget --version 2>/dev/null`)
   2. If yes → tell the developer: "jq is required for ticket fetching. Installing via winget..."
      → run `winget install jqlang.jq --accept-source-agreements --accept-package-agreements`
   3. If winget unavailable → try `choco install jq -y`
   4. If neither package manager is available → show download link:
      `https://jqlang.github.io/jq/download/`
   5. After any install attempt → re-check `jq --version 2>/dev/null` and capture the path

   Report results clearly:
   ```
   Dependency check:
     python   ✓ (3.11.4) — using: C:\Users\...\python.exe
     bash     ✓ (5.2.15) — using: /usr/bin/bash
     jq       ✓ (1.7.1)  — using: /usr/bin/jq        [or: ✗ MISSING — install manually]
     curl     ✓ (8.4.0)  — using: /usr/bin/curl
   ```

   **Persist discovered tool paths** to config.yaml alongside `python_cmd` (see template below).
   Record the full path for each tool, or `null` if not found after install attempts.

   **Missing python:** STOP — validators require Python with PyYAML.
   **Missing bash/jq/curl:** WARN — fetch-ticket.sh won't work, but the rest of the
   plugin functions fine. Continue with a warning.

5. **Azure DevOps connection check (`.env` file) — auto-populate flow.**
   The `fetch-ticket.sh` script requires Azure DevOps credentials stored in a `.env`
   file. This step auto-creates the file with sensible defaults so the developer only
   needs to paste their PAT.

   **Search order** — check both locations, use the first found:
   1. `{carrier_root}/.iq-update/.env`
   2. `{carrier_root}/.env`

   **If `.env` is found AND `ADO_PAT` has a non-empty value:**
   Report success and continue:
   ```
   Azure DevOps:  ✓ .env found, ADO_PAT is configured
   ```

   **If `.env` is found BUT `ADO_PAT` is empty or missing:**
   Skip to the PAT prompt below (Step 5c).

   **If `.env` is missing entirely:**

   5a. **Auto-create** `.iq-update/.env` with pre-filled defaults:
   ```
   ADO_ORG=rivalitinc
   ADO_PROJECT=Rival Insurance Technology
   ADO_USE_VSCOM=1
   ADO_PAT=
   ```

   5b. **Verify `.gitignore`** — check that `.env` is listed in `.iq-update/.gitignore`.
   If it is NOT listed, add it automatically and inform the developer:
   ```
   NOTE: Added .env to .iq-update/.gitignore to prevent accidental secret exposure.
   ```

   5c. **Prompt for PAT** — ask the developer:
   ```
   ═══════════════════════════════════════════════════════
     Azure DevOps PAT Setup
   ═══════════════════════════════════════════════════════

   To fetch tickets automatically, this plugin needs a Personal Access Token.

   Generate one at: https://rivalitinc.visualstudio.com/_usersettings/tokens
     → Click "New Token"
     → Name: "IQ Update Plugin"
     → Scopes: Work Items (Read)
     → Expiration: 90 days (or custom)
     → Click "Create" and copy the token

   Paste your Azure DevOps Personal Access Token:
   ═══════════════════════════════════════════════════════
   ```

   Wait for the developer to paste their PAT value.

   5d. **Write the PAT** into the `.env` file (replace the empty `ADO_PAT=` line with
   `ADO_PAT={pasted_value}`). Confirm:
   ```
   Azure DevOps:  ✓ PAT saved to .iq-update/.env
   ```

   5e. **If developer declines** (says "skip", "later", etc.):
   ```
   Azure DevOps:  ⚠ .env created but ADO_PAT is empty — /iq-plan will require manual ticket paste
   ```
   Continue to the next step.

   **IMPORTANT:** The `.env` file contains secrets (the PAT). The `.gitignore` check
   in Step 5b is mandatory — never skip it.

6. Check for province-like directories to confirm this is a TBW carrier folder:
   - Look for at least ONE directory matching a known province name (see the province
     lookup table below)
   - If no province directories found, STOP and tell the developer:
     ```
     ERROR: This does not appear to be a TBW carrier folder.
     Expected province directories (e.g., Alberta/, Ontario/, Saskatchewan/) but found none.
     Current directory: {cwd}
     ```

### Step 1: Two-Pass Scan

#### Pass 1 -- Enumerate Top-Level Directories

List all directories in the carrier root. Classify each one:

**Province Lookup Table** (folder name -> province code):

| Folder Name | Province Code | Hab Code |
|-------------|---------------|----------|
| Alberta | AB | ABHab |
| British Columbia | BC | BCHab |
| Manitoba | MB | MBHab |
| New Brunswick | NB | NBHab |
| Nova Scotia | NS | NSHab |
| Ontario | ON | ONHab |
| Prince Edward Island | PE | PEHab |
| Saskatchewan | SK | SKHab |

**Skip List** (known non-province directories -- silently skip):
- `.iq-update`
- `.iq-workstreams`
- `.build`
- `.claude`
- `.svn`
- `.git`
- `Hub`
- `Code`
- `knowledge`
- `Shared Files for Nodes`
- Any directory starting with `.`

**Unrecognized directories**: If a top-level directory is NOT in the province table
and NOT in the skip list, record a warning:
```
WARNING: Unrecognized directory: {name} (skipped)
```
Continue scanning -- do not crash.

For each province directory found, record:
- `folder`: the exact directory name (e.g., "British Columbia")
- `code`: the province code (e.g., "BC")
- `hab_code`: the hab code (e.g., "BCHab")

#### Pass 2 -- Per Province: Enumerate LOBs, Code/, SHARDCLASS/

For each province directory found in Pass 1, list its subdirectories and classify:

**Known LOB Names** (case-insensitive match, used for classification and is_hab):

| LOB Name | Default Code Suffix | is_hab |
|----------|---------------------|--------|
| Home | HOME | true |
| Auto | AUTO | false |
| Condo | CONDO | true |
| Farm | FARM | true |
| FEC | FEC | true |
| Seasonal | SEASONAL | true |
| Tenant | TENANT | true |
| Mobile Home | MH | true |

**IMPORTANT — Discovery-first LOB code suffix:**

The "Default Code Suffix" column above is a FALLBACK only. For each LOB directory,
the init MUST attempt to discover the actual suffix from `.vbproj` filenames:

1. Look inside the LOB directory for any version subfolder (pick the most recent).
2. Find the `.vbproj` file in that version folder.
3. Extract the LOB suffix from the `.vbproj` filename:
   - Pattern: `Cssi.IntelliQuote.{PREFIX}{PROV}{LOB_SUFFIX}{DATE}.vbproj`
   - Strip `Cssi.IntelliQuote.` prefix and `.vbproj` suffix
   - Strip the trailing 8-digit date
   - Strip the leading carrier prefix (discovered in Step 3 or from a prior LOB)
   - Strip the 2-letter province code
   - What remains is the actual LOB suffix
   - Example: `Cssi.IntelliQuote.PORTNBMH20260301.vbproj` → suffix = `MH`
4. If discovered suffix differs from the default table, use the DISCOVERED value
   and log: `NOTE: {LOB} uses suffix "{discovered}" (default was "{table_default}")`
5. If no `.vbproj` can be found (empty LOB directory), use the default table value
   and log: `WARNING: No .vbproj found for {LOB} — using default suffix "{default}"`

This ensures the plugin works with carriers that use non-standard LOB abbreviations
without requiring code changes.

**Special directories**:
- `Code` -> record as the province's Code/ directory (EXPECTED -- every province should have this)
- `SHARDCLASS` or `SharedClass` (case-insensitive check for both spellings) -> record `has_shardclass: true`
  - NOTE: Nova Scotia uses `SharedClass` instead of `SHARDCLASS`. The scan must handle BOTH.

**LOB code construction**: `{PROVINCE_CODE}{DISCOVERED_LOB_SUFFIX}` -- e.g., province "AB" + discovered suffix "HOME" -> `ABHOME`

For each province, record:
- List of LOBs found (name, folder, lob_code, is_hab, discovered_suffix)
- Whether Code/ exists (warn if missing: `WARNING: {Province} has no Code/ directory`)
- Whether SHARDCLASS/SharedClass exists (`has_shardclass: true/false`)
- The actual SHARDCLASS folder name on disk (`shardclass_folder`: "SHARDCLASS" or "SharedClass")

If a subdirectory does not match any known LOB name or special directory, record a warning:
```
WARNING: Unrecognized subdirectory in {Province}: {name} (skipped)
```

**No version folder scanning.** Do NOT enumerate version folders inside LOBs.
Do NOT track latest_version, version_count, or file lists. Agents discover all
of this from .vbproj at runtime. config.yaml only records the structural map
(which provinces exist, which LOBs they have, naming patterns).

### Step 2: Detect Cross-Province Shared Files and Hub

After the two-pass scan, detect carrier-wide shared resources:

1. **Cross-province shared files**: Check if `{carrier_root}/Code/` exists and list
   its contents. These are files shared by ALL provinces. Record them in
   config.yaml as `cross_province_shared_files`. These files must NEVER be auto-modified.
   E.g., for Portage Mutual: `PORTCommonHeat.vb`, `mod_VICCAuto.vb`.

2. **Hub directory**: Check if `{carrier_root}/Hub/` exists and look for:
   - `Cssi.IntelliQuote.*.sln` -- the master solution file
   Record the exact filename found.

Do NOT inventory per-province Code/ files, do NOT list shared module versions,
do NOT enumerate SHARDCLASS contents. Agents discover these from .vbproj at runtime.

### Step 3: Determine Carrier Metadata

Detect the carrier name and prefix from existing files:

1. **Carrier prefix**: Look at the master solution filename in Hub/.
   Pattern: `Cssi.IntelliQuote.{CarrierName}.sln`
   Extract `{CarrierName}` (e.g., "PortageMutual" -> carrier name "Portage Mutual")

2. **Carrier prefix for code**: Look at any .vbproj filename in any version folder.
   Pattern: `Cssi.IntelliQuote.{PREFIX}{PROV}{LOB_SUFFIX}{DATE}.vbproj`
   The `{PREFIX}` is typically "PORT" for Portage Mutual. Extract it by removing
   the province code + discovered LOB suffix + date from the .vbproj name.
   - Take a .vbproj filename like `Cssi.IntelliQuote.PORTABHOME20251201.vbproj`
   - Remove `Cssi.IntelliQuote.` prefix -> `PORTABHOME20251201.vbproj`
   - Remove `.vbproj` suffix -> `PORTABHOME20251201`
   - Remove the last 8 digits (date) -> `PORTABHOME`
   - Remove the province code + discovered LOB suffix -> if province is AB
     and discovered suffix is HOME, remove `ABHOME` -> `PORT`
   - That is the carrier prefix.
   - NOTE: Use the DISCOVERED LOB suffix (from Pass 2), not the default table.
     This is why Pass 2 discovery runs before prefix extraction.

3. If the carrier name or prefix cannot be determined, use reasonable defaults and
   add a comment in config.yaml for the developer to verify.

### Step 4: Generate or Update config.yaml

Create or update `.iq-workstreams/config.yaml`.

#### FRESH INIT (config.yaml does not exist)

Create the `.iq-workstreams/` directory if needed, then write `config.yaml`
using the template below. Populate ALL fields from the scan results.

#### RE-INIT / MERGE (config.yaml already exists)

1. Read the existing `config.yaml`
2. Scan produces a "fresh" config from the current folder state
3. Merge strategy:
   - **New provinces found on disk but not in config**: ADD them with a comment `# ADDED by re-scan on {date}`
   - **Provinces in config but missing from disk**: DO NOT delete. Add a comment `# WARNING: not found on disk during re-scan on {date}`
   - **New LOBs found on disk but not in config for a province**: ADD them
   - **LOBs in config but missing from disk**: DO NOT delete. Add a comment `# WARNING: not found on disk during re-scan on {date}`
   - **`_meta` section**: Update `last_scanned` and `scan_hash`
   - **All other sections** (naming, paths, cross_province_shared_files, etc.): Update from scan
   - **Existing workflow directories**: NEVER touched

#### config.yaml Template

Write the config.yaml with this structure. Replace all `{...}` placeholders with
actual scan results. Use YAML comments generously to explain each section.

config.yaml is a LIGHTWEIGHT CHEAT SHEET -- it records structure and naming, NOT
inventories. No version lists, no file counts, no shared module enumerations.
Agents discover all of that from .vbproj at runtime.

```yaml
# ============================================================================
# IQ Rate Update Plugin -- Carrier Configuration (Lightweight Cheat Sheet)
# ============================================================================
# Auto-generated by /iq-init from actual repository scan.
# This file tells agents WHERE things are and HOW they are named.
# It does NOT inventory every file or version -- agents discover that at runtime.
#
# To refresh after codebase changes: run /iq-init again (safe -- merges, never destroys)
# ============================================================================

# -- Metadata -----------------------------------------------------------------
_meta:
  generated_at: "{ISO 8601 timestamp of first generation}"
  last_scanned: "{ISO 8601 timestamp of this scan}"
  scan_hash: "{SHA256 hash of the scan results, so re-runs can detect changes}"
  scanner_version: "1.0.0"

# -- Carrier Identity ---------------------------------------------------------
carrier_name: "{Detected carrier name, e.g., Portage Mutual}"
carrier_prefix: "{Detected prefix, e.g., PORT}"
root_path: "{Absolute path to carrier folder}"

# -- Plugin Location ----------------------------------------------------------
# Discovered by /iq-init Step 0. All .iq-update/ references resolve to this path.
# Local install: "{carrier_root}/.iq-update"
# Marketplace:   "~/.claude/plugins/cache/iq-update-marketplace/iq-update/0.1.0"
plugin_root: "{Absolute path to the plugin directory}"
plugin_install_type: "{local | marketplace}"

# -- Python Environment ------------------------------------------------------
# Discovered by /iq-init preflight check. Used by all downstream skills
# to run validators. Cached here so each command doesn't re-discover.
python_cmd: "{Full path to working python executable, e.g., C:/Users/.../python.exe}"

# -- Tool Paths ---------------------------------------------------------------
# Discovered by /iq-init preflight check. null = not found after install attempts.
tool_paths:
  jq: "{Full path to jq, e.g., /usr/bin/jq, or null}"
  bash: "{Full path to bash, e.g., /usr/bin/bash, or null}"
  curl: "{Full path to curl, e.g., /usr/bin/curl, or null}"

# -- Province Definitions -----------------------------------------------------
# Each province has: code, full folder name, hab_code, LOBs, and SHARDCLASS presence.
# Data sourced from actual folder structure scan.
# NOTE: No version folders listed here -- agents discover versions from .vbproj at runtime.

provinces:
  {PROV_CODE}:
    name: "{Full province name}"
    folder: "{Exact directory name}"
    hab_code: "{ProvCode}Hab"
    has_shardclass: {true|false}
    shardclass_folder: "{SHARDCLASS or SharedClass -- actual folder name on disk}"
    has_code_dir: {true|false}
    lobs:
      - name: "{LOB display name}"
        folder: "{Exact directory name}"
        lob_code: "{PROV_CODE}{LOB_UPPER}"
        is_hab: {true|false}

# -- Naming Patterns ----------------------------------------------------------
# These patterns define how files, projects, and modules are named.
# {prov} = province code (AB, BC, etc.)
# {lob} = LOB name as it appears in code (HOME, AUTO, CONDO, etc.)
# {date} = effective date YYYYMMDD
# {hab_code} = province hab code (ABHab, SKHab, etc.)

naming:
  vbproj: "Cssi.IntelliQuote.{carrier_prefix}{prov}{lob}{date}.vbproj"
  code_files:
    calc_option: "CalcOption_{prov}{lob}{date}.vb"
    mod_common_hab: "mod_Common_{hab_code}{date}.vb"
    mod_algorithms_auto: "mod_Algorithms_{prov}Auto{date}.vb"
    mod_dissur_auto: "mod_DisSur_{prov}Auto{date}.vb"
    mod_sumrep_auto: "mod_SumRep_{prov}Auto{date}.vb"
    option: "Option_{name}_{prov}{lob}{date}.vb"
    liability: "Liab_{name}_{prov}{lob}{date}.vb"

# -- Path Patterns ------------------------------------------------------------
# Relative to carrier root (root_path above).

paths:
  version_folder: "{province_folder}/{lob_folder}/{date}/"
  province_code_dir: "{province_folder}/Code/"
  province_shardclass_dir: "{province_folder}/{shardclass_folder}/"
  cross_province_code_dir: "Code/"
  hub_dir: "Hub/"
  master_solution: "Hub/{detected .sln filename}"
  workstreams_dir: ".iq-workstreams/"

# -- Cross-Province Shared Files (NEVER auto-modify) --------------------------
cross_province_shared_files:
  - "Code/{filename}"
  # ... one entry per file found in the root Code/ directory

# -- Hab LOBs (LOBs that share mod_Common files) ------------------------------
hab_lob_names:
  - "Home"
  - "Condo"
  - "Tenant"
  - "FEC"
  - "Farm"
  - "Seasonal"
  - "Mobile Home"

# -- Function Name Search Patterns --------------------------------------------
# Function names are NOT consistent across provinces. The Analyzer must search
# by pattern, not by hardcoded name.

function_patterns:
  base_rate_hab:
    search: "GetBasePrem*"
    examples:
      - "GetBasePremium_Home"
      - "GetBasePremium_Condo"
      - "GetBasePremiumTenantHab"
      - "GetBasePrem_FarmMobileFEC"
      - "GetBasePrem_FEC"
      - "GetBasePremium_MobileFEC"
  base_rate_auto:
    search: "GetBaseRate*"
    examples:
      - "GetBaseRate"
      - "GetBaseRateCommercial"
      - "GetBaseRate_Commercial"
  deductible_factor:
    search: "SetDis*Deductible*"
    examples:
      - "SetDisSur_Deductible"
      - "SetDiscount_AgroDeductible"
  discount_surcharge:
    search: "SetDis*|SetSur*"
    examples:
      - "SetDisSur_MultiPolicy"
      - "SetDiscount_ClaimsFree"

# -- Validation Thresholds ----------------------------------------------------
validation:
  value_sanity_threshold_percent: 50
  max_array6_args: 20
```

### Step 5: Report Results

After writing config.yaml, print a structured summary to the console. The summary
must be clear, educational, and build trust with the developer.

#### Summary Format

```
===========================================================================
 IQ Rate Update Plugin -- Initialization Complete
===========================================================================

 Carrier:    {carrier_name}
 Prefix:     {carrier_prefix}
 Root:       {root_path}
 Mode:       {FRESH INIT | RE-INIT (merged)}

---------------------------------------------------------------------------
 Provinces Found: {count}
---------------------------------------------------------------------------

 Province               Code   LOBs   SHARDCLASS   Code/
 ---------              ----   ----   ----------   -----
 Alberta                AB     {n}    No           Yes
 British Columbia       BC     {n}    No           Yes
 Manitoba               MB     {n}    No           Yes
 New Brunswick          NB     {n}    Yes          Yes
 Nova Scotia            NS     {n}    Yes*         Yes
 Ontario                ON     {n}    No           Yes
 Prince Edward Island   PE     {n}    No           Yes
 Saskatchewan           SK     {n}    Yes          Yes

 * Nova Scotia uses "SharedClass" instead of "SHARDCLASS"

---------------------------------------------------------------------------
 Totals
---------------------------------------------------------------------------
 Total provinces:        {n}
 Total LOBs:             {n} across all provinces
 Cross-province files:   {n} (in Code/ -- NEVER auto-modify)
 Hub solution:           {filename}

---------------------------------------------------------------------------
 Warnings ({count})
---------------------------------------------------------------------------
 {list each warning from the scan, or "None" if clean}

---------------------------------------------------------------------------
 What Was Created
---------------------------------------------------------------------------
 .iq-workstreams/
   config.yaml          <- Carrier configuration ({n} provinces, {n} LOBs)
   pattern-library.yaml <- Function registry ({n} functions, {n} dead code)

---------------------------------------------------------------------------
 What This Means
---------------------------------------------------------------------------
 The plugin now knows your codebase structure. config.yaml maps every
 province and LOB so the agents know WHERE things are and HOW they are
 named. Agents discover specific versions and files from .vbproj at runtime.

 Next steps:
   1. Review .iq-workstreams/config.yaml if you want to verify the scan
   2. When you have a rate change ticket, run /iq-plan to begin a workflow

===========================================================================
```

If there are any WARNINGS, also print them prominently so the developer sees them.

If this is a RE-INIT, also show what changed:
```
---------------------------------------------------------------------------
 Changes Since Last Scan
---------------------------------------------------------------------------
 + Added:    {Province}/{LOB} (new on disk)
 ! Missing:  {Province}/{LOB} (was in config but not found on disk)
```

### Step 6: Build Pattern Library

After config.yaml is written and the summary is displayed, build the Pattern Library.
This is a one-time function registry with call-site counts, used by the Analyzer for
dead-code detection and canonical pattern discovery. Analogous to Aider's repository
map but simpler (regex + grep, no PageRank needed at this codebase scale).

**Skip conditions:**
- If `--skip-patterns` flag is passed, skip this step entirely
- If `pattern-library.yaml` already exists AND is less than 30 days old AND this is
  a RE-INIT (not fresh), print a note and skip:
  ```
  NOTE: Pattern Library exists and is {N} days old. Use /iq-init --refresh to rebuild.
  ```

#### 6.1 SCAN — Extract Function Definitions

For each `.vb` file under the codebase root (respecting province/LOB structure from
config.yaml — scan province `Code/` directories, `SHARDCLASS/` or `SharedClass/`
directories, and version folders), extract all function/sub definitions using regex:

```
Pattern: ^\s*(Public|Private|Friend)?\s*(Shared)?\s*(Function|Sub)\s+(\w+)
```

For each match, record:
- `name`: the function/sub name (capture group 4)
- `file`: relative path from codebase root
- `line`: 1-based line number of the definition
- `signature`: the full first line of the declaration (trimmed)
- `type`: "Function" or "Sub"
- `param_types`: Extract parameter names and `As` types from the declaration.
  Parse each `ByVal`/`ByRef` parameter in the signature parentheses:
  - Pattern: `(ByVal|ByRef)?\s*(\w+)\s+As\s+(\w+)` → `{name: "param_name", type: "TypeName"}`
  - If a parameter has no `As` clause, record `type: "Variant"` (VB.NET default)
  - If the function has no parameters (empty parens), record an empty list `[]`
- `return_type`: For `Function` declarations, extract the `As {Type}` after the
  closing parenthesis. For `Sub` declarations, record `null`.
  - Pattern (on the signature line): `\)\s*As\s+(\w+)` → capture group 1
  - If a `Function` has no `As` clause (rare but legal), record `"Variant"`
- `purpose_hint`: A short purpose description, capped at 120 characters:
  1. Look at the line immediately ABOVE the declaration. If it is a non-blank
     comment line (starts with `'`), strip the `'` prefix and whitespace, use it.
  2. If no comment above, apply a heuristic from the function name:
     - `Get*` → `"Returns {remainder_with_spaces}"` (e.g., `GetBasePremium_Home` → `"Returns base premium for Home"`)
     - `Set*` → `"Sets {remainder_with_spaces}"`
     - `Calc*` → `"Calculates {remainder_with_spaces}"`
     - `Is*` / `Has*` → `"Checks {remainder_with_spaces}"`
  3. If no heuristic matches, record `null`.

**Performance note:** Use Glob to find all `.vb` files first, then Grep with the
regex pattern. Run Grep calls in parallel across files where possible.

**Deduplication:** The same function name may appear in multiple files (different
provinces, different dates). Record ALL occurrences — the `file` field disambiguates.
For the top-level `functions` map, use the MOST RECENT dated file's definition
(determined by the 8-digit date in the filename).

#### 6.2 COUNT CALL SITES

For each discovered function/sub name, count non-comment references across `.vb`
files under the codebase root. **Scope to latest versions only:** For each
province/LOB combination, identify the most recent date-named version folder
(highest YYYYMMDD). Only scan `.vb` files from those latest folders, plus the
province `Code/` and `SHARDCLASS/` / `SharedClass/` directories. This prevents
older version folders from inflating call counts.

1. Search the scoped `.vb` files for the function name as a whole word (`\b{name}\b`)
2. **Exclude** the definition line itself (the line matching Step 6.1's regex)
3. **Exclude** commented lines (lines where the first non-whitespace character is `'`)
4. **Exclude** lines inside `Imports` statements
5. The remaining count = `call_sites`

**Optimization:** For large codebases, batch function names into groups and run
parallel Grep calls. A typical carrier has 500-2000 `.vb` files and 1000-2000
functions — scanning completes in ~30-60 seconds.

**Framework methods:** Some commonly-used methods (e.g., `GetClaimsVehicles`,
`GetCoverageItems`) are defined in TBW framework DLLs, not in source `.vb` files.
These will NOT appear in Step 6.1's scan but WILL appear as call sites. After the
initial function scan, also search for common accessor patterns:

```
Accessor patterns to search for:
  allIQCovItem.Get*           — framework collection accessors
  p_objCovItem.Fields.Item    — coverage item field access
  AlertHab(                   — hab alert function calls
  AlertAuto(                  — auto alert function calls
  .Claims                     — claims collection property
  .Vehicles                   — vehicle collection property
```

For each accessor pattern found, record it in the `accessor_index` section even if
no source definition exists.

#### 6.3 CLASSIFY

Mark each function based on call_sites count:

| call_sites | Status | Meaning |
|-----------|--------|---------|
| 0 | `DEAD` | No callers found — possible dead code |
| 1-2 | `ACTIVE` | Used but not widely |
| 3+ | `HIGH_USE` | Canonical/established pattern |

#### 6.4 WRITE — Save Pattern Library

Write the Pattern Library to `.iq-workstreams/pattern-library.yaml`:

```yaml
# ============================================================================
# IQ Rate Update Plugin -- Pattern Library (Function Registry)
# ============================================================================
# Auto-generated by /iq-init Step 6. One-time scan of all .vb files.
# Used by the Analyzer for dead-code detection and canonical pattern discovery.
#
# To rebuild: run /iq-init --refresh
# ============================================================================

generated_at: "{ISO 8601 timestamp}"
codebase_root: "{absolute path to carrier folder}"
scan_stats:
  total_vb_files: {N}
  total_functions: {N}
  active_functions: {N}         # call_sites >= 1
  dead_functions: {N}           # call_sites == 0
  high_use_functions: {N}       # call_sites >= 3

# -- Function Registry -------------------------------------------------------
# Keyed by function name. For duplicates across files, the most recent dated
# file's definition is used. All occurrences are recorded in all_definitions.
functions:
  {FunctionName}:
    file: "{relative path to most recent file}"
    line: {line_number}
    signature: "{full first line of declaration}"
    call_sites: {N}
    status: "{DEAD|ACTIVE|HIGH_USE}"
    # --- Type information (for downstream FUB generation and pattern matching) ---
    param_types:                     # Extracted from declaration signature
      - {name: "covItem", type: "ICoverageItem"}
      - {name: "territory", type: "Integer"}
      # Empty list [] if no parameters; each param has name + As type (or "Variant" if untyped)
    return_type: "Double"            # From "As {Type}" after closing paren; null for Sub; "Variant" if untyped Function
    purpose_hint: "Calculate base premium for Home coverage"  # First comment above decl, or heuristic from name, or null
    # all_definitions only present when function appears in multiple files:
    # all_definitions:
    #   - file: "..."
    #     line: N

  # Framework methods (found in call sites but no source definition):
  # {MethodName}:
  #   file: null
  #   call_sites: {N}
  #   status: "{ACTIVE|HIGH_USE}"
  #   note: "Framework method — found in {N} call sites, no source definition"

# -- Accessor Index -----------------------------------------------------------
# Keywords → commonly-used accessor patterns with call counts.
# The Analyzer queries this index for instant pattern lookups.
accessor_index:
  claims:
    - pattern: "{accessor pattern, e.g., allIQCovItem.GetClaimsVehicles}"
      call_sites: {N}
      example_file: "{file where this pattern is used}"
      example_line: {line_number}
    # Dead accessors included with warning:
    # - pattern: "p_objVehicle.Claims"
    #   call_sites: 0
    #   note: "DEAD — never used in active code paths"
  alerts:
    - pattern: "{e.g., AlertHab(\"...\", aaAlertAction.aanotrated)}"
      call_sites: {N}
  coverage_items:
    - pattern: "{e.g., p_objCovItem.Fields.Item(\"...\").Value}"
      call_sites: {N}
  vehicles:
    - pattern: "{e.g., allIQCovItem.GetVehicles}"
      call_sites: {N}
  premiums:
    - pattern: "{e.g., GetLiabilityBundlePremiums}"
      call_sites: {N}
```

#### 6.5 Update Summary

After writing pattern-library.yaml, append to the console summary:

```
---------------------------------------------------------------------------
 Pattern Library
---------------------------------------------------------------------------
 Total functions scanned:  {total_functions}
 Active (1+ callers):      {active_functions}
 High-use (3+ callers):    {high_use_functions}
 Dead code (0 callers):    {dead_functions}
 Accessor patterns:        {accessor_count}
 Saved to:                 .iq-workstreams/pattern-library.yaml

 The Pattern Library helps agents detect dead code and find established
 patterns. The Analyzer uses it for instant lookups during /iq-plan.
```

#### Rebuild Triggers

The Pattern Library is rebuilt when:
- **First /iq-init** — always built on fresh carrier initialization
- **/iq-init --refresh** — explicit developer request to rebuild
- **Staleness warning** — if pattern-library.yaml is older than 30 days, print:
  ```
  WARNING: Pattern Library is {N} days old. Consider running /iq-init --refresh
  to pick up new functions added since the last scan.
  ```
  This warning appears in /iq-plan's pre-flight checks (not in /iq-init itself).

#### Performance

| Metric | Typical Value |
|--------|--------------|
| Scan time | ~30-60 seconds for 500-2000 .vb files |
| Output size | ~50-200KB YAML |
| Memory usage | Never loaded fully into context — Analyzer queries specific entries |

### Step 6.6: Extract Dispatch Tables (Codebase Profile)

**Action:** For each province + LOB combination, find the LATEST CalcOption file and
parse its routing structure into a dispatch table. This gives agents instant knowledge
of "option code X routes to function Y in category Z."

6.6.1. For each province and LOB discovered in Steps 1-3:

```
1. Glob for CalcOption_{PROV}{LOB}*.vb in the province Code/ folder
   Example: Saskatchewan/Code/CalcOption_SKHome*.vb
2. Pick the latest file by date suffix (highest YYYYMMDD)
3. Read the file and find Select Case blocks:
   - Primary: Select Case for TheCategory / CategoryType / policyCategory
   - Each Case branch represents a CATEGORY (MISCPROPERTY, LIABILITY,
     ENDORSEMENTEXTENSION, VEHICLES, etc.)
4. Within each category block, extract Case lines:
   Pattern (regex): Case\s+(\d+)\s*.*?(\w+)\s*\(  OR
                     Case\s+(\d+)\s*:\s*'?\s*(.*)
   → case_value, function_call, inline_comment
5. Record: {code, function, category, description (from comment)}
```

**Parser edge cases:**
- Multi-line Case blocks (function call on next line) → join and parse
- Nested If blocks inside a Case → set `parse_warning: true` on that entry
- Missing inline comment → set `description: null`

6.6.2. Write the `dispatch_tables` section to `codebase-profile.yaml`:

```yaml
# .iq-workstreams/codebase-profile.yaml
_meta:
  version: 1
  carrier: "{carrier_name}"
  last_updated: "{ISO 8601 timestamp}"
  built_by: "/iq-init"

dispatch_tables:
  SK_HOME:
    source_file: "Saskatchewan/Code/CalcOption_SKHome20260101.vb"
    categories:
      MISCPROPERTY:
        - code: 110
          function: "Option_PersonalArticlesFloater"
          description: "Personal Articles Floater"
        - code: 120
          function: "Option_SpecialLimits"
          description: "Special Limits Coverage"
          # ... more entries
      LIABILITY:
        - code: 200
          function: "Liab_PersonalLiability"
          description: "Personal Liability"
        # ...
      ENDORSEMENTEXTENSION:
        - code: 4000
          function: "Option_IdentityFraud"
          description: "Identity Fraud Expense Coverage"
        - code: 4500
          function: "Option_ServiceLineBundle"
          description: "Service Line Coverage Bundle"
          parse_warning: true    # Only if parser encountered edge case
        # ...
  SK_CONDO:
    source_file: "Saskatchewan/Code/CalcOption_SKCondo20260101.vb"
    categories:
      # ... same structure per LOB
  AB_AUTO:
    source_file: "Alberta/Code/CalcOption_ABAuto20260101.vb"
    categories:
      # ...
```

6.6.3. If a CalcOption file is not found for a province+LOB pair, skip silently
(some LOBs may not have CalcOption files).

### Step 6.7: Build Vehicle Type Profiles

**Action:** For Auto LOBs only, discover all vehicle-type sub-functions and their
associated factor functions.

6.7.1. For each province that has an Auto LOB:

```
1. Find mod_Algorithms_{PROV}Auto*.vb (latest date suffix)
   Example: Alberta/Code/mod_Algorithms_ABAuto20260101.vb
2. Grep for GetBasePrem_ function declarations:
   Pattern: (Public|Private|Friend)\s+(Shared\s+)?Function\s+GetBasePrem_(\w+)
   → extract vehicle type name from capture group 3
3. For each vehicle type function:
   a. Record function name and line_start
   b. Read the function body (up to matching End Function)
   c. Search for sub-function calls matching patterns:
      - GetRateGroupDifferential, GetClassDifferential,
        GetTerrDifferential, GetDiscSur_*, Set*, Get*Factor
   d. Record the list of factor_functions found
4. Also check mod_DisSur_{PROV}Auto*.vb for discount/surcharge functions
   that are vehicle-type-specific (those with vehicle type in name)
```

6.7.2. Write the `vehicle_type_profiles` section:

```yaml
vehicle_type_profiles:
  AB_AUTO:
    source_file: "Alberta/Code/mod_Algorithms_ABAuto20260101.vb"
    types:
      - name: "PPV"
        entry_function: "GetBasePrem_PPV"
        line_start: 245
        factor_functions:
          - "GetRateGroupDifferential"
          - "GetClassDifferential"
          - "GetTerrDifferential"
          - "GetDiscSur_PPVDeductible"
      - name: "Motorcycle"
        entry_function: "GetBasePrem_Motorcycle"
        line_start: 890
        factor_functions:
          - "GetRateGroupDifferential"
          - "GetTerrDifferential"
      - name: "Motorhome"
        entry_function: "GetBasePrem_Motorhome"
        line_start: 1102
        factor_functions:
          - "GetRateGroupDifferential"
      # ... Trailer, Snowmobile, ATV, Commercial
  NB_AUTO:
    source_file: "NewBrunswick/Code/mod_Algorithms_NBAuto20260101.vb"
    types:
      # ... same structure
```

6.7.3. If no Auto LOB exists for a province, skip that province entirely.

### Step 6.8: Build Glossary Skeleton

**Action:** Auto-generate a business term glossary from function names discovered
in the Pattern Library (Step 6.1-6.5) and dispatch tables (Step 6.6).

6.8.1. For each function in the Pattern Library with `status: ACTIVE` or `HIGH_USE`:

```python
def parse_function_to_glossary_terms(func_name, pattern_entry, dispatch_tables):
    """Generate business term mappings from function names.

    Parsing heuristics:
    - Split on underscores and CamelCase boundaries
    - Map common prefixes: Get→"get", Set→"set/apply", Option_→"endorsement",
      Liab_→"liability option", Calc→"calculate"
    - Map common suffixes: Premium→rate, Factor→factor, Discount→discount,
      Surcharge→surcharge, Bundle→bundle
    - Combine into human-readable business terms
    """
    terms = []

    # Example: GetLiabilityBundlePremiums → "liability bundle premiums"
    # Example: SetDisSur_Deductible → "deductible discount/surcharge"
    # Example: Option_SewerBackup → "sewer backup endorsement"
    # Example: GetBasePremium_Home → "base premium home"

    # Cross-reference with dispatch tables for category context
    for prov_lob, table in dispatch_tables.items():
        for category, entries in table.get("categories", {}).items():
            for entry in entries:
                if entry["function"] == func_name:
                    # Add dispatch description as synonym
                    if entry.get("description"):
                        terms.append(entry["description"].lower())

    return terms
```

6.8.2. Build known synonym mappings from common actuarial vocabulary:

```
SYNONYM MAP (built-in):
  "deductible"      → also matches: "ded", "deductable" (common typo)
  "liability"       → also matches: "liab", "CGL"
  "premium"         → also matches: "rate", "pricing"
  "endorsement"     → also matches: "rider", "optional coverage"
  "surcharge"       → also matches: "loading", "penalty"
  "discount"        → also matches: "credit", "reduction"
  "base rate"       → also matches: "base premium", "manual rate"
  "territory"       → also matches: "terr", "location factor"
  "dwelling"        → also matches: "structure", "building"
  "contents"        → also matches: "personal property"
```

6.8.3. Write the `glossary` section:

```yaml
glossary:
  "liability bundle premiums":
    canonical_function: "GetLiabilityBundlePremiums"
    file_pattern: "mod_Common_{PROV}Hab*.vb"
    pattern: "base_rate_increase"
    synonyms: ["liability bundle", "bundle premiums", "liab bundle"]
    provenance: "init"

  "deductible discount/surcharge":
    canonical_function: "SetDisSur_Deductible"
    file_pattern: "mod_Common_{PROV}Hab*.vb"
    pattern: "factor_table_change"
    synonyms: ["deductible factor", "ded discount", "deductible surcharge"]
    provenance: "init"

  "sewer backup":
    canonical_function: "Option_SewerBackup"
    file_pattern: "Option_SewerBackup_{PROV}{LOB}*.vb"
    pattern: "new_endorsement_flat"
    synonyms: ["sewer backup coverage", "sewer backup endorsement"]
    provenance: "init"

  "base premium home":
    canonical_function: "GetBasePremium_Home"
    file_pattern: "mod_Common_{PROV}Hab*.vb"
    pattern: "base_rate_increase"
    synonyms: ["home base rate", "dwelling base premium"]
    provenance: "init"

  "distinct client discount":
    canonical_function: "SetDiscountDistinctClient"
    file_pattern: "mod_Common_{PROV}Hab*.vb"
    pattern: "factor_table_change"
    synonyms: ["distinct client", "multi-policy discount"]
    provenance: "init"

  # ... one entry per active function with a parseable name
```

6.8.4. Glossary quality target: ~70% accuracy on first build. Entries are
refined over time via `/iq-investigate --promote` (Step 5 in iq-investigate).
Wrong entries are harmless — the glossary provides HINTS, not directives.
Agents always confirm against the actual codebase.

### Step 6.9: Codebase Profile Summary

After writing `codebase-profile.yaml`, append to the console summary:

```
---------------------------------------------------------------------------
 Codebase Knowledge Base
---------------------------------------------------------------------------
 Dispatch tables:        {N} province+LOB combinations
 Option codes mapped:    {total_codes} across {categories} categories
 Vehicle type profiles:  {N} provinces with {total_types} vehicle types
 Glossary terms:         {N} business terms mapped to functions
 Saved to:               .iq-workstreams/codebase-profile.yaml

 The Codebase Knowledge Base gives agents domain vocabulary, dispatch
 routing, and vehicle type awareness. It is enriched automatically by
 the Analyzer during /iq-plan and manually via /iq-investigate --promote.
```

### Profile Rebuild Triggers

The Codebase Profile is rebuilt when:
- **First /iq-init** — always built on fresh carrier initialization
- **/iq-init --refresh** — explicit developer request to rebuild
- **Staleness warning** — if codebase-profile.yaml is older than 30 days, print:
  ```
  WARNING: Codebase Profile is {N} days old. Consider running /iq-init --refresh
  to pick up new CalcOption codes and functions added since the last scan.
  ```
  This warning appears in /iq-plan's pre-flight checks (not in /iq-init itself).

**Incremental enrichment (NOT from /iq-init):**
- **Analyzer Step 5.11** adds `factor_cardinality` and `rule_dependencies` entries
- **/iq-investigate --promote** adds validated glossary entries and rule dependencies
- These enrichments have `provenance: "analyzer"` or `provenance: "investigation"`
  and are NEVER overwritten by /iq-init rebuilds (init only overwrites
  `provenance: "init"` entries)

---

## Error Handling

### Resilience Rules

1. **One bad province does not crash the scan.** If a province directory cannot be read
   (permissions, corruption), log a warning and continue with the other provinces.

2. **One bad LOB does not crash the province.** Same principle at every level.

3. **Missing Code/ directory is a warning, not an error.** The province may be new or
   incomplete.

4. **Unrecognized directories are warnings, not errors.** The codebase may have
   carrier-specific directories we do not know about yet.

5. **File system errors (permission denied, etc.) are logged and skipped.** The scan
   reports what it CAN see.

### Error Messages

All error messages should:
- State what went wrong
- State what the plugin did about it (skipped, continued, etc.)
- Suggest what the developer can do to fix it (if applicable)

---

## Implementation Notes for Claude Code

When executing this skill, use these specific tool strategies:

### Scanning directories
Use the Bash tool with `ls` commands to enumerate directories. Example:
```bash
ls "{carrier_root}/"
```
For each province:
```bash
ls "{carrier_root}/{province_folder}/"
```
Do NOT enumerate version folders inside LOBs. Do NOT scan Code/ file contents.
Agents discover all of that from .vbproj at runtime.

### Writing config.yaml
Use the Write tool to write the complete YAML file. Do NOT use Bash echo/cat.

### Reading existing config.yaml for merge
Use the Read tool to read the existing file, then generate the merged version.

### Parallel operations
Where possible, run multiple Bash/Glob calls in parallel (e.g., scanning all 8
provinces at once) to speed up the init.

### Computing scan_hash
To generate a scan hash, concatenate the sorted list of all discovered paths
(provinces + LOBs + cross-province files) into a single string, then describe it
as a short fingerprint. Since Claude Code cannot run arbitrary hash functions
natively, use a simple approach: run a bash command like:
```bash
echo -n "{concatenated sorted paths}" | sha256sum | cut -d' ' -f1
```

---

## Downstream Consumers

**config.yaml** is read by:
- `/iq-plan` -- to validate target folders and detect workflow type
- **Intake agent** -- to map province/LOB mentions in the Summary of Changes to real paths
- **Analyzer agent** -- to find Code/ files, detect shared modules, check blast radius
- **Planner agent** -- to build execution plans with correct paths
- **Change Engine** -- to locate files and construct new filenames
- **Reviewer** -- to validate completeness across all affected LOBs

If config.yaml is wrong, EVERY downstream agent will fail. This is why /iq-init
must be accurate.

**pattern-library.yaml** is read by:
- **Analyzer agent** (Steps 5.9, 5.10) -- to look up function call counts, detect dead code, find canonical accessor patterns, and enrich Function Understanding Blocks with param_types/return_type/purpose_hint
- `/iq-investigate` -- for instant call-site lookups and pattern searches
- `/iq-plan` pre-flight -- to check staleness (>30 days → warning)

**codebase-profile.yaml** is read by:
- **Intake agent** (Step 2.5) -- glossary lookup to resolve business terms to functions before keyword matching
- **Decomposer agent** (Step 5) -- dispatch table for endorsement/coverage category, vehicle type enumeration for Auto
- **Analyzer agent** (Step 5.11) -- enriches factor_cardinality and rule_dependencies (WRITE)
- **Analyzer agent** (Step 12) -- rule_dependencies for blast radius warnings
- **Planner agent** (Step 9) -- rule_dependencies for risk flag elevation
- `/iq-investigate` -- profile queries (Type 7) and --promote pathway (WRITE)
- `/iq-plan` pre-flight -- to check staleness (>30 days → warning)

---

## Design Decisions

1. **Zero prompts.** The folder structure is convention-based and fully scannable.
   There is nothing to ask the user. This follows the Terraform init model.

2. **Merge on re-run.** Never overwrite, never destroy. Add new, flag missing,
   update lists. This follows the principle of least surprise.

3. **Warnings over errors.** A malformed province should not prevent scanning the
   other seven. This follows the Snyk resilience model.

4. **Educational output.** Since this is the first interaction with the plugin,
   the output explains what was created and why. This builds trust.

5. **SHARDCLASS/SharedClass dual naming.** Nova Scotia uses `SharedClass` instead
   of `SHARDCLASS`. The scan checks for both spellings (case-insensitive).

6. **config.yaml lives in .iq-workstreams/, not .iq-update/.** The plugin
   code (.iq-update/) is separate from the workspace (.iq-workstreams/).
   This separation means the plugin can be updated independently of the workspace.

7. **Lightweight cheat sheet, not an inventory.** config.yaml records structure
   and naming patterns, not lists of every file and version. Agents discover
   specific versions and files from .vbproj at runtime. This keeps config.yaml
   small, stable, and rarely needing a re-init.

---

## What Comes Next

After init completes, show the developer the full workflow roadmap:

```
===========================================================================
 Plugin initialized. Here's how the workflow works:
===========================================================================

 /iq-plan     Analyze your rate changes and build an execution plan.
              Paste the Summary of Changes, pick your IQWiz folder(s),
              and the plugin runs 5 analysis agents → Gate 1 approval.

 /iq-execute  Execute the approved plan. Copies Code/ files to new
              dates, updates .vbproj references, and applies all
              rate/logic changes. Internal review included.

 /iq-review   Final validation. Runs 8 validators, generates diffs
              and traceability reports → Gate 2 approval → DONE.

 /iq-investigate  Ask targeted questions about the codebase at any
              phase. Uses the Pattern Library for instant lookups.
              Finds dead code, canonical patterns, and call chains.

 Each command runs in a fresh context window. You can /clear between
 commands with zero information loss -- all state is in the workstream
 files.

 Ready? Run /iq-plan to start your first rate change workflow.
===========================================================================
```
