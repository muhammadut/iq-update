---
name: iq-plan
description: Analyze a rate change ticket and build an execution plan. Runs Intake, Discovery, Decomposer, Analyzer, and Planner agents, then presents Gate 1 for developer approval.
user-invocable: true
---

# Skill: /iq-plan

## 1. Purpose & Trigger

Start a new rate change workflow or resume an existing one. This is the analysis
orchestrator that drives the 5-agent analysis pipeline (Intake → Discovery →
Decomposer → Analyzer → Planner) through Gate 1 approval. After the developer types `/iq-plan`,
everything else is conversational: the developer approves, rejects, asks questions,
provides corrections, and the orchestrator routes work to agents, manages state,
and produces the execution plan. Execution and review are handled by `/iq-execute`
and `/iq-review` respectively.

**Trigger:** Slash command `/iq-plan`

---

## 2. Precondition Checks

Execute these checks IN ORDER before doing anything else. If any check fails,
STOP and report the issue to the developer.

### Check 1: Plugin Installed

Verify that `.iq-update/CLAUDE.md` exists in the carrier root directory.

- If missing, STOP:
  ```
  ERROR: The .iq-update/ plugin is not installed in this folder.
  Please install the IQ Rate Update Plugin first, then run /iq-plan.
  ```

### Check 2: Config Exists (/iq-init Has Been Run)

Verify that `.iq-workstreams/config.yaml` exists.

- If missing, STOP:
  ```
  ERROR: No config.yaml found. Please run /iq-init first to initialize
  the plugin, then come back and run /iq-plan.
  ```

### Check 3: Config Is Readable

Read `.iq-workstreams/config.yaml` and confirm it has the required keys:
`carrier_name`, `carrier_prefix`, `root_path`, `provinces`.

- If any key is missing, STOP:
  ```
  ERROR: config.yaml is malformed -- missing "{key}".
  Run /iq-init again to regenerate it.
  ```

### Check 4: Codebase Profile Freshness (Non-Blocking)

Check if `.iq-workstreams/codebase-profile.yaml` exists.

- If missing, NOTE (not error, not blocking):
  ```
  NOTE: No Codebase Knowledge Base found. The pipeline will work without it,
  but agents won't have dispatch tables, vehicle profiles, or glossary.
  Run /iq-init --refresh to build the profile for better accuracy.
  ```

- If present, check `_meta.last_updated`:
  - If older than 30 days, WARN (not blocking):
    ```
    WARNING: Codebase Profile is {N} days old. Consider running /iq-init --refresh
    to pick up new CalcOption codes and functions added since the last scan.
    ```
  - If current (< 30 days), continue silently.

If all checks pass, proceed to Resume Detection.

---

## 3. Archive Sweep & Resume Detection

### Step 3.0: Archive Sweep

Before scanning for incomplete workflows, clean up old completions to keep
the `changes/` folder focused on active work.

**Archive rules:**

1. Scan `.iq-workstreams/changes/*/manifest.yaml`
2. For each workstream:
   - If `state == "COMPLETED"`:
     - Use `lifecycle.archive_after` if present
     - Else fall back to `updated_at` + 14 days (backward compat)
     - If archive date has passed: ARCHIVE
   - If `state == "DISCARDED"`:
     - Use `lifecycle.archive_after` if present
     - Else fall back to `updated_at` + 7 days (backward compat)
     - If archive date has passed: ARCHIVE

**Archive procedure (per workstream):**

```
1. Create target directory:
   .iq-workstreams/archive/{YYYY-MM}/{workstream-id}/

2. Copy (keep):
   - manifest.yaml                  (audit trail)
   - summary/change_summary.md      (human-readable record, if exists)
   - verification/changes.diff      (exact diff, if exists)

3. Delete the original workstream directory from changes/

4. Append entry to .iq-workstreams/archive/index.yaml:
   - id: "{workstream-id}"
     ticket: "{ticket.key or ticket_ref or 'ADHOC'}"
     province: "{province}"
     completed: "{lifecycle.completed_at or updated_at}"
     svn_revision: "{svn_revision or null}"
     path: "archive/{YYYY-MM}/{workstream-id}/"
```

If `.iq-workstreams/archive/index.yaml` does not exist, create it:
```yaml
archived: []
```

**Report archived workstreams (if any):**
```
Archived {N} workstream(s):
  {workstream-id} (completed {date}) -> archive/{YYYY-MM}/
```

If nothing archived, continue silently.

### Step 3.1: Resume Detection

Scan `.iq-workstreams/changes/` for any subdirectory containing a `manifest.yaml`
where `state` is NOT `COMPLETED` and NOT `DISCARDED`.

### How to Scan

```
1. List all subdirectories in .iq-workstreams/changes/ (exclude config.yaml)
2. For each subdirectory, check if manifest.yaml exists
3. If it exists, read the "state" field
4. Collect all workflows where state != COMPLETED and state != DISCARDED
```

### If No Incomplete Workflows Found

Skip to section 4 (New Workflow Setup).

### If Incomplete Workflows Found

Present each incomplete workflow to the developer:

```
Found {N} incomplete workflow(s):

  1. {workflow_id}
     State:        {state}
     Province:     {province_name}
     LOBs:         {lobs}
     Last updated: {updated_at}
     SRD progress: {completed}/{total} SRDs
     Last action:  {description of last completed step}

Options:
  1. Resume this workflow
  2. Start a new workflow instead
  3. Discard this workflow and start fresh
```

### On Resume: Dirty File Detection

When the developer chooses to resume, perform hash verification:

```
1. Read execution/file_hashes.yaml from the workflow directory
2. For each file listed:
   a. Compute current SHA256 hash of the file on disk
   b. Compare against the stored hash
3. Classify results:
   - ALL MATCH: safe to resume, continue from current state
   - ANY DIFFER: files changed outside the plugin
```

**If files differ, warn the developer:**

```
WARNING: {N} file(s) changed since last session:

  {filename}
    Expected: {stored_hash} (at {timestamp})
    Current:  {current_hash}

Options:
  1. Show diff between expected and current state
  2. Re-analyze from current state (rebuild plan from scratch)
  3. Start over -- svn revert all files and rebuild
  4. Resume anyway (RISKY -- changes may conflict)
```

**If option 1 (show diff):** Read both the snapshot file (from `execution/snapshots/`)
and the current file, show the differences, then re-present the options.

**If option 2 (re-analyze):** Set state back to CREATED, discard the old plan and
analysis directories (keep input/ and parsed/), and re-run the pipeline from the
Analyzer step.

**If option 3 (start over):** Tell the developer to `svn revert` the affected files
first, then set state to CREATED and restart the entire pipeline.

**If option 4 (resume anyway):** Continue from current state but update file hashes
to match current state. Log a warning in manifest.yaml.

### On Resume: State-Based Continuation

Once hash verification passes (or developer overrides), determine where to resume
based on the workflow state:

| State | Resume Point |
|-------|-------------|
| CREATED | Prompt for input (Section 6, Step 1: Intake) |
| ANALYZING | Check which agent last completed; resume from next agent |
| PLANNED | Re-present execution plan at Gate 1 |
| EXECUTING | Inform developer: "This workflow is being executed. Run /iq-execute to resume." STOP. |
| EXECUTED | Inform developer: "This workflow has been executed. Run /iq-review to validate." STOP. |
| VALIDATING | Inform developer: "This workflow is being reviewed. Run /iq-review to resume." STOP. |
| COMPLETED | Nothing to resume -- inform developer |

**For ANALYZING state, determine sub-state from phase_status in manifest.yaml:**

```
Read manifest.yaml -> phase_status section

0. If execution_mode is "team": clean up any dangling teams first.
   Try TeamDelete() for team "iq-{workstream-name}". Ignore errors
   (team may already be cleaned up).

1. Find the last phase with status: "completed"
2. Resume from the NEXT phase in sequence:
   intake -> decomposer -> analyzer -> planner -> gate_1 -> modifiers -> reviewer -> gate_2

3. Also read developer_decisions to avoid re-asking questions:
   "Developer already confirmed: {list of decisions}"
   Do NOT re-ask these questions. Pass them to the agent prompt.

4. Read the completed phase summaries to understand context:
   "Intake found: {intake.summary}"
   "Decomposer produced: {decomposer.summary}"
   etc.

5. Launch the next agent using the current execution_mode
   (create a new team if team mode, or launch sub-agent if sequential).
```

**Fallback (if phase_status is missing or incomplete):** determine sub-state from artifacts:

```
If parsed/change_spec.yaml does NOT exist     -> resume at Intake
If analysis/dependency_graph.yaml does NOT exist -> resume at Decomposer
If analysis/blast_radius.md does NOT exist     -> resume at Analyzer
If plan/execution_plan.md does NOT exist       -> resume at Planner
```

**For EXECUTING state, determine sub-state from operations log:**

```
Read execution/operations_log.yaml
Find the last operation with status: COMPLETED
Resume from the next operation in plan/execution_order.yaml
```

---

## 4. New Workflow Setup

When no resume is needed (or the developer chose "start new"), set up a fresh
workflow.

### Step 4.1: Ticket-Driven Workstream Naming

Ask the developer for a ticket reference:

```
Ticket reference? You can:
  - Enter a ticket ID or URL to auto-fetch from Azure DevOps (e.g., 24778)
  - Enter a reference key (e.g., JIRA-122)
  - Press Enter for ad-hoc
>
```

