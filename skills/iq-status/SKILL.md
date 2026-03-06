---
name: iq-status
description: Dashboard and archive sweep -- displays all workstream statuses, next actions, overlap alerts, and optionally archives completed workstreams.
user-invocable: true
---

# Skill: /iq-status

## 1. Purpose & Trigger

Dashboard and archive sweep. Answers one question: **what do I do next?**

Scans all workstreams, groups by state, flags overlaps, detects staleness,
and runs an archive sweep on completed work. No changes to code files --
the only side effect is moving completed/discarded workstream directories
to `.iq-workstreams/archive/` and updating `archive/index.yaml`.

**Trigger:** Slash command `/iq-status`

---

## 2. Precondition Checks

Execute IN ORDER. If any fails, STOP and report.

### Check 1: Read paths.md (MANDATORY FIRST STEP)

Read `.iq-workstreams/paths.md`. This file contains all absolute paths you need:
`plugin_root`, `carrier_root`, `python_cmd`, agent spec paths, validator paths, etc.

If `paths.md` does not exist, STOP: `"ERROR: Run /iq-init first to initialize the plugin."`

Use the paths from this file for the entire command. Replace `.iq-update/` with `plugin_root`.

### Check 2: Config Exists

Verify `.iq-workstreams/config.yaml` exists. If missing:
```
ERROR: No config.yaml found. Run /iq-init first.
```

### Check 3: Config Is Readable

Read `.iq-workstreams/config.yaml` and confirm keys: `carrier_name`, `carrier_prefix`,
`root_path`, `provinces`. If any missing:
```
ERROR: config.yaml malformed -- missing "{key}". Run /iq-init again.
```

---

## 3. Main Logic

### Step 3.1: Archive Sweep

Before scanning active workstreams, run the archive sweep to clean up old
completions. This keeps the dashboard focused on actionable items.

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

If `.iq-workstreams/archive/index.yaml` does not exist, create it with:
```yaml
archived: []
```

**Report what was archived:**
```
Archived {N} workstream(s) (completed > 14 days ago):
  {workstream-id} -> archive/{YYYY-MM}/
  ...
```

If nothing archived, skip this message silently.

### Step 3.2: Scan Active Workstreams

```
1. List all subdirectories in .iq-workstreams/changes/
2. For each, read manifest.yaml
3. If manifest.yaml is missing or unparseable:
   - Log: "WARNING: Skipping {dir} -- corrupt or missing manifest."
   - Continue to next (do NOT crash the dashboard)
4. Collect all readable workstreams
```

### Step 3.3: Group by State

Classify each workstream:

**In-flight** (needs developer action):
- CREATED, ANALYZING, PLANNED, EXECUTING, EXECUTED, VALIDATING,
  GATE_1_REJECTED, GATE_2_REJECTED

**Terminal** (no action needed):
- COMPLETED, DISCARDED

### Step 3.4: Compute Next Action

For each in-flight workstream, derive the next action from state:

| State | Next Action |
|-------|-------------|
| CREATED | Run /iq-plan |
| ANALYZING | Run /iq-plan (will resume) |
| PLANNED | Run /iq-execute |
| EXECUTING | Run /iq-execute (will resume) |
| EXECUTED | Run /iq-review |
| VALIDATING | Run /iq-review (will resume) |
| GATE_1_REJECTED | Run /iq-plan (revise and re-plan) |
| GATE_2_REJECTED | Run /iq-execute (re-apply changes) |

### Step 3.5: Detect Staleness

Flag any workstream in EXECUTING state where `updated_at` is 3+ days ago:
```
WARNING: {workstream-id} has been EXECUTING for {N} days -- may be stale.
```

### Step 3.6: Cross-Check File Overlap

Compare all in-flight workstream pairs for file overlap:

```
1. For each in-flight workstream, read its footprint:
   - If footprint section exists: use footprint.code_files
   - Else fall back: collect target_folders paths + shared_modules file paths
2. For each pair (A, B) where A.index < B.index:
   - Compute intersection of code_files
   - If intersection is non-empty:
     a. Determine severity:
        - WARN: both are in CREATED/ANALYZING/PLANNED
        - HIGH: either is in EXECUTING/EXECUTED/VALIDATING
     b. Record: {workstream_A, workstream_B, files, severity}
```

### Step 3.7: Print Dashboard

Print the ASCII dashboard using the exact format below.

---

## 4. Dashboard Format

