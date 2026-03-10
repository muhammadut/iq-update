---
name: iq-plan
description: Analyze a ticket and build an execution plan. Runs Intake, Understand, and Plan agents, then presents Gate 1 for developer approval.
user-invocable: true
---

# Skill: /iq-plan

## 1. Purpose & Trigger

Start a new workflow or resume an existing one. This is the analysis
orchestrator that drives the 3-agent analysis pipeline (Intake → Understand →
Plan) through Gate 1 approval. After the developer types `/iq-plan`,
everything else is conversational: the developer approves, rejects, asks questions,
provides corrections, and the orchestrator routes work to agents, manages state,
and produces the execution plan. Execution and review are handled by `/iq-execute`
and `/iq-review` respectively.

**Trigger:** Slash command `/iq-plan`

---

## 2. Precondition Checks

Execute these checks IN ORDER before doing anything else. If any check fails,
STOP and report the issue to the developer.

### Check 1: Read paths.md (MANDATORY FIRST STEP)

Read `.iq-workstreams/paths.md`. This file contains all absolute paths you need:
`plugin_root`, `carrier_root`, `python_cmd`, agent spec paths, validator paths, etc.

If `paths.md` does not exist, STOP: `"ERROR: Run /iq-init first to initialize the plugin."`

**Use the paths from this file for the entire command.** Whenever this skill says
`.iq-update/agents/...` or `.iq-update/validators/...`, replace `.iq-update/` with
the `plugin_root` value from paths.md. All paths are absolute — use them directly.

### Check 1b: Verify plugin_root is still valid (auto-heal after plugin upgrade)

After reading `paths.md`, verify that the `plugin_root` directory still exists by
checking for `{plugin_root}/package.json`. If the directory does NOT exist (common
after reinstalling a newer plugin version), **auto-discover the new plugin root:**

1. Glob for `~/.claude/plugins/cache/*/iq-update/*/package.json`
   (on Windows: `C:/Users/{user}/.claude/plugins/cache/*/iq-update/*/package.json`)
2. If found, read the `package.json` to get the version
3. Update `paths.md` in-place: replace the old `plugin_root` and `plugin_version`
   values with the new ones. Use the Edit tool to do a find-and-replace of the old
   plugin_root path with the new one throughout the file (this also fixes any
   agent/validator paths that embed the plugin_root).
4. Print: `Plugin upgraded: v{old_version} → v{new_version} (paths.md updated)`

If the plugin_root IS valid, read `{plugin_root}/package.json` to get the current
version. If it differs from `plugin_version` in paths.md, update paths.md.

Print the version once at startup:
```
IQ Update v{version}
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
     CR progress:  {completed}/{total} change requests
     Last action:  {description of last completed step}

Options:
  1. Resume this workflow
  2. Start a new workflow instead
  3. Discard this workflow and start fresh
```

### On Resume: Dirty File Detection

When the developer chooses to resume, perform hash verification **only if
`execution/file_hashes.yaml` exists.** This file is created by the Plan agent
(during /iq-plan) — it does not exist for CREATED or early ANALYZING states.
If the file does not exist, skip hash verification entirely and proceed to
state-based continuation.

```
1. If execution/file_hashes.yaml does not exist: SKIP to state-based continuation
2. Read execution/file_hashes.yaml from the workflow directory
3. For each file listed:
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
Understand step.

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
   intake -> understand -> plan -> gate_1 -> change_engine -> reviewer -> gate_2

3. Also read developer_decisions to avoid re-asking questions:
   "Developer already confirmed: {list of decisions}"
   Do NOT re-ask these questions. Pass them to the agent prompt.

4. Read the completed phase summaries to understand context:
   "Intake found: {intake.summary}"
   "Understand produced: {understand.summary}"
   "Plan produced: {plan.summary}"
   etc.

5. Launch the next agent using the current execution_mode
   (create a new team if team mode, or launch sub-agent if sequential).
```

**Fallback (if phase_status is missing or incomplete):** determine sub-state from artifacts:

```
If parsed/ticket_understanding.md does NOT exist -> resume at Intake (Step 0: comprehension)
If parsed/change_requests.yaml does NOT exist    -> resume at Intake (Step 1: CR extraction)
If analysis/code_understanding.yaml does NOT exist -> resume at Understand
If analysis/intent_graph.yaml does NOT exist     -> resume at Plan
If plan/execution_plan.md does NOT exist         -> resume at Plan
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
   If the key is purely numeric, read `paths.md` to get `plugin_root` and `env_file`.
   Check that `{plugin_root}/fetch-ticket.sh` and `{env_file}` both exist, then auto-fetch.

   **IMPORTANT:** Do NOT use `source "{env_file}"` directly — `.env` files may have
   unquoted values with spaces (e.g., `ADO_PROJECT=Rival Insurance Technology`),
   which bash interprets as separate commands. Do NOT use `[[ =~ ]]` regex tests —
   they get mangled by shell escaping on Windows. Use simple POSIX `[ ]` tests only:

   ```bash
   cd "{carrier_root}" && export PYTHON_CMD="{python_cmd}" && set -a && while IFS='=' read -r key value; do if [ -n "$key" ] && [ "${key:0:1}" != "#" ]; then export "$key=$(echo $value | sed 's/^"//;s/"$//')"; fi; done < "{env_file}" && set +a && bash "{plugin_root}/fetch-ticket.sh" {key} 2>&1
   ```

   Where `{python_cmd}` is the `python_cmd` value from `paths.md`. This safely
   exports each `KEY=value` pair, stripping surrounding double quotes if present,
   handles values with spaces correctly, and passes the verified Python path to
   `fetch-ticket.sh` (avoiding Windows App Execution Alias interception).
   - **On success:** Read `workitem-{key}-full/llm-context.md` (the FULL version
     with ALL comments, not the brief) as the change description. Set
     `ticket.auto_fetched: true`. Extract a short description from the ticket
     title (strip "Portage", province names, "Effective {date}", common
     suffixes — keep 2-4 key words).

     **IMPORTANT:** Use `llm-context.md` (full), NOT `llm-context-brief.md`.
     The brief only has the first 3 comments and strips screenshots. Comments
     frequently contain corrections, clarifications, and the actual rate values
     that the description omits. The Intake agent needs ALL of this to understand
     the ticket correctly.

     Show the developer:
     ```
     Fetched ticket {key}: {title}
     Auto-generated description: {short_description}
     Ticket has {N} comments and {M} attachments — all will be analyzed.

     Use this as the change description? [Y/n]
     ```
     **CARRIER MISMATCH CHECK:** Before proceeding, compare the ticket content
     against `carrier_name` from config.yaml. Look for carrier names in the ticket
     title and body (e.g., "Portage Mutual", "Intact", "Wawanesa", "SGI", etc.).
     - If the ticket mentions a DIFFERENT carrier than `carrier_name`: WARN:
       ```
       WARNING: This ticket mentions "{detected_carrier}" but you are working
       in the {carrier_name} folder. Are you sure this is the right ticket?

       Type "yes" to continue or "no" to enter a different ticket.
       ```
     - If the ticket does NOT mention any carrier name: NOTE (non-blocking):
       ```
       NOTE: No carrier name found in the ticket. This workspace is configured
       for {carrier_name}. Proceeding — just confirm this ticket is for {carrier_name}.
       ```
     - If the ticket mentions `carrier_name`: proceed silently.

     If yes: store the full context as the raw input, **skip Step 4.2**.
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

**If auto-fetched in Step 4.1:** This step is skipped. The full context from
`workitem-{key}-full/llm-context.md` (ALL comments, ALL metadata) is stored as
the raw input. The full ticket data directory (including downloaded attachments
and images) is moved into the workstream in Step 4.7 for the Intake agent's
Deep Ticket Comprehension step (Step 0). The original directory in the carrier
root is removed to avoid clutter.

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

**OLD-DATE .vbproj CHECK (ALL WORKFLOWS):**
For ALL workflow types (not just Workflow 2), parse the .vbproj and check each
`<Compile Include>` reference to a Code/ file. Extract the 8-digit date from each
filename. If ANY referenced Code/ file has a date OLDER than the target version
folder date, this means IQWiz created the folder but Code/ file copies were never
made. This is expected for Workflow 1 (fresh IQWiz shell) and possible for
Workflow 2 (partial previous session) and Workflow 3 (multi-folder hab). Warn:

```
WARNING: .vbproj references OLD-dated Code/ files:
  {old_file} (date: {old_date}) -- target date: {target_date}
  {old_file2} ...