**Process the response:**

**If ticket reference provided (ticketed mode):**
1. Normalize the key: extract alphanumeric + hyphens, lowercase
   - `24778` -> key: `24778`
   - `DEVOPS-24778` -> key: `devops-24778`
   - `DevOps 24778` -> key: `24778`, raw ref preserved as-is
2. **Auto-fetch attempt (numeric IDs only):**
   If the key is purely numeric AND both `fetch-ticket.sh` and `.env` exist in
   the carrier root, attempt auto-fetch:
   ```bash
   cd "{carrier_root}" && source .env && bash fetch-ticket.sh {key} 2>&1
   ```
   - **On success:** Read `workitem-{key}-full/llm-context-brief.md` as the
     change description. Set `ticket.auto_fetched: true`. Extract a short
     description from the ticket title (strip "Portage", province names,
     "Effective {date}", common suffixes — keep 2-4 key words).
     Show the developer:
     ```
     Fetched ticket {key}: {title}
     Auto-generated description: {short_description}

     Use this as the change description? [Y/n]
     ```
     If yes: store the brief content as the raw input, **skip Step 4.2**.
     If no: proceed to Step 4.2 for manual input.
   - **On failure:** Warn and continue normally:
     ```
     Could not auto-fetch ticket {key}: {error}
     Continuing with manual input.
     ```
3. Ask for a short description (if not auto-generated):
   ```
   Short description (2-4 words):
   > sk hab rate increase
   ```
4. Generate ID: `{key}-{description}` (sanitized: lowercase, hyphens, no specials)
   - `24778` + "sk hab rate increase" -> `24778-sk-hab-rate-increase`
   - `devops-24778` + "sk hab rates" -> `devops-24778-sk-hab-rates`
5. Set `ticket.mode: "ticketed"`

**If Enter pressed (ad-hoc mode):**
1. Ask for a short description:
   ```
   Short description (2-4 words):
   > sk common cleanup
   ```
2. Generate ID: `adhoc-{YYYYMMDD}-{description}` using today's date
   - "sk common cleanup" -> `adhoc-20260301-sk-common-cleanup`
3. Set `ticket.mode: "adhoc"`

**Duplicate detection:**
- Check if generated ID already exists under `.iq-workstreams/changes/`
- If duplicate: auto-append `-02`, `-03`, etc.
  - `24778-sk-hab-rate-increase` exists -> `24778-sk-hab-rate-increase-02`

**Present and confirm:**
```
Workstream ID: {generated-id}
Press Enter to accept, or type a different name:
>
```

If the developer types a custom name, use it (sanitized) instead.

**Sanitization rules:**
1. Lowercase all characters
2. Replace spaces with hyphens
3. Remove special characters (keep alphanumeric, hyphens, underscores)
4. Ensure the name is non-empty and valid as a directory name

Create the workstream directory:
```bash
mkdir -p ".iq-workstreams/changes/{workstream-name}"
```

### Step 4.2: Gather Change Description

**If auto-fetched in Step 4.1:** This step is skipped. The brief from
`workitem-{key}-full/llm-context-brief.md` is already stored as the raw input.
The full ticket data (all comments, attachments) remains available at
`workitem-{key}-full/` if Intake needs to reference it.

**Otherwise,** ask the developer to describe the changes:

```
What changes need to be made? You can:
  - Paste the Summary of Changes text directly
  - Provide a path to a PDF: /path/to/summary.pdf
  - Provide a path to an Excel file: /path/to/rates.xlsx
  - Describe the changes in plain language
```

Hold the raw input in memory. It will be written to `input/source.md` in Step 4.7
after the directory structure is created.

### Step 4.3: Ask for Target Folder(s)

Read config.yaml and identify candidate folders. Present recently created version
folders (highest date values) as likely targets:

```
Which IQWiz folder(s) are you working on? Single or multiple?

I see these recent version folders:
  1. Saskatchewan/Home/20260101
  2. Saskatchewan/Condo/20260101
  3. Saskatchewan/Tenant/20260101
  4. Saskatchewan/FEC/20260101
  5. Saskatchewan/Farm/20260101
  6. Saskatchewan/Seasonal/20260101
  7. Alberta/Auto/20260101
  8. New Brunswick/Home/20260701

Type the number(s), or paste a folder path directly.
```

**How to identify "recent" folders:** For each province/LOB combination listed in
config.yaml, scan the LOB directory on disk for date-named subdirectories (8-digit
YYYYMMDD folders). Sort by date descending and show the most recent 1-2 folders per
LOB. Group folders from the same province and date together to highlight potential
multi-LOB hab tickets.

**Accept flexible input:**
- A number from the list: `1`
- Multiple numbers: `1, 2, 3, 4, 5, 6` or `all 6` or `1-6`
- A path: `Saskatchewan/Home/20260101`
- Multiple paths: `Saskatchewan/Home/20260101, Saskatchewan/Condo/20260101`
- Natural language: `All SK hab folders` or `just Alberta Auto`

### Step 4.4: Validate Each Selected Folder

For each folder the developer specified:

```
0. Path containment check: canonicalize the path and verify it is
   under the carrier root directory.
   - resolved_path = os.path.realpath(os.path.join(carrier_root, folder_path))
   - real_root = os.path.realpath(carrier_root)
   - assert os.path.commonpath([real_root, resolved_path]) == real_root,
     f"Path {folder_path} resolves outside the carrier root. Aborting."
   - On Windows, normalize case before comparison (os.path.normcase).
   - This prevents accidental out-of-root file operations if absolute
     or ../traversal paths are supplied.

1. Confirm the folder exists on disk
   - If not: "That folder doesn't exist. Did you run IQWiz yet? If your
     folder has a different date, tell me which one."

2. Find the .vbproj file in the folder
   - Use Glob: {folder}/*.vbproj
   - If none found: "No .vbproj file in {folder}. IQWiz may not have been
     run, or this folder is incomplete."
   - If multiple found: show them and ask which to use

3. Parse the .vbproj as XML
   - Read the file content
   - Extract all <Compile Include="..."> entries
   - If XML is malformed: "The .vbproj file is not valid XML. It may be
     corrupted. Check the file in a text editor."

4. Count the Code/ files referenced
   - Filter <Compile Include> entries for paths containing "/Code/" or "\Code\"
   - Report: "Found {N} Code/ files in the .vbproj"

5. Verify Code/ files exist on disk
   - For each Code/ file path extracted in step 4, resolve the relative path
     from the .vbproj folder and confirm the file exists
   - If ANY Code/ file is missing:
     "WARNING: {M} of {N} Code/ files referenced by the .vbproj do not exist
      on disk. Missing files:\n{list of missing paths}\n
      This usually means IQWiz pointed to Code/ files that were deleted or
      renamed. Check the .vbproj references before proceeding."
   - If ALL Code/ files are missing: STOP. This folder is not ready.
   - If all exist: continue silently (no extra output)
```

### Step 4.4b: Conflict Fence (Overlap Detection)

After validating folders, build the workstream's **footprint** and check for
overlaps with other in-flight workstreams. This catches conflicts at PLAN time,
not at EXECUTE time when it's too late.

**1. Build footprint from .vbproj parsing already done in Step 4.4:**

```
footprint:
  target_folders:
    - "{Province}/{LOB}/{Date}"         # from Step 4.3
  code_files:
    - "{Province}/Code/{filename}.vb"   # all Code/ files from .vbproj parsing (Step 4.4)
  shared_modules:
    - "{Province}/Code/mod_Common_*.vb" # subset of code_files that are shared (Step 4.5/4.6)
```

Note: `shared_modules` may be empty at this point if Step 4.5 hasn't detected
them yet. That's OK -- the overlap check uses `code_files` (the full list).
The `shared_modules` list is finalized after Step 4.6 and the footprint in the
manifest is updated at that point.

**2. Scan other in-flight workstreams:**

```
1. List all subdirectories in .iq-workstreams/changes/
2. For each (excluding the current workstream being created):
   a. Read manifest.yaml
   b. If state is COMPLETED or DISCARDED: skip
   c. Read footprint.code_files (or fall back to target_folders + shared_modules
      for old manifests without footprint)
   d. Collect as {id, state, code_files}
```

**3. Compare code_files for intersection:**

For each in-flight workstream, compute the intersection of its code_files
with the current workstream's code_files.

**4. Determine severity:**

| Overlap | Other workstream state | Severity |
|---------|----------------------|----------|
| Same province+date, different files | Any | INFO (just mention it) |
| Same file(s) | CREATED / ANALYZING / PLANNED | WARN |
| Same file(s) | EXECUTING / EXECUTED / VALIDATING | HIGH |

**5. WARN (both workstreams are still planning):**

```
OVERLAP DETECTED (WARN)
Your new workstream will touch the same file as an existing one:
  File: {filename}
  Other workstream: {workstream-id} ({state})

This is OK if the changes don't conflict. Both workstreams will modify
the file, but /iq-execute checks hashes before writing -- the second one
to execute will detect the conflict and pause.

Continue? [Y/n]
```

If developer says Y (or Enter): log acknowledgment in `developer_decisions`
and continue. If N: cancel workstream creation.

**6. HIGH (other workstream is already executing):**