```
IQ STATUS  {YYYY-MM-DD HH:MM}
In-flight: {N} | Needs action: {N} | Overlaps: {N}

NEXT ACTION
  1) Run {command}   {workstream-id}   {state}  ({time ago})
  ...
  (sorted by priority: EXECUTED first, then PLANNED, then others)

WORKSTREAMS
  # | Workstream                     | Ticket | Scope            | State     | Overlap | Updated
  --+--------------------------------+--------+------------------+-----------+---------+--------
  1 | {workstream-id}                | {key}  | {prov} {lobs} {date} | {state} | {overlap ref} | {time ago}
  ...

{if overlaps exist:}
OVERLAP ALERT
  #{A} and #{B} both touch: {filename}
  {severity context -- e.g., "#{B} has been EXECUTING for 3 days -- may be stale."}

{if terminal workstreams exist (last 14 days):}
COMPLETED (last 14 days)
  {workstream-id}  {completed_date}  {svn rNNN or "no SVN"}
  ...
  ({N} older -- archived)
```

**Scope formatting:**

- Single LOB: `SK Home 20260101`
- Multiple LOBs: `SK Hab (6 LOBs) 20260101` -- collapse, don't list all 6
- If no LOBs parsed yet: `SK 20260101`

**Ticket column:**

- If `ticket.key` exists: show the key (e.g., `24778`, `DEVOPS-123`)
- If `ticket.mode == "adhoc"` or no ticket section: show `ADHOC`
- Backward compat: if no `ticket` section, show `ticket_ref` or `--`

**Time ago formatting:**

- < 1 hour: `{N}m ago`
- 1-23 hours: `{N}h ago`
- 1-6 days: `{N}d ago`
- 7+ days: `{date}`

---

## 5. Edge Cases

### No Workstreams

```
IQ STATUS  {YYYY-MM-DD HH:MM}

No active workstreams. Run /iq-plan to start one.
```

### Corrupt Manifest

Skip with warning, continue scanning others:
```
WARNING: Skipping {dir} -- manifest.yaml is corrupt or unreadable.
```

### Wide LOB Lists

Collapse to `{Prov} Hab ({N} LOBs)` instead of listing all LOBs individually.
Only expand if 3 or fewer LOBs.

### Many Completed Workstreams

Show at most 3 recent completions in the COMPLETED section. Count the rest:
```
(5 older -- archived)
```

### Old Manifests Without New Fields

Workstreams created before the ticket/footprint/lifecycle fields were added:
- `ticket` missing: show `ticket_ref` value or `--`
- `footprint` missing: fall back to `target_folders` + `shared_modules` for overlap
- `lifecycle` missing: use `updated_at` for archive age calculation

---

## 6. `--archived` Flag

When the developer runs `/iq-status --archived`, display the archive index
instead of (or in addition to) the active dashboard.

**How it works:**

1. Read `.iq-workstreams/archive/index.yaml`
2. If file doesn't exist: `"No archived workstreams yet."`
3. Display:

```
ARCHIVED WORKSTREAMS
  # | Workstream                        | Ticket | Completed  | SVN
  --+-----------------------------------+--------+------------+--------
  1 | {workstream-id}                   | {key}  | {date}     | {rNNN}
  2 | ...                               | ...    | ...        | ...
```

Sort by completed date, most recent first.

---

## 7. Implementation Notes

### Scanning workstreams

```bash
ls ".iq-workstreams/changes/"
```

Then Read each `manifest.yaml`. Parse YAML for state, province, lobs,
effective_date, updated_at, ticket, footprint, lifecycle, svn_revision.

### Computing "time ago"

```bash
{python_cmd} -c "
from datetime import datetime, timezone
then = datetime.fromisoformat('{updated_at}'.replace('Z','+00:00'))
now = datetime.now(timezone.utc)
delta = now - then
if delta.total_seconds() < 3600:
    print(f'{int(delta.total_seconds()//60)}m ago')
elif delta.total_seconds() < 86400:
    print(f'{int(delta.total_seconds()//3600)}h ago')
elif delta.days < 7:
    print(f'{delta.days}d ago')
else:
    print(then.strftime('%Y-%m-%d'))
"
```

### Archive directory creation

```bash
mkdir -p ".iq-workstreams/archive/{YYYY-MM}/{workstream-id}"
```

### Writing/updating index.yaml

Use Write tool. Validate after:
```bash
{python_cmd} -c "import yaml; yaml.safe_load(open('.iq-workstreams/archive/index.yaml')); print('YAML OK')"
```

### Context management

This skill runs in a FRESH context window. Read all state from disk.
No changes to code files -- only archive moves (completed/discarded workstreams)
and `archive/index.yaml` updates.