These files need new dated copies before edits can be applied.
The Understand agent embeds file copy info in code_understanding.yaml (needs_copy/source_file/target_file per CR).
```

This is informational only — the Understand agent handles the actual copy list. But surfacing
it early gives the developer visibility into what the pipeline will do.

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
    requests/
  analysis/
  plan/
  execution/
    snapshots/
  verification/
  summary/
```

Use the Bash tool to create directories:
```bash
mkdir -p ".iq-workstreams/changes/{workstream-name}"/{input/attachments,parsed/requests,analysis,plan,execution/snapshots,verification,summary}
```

Write the developer's raw input (held from Step 4.2) to `input/source.md`.

**If auto-fetched from ADO (Step 4.1):** Move the full ticket data directory
into the workstream (not copy — move, to avoid cluttering the carrier root):
```bash
mv "workitem-{key}-full" ".iq-workstreams/changes/{workstream-name}/input/ticket-data"
```
This preserves all comments, attachments, and raw API responses alongside the brief
that was used as `input/source.md`, and keeps the carrier root clean.

**IMPORTANT:** The `fetch-ticket.sh` script downloads `workitem-{key}-full/` into
the carrier root directory. If left there, multiple tickets will clutter the carrier
root with `workitem-24778-full/`, `workitem-25001-full/`, etc. Always MOVE (not copy)
the directory into the workstream, so the carrier root stays clean. If the move fails
(e.g., target exists), fall back to `cp -r` then `rm -rf` the source:
```bash
cp -r "workitem-{key}-full" ".iq-workstreams/changes/{workstream-name}/input/ticket-data" && rm -rf "workitem-{key}-full"
```

### Step 4.8: Write Initial manifest.yaml

Write the manifest.yaml with initial metadata (see Section 11 for full schema):

```yaml
manifest_version: "2.0"
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
  fetch_dir: null                   # "input/ticket-data" (moved from carrier root after fetch)

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

cr_count: 0
change_requests: {}

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

This is the CORE of the orchestrator. The orchestrator coordinates 3 analysis
agents through a pipeline: it launches each agent as a **separate process**,
relays developer questions, collects results, and presents the plan at Gate 1.

Agents are NOT executed inline. Each agent is a self-contained process that
reads its own `.md` instruction file from `{plugin_root}/agents/`, reads input
files from the workstream folder, executes its logic autonomously, and writes
output files back to the workstream folder. The orchestrator's job is
**coordination, not execution**.

```
Pipeline flow:

  Step 1: Intake
    Step 0: Deep Ticket Comprehension (reads ALL comments, ALL images)
            |
      [CHECKPOINT: developer confirms ticket understanding]
            |
    Steps 1-6: CR extraction from confirmed understanding
            |
  Step 1.5: Understand -> Step 2: Plan
                                       |
                                 [GATE 1: developer approves plan]
                                       |
                                 state: PLANNED -- /iq-plan ends here
                                       |
  (Execution and review handled by /iq-execute and /iq-review respectively)
```

**Two developer checkpoints in /iq-plan:**
1. **Ticket Understanding Checkpoint** (after Intake Step 0) — "Do I understand
   the ticket correctly?" — catches misunderstandings BEFORE the pipeline runs
2. **Gate 1** (after Plan) — "Is the execution plan correct?" — catches
   implementation errors BEFORE files are modified

### Execution Modes

The pipeline supports two execution modes, controlled by `execution_mode`
in manifest.yaml ("team" or "sequential"). The developer can override with
`/iq-plan --sequential`.

**Team mode (default):**

Before Step 1, the orchestrator creates an agent team:

```
1. TeamCreate(team_name="iq-{workstream-name}")
2. Create 3 tasks with sequential dependencies:
   - "Run Intake agent"       (no blockers)
   - "Run Understand agent"   (blocked by Intake)
   - "Run Plan agent"         (blocked by Understand)
3. For each step: spawn a teammate agent (see Agent Launch Protocol)
4. Developer questions are relayed via SendMessage:
   agent -> orchestrator -> developer -> orchestrator -> agent
5. After all 3 complete: TeamDelete(), proceed to Gate 1
```

Requires: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in Claude Code settings.

**Fallback detection:** If ANY of these conditions are true, use sequential mode:
1. TeamCreate tool is not available (tool call returns error or is not listed)
2. TeamCreate returns an error (permissions, unsupported version)
3. TeamCreate times out (10+ seconds with no response)

On fallback, log and print:
```
Team mode unavailable — falling back to sequential execution.
error_log entry: {type: "team_mode_unavailable", resolution: "Falling back to sequential"}
```
Do NOT retry TeamCreate or sleep-loop. Switch to sequential immediately.

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

For each agent in Steps 1-2 (Intake, Understand, Plan),
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

**CRITICAL:** All `{...}` placeholders below MUST be replaced with actual absolute
paths from `paths.md` (read in Check 1). NEVER use `.iq-update/` literally — it
does not exist on marketplace installs.

```
You are the {Agent} agent for the IQ Rate Update Plugin.

CARRIER ROOT: {carrier_root}
PLUGIN ROOT: {plugin_root}
WORKSTREAM: {carrier_root}/.iq-workstreams/changes/{workstream-name}/
PYTHON: {python_cmd}

Read your full instructions from: {plugin_root}/agents/{agent}.md
Follow ALL steps in that file. Your instructions are complete and
self-contained.

INPUT FILES:
  {list — varies by agent, see each Step below}

OUTPUT FILES:
  {list — varies by agent, see each Step below}

ALSO READ:
  {carrier_root}/.iq-workstreams/config.yaml

TOOL PATHS:
  Python: {python_cmd}
  Validators: {plugin_root}/validators/
  Patterns: {plugin_root}/patterns/

{mode-specific developer interaction protocol — see below}

IMPORTANT: Do NOT update manifest.yaml — the orchestrator handles that.
IMPORTANT: For file path operations, use Python (os.path). For XML parsing,
use Python (xml.etree.ElementTree). NEVER use sed, awk, or Perl.
IMPORTANT: NEVER use sleep or retry loops. If a step fails, log the error
and continue to the next step.
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

### Step 1: INTAKE (with Ticket Understanding Checkpoint)

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
- If image path (PNG, JPG, etc.): copy to `input/attachments/`, note the path
  in `source.md`. The Intake agent will read images using Claude's multimodal
  capabilities to extract rate tables or annotations.
- If natural language: write verbatim