```
OVERLAP DETECTED (HIGH)
Your new workstream will touch a file being modified by another workstream:
  File: {filename}
  Other workstream: {workstream-id} ({state}, {time ago})

The other workstream may have already changed this file. If you plan now,
your plan will be based on the CURRENT file state -- which may include
the other workstream's partial changes.

Options:
  1) Check on the other workstream first (/iq-status)
  2) Continue anyway (you'll need to re-plan if the file changes again)
  3) Cancel
```

If option 1: stop here, developer runs /iq-status and comes back.
If option 2: log acknowledgment in `developer_decisions`, continue.
If option 3: cancel workstream creation.

**7. Log acknowledgment:**

Append to `developer_decisions` (written later in Step 4.8):
```yaml
- timestamp: "{now}"
  phase: "conflict_fence"
  question: "Overlap with {workstream-id} on {filename} ({severity})"
  answer: "{developer's choice}"
```

**8. Update footprint in manifest (Step 4.8):**

The footprint computed here is written to `manifest.yaml` in Step 4.8.
After Step 4.6 (reverse lookup), if new shared_modules were discovered,
update `footprint.shared_modules` before writing the manifest.

### Step 4.5: Detect Workflow Type

Based on the validated folders, determine the workflow type:

**Workflow 1 -- Single New Folder:**
- Exactly 1 folder selected
- No pre-existing uncommitted changes in the Code/ files referenced by the .vbproj
- Detection: for each Code/ file in the .vbproj, check if a target-dated version
  already exists in the Code/ directory. If none exist, this is a fresh start.

**Workflow 2 -- Existing Folder:**
- Exactly 1 folder selected
- Pre-existing changes detected (target-dated Code/ files already exist, or the
  .vbproj already references target-dated files, or there are modified files)
- Tell the developer: "This folder already has changes from a previous session.
  I'll work against the CURRENT file state."

**Workflow 3 -- Multi-Folder Habitational:**
- 2 or more folders selected
- All folders share a common province and effective date (typical for hab tickets)
- Detection: read all selected .vbproj files, find common Code/ file references
  (files referenced by 2+ .vbproj files = shared modules)

```
Working on {N} {Province} {LOB_type} folders.
Shared module detected: {Province}/Code/mod_Common_{HabCode}{Date}.vb
  -> shared by {list of LOBs} -- will be edited ONCE
```

**How to detect shared modules:**

```
1. For each selected folder, parse .vbproj and extract Code/ file references
2. Build a map: {Code/ filename -> [list of .vbproj files that reference it]}
3. Any file referenced by 2+ .vbproj files is a shared module
4. mod_Common_*Hab* files are the most common shared modules
```

### Step 4.6: Reverse Lookup for Hidden Blast Radius

When shared modules are detected, scan for ADDITIONAL .vbproj files that reference
them but are NOT in the developer's target list:

```
1. For each shared module, glob for:
   {Province}/**/Cssi.IntelliQuote.{config.carrier_prefix}*.vbproj
2. Parse each .vbproj found
3. Check if it references the shared module
4. If any referencing .vbproj is NOT in the target list, warn:

   WARNING: mod_Common_SKHab20260101.vb is also referenced by:
     - Saskatchewan/Farm/20260101 (NOT in your target list)
     - Saskatchewan/Seasonal/20260101 (NOT in your target list)

   Changes to this file will affect ALL referencing LOBs.
   Options:
     1. Add the missing folders to the workflow
     2. Proceed anyway (those LOBs will pick up the changes)
     3. Cancel and rethink
```

### Step 4.7: Create Workflow Directory

Using the workstream name from Step 4.1, create the full directory structure:

```
.iq-workstreams/changes/{workstream-name}/
  manifest.yaml
  input/
    attachments/
  parsed/
    srds/
  analysis/
    operations/
  plan/
  execution/
    snapshots/
  verification/
  summary/
```

Use the Bash tool to create directories:
```bash
mkdir -p ".iq-workstreams/changes/{workstream-name}"/{input/attachments,parsed/srds,analysis/operations,plan,execution/snapshots,verification,summary}
```

Write the developer's raw input (held from Step 4.2) to `input/source.md`.

**If auto-fetched from ADO (Step 4.1):** Also copy the full ticket data directory
into the workstream for reference:
```bash
cp -r "workitem-{key}-full" ".iq-workstreams/changes/{workstream-name}/input/ticket-data"
```
This preserves all comments, attachments, and raw API responses alongside the brief
that was used as `input/source.md`.

### Step 4.8: Write Initial manifest.yaml

Write the manifest.yaml with initial metadata (see Section 11 for full schema):

```yaml
workflow_id: "{workstream-name}"
codebase_root: "{root_path from config.yaml}"
carrier: "{carrier_name from config.yaml}"
province: "{province_code}"
province_name: "{province_name}"
lobs: ["{LOB1}", "{LOB2}", ...]
effective_date: "{YYYYMMDD from target folder name}"
ticket_ref: "{ticket.ref or null}"
workflow_type: "{single_new | existing_folder | multi_folder_hab}"
state: "CREATED"
created_at: "{ISO 8601 timestamp}"
updated_at: "{ISO 8601 timestamp}"
svn_revision: null

ticket:
  ref: "{raw input, e.g., 'DevOps 24778'}"
  key: "{normalized, e.g., '24778'}"
  mode: "{ticketed | adhoc}"
  auto_fetched: false               # true if fetched via fetch-ticket.sh
  fetch_dir: null                   # "workitem-{id}-full" if auto-fetched

target_folders:
  - path: "{relative path from carrier root}"
    vbproj: "{.vbproj filename}"
  # ... one per target folder

shared_modules: []
  # Populated after shared module detection

footprint:                              # Populated in Step 4.4b
  target_folders: []                    # paths from target_folders above
  code_files: []                        # all Code/ files from .vbproj parsing
  shared_modules: []                    # shared files across LOBs

lifecycle:
  completed_at: null                    # set when state -> COMPLETED
  archive_after: null                   # completed_at + 14 days (or 7 for DISCARDED)
  archived_at: null                     # set when moved to archive/

srd_count: 0
srds: {}

error_log: []
```

**Backward compatibility:** `ticket_ref` is kept and mirrored from `ticket.ref`
so that older agents (/iq-execute, /iq-review) and validators that read
`ticket_ref` continue to work.

---

## 5. Workflow ID Convention

The workflow ID is generated from the ticket reference (Step 4.1).

**Naming format (ticket-first):**

| Mode | Format | Example |
|------|--------|---------|
| Ticketed | `{key}-{description}` | `24778-sk-hab-rate-increase` |
| Ticketed (prefix) | `{prefix-key}-{description}` | `devops-24778-sk-hab-rates` |
| Ad-hoc | `adhoc-{YYYYMMDD}-{description}` | `adhoc-20260301-sk-common-cleanup` |
| Duplicate | `{base-id}-02` | `24778-sk-hab-rate-increase-02` |

**Examples:**
- `24778-sk-hab-rate-increase` -- ticket 24778, SK hab rate work
- `devops-24778-sk-hab-rates` -- prefixed ticket key
- `adhoc-20260301-sk-common-cleanup` -- no ticket, date-prefixed
- `24778-sk-hab-rate-increase-02` -- second workstream for same ticket

**Developer override:** If the developer types a custom name at the confirmation
prompt, use it (sanitized) instead. The ticket-first convention is the default,
not a requirement.

**Sanitization rules:**
1. Lowercase all characters
2. Replace spaces with hyphens
3. Remove special characters (keep alphanumeric, hyphens, underscores)
4. Ensure the name is non-empty and valid as a directory name

---

## 6. The Agent Pipeline

This is the CORE of the orchestrator. The orchestrator coordinates 5 analysis
agents through a pipeline: it launches each agent as a **separate process**,
relays developer questions, collects results, and presents the plan at Gate 1.

Agents are NOT executed inline. Each agent is a self-contained process that
reads its own `.md` instruction file from `.iq-update/agents/`, reads input
files from the workstream folder, executes its logic autonomously, and writes
output files back to the workstream folder. The orchestrator's job is
**coordination, not execution**.

```
Pipeline flow:

  Steps 1-4 (launched as sub-agents or team):
    Intake -> Discovery -> Decomposer -> Analyzer -> Planner
                                          |
                                    [GATE 1: developer approves plan]
                                          |
                                    state: PLANNED -- /iq-plan ends here
                                          |
  (Execution and review handled by /iq-execute and /iq-review respectively)
```

### Execution Modes

The pipeline supports two execution modes, controlled by `execution_mode`
in manifest.yaml ("team" or "sequential"). The developer can override with
`/iq-plan --sequential`.

**Team mode (default):**

Before Step 1, the orchestrator creates an agent team:

```
1. TeamCreate(team_name="iq-{workstream-name}")
2. Create 5 tasks with sequential dependencies:
   - "Run Intake agent"       (no blockers)
   - "Run Discovery agent"    (blocked by Intake)
   - "Run Decomposer agent"   (blocked by Discovery)
   - "Run Analyzer agent"     (blocked by Decomposer)
   - "Run Planner agent"      (blocked by Analyzer)
3. For each step: spawn a teammate agent (see Agent Launch Protocol)
4. Developer questions are relayed via SendMessage:
   agent -> orchestrator -> developer -> orchestrator -> agent
5. After all 5 complete: TeamDelete(), proceed to Gate 1
```

Requires: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in Claude Code settings.
If TeamCreate fails, automatically fall back to sequential mode and log:
```
error_log entry: {type: "team_mode_unavailable", resolution: "Falling back to sequential"}
```

