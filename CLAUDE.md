# IQ Update Plugin

This folder contains a TBW/IntelliQuote rating engine. The `.iq-update/` plugin
helps developers implement any ticket against the existing VB.NET codebase. Portage
Mutual is the first carrier -- this plugin is designed to work with any TBW carrier
folder.

**Carrier-agnostic design:** This plugin works with any TBW/IntelliQuote carrier
that uses manufactured rating. Examples throughout use Portage Mutual (the first
carrier), but all carrier-specific values (prefix, provinces, LOBs, cross-province
files) are discovered at runtime via `/iq-init` and stored in `config.yaml`. The
plugin assumes the developer points it at a manufactured rating folder -- it does
not distinguish between manufactured and direct rating lines of business.

## Plugin Path Resolution — MANDATORY FIRST STEP

**Every `/iq-*` command (except `/iq-init`) MUST read `.iq-workstreams/paths.md` as its
very first action.** This file contains all absolute paths — plugin root, agent specs,
validators, Python command, tool paths. No discovery, no globbing, no fallback chains.
Just read the file.

If `.iq-workstreams/paths.md` does not exist, tell the developer: `"Run /iq-init first."`

Whenever you see `.iq-update/` in any instruction (agent specs, validators, patterns),
replace it with the `plugin_root` value from `paths.md`. All paths in `paths.md` are
absolute and fully resolved — use them directly with the Read tool.

## How This Codebase Works

- Each province has LOB folders (Home, Auto, Condo, etc.) with dated version subfolders
- Each version folder is a VB.NET project that compiles to a DLL
- The `.vbproj` in each folder references Code/ files via relative paths
- Code/ files are shared across versions -- only changed files get new dated copies
- Habitational LOBs (Home, Condo, Tenant, FEC, Farm, Seasonal) share `mod_Common_{Prov}Hab` files
- IQWiz creates the shell folder (GUIDs, .vbproj pointing to OLD Code/ files)
- This plugin creates new dated Code/ copies, updates .vbproj references, AND edits rate values

### Repository Layout

```
{carrier_root}/
  {Province}/
    {LOB}/                          <- Line of business (Home, Auto, Condo, etc.)
      {YYYYMMDD}/                   <- Version folder (effective date)
        Cssi.IntelliQuote.{PREFIX}{PROV}{LOB}{DATE}.vbproj  # PREFIX from config.yaml (e.g., "PORT")
        CalcMain.vb, ResourceID.vb, TbwApplicationTypeFactory.vb
        My Project/AssemblyInfo.vb, ...
    Code/                           <- Shared code files for ALL LOBs in this province
      mod_Common_{PROV}Hab{DATE}.vb <- THE BIG FILE (hab rate values, factor tables)
      CalcOption_{PROV}{LOB}{DATE}.vb
      mod_Algorithms_{PROV}Auto{DATE}.vb
      mod_DisSur_{PROV}Auto{DATE}.vb
      Option_{Name}_{PROV}{LOB}{DATE}.vb
      Liab_{Name}_{PROV}{LOB}{DATE}.vb
    SHARDCLASS/                     <- Shared helper classes (some provinces; NS uses "SharedClass")
  Hub/
    Cssi.IntelliQuote.PortageMutual.sln  <- Master solution (~90 projects)
  Code/                             <- Cross-province shared modules (NEVER auto-modify)
    PORTCommonHeat.vb
    mod_VICCAuto.vb
```

### How the .vbproj Connects Everything

The `.vbproj` is the critical file. It lists every source file compiled into the DLL
via `<Compile Include>` elements with relative paths. Files come from:
- Local (in the version folder itself): CalcMain.vb, ResourceID.vb, etc.
- Province Code/ files (dated, shared across versions)
- Hub-level files (modAttachScheduledArticleToDwellings.vb, etc.)
- Cross-province shared files (Code/PORTCommonHeat.vb, etc.)
- Global shared engine files (Shared Files for Nodes/cCalcEngine.vb, etc.)

After IQWiz creates a shell folder, the .vbproj still points to OLD Code/ files.
This plugin determines which files need changes, creates new dated copies, updates
the .vbproj references, and makes the rate edits -- all in one workflow.