**Auto-fetched tickets with attachments:** If `fetch-ticket.sh` downloaded ticket
attachments (images, PDFs), they are already in `input/ticket-data/`. The Intake
agent will read the FULL `llm-context.md` (all comments), scan for image files,
and read them to extract rate values or context.

**Launch the Intake agent** using the Agent Launch Protocol above:

```
Agent:  intake
Input:  input/source.md, input/ticket-data/ (if exists),
        .iq-workstreams/config.yaml
Output: parsed/ticket_understanding.md,
        parsed/change_requests.yaml, parsed/requests/cr-NNN.yaml
```

**IMPORTANT — Intake agent prompt addition for auto-fetched tickets:**
When the ticket was auto-fetched, add this to the agent prompt:

```
TICKET DATA: Full ticket data is at {workstream}/input/ticket-data/
  - llm-context.md: Full ticket with ALL comments (use this, NOT the brief)
  - llm-context.json: Structured data (comments, attachments metadata)
  - attachments/: Downloaded images and files

You MUST run Step 0 (Deep Ticket Comprehension) FIRST:
  1. Read llm-context.md for the full description and ALL comments
  2. Read EVERY image in attachments/ using the Read tool (multimodal)
  3. Synthesize a ticket understanding document
  4. Present it to the developer for confirmation
  5. ONLY THEN proceed to CR extraction

The developer expects to see your understanding of the ticket BEFORE
you start extracting change requests. This is the most critical step.
```

The Intake agent reads `{plugin_root}/agents/intake.md` and autonomously:
- **FIRST:** Reads the full ticket (all comments, all images) and presents a
  comprehensive ticket understanding for developer confirmation (Step 0)
- **THEN:** Parses the confirmed understanding into structured change requests (CRs)
- Understands any ticket format (ADO, Jira, plain text, PDF, Excel)
- Detects DAT-file-based rate changes (hab dwelling base rates)
- Detects rounding mode (multiply+round vs explicit values)
- Asks clarifying questions if input is ambiguous (via developer interaction protocol)

**After the agent completes:**

1. **FIRST: Present the Ticket Understanding.** Read `parsed/ticket_understanding.md`
   and show the developer:

   ```
   TICKET UNDERSTANDING
   =====================

   {Full content of parsed/ticket_understanding.md}

   =====================
   Does this match your understanding?
   ```

   **Wait for developer confirmation.** If the developer says the understanding is
   wrong, feed corrections back to the Intake agent prompt and re-run Step 0.
   Do NOT proceed to CR review until understanding is confirmed.

2. **THEN: Show the parsed CRs.** Read `parsed/change_requests.yaml`:

   ```
   Based on the confirmed understanding, I extracted {N} change request(s):

     CR-001: {title} ({complexity})
            → Source: {evidence trail from ticket}
     CR-002: {title} ({complexity})
            → Source: {evidence trail from ticket}
     ...
   ```

   If any CR has `dat_file_warning: true`:
   ```
   NOTE: CR-{NNN} targets hab dwelling base rates, which live in external
   DAT files -- NOT in VB code. This change is outside the plugin's scope.
   I'll flag it in the summary but won't attempt to edit DAT files.
   ```

3. Update manifest:
   - `cr_count: {N}`
   - `change_requests:` with each CR ID and status `PENDING`
   - `ticket_ref:` if extracted from input
   - `phase_status.intake.status: "completed"`
   - `phase_status.intake.summary: "Understanding confirmed, {N} CRs parsed"`
   - `updated_at: "{now}"`
   - Append any developer Q&A to `developer_decisions`

**Handoff validation (Intake → Understand):**
Run validate_handoff to ensure Intake produced valid artifacts before proceeding:
```bash
{python_cmd} {plugin_root}/validators/validate_handoff.py "{workstream_dir}" intake
```
If the result contains `"passed": false`, STOP and show the findings to the developer.
The most common failure is malformed `parsed/change_requests.yaml` (missing CR fields).

**If the developer says "I forgot to mention X" AFTER intake:** Add the new
information to `input/source.md`, re-launch the Intake agent (or launch a
supplemental run). Create additional CRs and update the manifest accordingly.

---

### Step 1.5: UNDERSTAND

**Manifest update:** Set `phase_status.understand.status: "in_progress"`,
`updated_at: "{now}"`

**Launch the Understand agent** using the Agent Launch Protocol:

```
Agent:  understand
Input:  parsed/change_requests.yaml,
        .iq-workstreams/config.yaml,
        .iq-workstreams/paths.md,
        .iq-workstreams/codebase-profile.yaml
Output: analysis/code_understanding.yaml
```

The Understand agent reads `{plugin_root}/agents/understand.md` and autonomously:
- Uses the vb-parser tool to parse target .vbproj files and VB.NET source code
- Traces CalcMain calculation flow and matches CRs to exact functions
- Reads actual code to build function understanding blocks with branch trees
- Identifies files to copy, blast radius, shared module impacts
- Resolves ambiguous targets (asks developer when multiple candidates exist)
- Produces a single comprehensive code understanding artifact

**After the agent completes:**

1. Read `analysis/code_understanding.yaml` to verify the results.

2. Show the developer what was discovered:

   ```
   Code Understanding Complete:
     CR targets resolved: {N}/{total}
     Functions analyzed: {N} across {N} files
     Files to copy: {N}
     Blast radius: {N} LOBs affected
   ```

3. Update manifest:
   - `phase_status.understand.status: "completed"`
   - `phase_status.understand.summary: "{N}/{total} CRs resolved, {N} functions analyzed"`
   - `updated_at: "{now}"`
   - Append any developer Q&A to `developer_decisions`

**Handoff validation (Understand → Plan):**
Run validate_handoff to ensure Understand produced valid artifacts before proceeding:
```bash
{python_cmd} {plugin_root}/validators/validate_handoff.py "{workstream_dir}" understand
```
If the result contains `"passed": false`, STOP and show the findings to the developer.
The most common failure is missing `analysis/code_understanding.yaml` or empty CR targets.

**If Understand fails** (parser error, CalcMain not found, .vbproj unreadable):
The parser is required for v0.4.0 — there is no fallback. Log the error, set
`phase_status.understand.status: "failed"`, and STOP with an error message:
```
ERROR: Understand agent failed: {error}
The vb-parser tool is required. Check that vb-parser.exe exists at the path
specified in paths.md and that target files are accessible.
```

---

### Step 2: PLAN

**Manifest update:** Set `phase_status.plan.status: "in_progress"`,
`updated_at: "{now}"`

**Launch the Plan agent** using the Agent Launch Protocol:

```
Agent:  plan
Input:  analysis/code_understanding.yaml,
        parsed/change_requests.yaml,
        .iq-workstreams/config.yaml,
        .iq-workstreams/paths.md,
        .iq-workstreams/pattern-library.yaml
Output: analysis/intent_graph.yaml,
        plan/execution_plan.md, plan/execution_order.yaml,
        execution/file_hashes.yaml
```

The Plan agent reads `{plugin_root}/agents/plan.md` and autonomously:
- Breaks change requests into intents grounded in the code understanding
- Builds the intent graph with dependencies and strategy hints
- Orders operations bottom-to-top within each file (prevents line drift)
- Groups operations into readable phases with dependency ordering
- Computes risk level (LOW/MEDIUM/HIGH)
- Generates the human-readable execution plan and machine-readable order

The Plan agent has NO developer interaction — it is fully automated.

**After the agent completes:**

1. Update manifest (NOTE: do NOT set `state: "PLANNED"` yet — that happens after
   the pre-Gate-1 validation in step 2):
   - `phase_status.plan.status: "completed"`
   - `phase_status.plan.summary: "{N} phases, {risk} risk"`
   - `updated_at: "{now}"`