**Sequential mode (fallback):**

The orchestrator launches each agent one at a time as a sub-agent via the
Task tool:

```
1. For each step: launch sub-agent (see Agent Launch Protocol)
2. Sub-agent runs to completion, returns a summary
3. If the agent needs developer input: it writes candidates to output
   YAML with status: "pending_confirmation" and returns. The orchestrator
   presents choices to the developer, then re-launches the agent with
   the developer's answers.
4. Read output files, update manifest, proceed to next step
```

**In BOTH modes:**
- Agents read their own `.md` instruction files autonomously
- The workstream folder is the handoff mechanism between agents
- Modifiers and Reviewer ALWAYS run inline (via /iq-execute and /iq-review)
- Gates (1 and 2) ALWAYS run in the orchestrator
- `manifest.yaml` is updated by the orchestrator after each agent completes
- `developer_decisions` are recorded in manifest.yaml by the orchestrator

### Agent Launch Protocol

For each agent in Steps 1-4 (Intake, Discovery, Decomposer, Analyzer, Planner),
the orchestrator launches it with the Task tool.

**Team mode** — include `team_name`:
```
Task(
  name: "{agent}-agent",
  team_name: "iq-{workstream-name}",
  subagent_type: "general-purpose",
  prompt: <standard agent prompt below>
)
```

**Sequential mode** — no `team_name`:
```
Task(
  name: "{agent}-agent",
  subagent_type: "general-purpose",
  prompt: <standard agent prompt below>
)
```

**Standard agent prompt template:**

```
You are the {Agent} agent for the IQ Rate Update Plugin.

CARRIER ROOT: {root_path}
WORKSTREAM: .iq-workstreams/changes/{workstream-name}/

Read your full instructions from: .iq-update/agents/{agent}.md
Follow ALL steps in that file. Your instructions are complete and
self-contained.

INPUT FILES:
  {list — varies by agent, see each Step below}

OUTPUT FILES:
  {list — varies by agent, see each Step below}

ALSO READ:
  .iq-workstreams/config.yaml

{mode-specific developer interaction protocol — see below}

IMPORTANT: Do NOT update manifest.yaml — the orchestrator handles that.
```

**Team mode — add to prompt:**
```
DEVELOPER INTERACTION:
  When you need developer input (ambiguity, candidate selection,
  confirmation), send a message to "orchestrator" with prefix:
    "DEVELOPER_QUESTION: {your formatted question}"
  Wait for the reply:
    "DEVELOPER_ANSWER: {the developer's response}"

ON COMPLETION:
  Send to "orchestrator":
    "AGENT_COMPLETE: {1-2 line summary of what you produced}"
  Then mark your task as completed via TaskUpdate.
```

**Sequential mode — add to prompt:**
```
DEVELOPER INTERACTION:
  When you encounter ambiguity (multiple candidates, unclear targets),
  write all candidates to your output YAML with status: "pending_confirmation".
  Include full candidate details so the orchestrator can present them.

ON COMPLETION:
  Return a summary: output counts, pending confirmations, warnings.
```

---

### Step 1: INTAKE

**Manifest update:** Set `state: "ANALYZING"`, `phase_status.intake.status: "in_progress"`,
`updated_at: "{now}"`

**Before launching the agent:**

The developer already provided the change description in Step 4.2. If the input
was saved to `input/source.md`, read it back. Otherwise, prompt:

```
What changes need to be made? You can:
  - Paste the Summary of Changes text directly
  - Provide a path to a PDF: /path/to/summary.pdf
  - Provide a path to an Excel file: /path/to/rates.xlsx
  - Describe the changes in plain language
```

Save the raw input to `input/source.md`:
- If text: write the text as-is
- If PDF/Excel path: copy the file to `input/attachments/`, note the path
  in `source.md`
- If natural language: write verbatim

**Launch the Intake agent** using the Agent Launch Protocol above:

```
Agent:  intake
Input:  input/source.md, .iq-workstreams/config.yaml
Output: parsed/change_spec.yaml, parsed/srds/srd-NNN.yaml
```

The Intake agent reads `.iq-update/agents/intake.md` and autonomously:
- Parses the input into structured SRDs
- Classifies each SRD by type and complexity
- Detects DAT-file-based rate changes (hab dwelling base rates)
- Detects rounding mode (multiply+round vs explicit values)
- Asks clarifying questions if input is ambiguous (via developer interaction protocol)

**After the agent completes:**

1. Read `parsed/change_spec.yaml` to get the parsed results.

2. Show the developer what was parsed:

   ```
   Parsed {N} change(s):
     SRD-001: {title} ({type}, {complexity})
     SRD-002: {title} ({type}, {complexity})
     ...
   ```

   If any SRD has `dat_file_warning: true`:
   ```
   NOTE: SRD-{NNN} targets hab dwelling base rates, which live in external
   DAT files -- NOT in VB code. This change is outside the plugin's scope.
   I'll flag it in the summary but won't attempt to edit DAT files.
   ```

3. Update manifest:
   - `srd_count: {N}`
   - `srds:` with each SRD ID and status `PENDING`
   - `ticket_ref:` if extracted from input
   - `phase_status.intake.status: "completed"`
   - `phase_status.intake.summary: "{N} SRDs: {types}"`
   - `updated_at: "{now}"`
   - Append any developer Q&A to `developer_decisions`

**If the developer says "I forgot to mention X" AFTER intake:** Add the new
information to `input/source.md`, re-launch the Intake agent (or launch a
supplemental run). Create additional SRDs and update the manifest accordingly.

---

### Step 1.5: DISCOVERY

**Manifest update:** Set `phase_status.discovery.status: "in_progress"`,
`updated_at: "{now}"`

**Launch the Discovery agent** using the Agent Launch Protocol:

```
Agent:  discovery
Input:  parsed/change_spec.yaml, parsed/srds/srd-NNN.yaml,
        target .vbproj files, CalcMain.vb, Code/ files,
        .iq-workstreams/config.yaml
Output: analysis/code_discovery.yaml
```

The Discovery agent reads `.iq-update/agents/discovery.md` and autonomously:
- Reads CalcMain.vb and traces the full calculation flow
- Reads the primary shared code files (mod_Common, mod_Algorithms, etc.)
- Matches each SRD to its exact target function by reading actual code
- Identifies related functions and peer templates for downstream agents
- Extracts CalcOption dispatch tables (if endorsement SRDs exist)

**After the agent completes:**

1. Read `analysis/code_discovery.yaml` to verify the results.

2. Show the developer what was discovered:

   ```
   Code Discovery Complete:
     Entry point: {main_function} in {CalcMain path}
     Calculation flow: {N} functions traced from CalcMain
     SRD targets resolved:
       SRD-001: {title} → {function} in {file}
       SRD-002: {title} → {function} in {file}
     Related functions flagged: {N}
     Peer templates found: {N}
   ```

   If any SRD has `resolved: false`:
   ```
   NOTE: SRD-{NNN} could not be mapped to a specific function.
   The Decomposer will fall back to heuristic matching for this SRD.
   ```

3. Update manifest:
   - `phase_status.discovery.status: "completed"`
   - `phase_status.discovery.summary: "{N}/{total} SRDs resolved, {N} flow steps"`
   - `updated_at: "{now}"`

**If Discovery fails entirely** (e.g., CalcMain not found, .vbproj unreadable):
Log the error, set `phase_status.discovery.status: "skipped"`, and proceed to
Step 2. All downstream agents have graceful degradation — they fall back to
existing heuristic behavior when `code_discovery.yaml` is absent.

---

### Step 2: DECOMPOSER

**Manifest update:** Set `phase_status.decomposer.status: "in_progress"`,
`updated_at: "{now}"`

**Launch the Decomposer agent** using the Agent Launch Protocol:

```
Agent:  decomposer
Input:  parsed/change_spec.yaml, parsed/srds/srd-NNN.yaml,
        analysis/code_discovery.yaml (from Discovery, if exists),
        target .vbproj files, .iq-workstreams/config.yaml
Output: analysis/dependency_graph.yaml, analysis/operations/op-NNN.yaml
```

The Decomposer agent reads `.iq-update/agents/decomposer.md` and autonomously:
- Breaks each SRD into atomic operations
- Identifies which file(s) each operation targets
- Builds a dependency graph with inter-SRD constraints
- Assigns each operation to `rate-modifier` or `logic-modifier`

**After the agent completes:**

1. Read `analysis/dependency_graph.yaml` to verify operation count.

2. Update manifest:
   - Update each SRD status to `ANALYZING`
   - `phase_status.decomposer.status: "completed"`
   - `phase_status.decomposer.summary: "{N} operations across {N} files"`
   - `updated_at: "{now}"`
   - Append any developer Q&A to `developer_decisions`

---

### Step 3: ANALYZER

**Manifest update:** Set `phase_status.analyzer.status: "in_progress"`,
`updated_at: "{now}"`

**Launch the Analyzer agent** using the Agent Launch Protocol:

```
Agent:  analyzer
Input:  analysis/dependency_graph.yaml, analysis/operations/op-NNN.yaml,
        target .vbproj files, actual Code/ source files,
        .iq-workstreams/config.yaml
Output: enriched analysis/operations/op-NNN.yaml (with line numbers),
        analysis/files_to_copy.yaml, analysis/blast_radius.md
```