### What Rate Values Look Like in Code

**Array6 (MISNOMER -- accepts 1-14+ args, not just 6):**
```vb
Case 1 : varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)
```
Array6 is a rate value when assigned to a variable (LHS of `=`).
Array6 is NOT a rate value when passed as an argument to another function (e.g., IsItemInArray).

**Select Case factor tables:**
```vb
Select Case deductible
    Case 500  : dblDedDiscount = 0
    Case 1000 : dblDedDiscount = -0.075
End Select
```
Some functions have 4+ Select Case blocks with nested If/ElseIf -- show ALL matches to developer.

**Constants as rate values:**
```vb
Const ACCIDENTBASE = 200
```

### Auto vs Hab -- Different Structures

| Rate Type | Location | In VB Code? | Plugin Can Edit? |
|-----------|----------|:-----------:|:----------------:|
| Auto base rates | mod_Algorithms **scalar assignments** (`baseRate = 66.48`) | YES | YES (factor_table_change) |
| Hab deductible factors | mod_Common Select Case blocks | YES | YES |
| Hab liability premiums | mod_Common Array6 arrays | YES | YES |
| Endorsement premiums | Option_*.vb / Liab_*.vb | YES | YES |
| **Hab dwelling base rates** | **External DAT files** | **NO** | **NO** |

## Commands

- `/iq-init`         -- Initialize the plugin (one-time setup per carrier folder)
- `/iq-plan`         -- Analyze changes and build an execution plan (Gate 1 approval)
- `/iq-execute`      -- Execute the approved plan (file copies + rate/logic changes)
- `/iq-review`       -- Validate results and approve (Gate 5 approval)
- `/iq-status`       -- Dashboard: show all workstreams, next actions, overlap alerts
- `/iq-investigate`  -- Ad-hoc codebase investigation (dead code, patterns, call sites)

Each command runs in a **fresh context window**. The developer can `/clear` between
commands with zero information loss — all state is persisted in manifest.yaml and
workstream files. These six commands cover the full workflow.

## Key Rules