2. In team mode: TeamDelete() to clean up the analysis team.

3. **PRE-GATE-1 VALIDATION — Copy-First Check:**

   Before presenting the plan, the orchestrator MUST verify that file copies are
   accounted for. This catches the C2 bug (edits applied to old-dated files):

   a. Parse each target .vbproj (from footprint) and extract all `<Compile Include>`
      Code/ file references with their 8-digit dates.
   b. If ANY Code/ file reference has a date older than the target version folder date,
      check `analysis/code_understanding.yaml` and verify the relevant CR entry has
      `needs_copy: true` with `source_file` (old-dated path) and `target_file` (new-dated path)
      — verify the old-dated file appears as a `source_file`.
   c. If old-dated files are referenced but `code_understanding.yaml` is missing copy info
      (no `needs_copy`/`source_file`/`target_file` for the affected CRs), **STOP — do not present Gate 1**:
      ```
      ERROR: .vbproj references old-dated Code/ files but no copy plan exists:
        {file} (date: {old_date}, target: {target_date})

      The Understand agent should have set needs_copy/source_file/target_file in code_understanding.yaml.
      Re-running analysis pipeline to fix this...
      ```
      Then re-run the **Understand → Plan** pipeline (both agents, not just
      Understand) with the Understand agent receiving an additional prompt:
      `"CRITICAL: .vbproj references old-dated files. You MUST set needs_copy/source_file/target_file in code_understanding.yaml for affected CRs."`
      The Plan agent must re-run because its outputs (intent_graph.yaml,
      execution_plan.md) were built on the incomplete Understand output and are now stale.
      After re-run, re-validate. If still missing after 2 re-runs (i.e., the Understand
      agent has now run 3 times total), present the error to the developer and ask how to proceed.
   d. If all Code/ file dates match the target date (or `code_understanding.yaml` has
      complete copy info for all affected CRs), proceed to step 3b.

3b. **PRE-GATE-1 VALIDATION — Symbol Reference Check:**

   Scan the Plan agent's output for any code snippets that introduce NEW symbols
   (constants, enums, function calls, Case values) that don't appear in the
   original code. This catches hallucinated references before the developer sees
   them. Pattern extrapolation applies to ALL symbol types, not just constants.

   a. Read `plan/execution_plan.md` (which contains before/after code
      snippets). For each intent section, extract these symbol categories:

      **Constants & enums:** `Cssi.ResourcesConstants.MappingCodes.*`,
      `ResourcesConstants.*`, all-caps constant names (`DISCOUNT_*`, etc.).

      **Function/Sub calls:** Any function or Sub call in "after" code that does
      NOT appear in the corresponding "before" code. Extract the function name
      from patterns like `FunctionName(...)` or `Call SubName(...)`.

      **Case string values:** Any `Case "..."` string in "after" code that does
      NOT appear in "before" code. Numeric Case values (e.g., `Case 7500`) are
      exempt — these are typically new tiers specified in the ticket.

   b. For each extracted symbol, check if it exists in the codebase using Grep:
      - Constants: search source file + `ResourceID.vb` files
      - Function calls: search carrier root for `Function {name}` or `Sub {name}`
      - Case strings: search carrier root for the string value

   c. If a symbol is NOT found anywhere in the codebase:
      ```
      WARNING: Unresolved symbol in plan — may be hallucinated:
        {symbol_name} ({symbol_type}) in intent {intent_id}
        Not found in codebase.
        The Plan agent may have extrapolated this from a pattern in the file.

      Review this carefully at Gate 1.
      ```
      Add the warning to `plan/execution_plan.md` in the Warnings section.
      Do NOT block Gate 1 — the developer may confirm it's valid. But surface
      it prominently.

4. Validation passed.

   **Handoff validation (Plan → Execute):**
   Run validate_handoff to ensure Plan produced valid artifacts:
   ```bash
   {python_cmd} {plugin_root}/validators/validate_handoff.py "{workstream_dir}" plan
   {python_cmd} {plugin_root}/validators/validate_handoff.py "{workstream_dir}" planner
   ```
   If either result contains `"passed": false`, STOP and show the findings. The most
   common failures are: missing intents in `intent_graph.yaml`, missing
   `execution_order.yaml`, or missing `file_hashes.yaml`.

   Update manifest: `state: "PLANNED"`, `updated_at: "{now}"`.