The Analyzer agent reads `.iq-update/agents/analyzer.md` and autonomously:
- Reads actual VB.NET source files to find exact line numbers
- Identifies function boundaries, Array6 calls, Select Case blocks
- Determines which Code/ files need new dated copies
- Runs reverse .vbproj lookup for hidden blast radius
- Computes TOCTOU file hashes

**DEVELOPER INTERACTION — the Analyzer is the most interactive agent:**

The Analyzer's "show, don't guess" principle means it will ask the developer
to choose when it finds multiple candidates for a target (e.g., 4 Select Case
blocks matching "deductible", or 2 functions matching "GetBasePrem*").

- **Team mode:** The Analyzer sends `DEVELOPER_QUESTION:` messages via
  SendMessage. The orchestrator receives these, presents them to the developer,
  and relays the answer back. Expect 3-5 questions for a typical hab workflow.
  Each question includes candidate details formatted per the Analyzer's .md spec.

- **Sequential mode:** The Analyzer writes candidates to `op-NNN.yaml` with
  `status: "pending_confirmation"` and returns. The orchestrator reads all
  pending confirmations, presents them to the developer in batch:

  ```
  The Analyzer found ambiguous targets that need your input:

    op-001-02: 4 candidates for "deductible" Select Case
      Candidate 1: SetDisSur_Deductible() at line 1205
      Candidate 2: SetDisSur_Deductible() at line 1340 (farm path)
      ...
    Which one? (enter number, or "all")

    op-002-01: 2 candidates for "GetBasePremium"
      ...
  ```

  After the developer answers, write their choices to
  `analysis/developer_choices.yaml` and re-launch the Analyzer with an
  additional prompt line:
  ```
  DEVELOPER CHOICES: Read analysis/developer_choices.yaml for resolved
  ambiguities. Apply these choices instead of asking again.
  ```

**After the agent completes:**

1. Read `analysis/blast_radius.md` and show the developer:

   ```
   Blast radius:
     {N} file(s) to copy (new dated versions)
     {N} shared module change(s) (affects {N} LOBs)
     {N} LOB-specific change(s)
     {N} total operations across {N} files

   {Any warnings from reverse lookup or cross-LOB detection}
   ```

2. Update manifest:
   - `phase_status.analyzer.status: "completed"`
   - `phase_status.analyzer.summary: "{N} files, {N} operations, {warnings}"`
   - `updated_at: "{now}"`
   - Append all developer Q&A to `developer_decisions`

---

### Step 4: PLANNER

**Manifest update:** Set `phase_status.planner.status: "in_progress"`,
`updated_at: "{now}"`

**Launch the Planner agent** using the Agent Launch Protocol:

```
Agent:  planner
Input:  analysis/dependency_graph.yaml, analysis/operations/op-NNN.yaml,
        analysis/files_to_copy.yaml, analysis/blast_radius.md,
        actual Code/ source files
Output: plan/execution_plan.md, plan/execution_order.yaml,
        execution/file_hashes.yaml
```

The Planner agent reads `.iq-update/agents/planner.md` and autonomously:
- Orders operations bottom-to-top within each file (prevents line drift)
- Groups operations into readable phases with dependency ordering
- Computes risk level (LOW/MEDIUM/HIGH)
- Generates the human-readable execution plan and machine-readable order

The Planner has NO developer interaction — it is fully automated.

**After the agent completes:**

1. Update manifest:
   - `state: "PLANNED"`
   - `phase_status.planner.status: "completed"`
   - `phase_status.planner.summary: "{N} phases, {risk} risk"`
   - `updated_at: "{now}"`

2. In team mode: TeamDelete() to clean up the analysis team.

3. Read `plan/execution_plan.md` and present it to the developer at Gate 1.

**Present the execution plan to the developer (GATE 1):**

Show the full content of `plan/execution_plan.md`. The format depends on complexity:

**For SIMPLE changes (e.g., 5% rate increase):**

```
EXECUTION PLAN: {Province} {LOB(s)} {Date}
============================================

Summary: {N} change(s), {N} file(s), {N} value edits, {risk} risk

FILE COPIES:
  {old_file} -> {new_file}
    .vbproj updates: {N} file(s)

Phase 1: {title} (op-{NNN}) [{agent}]
  File: {filepath}
  Function: {function_name}()
  Action: {description}

  Before -> After (Territory 1):
    {old line}
    {new line}

  Impact: {N} territories x {N} values = {N} changes
  All changes: {min%} to {max%} (rounding variation)

Approve this plan? Say "approve" to proceed or tell me what to change.
```

**For COMPLEX changes (multiple phases, dependencies):**

```
EXECUTION PLAN: {Province} {LOB(s)} {Date}
============================================

Summary: {N} operations across {N} files, {risk} risk
LOBs affected: {list}
Shared module: {filename}

FILE COPIES:
  {list of copies with .vbproj update counts}

Phase 1: {title} (op-{NNN}) [{agent}]
  {details}

Phase 2: {title} (op-{NNN}) [{agent}, depends on Phase 1]
  {details}

... (all phases)

Approve this plan? Say "approve" to proceed or tell me what to change.
```

---

### === GATE 1: PLAN APPROVAL ===

This is the first developer checkpoint. NO files have been modified yet. The
developer reviews the execution plan and decides whether to proceed.

**Wait for the developer's response. Classify it using the Conversational Action
Mapping (Section 12):**

**APPROVE** (developer says "approve", "yes", "looks good", "go ahead", "LGTM",
"proceed", "do it"):

```
1. Set manifest state: "PLANNED"
2. Set manifest phase_status.gate_1.status: "approved"
3. Set manifest phase_status.gate_1.summary: "Developer approved all {N} SRDs"
4. Set manifest updated_at: "{now}"
5. Present the "After Plan Approval" message (Section 9)
```

**IMPORTANT:** /iq-plan ends here. Execution is handled by `/iq-execute` in a
fresh context window. Do NOT attempt to run modifier agents.

**REJECT** (developer says "no", "wrong", "that's not right", "reject",
"change X to Y", "the value should be Z"):

```
1. Capture the developer's feedback
2. Determine what needs to change:
   - If specific correction ("change Territory 1 to 0.0935"):
     update the relevant SRD/operation, re-run Planner
   - If general rejection ("the whole approach is wrong"):
     ask what to change, potentially re-run from Analyzer
3. Re-present the revised plan
4. Stay at GATE 1 -- wait for approval again
```

**PARTIAL APPROVE** (developer says "approve SRD-001 but reject SRD-003",
"skip the Elite Comp changes", "do everything except the deductible"):

```
1. Parse which SRDs are approved and which are rejected
2. Run dependency validation (see Section 7)
3. If dependencies block the requested split: inform and offer alternatives
4. If dependencies are OK:
   - Mark approved SRDs for execution
   - Mark rejected SRDs as DEFERRED in manifest
   - Proceed to Step 5 with only approved operations
   - Tell developer: "When ready for the deferred SRDs, run /iq-plan
     and I'll pick up where we left off."
```