1. **NEVER modify old dated Code/ files** -- only edit files that match the target version date
2. **Read the .vbproj using an XML parser** (not regex) to know which Code/ files belong to this version
3. **Shared modules** (`mod_Common_*Hab*`) affect ALL hab LOBs -- handle with care, edit ONCE
4. **Run reverse lookup:** check ALL .vbproj files in the province, not just the developer's targets
5. **NEVER modify cross-province shared files** (listed in `config.yaml["cross_province_shared_files"]`, e.g., `Code/PORTCommonHeat.vb` for Portage Mutual) -- flag for developer
6. **Hab dwelling base rates are in DAT files**, NOT VB code -- flag, don't attempt to edit
7. **SHARDCLASS/** (or **SharedClass/** in Nova Scotia) exists alongside Code/ for hab helper classes -- include in blast radius scans
8. **Preserve exact VB.NET formatting** (indentation, spacing, line endings)
9. **Skip commented lines** (starting with `'`) -- never modify commented-out code
10. **Understand before acting:** Intake MUST present a ticket understanding **journey** (description → comments → images → synthesis) showing HOW the understanding was built, not just a summary. The developer sees exactly which evidence led to each conclusion — comments often correct the description. Get confirmation BEFORE extracting change requests.
11. **Three checkpoints, full traceability:** (a) Understanding journey (Intake Step 0) BEFORE CR extraction, (b) Gate 1 (/iq-plan) with verification strategy (automated vs developer checks) BEFORE editing, (c) Gate 5 (/iq-review) with CR-linked completion checklist ([AUTO] vs [DEV] items) AFTER validation
12. **Save per-file snapshots** before editing -- restore on validator failure
13. **Hash-check files before writing** -- abort if file changed since plan approval (TOCTOU protection)
14. **SVN is the version control** -- the plugin does not manage system-level rollback
15. **Bottom-to-top execution** within each file (highest line number first) to prevent line-number drift
16. **Show, don't guess** -- present all candidates to developer, never silently pick one
17. **Fresh context per command** -- each /iq-* command reads ALL state from disk, never from memory
18. **NEVER use `sleep` to wait for anything** -- if an Agent tool call fails or an agent cannot be resumed, log the error and fall back to sequential execution. Do not retry in a sleep loop. Do not `sleep` between steps.
19. **Windows path safety** -- NEVER use `sed`, `awk`, or bash string manipulation for file paths. Use Python `os.path` for path operations, Python `xml.etree.ElementTree` for XML parsing, and Python `os.path.exists()` for file existence checks.
20. **Python-only for scripting** -- when generating YAML, parsing files, or processing data, ALWAYS use Python (with the `python_cmd` from config.yaml). NEVER use Perl, Ruby, Node, or other scripting languages. Python + PyYAML is the only verified runtime.
21. **Contract registry** -- `contracts/contract_registry.yaml` defines all inter-agent artifact schemas. It is the source of truth. Inline schema examples in agent specs are illustrative only -- if they conflict with the registry, the registry wins.
22. **Parser-first for VB.NET questions** -- When the developer asks about a function, variable, call chain, or code structure (even outside a `/iq-*` command), use the VB parser (`vb_parser` from paths.md) as the primary tool: `{vb_parser} parse {file}` for file structure, `{vb_parser} function {file} {name}` for function detail. Combine parser output with Read for semantic understanding. The parser gives exact line ranges, call inventories, Array6 counts, and Select Case structures — never rely on grep alone for structural questions about VB.NET code.

## Province Codes

| Code | Province | Hab Code |
|------|----------|----------|
| AB | Alberta | ABHab |
| BC | British Columbia | BCHab |
| MB | Manitoba | MBHab |
| NB | New Brunswick | NBHab |
| NS | Nova Scotia | NSHab |
| ON | Ontario | ONHab |
| PE | Prince Edward Island | PEHab |
| SK | Saskatchewan | SKHab |

## Plugin Architecture

```
.iq-update/                          <- PLUGIN CODE (ships to marketplace)
  CLAUDE.md                          <- This file (master instructions)
  skills/
    iq-init/SKILL.md                 <- /iq-init skill definition
    iq-plan/SKILL.md                 <- /iq-plan skill definition (analysis + Gate 1)
    iq-execute/SKILL.md              <- /iq-execute skill definition (file changes)
    iq-review/SKILL.md               <- /iq-review skill definition (validation + Gate 5)
    iq-status/SKILL.md               <- /iq-status skill definition (dashboard)
    iq-investigate/SKILL.md          <- /iq-investigate skill definition (codebase investigation)
  agents/
    intake.md                        <- Understands any ticket format, extracts change requests
    understand.md                    <- Parser-powered code analysis, builds FUBs (replaces Discovery + Analyzer)
    plan.md                          <- CR→intent mapping, execution ordering (replaces Decomposer + Planner)
    change-engine/                   <- Unified code modification engine
      core.md                        <- Universal rules, schemas, parser gates CE.0-CE.5 (always loaded)
      strategies.md                  <- Reference examples for common patterns (loaded when strategy_hint present)
    reviewer.md                      <- Validates all changes, produces summary
    semantic-verifier.md             <- Parser-backed arithmetic proofs for value edits
  tools/
    win-x64/vb-parser.exe           <- Roslyn parser binary (37MB, self-contained)
  contracts/
    contract_registry.yaml           <- Artifact schemas, producers, consumers (source of truth)
  patterns/                          <- Reusable recipes for common change types
  validators/                        <- Automated validation checks (Python)

.iq-workstreams/                     <- WORKSPACE (created by /iq-init per carrier)
  config.yaml                        <- Carrier/province/LOB configuration
  pattern-library.yaml               <- Function registry with call counts (from /iq-init Step 6)
  codebase-profile.yaml              <- Codebase Knowledge Base (from /iq-init Steps 6.6-6.8)
  changes/
    {workflow-id}/                   <- One folder per ticket (created by /iq-plan)
      manifest.yaml                  <- State machine + all tracking data
      input/, parsed/                <- Intake artifacts (ticket_understanding.md, cr-NNN.yaml)
      analysis/                      <- Understand + Plan artifacts (from /iq-plan)
        code_understanding.yaml      <- Unified code analysis with parser data (from Understand)
        intent_graph.yaml            <- Intents with target regions + dependencies (from Plan)
      plan/                          <- Plan artifacts (from /iq-plan)
      execution/                     <- Execution artifacts (from /iq-execute)
        checkpoint.yaml              <- Crash-recovery state for orchestrator
        capsules/                    <- Pre-built worker briefs (one per file group)
        results/                     <- Structured outputs from each worker
        snapshots/                   <- Pre-edit file backups
        parser-cache/                <- Parser output cache (from Gate 2b, consumed by CE.0)
        file_hashes.yaml, operations_log.yaml
      verification/, summary/        <- Review artifacts (from /iq-review)
      investigation/                 <- Saved findings from /iq-investigate (feed into Understand)
  archive/                           <- Completed workstreams (auto-archived by /iq-status, /iq-plan)
    index.yaml                       <- Lightweight index of all archived workstreams
    {YYYY-MM}/{workflow-id}/         <- manifest.yaml + summary + diff only
```

## Agent Pipeline

```
/iq-plan:    Intake(Understanding Journey -> [DEV CONFIRMS] -> CR Extraction) -> Understand(Parser+Claude) -> Plan(+Verification Strategy) -> [GATE 1]
/iq-execute: [GATE 2a] -> File-Copy -> [GATE 2b] -> [Change Engine Workers (CE.0-CE.5)...] -> [GATE 4] -> [EXECUTED]
/iq-review:  Validator -> Diff -> Semantic Verifier(parser-backed proofs) -> Report -> [GATE 5 + CR Checklist] -> DONE
```

**Understand Agent:** Uses vb-parser.exe (Roslyn) for structural analysis, then Claude
for semantic reasoning. Produces `analysis/code_understanding.yaml` — a unified artifact
with project maps, call chains, per-CR targets with parser-verified line numbers, FUBs,
and hazard flags. Parser is required (no regex fallback). Replaces Discovery + Analyzer.

**Context engineering:** `/iq-execute` uses the **capsule pattern** — the orchestrator
pre-builds self-contained capsules (one per target file), then spawns short-lived
Change Engine workers that each get a fresh context window. Workers load
`change-engine/core.md` (always) and optionally `change-engine/strategies.md`
(when strategy_hint is present). Progress is tracked in `execution/checkpoint.yaml`
for crash recovery.

`/iq-plan` launches agents as an **agent team** (default) or **sequential sub-agents**
(fallback). `/iq-review` uses the same team/sequential pattern.

Same-file intents are always sequential, bottom-to-top.

## Three Workflows

1. **Single New Folder** -- One region, one policy type, one date (typical for Auto)
2. **Existing Folder** -- Changes to an already-set-up version folder
3. **Multi-Folder Habitational** -- Up to 6 LOBs sharing mod_Common, one date

## Configuration

See `.iq-workstreams/config.yaml` for province definitions, LOB lists, naming patterns, and path templates.
See `.iq-workstreams/codebase-profile.yaml` for the Codebase Knowledge Base (dispatch tables, vehicle profiles, glossary, factor cardinality, rule dependencies).
See `agents/*.md` for individual agent interface contracts.
See `patterns/*.yaml` for common change type recipes.
See `validators/*.py` for automated validation checks.

### Codebase Knowledge Base (codebase-profile.yaml)

A persistent knowledge artifact built by `/iq-init` (Steps 6.6-6.8) and incrementally
enriched by the Understand agent (Step U.12) and `/iq-investigate --promote`. Contains:

- **dispatch_tables** — CalcOption routing maps (option code → function → category)
- **vehicle_type_profiles** — Auto sub-functions per vehicle type (PPV, Motorcycle, etc.)
- **glossary** — Business terms → canonical functions (e.g., "liability bundle" → `GetLiabilityBundlePremiums`)
- **factor_cardinality** — Case branch counts per function (enriched by Understand at runtime)
- **rule_dependencies** — Business rule pairs (e.g., Water Coverage ↔ Sewer Backup)

Agents Grep for specific sections — **never load the full file**. Workers never see it
(zero capsule impact). All agents gracefully degrade if the profile is absent.