4b. **INDEPENDENT CODE REVIEW — Cross-Model or Self-Review**

   An independent reviewer reads the actual VB.NET source code from scratch,
   traces the calculation flow, and verifies the plan is correct. This catches
   errors that the pipeline's sequential reasoning would miss — missed subtotals,
   removed function references, incomplete coverage.

   **Why this exists:** Claude's pipeline builds understanding incrementally
   (Intake → Understand → Plan). Each agent passes
   findings to the next. If an early agent misunderstands something (wrong function,
   missed subtotal, overlooked caller), that error propagates through all agents.
   An independent review — reading the code fresh with zero inherited assumptions —
   breaks the error propagation chain.

   **4b.0 Choose the reviewer:**

   Read the `codex` value from paths.md (already loaded in Check 1).
   If the value is a valid path (not "NOT FOUND"), Codex CLI is available.

   - **If codex path is valid:** Use GPT-5.4 via Codex CLI (cross-model review).
     Two different models with different training data catch different things.
   - **If codex is NOT found:** Spawn a Claude sub-agent as an independent
     reviewer. The sub-agent gets a fresh context window with NO pipeline
     artifacts — only the plan, the ticket, and the raw source files. It must
     read the code and trace the logic from scratch.

   **4b.1 Build the review prompt:**

   Read these files and assemble them into a single markdown prompt:
   - `plan/execution_plan.md` — what Claude's pipeline plans to do
   - `plan/execution_order.yaml` — the machine-readable execution plan
   - `parsed/ticket_understanding.md` — what the ticket asks for
   - `parsed/requests/cr-*.yaml` — the extracted change requests
   - The actual source files listed in the execution plan (the VB.NET files being modified)

   Write the assembled prompt to `plan/cross_review_prompt.md`:

   ```markdown
   # Independent Code Review Request

   You are an independent code reviewer. A separate AI system has analyzed a
   support ticket and produced an execution plan for modifying a VB.NET rating
   engine codebase. Your job is to independently verify the plan is correct by
   reading the actual code yourself.

   DO NOT trust the plan blindly. The plan may be wrong. Read the code.

   ## Your Task

   1. Read the TICKET UNDERSTANDING below to know what changes are requested
   2. Read the EXECUTION PLAN below to see what the other system plans to do
   3. **READ THE ACTUAL SOURCE FILES.** This is the critical step:
      - Open CalcMain.vb and trace the full calculation flow
      - For each function the plan targets, read the ENTIRE function body
      - Read the CALLER of each target function — trace what happens to the
        return value after the call
      - Read any RELATED functions (subtotals, accumulators, secondary calcs)
      - Read the .vbproj to understand which files are compiled together
   4. For each planned change, verify:
      a. Is the correct function targeted? (trace CalcMain → target function)
      b. Are ALL affected values covered? (check for subtotals, accumulators,
         secondary calculations that use the same values)
      c. Does the caller properly use the return value? (no post-processing
         overwrites, no unconditional reassignment after the call)
      d. Are there side effects? (other functions that read the changed values,
         variables that accumulate the result, Select Case branches that route
         based on the value)
      e. Will any existing function calls or references be broken?
      f. Are ALL lines that need changing actually in the plan? (count the
         Array6 lines, count the Case branches, compare to the plan)
   5. Look for GAPS — things the plan should do but doesn't:
      a. Missing subtotal/accumulation updates
      b. Missing related functions (if liability changes, check extension too)
      c. Missing resource ID or constant references
      d. Values that flow to other calculations not covered by the plan
      e. Functions that are called from the target but whose output isn't
         accounted for in the plan

   ## Codebase Structure

   This is a TBW/IntelliQuote manufactured rating engine:
   - Each province has LOB folders (Home, Auto, Condo, etc.) with dated
     version subfolders (YYYYMMDD)
   - Code/ files are shared across versions — only changed files get new
     dated copies. The .vbproj references Code/ files via relative paths.
   - Habitational LOBs (Home, Condo, Tenant, FEC, Farm, Seasonal) share
     mod_Common_{Prov}Hab files — one edit affects ALL hab LOBs
   - Array6() is a rate value function (accepts 1-14+ args, not just 6).
     It is a rate value ONLY when assigned to a variable (LHS of `=`).
     When passed as argument to another function, it is NOT a rate value.
   - CalcMain.vb (TotPrem) is the top-level flow — it dispatches to
     sub-functions that compute rates, factors, premiums
   - Select Case blocks contain factor tables with Case values and assignments
   - Const declarations hold base rates and fixed values

   ## TICKET UNDERSTANDING

   {content of parsed/ticket_understanding.md}

   ## CHANGE REQUESTS

   {content of each cr-*.yaml}

   ## EXECUTION PLAN

   {content of plan/execution_plan.md}

   ## SOURCE FILES TO REVIEW

   {for each unique source_file in execution_order.yaml, include the file path}

   READ EACH FILE. Trace the calculation flow end-to-end. Verify every function
   the plan touches and every function that USES the output of those functions.

   ## Output Format

   Write your review as Markdown with these exact sections:

   ### VERIFIED (plan is correct for these items)
   - {item}: {why it's correct, with file:line references to the code you read}

   ### CONCERNS (potential issues found)
   - {concern}: {what you found in the code, with file:line references}

   ### GAPS (things the plan misses)
   - {gap}: {what should be added and why, with file:line references showing
     the code that was overlooked}

   ### FUNCTION TRACE
   For each function the plan modifies, show the call chain you traced:
   - CalcMain → {function_A} → {function_B} (target) → return value used in {where}

   ### VERDICT
   One of: APPROVE / CONCERNS / REVISE
   {brief justification with the most important finding}
   ```

   **4b.2 Run the reviewer:**

   **PATH A — Codex CLI (cross-model review):**

   ```bash
   codex exec \
     -m "gpt-5.4" \
     -c 'reasoning.effort="xhigh"' \
     --full-auto \
     --ephemeral \
     -C "{carrier_root}" \
     -o "{workstream_dir}/plan/cross_review.md" \
     "$(cat {workstream_dir}/plan/cross_review_prompt.md)"
   ```

   Flags explained:
   - `-m "gpt-5.4"` — latest frontier model with strongest reasoning
   - `-c 'reasoning.effort="xhigh"'` — maximum thinking depth
   - `--full-auto` — never ask for permissions, auto-approve all file reads
     and shell commands in a sandboxed environment (Codex equivalent of YOLO
     mode). The reviewer needs to freely read files, run `find`, `grep`, etc.
     without getting stuck on permission prompts.
   - `--ephemeral` — no session persistence (fresh context every time)
   - `-C "{carrier_root}"` — working directory is the carrier root so Codex
     can navigate and read all VB.NET source files independently
   - `-o` — write the final response as markdown to a file we read back

   **PATH B — Claude sub-agent (self-review fallback):**

   If Codex is not found, launch a Claude sub-agent using the Agent tool:

   ```
   Agent(
     description: "Independent plan review",
     prompt: "{content of plan/cross_review_prompt.md}",
     subagent_type: "general-purpose"
   )
   ```

   The sub-agent gets a FRESH context window — it has never seen the pipeline's
   intermediate artifacts (Understand output, code understanding).
   It only sees the plan, the ticket, and the raw source files. Its job is to
   read the actual code at the highest reasoning level and trace the logic
   independently — the same thing Codex would do.

   Write the sub-agent's response to `plan/cross_review.md`.

   **Timeout (both paths):** Allow up to 10 minutes. If the reviewer times out:
   ```
   [Independent Review] Reviewer did not complete within timeout.
   Proceeding without independent review. Run /iq-plan again to retry.
   ```
   Do NOT block the pipeline on reviewer failure.

   **4b.3 Incorporate findings:**

   Read `plan/cross_review.md`. All output is markdown. Parse the verdict:

   **APPROVE:** Log it and proceed. Include a note in the plan:
   ```
   Independent Review: {GPT-5.4 | Claude sub-agent} independently verified
   this plan. No concerns found.
   ```

   **CONCERNS:** Read each concern. For each one:
   1. Investigate independently — read the file and line the reviewer references
   2. If the concern is valid: add it to `plan/execution_plan.md` in a new
      "Independent Review Findings" section, and add to the plan's warnings
   3. If the concern is NOT valid (reviewer misread the code): note it as
      "reviewed and dismissed" with a brief reason

   **REVISE:** Read each gap the reviewer identified. For each one:
   1. Investigate independently — trace the code path described
   2. If the gap is real (e.g., missing subtotal update, removed function ref):
      - Record it in manifest.yaml → `independent_review_findings`
      - Add a prominent warning to `plan/execution_plan.md`:
        ```
        INDEPENDENT REVIEW — GAP FOUND:
          {description of what was found}
          Source: {file}:{line}
          Impact: {what would happen if this is not addressed}
        ```
      - Do NOT automatically re-run the pipeline. Present the finding to the
        developer at Gate 1 and let them decide
   3. If the gap is not real: note "reviewed and dismissed" with reason

   **4b.4 Write the review section to the plan:**

   Append an "Independent Review" section to `plan/execution_plan.md`. This
   section MUST be markdown formatted:

   ```markdown
   ---
   ## Independent Review ({reviewer_name})

   An independent reviewer ({GPT-5.4 via Codex | Claude sub-agent}) read the
   source code from scratch, traced the calculation flow, and verified the plan.

   **Verdict:** {APPROVE | CONCERNS | REVISE}

   ### Function Traces
   {the FUNCTION TRACE section from the review — shows the call chains verified}

   ### Findings
   {list of valid concerns/gaps with file:line code references}

   ### Dismissed
   {list of concerns investigated and found not applicable, with reasons}
   ```

   Also write the raw review output to `plan/cross_review.md` (already done
   by the reviewer). This preserves the full independent analysis for audit.

5. Read `plan/execution_plan.md` and present it to the developer at Gate 1.

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

Phase 1: {title} (intent-{NNN}) [{capability}]
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

Phase 1: {title} (intent-{NNN}) [{capability}]
  {details}