**INVESTIGATE** (developer asks a question -- "show me the file", "does this
affect Farm?", "what does line 350 look like?"):

```
1. DO NOT change state
2. Answer the question (see Section 8: Investigation Mode)
3. Return to GATE 1: "Back to the plan -- approve, reject, or keep asking."
```

**DISCARD** (developer says "never mind", "cancel", "throw this away",
"forget it"):

```
1. Set manifest state: "DISCARDED"
2. Tell developer: "Workflow discarded. No files were modified.
   The workflow directory will be kept for reference."
```

---

---

## 7. Partial Approval Logic

When the developer approves some SRDs and rejects others at Gate 1, the
orchestrator must validate dependencies before proceeding.

### Dependency Validation Algorithm

```
1. Parse the developer's response to identify:
   - approved_srds: list of SRD IDs to execute
   - rejected_srds: list of SRD IDs to defer

2. For each approved SRD:
   a. Look up all its operations in dependency_graph.yaml
   b. For each operation, check its depends_on list
   c. Resolve each dependency to its parent SRD
   d. If any dependency's SRD is in rejected_srds:
      -> BLOCK: cannot approve this SRD without its dependency

3. If any blocks found:

   Cannot approve SRD-{NNN} without SRD-{NNN}.
   SRD-{NNN} ({title}) depends on SRD-{NNN} ({title}).

   Options:
     1. Approve both SRD-{NNN} and SRD-{NNN}
     2. Reject both SRD-{NNN} and SRD-{NNN}
     3. Show me the dependency graph

4. If no blocks:
   a. Filter execution_order.yaml to include only approved SRD operations
   b. Maintain bottom-to-top ordering within each file
   c. Mark approved SRDs as APPROVED in manifest
   d. Mark rejected SRDs as DEFERRED in manifest
   e. Set state: PLANNED
   f. Tell developer:
      "Plan approved for SRD(s): {approved list}.
       SRD(s) deferred: {deferred list}.
       You can /clear and run /iq-execute to apply the approved changes.
       When ready for the deferred SRDs, run /iq-plan to pick them up."
```

### Resume After Partial Approval

When the developer runs `/iq-plan` later:

```
1. Resume detection finds the workflow with DEFERRED SRDs
2. Present: "Found workflow {id} with {N} deferred SRD(s): {list}"
3. Developer provides updated information for rejected SRDs
4. Pipeline re-runs from Analyzer (for the deferred SRDs only)
5. New plan includes only the deferred operations
6. Gate 1 approval as normal
```

---

## 8. Investigation Mode

At ANY point during the workflow, the developer can ask questions. Questions
DO NOT change the workflow state. After answering, the orchestrator returns to
exactly where it was.

### How to Detect Investigation Queries

The developer's message is a question (not a command) when it:
- Contains a question mark
- Starts with "show me", "what", "how", "does", "can", "will", "is"
- Asks about something outside the current workflow step
- Requests information without making a decision

### What Investigation Mode Does

```
1. Note the current workflow position (state, gate, step)
2. Process the question:
   - File exploration: use Read tool to show file contents
   - Cross-reference queries: parse .vbproj files, search Code/ files
   - Status queries: read manifest.yaml and summarize
   - Comparison queries: read old and new file versions
   - Codebase queries: search config.yaml and the file system
3. Present the answer
4. Return to the current position:

   "Back to {current context}. {prompt for next action}"

   Examples:
   "Back to the plan -- approve, reject, or keep asking."
   "Back to the results -- approve or tell me what to fix."
   "You were describing the changes. Continue?"
```

### Common Investigation Queries and How to Handle Them

| Developer Says | What to Do |
|----------------|-----------|
| "Show me the current file" | Read the file and display with line numbers |
| "Show me {function_name}" | Find the function in the relevant file, display it |
| "What does line {N} look like?" | Read and display specific lines |
| "Does this affect Farm?" | Check all .vbproj files that reference the shared module |
| "What other files reference this?" | Run reverse lookup on the file |
| "What's the status?" | Read manifest.yaml, show state and SRD progress |
| "How many territories does {Province} {LOB} have?" | Search the relevant mod file |
| "What did the previous version look like?" | Find and display the prior-dated file |
| "Show me the diff so far" | Compare snapshot to current file state |
| "What's left to do?" | Show remaining operations from execution_order.yaml |
| "I forgot to mention, also change X" | Treat as addendum -- see below |

### Addendum Handling ("I forgot to mention...")

If the developer adds new changes mid-workflow:

```
If before Gate 1 (state: ANALYZING or PLANNED):
  1. Add new SRDs to the change spec
  2. Re-run from Decomposer with the expanded set
  3. Re-run Analyzer and Planner
  4. Present updated plan at Gate 1

If after Gate 1 (state: PLANNED, developer about to /iq-execute):
  1. Warn: "The plan is already approved. I can add this as a
     separate workflow, or we can re-plan with the new changes
     included (state will go back to ANALYZING)."
  2. Let developer decide
```

---

## 9. After Plan Approval

When the developer approves at Gate 1, the workflow reaches state: PLANNED.
This is the end of `/iq-plan`'s responsibility.

### What to Tell the Developer

```
Plan approved. State: PLANNED.

The execution plan is saved in:
  plan/execution_plan.md
  plan/execution_order.yaml

Next steps:
  1. You can /clear to free up context
  2. Run /iq-execute to apply the approved changes
  3. After execution, run /iq-review for final validation

All workstream data is preserved in .iq-workstreams/changes/{workstream-name}/.
Nothing is lost when you /clear.
```

### What Gets Saved for /iq-execute

The following files are the handoff to `/iq-execute`:

```
manifest.yaml           — state: PLANNED, all SRDs, phase_status, developer_decisions
parsed/change_spec.yaml — structured SRDs
parsed/srds/srd-*.yaml  — individual SRD details
analysis/dependency_graph.yaml
analysis/operations/op-*.yaml — with exact line numbers, current values
analysis/files_to_copy.yaml
analysis/blast_radius.md
analysis/developer_choices.yaml — resolved ambiguities (if any)
execution/file_hashes.yaml — TOCTOU baseline
plan/execution_plan.md — human-readable approved plan
plan/execution_order.yaml — machine-readable execution order
```

No information lives only in context. Everything is in files.

---

## 10. Error Recovery

### Session Interrupted Mid-Analysis

The developer's Claude Code session ends unexpectedly (window closed, network
issue, context overflow).

**Recovery:** On next `/iq-plan`:
1. Resume detection finds the incomplete workflow (Section 3)
2. Reads phase_status to find which agents completed
3. Resumes from the next incomplete agent
4. developer_decisions from manifest avoid re-asking questions

### Agent Team Failure

An agent teammate crashes or times out during analysis.

**Recovery:**
1. Orchestrator detects agent is unresponsive
2. Offer options:
   - Retry: spawn a new agent for the same step
   - Switch to sequential mode for remaining steps
   - Abort analysis
3. Log the failure in manifest error_log

### File Modified Between /iq-plan Sessions

Another developer or process modified a target file while the developer
was reviewing the plan.

**Recovery:** Hash-check catches this on resume. Options:
1. Show diff between expected and actual state
2. Re-analyze from current state (re-run Analyzer)
3. Start over (svn revert first)
4. Accept new state (update hashes, re-plan)

Note: TOCTOU violations during execution are handled by `/iq-execute`.

---

## 11. manifest.yaml Schema

The manifest.yaml is the SINGLE SOURCE OF TRUTH for a workflow's state. It is
read by the orchestrator on resume, and updated after every agent completes and
every operation executes.

```yaml
# ============================================================================
# Workflow Manifest -- Master Tracking File
# ============================================================================
# This file tracks the complete state of a rate change workflow.
# Updated by /iq-plan, /iq-execute, and /iq-review orchestrators.
# Read on resume to determine where to continue.
# ============================================================================

# -- Identity ----------------------------------------------------------------
workflow_id: "20260101-SK-Hab-rate-update"     # Unique ID (Section 5 convention)
carrier: "Portage Mutual"                      # From config.yaml
province: "SK"                                 # Province code
province_name: "Saskatchewan"                  # Full province name
lobs:                                          # List of LOBs in this workflow
  - "Home"
  - "Condo"
  - "Tenant"
  - "FEC"
  - "Farm"
  - "Seasonal"
effective_date: "20260101"                     # YYYYMMDD from target folder
ticket_ref: "DevOps 24778"                     # Mirrored from ticket.ref (backward compat)
workflow_type: "multi_folder_hab"              # single_new | existing_folder | multi_folder_hab

# -- Ticket (new -- Step 4.1 ticket-driven naming) --------------------------
ticket:
  ref: "DevOps 24778"                          # Raw input, for display
  key: "24778"                                 # Normalized, for matching/ID generation
  mode: "ticketed"                             # "ticketed" or "adhoc"

# -- State -------------------------------------------------------------------
state: "PLANNED"                               # See State Machine below
created_at: "2026-01-15T10:30:00Z"             # ISO 8601
updated_at: "2026-01-15T11:45:00Z"             # ISO 8601, updated on every change
svn_revision: null                             # Set after developer commits

# -- Target Folders ----------------------------------------------------------
# Portage Mutual example -- discovered from config.yaml at runtime
target_folders:
  - path: "Saskatchewan/Home/20260101"         # Relative to carrier root
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  - path: "Saskatchewan/Condo/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKCONDO20260101.vbproj"
  - path: "Saskatchewan/Tenant/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKTENANT20260101.vbproj"
  - path: "Saskatchewan/FEC/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKFEC20260101.vbproj"
  - path: "Saskatchewan/Farm/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKFARM20260101.vbproj"
  - path: "Saskatchewan/Seasonal/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKSEASONAL20260101.vbproj"

# -- Shared Modules ----------------------------------------------------------
shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
    shared_by:
      - "Home"
      - "Condo"
      - "Tenant"
      - "FEC"
      - "Farm"
      - "Seasonal"

# -- Footprint (new -- Step 4.4b conflict fence) ----------------------------
footprint:
  target_folders:                              # From Step 4.3
    - "Saskatchewan/Home/20260101"
    - "Saskatchewan/Condo/20260101"
    - "Saskatchewan/Tenant/20260101"
    - "Saskatchewan/FEC/20260101"
    - "Saskatchewan/Farm/20260101"
    - "Saskatchewan/Seasonal/20260101"
  code_files:                                  # All Code/ files from .vbproj (Step 4.4)
    - "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    - "Saskatchewan/Code/CalcOption_SKHome20260101.vb"
    - "Saskatchewan/Code/CalcOption_SKCondo20260101.vb"
    # ... etc
  shared_modules:                              # Subset shared by 2+ LOBs (Step 4.6)
    - "Saskatchewan/Code/mod_Common_SKHab20260101.vb"

# -- Lifecycle (new -- archive sweep) ---------------------------------------
lifecycle:
  completed_at: null                           # Set when state -> COMPLETED
  archive_after: null                          # completed_at + 14 days (7 for DISCARDED)
  archived_at: null                            # Set when moved to archive/

# -- SRD Tracking ------------------------------------------------------------
srd_count: 3
srds:
  srd-001:
    title: "Increase base rates by 5%"
    type: "base_rate_increase"
    complexity: "SIMPLE"
    status: "COMPLETED"                        # PENDING | ANALYZING | PLANNED |
                                               # APPROVED | EXECUTING | COMPLETED |
                                               # FAILED | DEFERRED | OUT_OF_SCOPE |
                                               # DISCARDED
    operations:
      op-001: "COMPLETED"                      # PENDING | IN_PROGRESS | COMPLETED |
                                               # FAILED | DEFERRED
  srd-002:
    title: "Change $5000 deductible factor"
    type: "factor_table_change"
    complexity: "SIMPLE"
    status: "EXECUTING"
    operations:
      op-002: "IN_PROGRESS"

  srd-003:
    title: "Add Elite Comp coverage type"
    type: "new_coverage_type"
    complexity: "COMPLEX"
    status: "PENDING"
    operations:
      op-003: "PENDING"
      op-004: "PENDING"
      op-005: "PENDING"
      op-006: "PENDING"

# -- Cross-Province Consent (if applicable) ----------------------------------
cross_province_consent: null                   # Set if developer approves editing
                                               # cross-province shared files
# Example when set:
# cross_province_consent:
#   file: "Code/PORTCommonHeat.vb"
#   developer_response: "It's intentional, all provinces should get it."
#   timestamp: "2026-01-15T11:30:00Z"

# -- Phase Status (for resume after /clear or new session) -------------------
# Each phase records a 1-2 line summary when it completes.
# The orchestrator reads these on resume to understand what happened
# WITHOUT re-reading full agent outputs.
phase_status:
  intake:
    status: "completed"                           # pending | in_progress | completed | failed
    summary: "3 SRDs: 2 base_rate_increase, 1 factor_table_change, no DAT warnings"
  discovery:
    status: "completed"                           # pending | in_progress | completed | skipped | failed
    summary: "3/3 SRDs resolved, 20 flow steps from TotPrem"
  decomposer:
    status: "completed"
    summary: "7 ops (2 shared, 5 LOB-specific), no conflicts, no inter-SRD deps"
  analyzer:
    status: "completed"
    summary: "All verified, 3 files, 6 LOBs blast radius, mixed rounding on SRD-003"
  planner:
    status: "completed"
    summary: "7 ops in execution plan, bottom-to-top in 3 files, no partial approval issues"
  gate_1:
    status: "approved"                            # pending | approved | rejected | revision_N
    summary: "Developer approved all 3 SRDs, no changes requested"
  # --- Phases below managed by /iq-execute and /iq-review ---
  # --- Included here for complete manifest schema reference ---
  modifiers:
    status: "pending"
    summary: null
  reviewer:
    status: "pending"
    summary: null
  gate_2:
    status: "pending"
    summary: null

# -- Developer Decisions (captures nuance that YAML data cannot) -------------
# Every time the orchestrator asks the developer a question and gets an answer,
# append to this list. This is the ONLY record of conversational decisions.
# On resume after /clear or new session, read this to avoid re-asking questions.
developer_decisions: []
# Example entries:
# - timestamp: "2026-01-15T10:45:00Z"
#   phase: "intake"
#   question: "Should all 6 SK hab LOBs be included?"
#   answer: "Yes, all 6"
# - timestamp: "2026-01-15T11:10:00Z"
#   phase: "analyzer"
#   question: "SetDisSur_Deductible has farm and non-farm paths. Which is the target?"
#   answer: "Farm path"
# - timestamp: "2026-01-15T11:30:00Z"
#   phase: "analyzer"
#   question: "SRD-003 has mixed rounding (42 banker + 6 decimal lines). Proceed?"
#   answer: "Yes, proceed with per-line rounding"

# -- Execution Mode ----------------------------------------------------------
execution_mode: "team"                            # "team" (agent team, default) |
                                                  # "sequential" (sub-agents)

# -- Error Log ---------------------------------------------------------------
error_log: []
# Example entries:
# - timestamp: "2026-01-15T11:20:00Z"
#   operation: "op-003"
#   error: "TOCTOU violation: file hash mismatch"
#   resolution: "Developer chose to re-analyze"
# - timestamp: "2026-01-15T11:22:00Z"
#   type: "dirty_file_warning"
#   file: "mod_Common_SKHab20260101.vb"
#   resolution: "Developer resumed anyway"
```

### State Machine

```
/iq-plan:     CREATED -----> ANALYZING -----> PLANNED
                                                |    ^
                                                |    |
                                                v    |
                                           (reject: revise,
                                            loops back to PLANNED)

/iq-execute:  PLANNED -----> EXECUTING -----> EXECUTED
                                |
                                v
                           (op failed: retry/skip)

/iq-review:   EXECUTED -----> VALIDATING -----> COMPLETED
                                  |    ^
                                  |    |
                                  v    |
                             (reject: rework,
                              re-validate)

Special states:
  DISCARDED -- developer cancelled at any point
```

**Valid state transitions:**

| From | To | Who | How |
|------|----|-----|-----|
| (new) | CREATED | /iq-plan | Creates workflow |
| CREATED | ANALYZING | /iq-plan | Developer provides input |
| ANALYZING | PLANNED | /iq-plan | Planner completes, developer approves at Gate 1 |
| PLANNED | PLANNED | /iq-plan | Developer rejects at Gate 1 (revision loop) |
| PLANNED | EXECUTING | /iq-execute | Execution team starts |
| EXECUTING | EXECUTED | /iq-execute | All operations complete |
| EXECUTING | EXECUTING | /iq-execute | Operation retry (self-correction) |
| EXECUTED | VALIDATING | /iq-review | Review team starts |
| VALIDATING | COMPLETED | /iq-review | Developer approves at Gate 2 |
| VALIDATING | VALIDATING | /iq-review | Rework + re-validate loop |
| VALIDATING | PLANNED | /iq-review | Major rework needed, back to /iq-execute |
| Any | DISCARDED | Any | Developer cancels |

**Lifecycle notes:**

- When state transitions to **COMPLETED** (in /iq-review), also set:
  - `lifecycle.completed_at` = current timestamp
  - `lifecycle.archive_after` = completed_at + 14 days
- When state transitions to **DISCARDED** (any command), also set:
  - `lifecycle.completed_at` = current timestamp
  - `lifecycle.archive_after` = completed_at + 7 days
- The `/iq-status` and `/iq-plan` archive sweeps use `lifecycle.archive_after`
  to determine when to move a workstream to the archive directory.
- Old manifests without a `lifecycle` section: fall back to `updated_at` + 14 days.

---

## 12. Conversational Action Mapping

This table tells Claude how to interpret the developer's natural language during
the workflow. The orchestrator classifies each developer message into one of these
action categories and responds accordingly.

### Classification Priority

When a message could match multiple categories, use this priority order:
1. DISCARD (explicit cancellation overrides everything)
2. ADDENDUM (adding new changes)
3. PARTIAL APPROVE (mentions specific SRDs)
4. APPROVE / REJECT (clear decision)
5. INVESTIGATE (questions)
6. STATUS (status queries)

### Action Mapping Table

| Category | Developer Phrases | Plugin Action | State Change? |
|----------|------------------|---------------|:------------:|
| APPROVE | "approve", "approved", "yes", "looks good", "LGTM", "go ahead", "proceed", "do it", "ship it", "OK", "fine", "good", "accept" | Approve plan at Gate 1, set state: PLANNED | YES |
| REJECT | "no", "wrong", "reject", "that's not right", "incorrect", "bad", "nope" | Ask what to change, enter revision loop | NO (stays at gate) |
| CORRECT | "change X to Y", "the value should be Z", "actually it's 0.0935", "territory 1 is wrong" | Accept correction, revise plan | NO (stays at gate) |
| PARTIAL APPROVE | "approve SRD-001 but reject SRD-003", "skip the Elite Comp", "do everything except...", "just do the base rates" | Split SRDs into approved/deferred (with dependency validation) | YES (for approved) |
| INVESTIGATE | "show me...", "what does...", "how many...", "does this affect...", "is there...", any question mark | Answer without changing state, return to current position | NO |
| STATUS | "what's the status?", "where are we?", "what's left?", "progress", "how far along" | Show current state, SRD progress, next action | NO |
| ADDENDUM | "I forgot to mention...", "also change...", "one more thing...", "add this too" | Add to change spec, re-run from appropriate agent | MAYBE |
| DISCARD | "never mind", "cancel", "throw this away", "forget it", "abort", "stop" | Set state to DISCARDED, inform developer | YES |
| RESUME DEFERRED | "pick up the deferred SRDs", "do the rest", "continue with SRD-003" | Re-enter pipeline for deferred SRDs | YES |

### Ambiguity Resolution

When the developer's message is ambiguous:

```
- "OK" at Gate 1 -> treat as APPROVE (most likely intent at a gate)
- "OK" mid-conversation -> treat as acknowledgment, continue
- "sure" -> treat as APPROVE at gates, acknowledgment elsewhere
- "hmm" or "let me think" -> wait silently for a real response
- Unrecognized input -> ask: "I'm not sure what you'd like to do.
  Are you approving, rejecting, or asking a question?"
```

### Context-Dependent Behavior

The same phrase can mean different things at different stages:

| Phrase | At Gate 1 | During Analysis | During Investigation |
|--------|-----------|----------------|---------------------|
| "yes" | Approve plan | Confirm agent question | N/A |
| "no" | Reject plan | Answer "no" to question | N/A |
| "change X" | Revise plan | Clarify input | N/A |
| "show me" | Investigation | Investigation | Continue exploring |

---

## Implementation Notes for Claude Code

### Context Management (IMPORTANT)

As the orchestrator, you will read agent .md files, .vbproj files, source code, and
YAML state files across a potentially long conversation. To prevent context exhaustion:

1. **Rely on YAML files as state memory.** After completing an agent's step and
   updating manifest.yaml, do NOT try to hold the full contents of that agent's
   .md instructions or source files in your active reasoning. Re-read from YAML
   state files (manifest.yaml, change_spec.yaml, execution_order.yaml) when needed.