Phase 2: {title} (intent-{NNN}) [{capability}, depends on Phase 1]
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
3. Set manifest phase_status.gate_1.summary: "Developer approved all {N} CRs"
4. Set manifest updated_at: "{now}"
5. Present the "After Plan Approval" message (Section 9)
```

**IMPORTANT:** /iq-plan ends here. Execution is handled by `/iq-execute` in a
fresh context window. Do NOT attempt to run modifier agents.

**REJECT** (developer says "no", "wrong", "that's not right", "reject",
"change X to Y", "the value should be Z"):

**HARD RULE — AGENT OUTPUT IMMUTABILITY:**
The orchestrator MUST NEVER directly edit files in these directories:
- `plan/` — owned by Plan agent
- `analysis/` — owned by Understand and Plan agents
- `parsed/` — owned by Intake agent

These files are **agent outputs**. The only way to change them is to re-run
the agent that produced them. Directly editing these files breaks the contract
between agents and creates inconsistent state. If you feel tempted to "just
fix the value in the YAML," STOP — use the structured update loop below.

**Structured Update Loop:**

```
1. CAPTURE the developer's correction:
   a. Record it in manifest.yaml → developer_decisions:
      - phase: "gate_1"
        action: "correction"
        timestamp: "{now}"
        feedback: "{developer's exact words}"
        correction_type: "value" | "target" | "scope" | "approach"
        iteration: {N}  # 1-based, increments on each rejection

2. DETERMINE which agent to re-run based on correction_type:

   ┌─────────────────────────────────────────────────────────┐
   │ Correction Type    │ Re-run From     │ Example          │
   ├────────────────────┼─────────────────┼──────────────────┤
   │ value              │ Plan            │ "Territory 1     │
   │ (rate/factor wrong)│                 │  should be .0935"│
   ├────────────────────┼─────────────────┼──────────────────┤
   │ target             │ Understand →    │ "Wrong function, │
   │ (wrong file/func)  │ Plan            │  it's in SetDed" │
   ├────────────────────┼─────────────────┼──────────────────┤
   │ scope              │ Intake →        │ "Also change the │
   │ (add/remove CRs)   │ full pipeline   │  NB deductibles" │
   ├────────────────────┼─────────────────┼──────────────────┤
   │ approach           │ Understand →    │ "The whole        │
   │ (strategy wrong)   │ Plan            │  approach is      │
   │                    │                 │  wrong"           │
   └─────────────────────────────────────────────────────────┘

3. RE-RUN the identified agent (and ALL downstream agents):
   a. Pass the developer_decisions entry to the agent's prompt
   b. The agent reads developer_decisions and incorporates the feedback
   c. The agent produces NEW output files (overwriting old ones)
   d. Downstream agents run on the updated outputs

4. RE-PRESENT the revised plan at Gate 1:
   "Revised plan (iteration {N}) — changes based on your feedback:
    - {summary of what changed}
    Approve, reject, or keep asking."

5. ESCALATION: If the same correction fails 3 times (iteration >= 3):
   "I've tried to incorporate your correction 3 times but the result
    still doesn't match your intent. Options:
      1. Tell me the EXACT change (file, line, old value → new value)
         and I'll apply it directly in the plan
      2. Start fresh with /iq-plan
      3. Try one more iteration"
   On option 1: ONLY THEN may the orchestrator directly edit plan files,
   and MUST log this as correction_type: "manual_override" in
   developer_decisions with the developer's exact specification.
```

Stay at GATE 1 — wait for approval again.

**PARTIAL APPROVE** (developer says "approve CR-001 but reject CR-003",
"skip the Elite Comp changes", "do everything except the deductible"):

```
1. Parse which CRs are approved and which are rejected
2. Run dependency validation (see Section 7)
3. If dependencies block the requested split: inform and offer alternatives
4. If dependencies are OK:
   - Mark approved CRs for execution
   - Mark rejected CRs as DEFERRED in manifest
   - Proceed to Step 5 with only approved intents
   - Tell developer: "When ready for the deferred CRs, run /iq-plan
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

## 7. Partial Approval Logic

When the developer approves some CRs and rejects others at Gate 1, the
orchestrator must validate dependencies before proceeding.

### Dependency Validation Algorithm

```
1. Parse the developer's response to identify:
   - approved_crs: list of CR IDs to execute
   - rejected_crs: list of CR IDs to defer

2. For each approved CR:
   a. Look up all its intents in intent_graph.yaml
   b. For each intent, check its depends_on list
   c. Resolve each dependency to its parent CR
   d. If any dependency's CR is in rejected_crs:
      -> BLOCK: cannot approve this CR without its dependency

3. If any blocks found:

   Cannot approve CR-{NNN} without CR-{NNN}.
   CR-{NNN} ({title}) depends on CR-{NNN} ({title}).

   Options:
     1. Approve both CR-{NNN} and CR-{NNN}
     2. Reject both CR-{NNN} and CR-{NNN}
     3. Show me the intent graph

4. If no blocks:
   a. Filter execution_order.yaml to include only approved CR intents
   b. Maintain bottom-to-top ordering within each file
   c. Mark approved CRs as APPROVED in manifest
   d. Mark rejected CRs as DEFERRED in manifest
   e. Set state: PLANNED
   f. Set phase_status.gate_1.status: "approved"
   g. Set phase_status.gate_1.summary: "Partial approval: {N} CRs approved, {M} deferred"
   h. Tell developer:
      "Plan approved for CR(s): {approved list}.
       CR(s) deferred: {deferred list}.
       You can /clear and run /iq-execute to apply the approved changes.
       When ready for the deferred CRs, run /iq-plan to pick them up."
```

### Resume After Partial Approval

When the developer runs `/iq-plan` later:

```
1. Resume detection finds the workflow with DEFERRED CRs
2. Present: "Found workflow {id} with {N} deferred CR(s): {list}"
3. Developer provides updated information for rejected CRs
4. Pipeline re-runs from Understand (for the deferred CRs only)
5. New plan includes only the deferred intents
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

### Step 1: Classify the Question

Before answering, classify what kind of context the question needs:

| Category | Examples | How to Handle |
|----------|----------|---------------|
| **TICKET-ONLY** | "What would the total be after the fix?", "What did comment 3 say?", "How many CRs?" | Answer directly from ticket data, manifest, agent outputs already produced. No agent needed. |
| **STATUS** | "What's the status?", "Where are we?", "What's left?" | Read manifest.yaml and summarize. No agent needed. |
| **CODE-LEVEL** | "Show me how All Perils is currently calculated", "What does the function look like?", "How does the code handle high theft?" | **Spawn investigation sub-agent** (see below). |
| **CROSS-REFERENCE** | "Does this affect other LOBs?", "What other files reference this module?", "Which projects use this function?" | **Spawn investigation sub-agent** (see below). |
| **ADDENDUM** | "I forgot to mention, also change X" | Not a question — treat as addendum (see below). |

**Rule of thumb:** If the answer requires reading VB.NET source files, .vbproj
files, or searching the codebase, spawn a sub-agent. If the answer is in the
ticket data or manifest, answer directly.

### Step 2a: Direct Answer (TICKET-ONLY, STATUS)

For simple questions, answer inline:

```
1. Note the current workflow position (state, gate, step)
2. Read the relevant data (ticket_understanding.md, manifest.yaml, agent outputs)
3. Compute or summarize the answer
4. Present the answer
5. Return to the current position:

   "Back to {current context}. {prompt for next action}"
```

### Step 2b: Investigation Sub-Agent (CODE-LEVEL, CROSS-REFERENCE)

For questions that need codebase access, spawn a focused sub-agent via the
Agent tool. This keeps the orchestrator's context clean and gives the sub-agent
full access to grep, read, and search the codebase.

**Build the sub-agent prompt with this template:**

```
You are an investigation sub-agent for the IQ Update plugin. Answer the
developer's question using the codebase.