2. **Between Gate 1 and Gate 2**, read `plan/execution_order.yaml` for the plan —
   do not try to recall it from earlier in the conversation.
3. **One agent at a time.** When transitioning to the next agent, read its .md file
   fresh. Do not carry forward the previous agent's detailed instructions.

### Manifest Update Protocol (CRITICAL for resume)

After EVERY agent completes, the orchestrator MUST update manifest.yaml:

1. **Update `phase_status`** for the completed phase:
   - Set `status` to "completed" (or "failed")
   - Write a 1-2 line `summary` capturing what happened
   - Example: `summary: "3 SRDs: 2 base_rate_increase, 1 factor_table_change"`

2. **Append to `developer_decisions`** if the developer answered any questions:
   - Record the question, answer, phase, and timestamp
   - These are the ONLY record of conversational decisions
   - Example: `{phase: "analyzer", question: "Farm or non-farm path?", answer: "Farm"}`
   - On resume, the orchestrator reads these to avoid re-asking

3. **Update `state`** to reflect the new workflow state.

This ensures that if the developer does `/clear` or starts a new session,
the next `/iq-plan` invocation reads manifest.yaml and knows EVERYTHING:
- What phases completed (from `phase_status`)
- What was found (from `phase_status.*.summary`)
- What the developer decided (from `developer_decisions`)
- Where to resume (from `state` + `phase_status`)

### Execution Mode

The manifest includes `execution_mode` ("team" or "sequential"). This controls
how Steps 1-4 (Intake, Discovery, Decomposer, Analyzer, Planner) are launched.
Steps 5-6 (Modifiers, Reviewer) always run inline regardless of this setting.

**Team mode (default):**

Launch analysis agents as an agent team. The orchestrator creates a team,
spawns one agent at a time as a teammate, and coordinates via SendMessage.
Each agent gets its own context window — the main window stays light.

```
Team lifecycle:
  1. TeamCreate(team_name="iq-{workstream-name}")
  2. TaskCreate: 5 tasks with sequential dependencies
     - "Run Intake agent"       (no blockers)
     - "Run Discovery agent"    (blocked by Intake)
     - "Run Decomposer agent"   (blocked by Discovery)
     - "Run Analyzer agent"     (blocked by Decomposer)
     - "Run Planner agent"      (blocked by Analyzer)
  3. For each task:
     a. Spawn teammate via Task tool (with team_name parameter)
     b. Monitor for messages:
        - "DEVELOPER_QUESTION: ..." → present to developer, relay answer
        - "AGENT_COMPLETE: ..."     → update manifest, shutdown agent
        - "AGENT_ERROR: ..."        → log error, present recovery options
     c. After agent completes: TaskUpdate(status="completed")
  4. After all 5 complete: TeamDelete()
  5. Proceed to Gate 1 with Planner's output
```

Communication protocol:
- `DEVELOPER_QUESTION:` prefix = agent needs developer input. Strip prefix,
  present to developer, send back with `DEVELOPER_ANSWER:` prefix.
- `AGENT_COMPLETE:` prefix = agent finished. Update manifest phase_status.
- `AGENT_ERROR:` prefix = agent hit an error. Log to error_log, offer:
  (a) retry with new agent, (b) switch to sequential, (c) abort.

Requires: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in Claude Code settings.

Fallback: if TeamCreate fails, log to error_log and switch to sequential:
```
Tell developer: "Agent teams feature not available. Falling back to
sequential mode. To enable: set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
in Claude Code settings."
```

**Sequential mode (fallback):**

Launch each analysis agent one at a time as a sub-agent via the Task tool
(no team_name). Each agent runs to completion and returns a summary.

```
Sequential lifecycle:
  For each agent (Intake, Discovery, Decomposer, Analyzer, Planner):
    1. Launch via Task tool (no team_name)
    2. Agent runs autonomously, returns when done
    3. If agent returned pending_confirmation items:
       a. Present all pending items to developer in batch
       b. Write developer's choices to analysis/developer_choices.yaml
       c. Re-launch agent with "Read developer_choices.yaml" in prompt
    4. Read output files, update manifest
    5. Proceed to next agent
```

No inter-agent communication. Cheaper but the Analyzer's developer interaction
is batched (all questions at once after the agent returns) rather than
real-time (one at a time during agent execution).

The developer can force sequential mode: `/iq-plan --sequential`

### Team Mode Resume

When resuming a workflow that was using team mode (state=ANALYZING):
1. Check for dangling teams: attempt TeamDelete() for any leftover team
2. Read phase_status to find which agents completed
3. Skip completed agents (their output files exist in the workstream)
4. Resume from the first incomplete agent by creating a new team
5. Pass developer_decisions from manifest to the new agent's prompt
   so it does not re-ask resolved questions

When executing this skill, use these specific tool strategies:

### Reading manifest.yaml
Use the Read tool to read the manifest file. Parse the YAML content to determine
current state and SRD progress.

### Scanning for incomplete workflows
Use Bash `ls` to list directories in `.iq-workstreams/changes/`, then Read each
`manifest.yaml` found.

### Computing file hashes
Use Bash with sha256sum:
```bash
sha256sum "{filepath}" | cut -d' ' -f1
```
On Windows, use:
```bash
python -c "import hashlib; print(hashlib.sha256(open('{filepath}','rb').read()).hexdigest())"
```

### Creating workflow directories
Use Bash with mkdir -p:
```bash
mkdir -p ".iq-workstreams/changes/{workstream-name}"/{input/attachments,parsed/srds,analysis/operations,plan,execution/snapshots,verification,summary}
```

### Writing YAML files
Use the Write tool to write YAML files. Do NOT use Bash echo/cat.
After writing any YAML file (manifest.yaml, change_spec.yaml, etc.), validate it:
```bash
python -c "import yaml; yaml.safe_load(open('{filepath}')); print('YAML OK')"
```
If validation fails, the file has a structural error. Fix and re-write before proceeding.

### Parsing .vbproj files
Read the .vbproj file content and parse it as XML to extract `<Compile Include>`
entries. Claude Code can read XML content and understand its structure natively —
treat the file as structured XML, not as a string to regex against. Look for
`<Compile Include="...">` entries containing "Code\" or "Code/" in the path.
Flag any `<Compile>` nodes with `Condition` attributes for developer review.

### Showing code to the developer
Use the Read tool with offset and limit to show specific line ranges. Always
include line numbers for context.

### Generating timestamps
Use Bash to get current timestamp:
```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

---

## Downstream Agent References

The /iq-plan orchestrator launches these 5 analysis agents. Each agent's .md file
contains its complete interface contract, input/output schemas, execution steps,
and edge cases. The orchestrator does NOT read these files — the agents read them.

| Agent | File | When Called | What It Produces |
|-------|------|-------------|-----------------|
| Intake | `.iq-update/agents/intake.md` | Step 1 | `parsed/change_spec.yaml`, `parsed/srds/srd-NNN.yaml` |
| Discovery | `.iq-update/agents/discovery.md` | Step 1.5 | `analysis/code_discovery.yaml` |
| Decomposer | `.iq-update/agents/decomposer.md` | Step 2 | `analysis/dependency_graph.yaml`, `analysis/operations/op-NNN.yaml` |
| Analyzer | `.iq-update/agents/analyzer.md` | Step 3 | Updated `op-NNN.yaml` with line numbers, `analysis/blast_radius.md`, `analysis/files_to_copy.yaml` |
| Planner | `.iq-update/agents/planner.md` | Step 4 | `plan/execution_plan.md`, `plan/execution_order.yaml`, `execution/file_hashes.yaml` |

Execution agents (Rate Modifier, Logic Modifier) are launched by `/iq-execute`.
Review agent (Reviewer) is launched by `/iq-review`.
See `skills/iq-execute/SKILL.md` and `skills/iq-review/SKILL.md` for those agent references.

---

## Workflow Directory Structure

For reference, the complete directory structure created per workflow:

```
.iq-workstreams/changes/{workstream-name}/
  manifest.yaml                    <- Master tracking file (this schema)
  input/
    source.md                      <- Original ticket text or description
    attachments/                   <- PDF, Excel files
  parsed/
    change_spec.yaml               <- Structured change specification
    srds/
      srd-001.yaml                 <- Individual change items
      srd-002.yaml
      ...
  analysis/
    blast_radius.md                <- Full blast radius report
    dependency_graph.yaml          <- Operation dependencies
    files_to_copy.yaml             <- Code/ files needing new dated copies
    operations/
      op-001.yaml                  <- Atomic operations (with line numbers after Analyzer)
      op-002.yaml
      ...
  plan/
    execution_plan.md              <- Human-readable plan (GATE 1 document)
    execution_order.yaml           <- Machine-readable ordered operations
  execution/
    operations_log.yaml            <- What was done: file, line, old -> new
    file_hashes.yaml               <- SHA256 hashes for TOCTOU protection
    snapshots/                     <- Pre-edit copies for self-correction
      mod_Common_SKHab20260101.vb.snapshot
      ...
  verification/
    validator_results.yaml         <- Results from all 7 validators
    traceability_matrix.md         <- SRD -> file:line mapping
    diff_report.md                 <- Human-readable diff of all changes
    changes.diff                   <- Unified diff format
  summary/
    change_summary.md              <- Final summary for developer + SVN commit
```