## Question
{developer's question}

## Current Context
- Carrier: {carrier_name} ({carrier_prefix})
- Province: {province_code} ({province_name})
- LOB: {lob}
- Target version: {effective_date}
- Carrier root: {carrier_root}

## Ticket Understanding (Summary)
{2-3 sentence summary of the ticket — what change is being made and why}

## Change Requests
{List CR IDs and titles}

## What to Search
- Pattern Library: {carrier_root}/.iq-workstreams/pattern-library.yaml
  (Grep for relevant function names — do NOT load the whole file)
- Codebase Profile: {carrier_root}/.iq-workstreams/codebase-profile.yaml
  (Grep for glossary terms, dispatch tables — do NOT load the whole file)
- Province Code/ files: {carrier_root}/{province}/Code/
- Target .vbproj: {path to .vbproj if known}

## Instructions
1. Search the Pattern Library and Codebase Profile for relevant functions
2. Read the actual source code to find the answer
3. Report back with:
   - What you found (file, function name, line numbers)
   - The relevant code snippet (keep it focused, not the whole file)
   - How it relates to the developer's question
4. Do NOT modify any files. Read-only investigation.
```

**After the sub-agent returns:**

1. Present the answer to the developer
2. **Save to developer_decisions** in manifest.yaml:
   ```yaml
   - phase: "{current_phase}"
     question: "{developer's question}"
     answer: "{summary of what the sub-agent found}"
     source: "investigation_subagent"
     timestamp: "{now}"
   ```
   This is important — downstream agents (Understand, Plan) will see this
   finding and use it instead of re-discovering the same information.
3. Return to the current position:
   ```
   Back to {current context}. {prompt for next action}
   ```

### Common Investigation Queries

| Developer Says | Category | What Happens |
|----------------|----------|-------------|
| "What would the total be after the fix?" | TICKET-ONLY | Compute from ticket values directly |
| "What did comment 3 say?" | TICKET-ONLY | Read ticket_understanding.md or llm-context.md |
| "How many CRs are there?" | STATUS | Read manifest.yaml |
| "Show me the current file" | CODE-LEVEL | Sub-agent reads and displays with line numbers |
| "Show me {function_name}" | CODE-LEVEL | Sub-agent finds function in codebase, shows code |
| "How does the code currently calculate this?" | CODE-LEVEL | Sub-agent traces the logic in VB source |
| "Does this affect Farm?" | CROSS-REFERENCE | Sub-agent checks all .vbproj files for shared module refs |
| "What other files reference this?" | CROSS-REFERENCE | Sub-agent runs reverse lookup |
| "How many territories does {Province} {LOB} have?" | CODE-LEVEL | Sub-agent searches the relevant mod file |
| "What did the previous version look like?" | CODE-LEVEL | Sub-agent finds and displays prior-dated file |
| "Show me the diff so far" | CODE-LEVEL | Sub-agent compares snapshot to current file state |
| "I forgot to mention, also change X" | ADDENDUM | Not a question — see addendum handling below |

### Addendum Handling ("I forgot to mention...")

If the developer adds new changes mid-workflow:

```
If before Gate 1 (state: ANALYZING or PLANNED):
  1. Add new CRs to the change requests
  2. Re-run from Understand with the expanded set
  3. Re-run Plan agent
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
manifest.yaml              — state: PLANNED, all CRs, phase_status, developer_decisions
parsed/change_requests.yaml — structured change requests
parsed/requests/cr-*.yaml  — individual CR details
analysis/intent_graph.yaml — intents with target regions and dependencies
analysis/code_understanding.yaml — code analysis, function understanding, blast radius, file copy info (needs_copy/source_file/target_file per CR)
analysis/developer_choices.yaml — resolved ambiguities (if any)
execution/file_hashes.yaml — TOCTOU baseline
plan/execution_plan.md     — human-readable approved plan
plan/execution_order.yaml  — machine-readable execution order
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
2. Re-analyze from current state (re-run Understand)
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

# -- Change Request Tracking -------------------------------------------------
cr_count: 3
change_requests:
  cr-001:
    title: "Increase base rates by 5%"
    complexity: "SIMPLE"
    status: "COMPLETED"                        # PENDING | ANALYZING | PLANNED |
                                               # APPROVED | EXECUTING | COMPLETED |
                                               # FAILED | DEFERRED | OUT_OF_SCOPE |
                                               # DISCARDED
    intents:
      intent-001: "COMPLETED"                  # PENDING | IN_PROGRESS | COMPLETED |
                                               # FAILED | DEFERRED
  cr-002:
    title: "Change $5000 deductible factor"
    complexity: "SIMPLE"
    status: "EXECUTING"
    intents:
      intent-002: "IN_PROGRESS"

  cr-003:
    title: "Add Elite Comp coverage type"
    complexity: "COMPLEX"
    status: "PENDING"
    intents:
      intent-003: "PENDING"
      intent-004: "PENDING"
      intent-005: "PENDING"
      intent-006: "PENDING"

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
    summary: "3 CRs parsed, no DAT warnings"
  understand:
    status: "completed"                           # pending | in_progress | completed | failed
    summary: "3/3 CRs resolved, 3 files, 6 LOBs blast radius, 20 functions analyzed"
  plan:
    status: "completed"
    summary: "7 intents in execution plan, bottom-to-top in 3 files, no partial approval issues"
  gate_1:
    status: "approved"                            # pending | approved | rejected | revision_N
    summary: "Developer approved all 3 CRs, no changes requested"
  # --- Phases below managed by /iq-execute and /iq-review ---
  # --- Included here for complete manifest schema reference ---
  change_engine:
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
#   phase: "understand"
#   question: "SetDisSur_Deductible has farm and non-farm paths. Which is the target?"
#   answer: "Farm path"
# - timestamp: "2026-01-15T11:30:00Z"
#   phase: "understand"
#   question: "CR-003 has mixed rounding (42 banker + 6 decimal lines). Proceed?"
#   answer: "Yes, proceed with per-line rounding"

# -- Execution Mode ----------------------------------------------------------
execution_mode: "team"                            # "team" (agent team, default) |
                                                  # "sequential" (sub-agents)

# -- Error Log ---------------------------------------------------------------
error_log: []
# Example entries:
# - timestamp: "2026-01-15T11:20:00Z"
#   operation: "intent-003"
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
                                                |
                                                v
                                          GATE_1_REJECTED
                                          (developer re-runs /iq-plan)

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
                                  |
                                  v
                            GATE_2_REJECTED
                            (re-enters Change Engine phase)

Special states:
  DISCARDED        -- developer cancelled at any point
  GATE_1_REJECTED  -- RESERVED (not currently produced — Gate 1 rejection uses revision loop at PLANNED)
  GATE_2_REJECTED  -- RESERVED (not currently produced — Gate 2 rejection uses rework at VALIDATING or back to PLANNED)
```

**Valid state transitions:**

| From | To | Who | How |
|------|----|-----|-----|
| (new) | CREATED | /iq-plan | Creates workflow |
| CREATED | ANALYZING | /iq-plan | Developer provides input |
| ANALYZING | PLANNED | /iq-plan | Plan agent completes, developer approves at Gate 1 |
| PLANNED | PLANNED | /iq-plan | Developer rejects at Gate 1 (revision loop) |
| PLANNED | GATE_1_REJECTED | /iq-plan | Developer rejects plan outright at Gate 1 |
| GATE_1_REJECTED | ANALYZING | /iq-plan | Developer re-runs /iq-plan with corrections |
| PLANNED | EXECUTING | /iq-execute | Execution team starts |
| EXECUTING | EXECUTED | /iq-execute | All operations complete |
| EXECUTING | EXECUTING | /iq-execute | Operation retry (self-correction) |
| EXECUTED | VALIDATING | /iq-review | Review team starts |
| VALIDATING | COMPLETED | /iq-review | Developer approves at Gate 2 |
| VALIDATING | VALIDATING | /iq-review | Rework + re-validate loop |
| VALIDATING | GATE_2_REJECTED | /iq-review | Developer rejects changes at Gate 2 |
| GATE_2_REJECTED | EXECUTING | /iq-execute | Re-enters Change Engine phase |
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
3. PARTIAL APPROVE (mentions specific CRs)
4. APPROVE / REJECT (clear decision)
5. INVESTIGATE (questions)
6. STATUS (status queries)

### Action Mapping Table

| Category | Developer Phrases | Plugin Action | State Change? |
|----------|------------------|---------------|:------------:|
| APPROVE | "approve", "approved", "yes", "looks good", "LGTM", "go ahead", "proceed", "do it", "ship it", "OK", "fine", "good", "accept" | Approve plan at Gate 1, set state: PLANNED | YES |
| REJECT | "no", "wrong", "reject", "that's not right", "incorrect", "bad", "nope" | Ask what to change, enter revision loop | NO (stays at gate) |
| CORRECT | "change X to Y", "the value should be Z", "actually it's 0.0935", "territory 1 is wrong" | Accept correction, revise plan | NO (stays at gate) |
| PARTIAL APPROVE | "approve CR-001 but reject CR-003", "skip the Elite Comp", "do everything except...", "just do the base rates" | Split CRs into approved/deferred (with dependency validation) | YES (for approved) |
| INVESTIGATE | "show me...", "what does...", "how many...", "does this affect...", "is there...", any question mark | Answer without changing state, return to current position | NO |
| STATUS | "what's the status?", "where are we?", "what's left?", "progress", "how far along" | Show current state, CR progress, next action | NO |
| ADDENDUM | "I forgot to mention...", "also change...", "one more thing...", "add this too" | Add to change spec, re-run from appropriate agent | MAYBE |
| DISCARD | "never mind", "cancel", "throw this away", "forget it", "abort", "stop" | Set state to DISCARDED, inform developer | YES |
| RESUME DEFERRED | "pick up the deferred CRs", "do the rest", "continue with CR-003" | Re-enter pipeline for deferred CRs | YES |

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
   state files (manifest.yaml, change_requests.yaml, execution_order.yaml) when needed.
2. **Between Gate 1 and Gate 2**, read `plan/execution_order.yaml` for the plan —
   do not try to recall it from earlier in the conversation.
3. **One agent at a time.** When transitioning to the next agent, read its .md file
   fresh. Do not carry forward the previous agent's detailed instructions.

### Manifest Update Protocol (CRITICAL for resume)

After EVERY agent completes, the orchestrator MUST update manifest.yaml:

1. **Update `phase_status`** for the completed phase:
   - Set `status` to "completed" (or "failed")
   - Write a 1-2 line `summary` capturing what happened
   - Example: `summary: "3 CRs parsed, no DAT warnings"`

2. **Append to `developer_decisions`** if the developer answered any questions:
   - Record the question, answer, phase, and timestamp
   - These are the ONLY record of conversational decisions
   - Example: `{phase: "understand", question: "Farm or non-farm path?", answer: "Farm"}`
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
how Steps 1-2 (Intake, Understand, Plan) are launched.
Change Engine workers and Reviewer always run inline regardless of this setting.

**Team mode (default):**

Launch analysis agents as an agent team. The orchestrator creates a team,
spawns one agent at a time as a teammate, and coordinates via SendMessage.
Each agent gets its own context window — the main window stays light.

```
Team lifecycle:
  1. TeamCreate(team_name="iq-{workstream-name}")
  2. TaskCreate: 3 tasks with sequential dependencies
     - "Run Intake agent"       (no blockers)
     - "Run Understand agent"   (blocked by Intake)
     - "Run Plan agent"         (blocked by Understand)
  3. For each task:
     a. Spawn teammate via Task tool (with team_name parameter)
     b. Monitor for messages:
        - "DEVELOPER_QUESTION: ..." → present to developer, relay answer
        - "AGENT_COMPLETE: ..."     → update manifest, shutdown agent
        - "AGENT_ERROR: ..."        → log error, present recovery options
     c. After agent completes: TaskUpdate(status="completed")
  4. After all 3 complete: TeamDelete()
  5. Proceed to Gate 1 with Plan agent's output
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
  For each agent (Intake, Understand, Plan):
    1. Launch via Task tool (no team_name)
    2. Agent runs autonomously, returns when done
    3. If agent returned pending_confirmation items:
       a. Present all pending items to developer in batch
       b. Write developer's choices to analysis/developer_choices.yaml
       c. Re-launch agent with "Read developer_choices.yaml" in prompt
    4. Read output files, update manifest
    5. Proceed to next agent
```

No inter-agent communication. Cheaper but the Understand agent's developer interaction
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
current state and CR progress.

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
{python_cmd} -c "import hashlib; print(hashlib.sha256(open('{filepath}','rb').read()).hexdigest())"
```

### Creating workflow directories
Use Bash with mkdir -p:
```bash
mkdir -p ".iq-workstreams/changes/{workstream-name}"/{input/attachments,parsed/requests,analysis,plan,execution/snapshots,verification,summary}
```

### Writing YAML files
Use the Write tool to write YAML files. Do NOT use Bash echo/cat.
After writing any YAML file (manifest.yaml, change_requests.yaml, etc.), validate it:
```bash
{python_cmd} -c "import yaml; yaml.safe_load(open('{filepath}')); print('YAML OK')"
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

The /iq-plan orchestrator launches these 3 analysis agents. Each agent's .md file
contains its complete interface contract, input/output schemas, execution steps,
and edge cases. The orchestrator does NOT read these files — the agents read them.

| Agent | File | When Called | What It Produces |
|-------|------|-------------|-----------------|
| Intake | `{plugin_root}/agents/intake.md` | Step 1 | `parsed/change_requests.yaml`, `parsed/requests/cr-NNN.yaml` |
| Understand | `{plugin_root}/agents/understand.md` | Step 1.5 | `analysis/code_understanding.yaml` |
| Plan | `{plugin_root}/agents/plan.md` | Step 2 | `analysis/intent_graph.yaml`, `plan/execution_plan.md`, `plan/execution_order.yaml`, `execution/file_hashes.yaml` |

The Change Engine is launched by `/iq-execute`.
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
    change_requests.yaml           <- Structured change requests
    requests/
      cr-001.yaml                  <- Individual change request details
      cr-002.yaml
      ...
  analysis/
    blast_radius.md                <- Full blast radius report
    code_understanding.yaml        <- Code analysis, function understanding, blast radius, file copy info (needs_copy/source_file/target_file per CR) (from Understand)
    intent_graph.yaml              <- Intents with target regions and dependencies (from Plan)
  plan/
    execution_plan.md              <- Human-readable plan (GATE 1 document)
    execution_order.yaml           <- Machine-readable ordered intents
  execution/
    operations_log.yaml            <- What was done: file, line, old -> new
    file_hashes.yaml               <- SHA256 hashes for TOCTOU protection
    snapshots/                     <- Pre-edit copies for self-correction
      mod_Common_SKHab20260101.vb.snapshot
      ...
  verification/
    validator_results.yaml         <- Results from all 8 validators
    traceability_matrix.md         <- CR -> file:line mapping
    diff_report.md                 <- Human-readable diff of all changes
    changes.diff                   <- Unified diff format
  summary/
    change_summary.md              <- Final summary for developer + SVN commit
```
