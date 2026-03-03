---
name: iq-review
description: Validate all changes and produce a summary report. Runs 7 validators, generates diffs, and presents Gate 2 for developer approval.
user-invocable: true
---

# Skill: /iq-review

## 1. Purpose & Trigger

Run the RIGOROUS final review after /iq-execute has applied all modifications.
This is the third and final command in the plugin's workflow -- it validates
everything, generates comprehensive reports, and presents Gate 2 for developer
approval. The orchestrator launches the review agent team, runs all 7 validators,
produces diffs and traceability reports, and walks the developer through approval
or rework.

This skill runs in a FRESH context window. It knows nothing about /iq-plan or
/iq-execute except what is written in manifest.yaml and workstream files. Those
files ARE the memory.

**Trigger:** Slash command `/iq-review`

**State transition:** `EXECUTED` --> `VALIDATING` --> `COMPLETED`

---

## 2. Precondition Checks

Execute IN ORDER. If any fails, STOP and report.

### Check 1: Plugin Installed

Verify `.iq-update/CLAUDE.md` exists. If missing: `"ERROR: .iq-update/ plugin not installed."`

### Check 2: Config Exists

Verify `.iq-workstreams/config.yaml` exists. If missing: `"ERROR: Run /iq-init first."`

### Check 3: Config Is Readable

Read config.yaml, confirm keys: `carrier_name`, `carrier_prefix`, `root_path`, `provinces`.
If any missing: `"ERROR: config.yaml malformed -- missing {key}. Run /iq-init again."`

### Check 4: Find Executed Workstream

Scan `.iq-workstreams/changes/` for `manifest.yaml` where state is `EXECUTED` or `VALIDATING`.

- **NONE found:** Check other states and give appropriate guidance:
  - PLANNED: `"Run /iq-execute first."`
  - ANALYZING/CREATED: `"Run /iq-plan first."`
  - COMPLETED: `"Already completed. Run /iq-plan for a new ticket."`
  - No workflows: `"No workstreams found. Run /iq-plan to start."`
- **ONE found:** Use it. Show workflow_id, province, LOBs, date, state.
- **MULTIPLE found:** Present list, let developer choose.

### Check 5: Verify Required Files

Confirm these exist in the workstream directory:

```
From /iq-plan:  manifest.yaml, input/source.md, parsed/change_spec.yaml,
                parsed/srds/ (1+ files), analysis/operations/ (1+ files),
                plan/execution_plan.md, plan/execution_order.yaml
From /iq-execute: execution/operations_log.yaml, execution/file_hashes.yaml,
                  execution/snapshots/ (1+ .snapshot files)
```

If any missing: `"ERROR: Missing {file}. Run /iq-execute if needed."`

### Check 6: Verify Modified Files on Disk

Read `execution/file_hashes.yaml`. Confirm every listed file exists on disk.
If any missing: show which files, offer to check execution log or abort.

---

## 3. Resume Detection

### State: EXECUTED (Fresh Start)

Proceed to Section 4.

### State: VALIDATING (Resume)

Check which review artifacts exist: `verification/validator_results.yaml`,
`verification/diff_report.md`, `summary/change_summary.md`.

- **ALL exist AND file hashes match:** Skip to Gate 2 (Section 6).
  `"Previous review results still valid. Skipping to approval."`
- **Hashes changed:** `"Files changed since last review. Re-running full review."`
  Proceed to Section 4.
- **Artifacts incomplete:** Proceed to Section 4 (safer to re-run everything).

---

## 4. Launch Review Team

### Pre-Launch: Update Manifest

```yaml
state: "VALIDATING"
updated_at: "{now}"
phase_status:
  reviewer:
    status: "in_progress"
```

### Execution Mode

Read `execution_mode` from manifest.yaml ("team" or "sequential").

**Team mode (default):**
```
1. TeamCreate(team_name="iq-review-{workstream-name}")
2. Create 3 tasks with sequential dependencies:
   - "Run validator agent"   (no blockers)
   - "Run diff agent"        (blocked by validator)
   - "Run report agent"      (blocked by diff)
3. Spawn each agent (see Agent Launch Protocol below)
4. Monitor for DEVELOPER_QUESTION, AGENT_COMPLETE, AGENT_ERROR messages
5. After all 3 complete: TeamDelete(), proceed to Gate 2
```

If TeamCreate fails, fall back to sequential mode. Log to error_log.

**Sequential mode (fallback):**
```
For each agent (validator, diff, report):
  1. Launch via Task tool (no team_name)
  2. Agent runs, returns when done
  3. Read output files, proceed to next
```

### Agent Launch Protocol

**Team mode** -- include `team_name`:
```
Task(name: "{agent}-agent", team_name: "iq-review-{workstream-name}",
     subagent_type: "general-purpose", prompt: <below>)
```

**Sequential mode** -- no `team_name`:
```
Task(name: "{agent}-agent", subagent_type: "general-purpose", prompt: <below>)
```

**Standard prompt template:**
```
You are the {Agent} agent for the IQ Rate Update Plugin review phase.

CARRIER ROOT: {root_path}
WORKSTREAM: .iq-workstreams/changes/{workstream-name}/

Read the reviewer agent spec from: .iq-update/agents/reviewer.md
Use it as reference for validator definitions and output schemas.

{agent-specific instructions}

ALSO READ: .iq-workstreams/config.yaml, manifest.yaml

IMPORTANT: Do NOT update manifest.yaml -- the orchestrator handles that.
```

**Team mode -- append:**
```
DEVELOPER INTERACTION: Send "DEVELOPER_QUESTION: {question}" to "orchestrator".
  Wait for "DEVELOPER_ANSWER: {response}".
INTER-AGENT: Send "AGENT_INFO: {message}" to other agents by name.
ON COMPLETION: Send "AGENT_COMPLETE: {summary}" to "orchestrator". TaskUpdate.
```

**Sequential mode -- append:**
```
DEVELOPER INTERACTION: Write issues to output files with status: "needs_review".
ON COMPLETION: Return summary with output counts, issues, warnings.
```

---

## 5. Review Flow

### Agent 1: VALIDATOR

**Purpose:** Run all 7 validators. Attempt self-correction for BLOCKERs.

**Input:** execution/operations_log.yaml, execution/file_hashes.yaml,
execution/snapshots/*.snapshot, parsed/change_spec.yaml, parsed/srds/srd-NNN.yaml,
analysis/operations/op-NNN.yaml, analysis/files_to_copy.yaml, all modified source
files, all target .vbproj files.

**Output:** verification/validator_results.yaml

**Validators (included in agent prompt):**

1. **ARRAY6 SYNTAX (BLOCKER):** For every modified file, find all Array6() calls.
   Compare arg count to snapshot. Verify: matching parens, no empty args, count unchanged.

2. **COMPLETENESS (BLOCKER):** Verify every planned operation was executed. For
   territory-based changes, count territories and confirm all were updated.

3. **NO OLD FILE MODIFICATION (BLOCKER):** Verify snapshots match current state of
   ORIGINAL source files (not targets). Confirm .vbproj refs point to new dated files.

4. **NO COMMENTED CODE MODIFIED (BLOCKER):** Compare modified files to snapshots.
   For any changed line, verify the original did not start with `'` (VB.NET comment).

5. **VALUE SANITY (WARNING):** Compute % change for each value edit. Flag > 50%.
   Report min/max percentage.

6. **CROSS-LOB CONSISTENCY (WARNING):** If shared_modules exist, verify all .vbproj
   files referencing the shared module point to the same file (same path, same date).

7. **TRACEABILITY (WARNING):** Verify every SRD maps to at least one operation in
   operations_log. Report untraced SRDs and orphan changes.

**Self-Correction Protocol (include in agent prompt):**
```
If BLOCKER fails:
  1. Identify failing line(s)/file(s)
  2. Read snapshot + current file
  3. If fixable: Edit, update file_hashes, log as "self_correction", re-validate
  4. If not fixable: record failure, mark passed: false
  5. Max 1 self-correction attempt per BLOCKER
  6. Notify diff-agent of corrections (team: AGENT_INFO, sequential: verification/corrections.yaml)
```

**After validator-agent completes:**

Read validator_results.yaml. If any BLOCKER has `passed: false`:
```
BLOCKER DETECTED during validation:
  {validator_name}: {message}
    {details}
Self-correction was attempted but failed.
Options:
  1. Show me the affected file
  2. I'll fix it manually -- then say "re-validate"
  3. Restore from snapshot and re-execute this operation
  4. Skip this check and proceed anyway (NOT RECOMMENDED)
```
Wait for developer. On "re-validate": re-launch validator-agent. On option 3:
restore file, set state to PLANNED with rework_notes, tell developer to run
/iq-execute. On option 4: log override in developer_decisions, continue.

If all BLOCKERs pass: proceed to diff-agent.

### Agent 2: DIFF

**Purpose:** Generate diffs comparing snapshots to current files. Cross-reference
with plan (intended vs actual).

**Input:** execution/operations_log.yaml, execution/snapshots/*.snapshot,
plan/execution_plan.md, plan/execution_order.yaml, verification/validator_results.yaml,
verification/corrections.yaml (if exists), all modified source files.

**Output:** verification/diff_report.md, verification/changes.diff

**Steps (included in agent prompt):**
1. For each snapshot: generate unified diff, annotate with operation ID and SRD.
2. Cross-check: logged-but-no-change and undocumented-change detection.
3. Intended-vs-actual comparison against execution_order.yaml. Flag discrepancies.
4. Write diff_report.md (human-readable, annotated, per-file sections, summary).
5. Write changes.diff (standard unified diff, file paths relative to carrier root).
6. If validator flagged issues or self-corrections: highlight at TOP of diff report.

**After diff-agent completes:** Confirm diff_report.md exists. Proceed to report-agent.

### Agent 3: REPORT

**Purpose:** Produce traceability matrix and final change summary.

**Input:** manifest.yaml, parsed/change_spec.yaml, parsed/srds/srd-NNN.yaml,
analysis/operations/op-NNN.yaml, execution/operations_log.yaml,
verification/validator_results.yaml, verification/diff_report.md.

**Output:** verification/traceability_matrix.md, summary/change_summary.md

**Steps (included in agent prompt):**
1. **Traceability matrix:** For each SRD, list all operations, map to file:line
   changes, mark [OK] or [MISSING]. Count UNTRACED SRDs and ORPHAN CHANGES.
2. **Change summary:** Use EXACT format from reviewer.md -- RATE UPDATE header,
   ticket ref, workflow ID, bullet per SRD, files modified/created, .vbproj count,
   validation pass count.

**After report-agent completes:**
1. Read traceability_matrix.md and change_summary.md
2. Team mode: TeamDelete()
3. Update manifest: `phase_status.reviewer.status: "completed"`, summary, updated_at
4. Proceed to Gate 2

---

## 6. Gate 2: Result Approval

```
REVIEW: {Province_Name} {LOB(s)} {effective_date}
==========================================

Validators:
  [{OK_or_FAIL}] Array6 Syntax: {PASS_or_FAIL} {detail}
  [{OK_or_FAIL}] Completeness: {PASS_or_FAIL} {detail}
  [{OK_or_FAIL}] No Old File Modification: {PASS_or_FAIL} {detail}
  [{OK_or_FAIL}] No Commented Code Modified: {PASS_or_FAIL} {detail}
  [{OK_or_FAIL}] Value Sanity: {PASS_or_FAIL} {detail}
  [{OK_or_FAIL}] Cross-LOB Consistency: {PASS_or_FAIL} {detail}
  [{OK_or_FAIL}] Traceability: {PASS_or_FAIL} {detail}

{passed}/7 validators passed. {blockers} BLOCKER(s), {warnings} WARNING(s).
```

If WARNINGs exist, show each with context. If BLOCKERs persist (safety net),
show VALIDATION FAILED with fix/show/restore options -- do NOT show approval prompt.

If no BLOCKERs: `"Approve results? Say 'approve' to finalize, or tell me what needs fixing."`

Classify developer response using Section 10 (Conversational Action Mapping).

---

## 7. Rework Loop

### Minor Rework (Specific Fix)

Developer says: "territory 5 values are wrong" / "fix the Array6 in territory 12"

```
1. CAPTURE: Which file, line/function/territory, correct value
2. TOCTOU CHECK: Compare file hash. Warn on mismatch.
3. APPLY FIX: Edit tool, preserve VB.NET formatting
4. LOG: Append "rework-{NNN}" entry to operations_log.yaml. Update file hashes.
5. RE-VALIDATE: Re-launch all 3 review agents (or inline if simple)
6. RE-PRESENT at Gate 2 with updated results
```

### Complex Rework (Re-Execution Needed)

Multiple files, shifted line numbers, scope change, or re-analysis needed:

```
"This requires re-planning. Saving rework notes to manifest."
1. Set state: PLANNED with rework_notes
2. Developer runs /iq-execute (reads rework_notes)
3. Developer runs /iq-review again
```

Manifest update on complex rework:
```yaml
state: "PLANNED"
rework_notes:
  - description: "{what needs to change}"
    requested_at: "{now}"
    context: "{details}"
phase_status:
  reviewer: {status: "pending", summary: "Rework requested -- returned to PLANNED"}
  gate_2: {status: "rework_requested", summary: "{description}"}
```

### Rework Loop Limit

After 3 rework cycles without approval, suggest: review original plan, start
fresh /iq-plan, or continue (cycle N+1).

---

## 8. The Done Moment

On developer approval at Gate 2, read `summary/change_summary.md` and present:

```
===========================================================================
 DONE: {Province_Name} {LOB(s)} {effective_date}
===========================================================================

 {N} file(s) modified, {N} value(s) changed

 Files modified:
   - {filepath} {(shared across {N} LOBs) if applicable}

 Files created (new Code/ copies):
   - {new_file} (from {old_file})

 .vbproj references updated: {N}
 Validation: {N}/7 checks passed

---------------------------------------------------------------------------
 Suggested SVN commit message:
---------------------------------------------------------------------------

 RATE UPDATE: {Province_Name} {LOB(s)} {effective_date}
 Ticket: {ticket_ref or "N/A"}
 IQ-Workflow: {workflow_id}

   - {bullet per SRD}

 Files modified:
   - {list}

---------------------------------------------------------------------------
 Next steps:
---------------------------------------------------------------------------
   1. Build {project_name(s)} in Visual Studio
   2. Test a few {Province_Name} {LOB} quotes in TBW
   3. svn commit (use the suggested commit message above)

===========================================================================
```

Project names: strip `.vbproj` extension from manifest `target_folders` entries.

### Record SVN Revision

```
"After you commit, tell me the SVN revision number and I'll record it.
(Or say 'skip'.)"
```

If number provided: validate, set `svn_revision`, confirm `"Recorded SVN r{N}."`
If skipped: leave `svn_revision: null`.

### Archive

```yaml
state: "COMPLETED"
svn_revision: {number or null}
updated_at: "{now}"
lifecycle:
  completed_at: "{now}"
  archive_after: "{now + 14 days}"
  archived_at: null
phase_status:
  reviewer: {status: "completed", summary: "{N}/7 passed, {b} BLOCKERs, {w} WARNINGs"}
  gate_2: {status: "approved", summary: "Developer approved{. SVN rNNN if provided}"}
```

**Lifecycle fields:** When state transitions to COMPLETED, set `lifecycle.completed_at`
to the current timestamp and `lifecycle.archive_after` to 14 days later. The
`/iq-status` and `/iq-plan` archive sweeps use these fields to determine when
to move completed workstreams to `.iq-workstreams/archive/`. Old manifests
without a `lifecycle` section are handled by fallback logic (uses `updated_at`).

Tell developer: `"Workstream complete. Run /iq-status to see all workstreams, or /iq-plan for the next ticket."`

---

## 9. Error Recovery

### Session Interrupted During Review

On next `/iq-review`: precondition checks find state: VALIDATING. Resume detection
(Section 3) checks artifacts. Valid = skip to Gate 2. Stale/incomplete = re-run.

### Validator Agent Fails

Log to error_log. Offer: retry, switch to sequential, or manual guidance.
If retry fails twice, fall back to manual validation.

### File Modified During Review

Caught during Check 6 (hash verification). Options: show diff, re-run /iq-execute,
or accept current state with warning.

### Snapshot Missing

```
WARNING: Snapshot missing for {filename}.
Options: skip diff for this file, use source file as baseline, or abort.
```

### TOCTOU During Rework

Abort rework write. Report mismatch. Offer: re-capture hashes, show changes, abort.

---

## 10. Conversational Action Mapping

### Classification Priority

1. DISCARD > 2. CORRECT > 3. APPROVE/REJECT > 4. RE-VALIDATE > 5. SHOW DIFF > 6. INVESTIGATE > 7. STATUS

### Action Table

| Category | Phrases | Action | State Change? |
|----------|---------|--------|:---:|
| APPROVE | "approve", "yes", "looks good", "LGTM", "ship it", "OK", "accept" | Done Moment (Sec 8) | YES -> COMPLETED |
| REJECT | "no", "wrong", "reject", "incorrect", "nope" | Ask what to fix, rework loop (Sec 7) | NO |
| CORRECT | "change X to Y", "value should be Z", "territory 5 is wrong" | Apply rework, re-validate | NO |
| INVESTIGATE | "show me...", "what does...", any question mark | Answer, return to Gate 2 | NO |
| RE-VALIDATE | "re-run validation", "validate again", "check again" | Re-launch review team | NO |
| SHOW DIFF | "show diff", "show changes", "what changed" | Display diff_report.md | NO |
| STATUS | "status?", "where are we?", "what's left?" | Show state + validator results | NO |
| DISCARD | "cancel", "abort", "stop", "never mind" | Confirm (files NOT reverted), set DISCARDED | YES |

### Context-Dependent Behavior

| Phrase | At Gate 2 | During Rework | After Approval |
|--------|-----------|---------------|----------------|
| "yes" | Approve | Confirm rework | Acknowledge |
| "no" | Reject | Cancel rework | N/A |
| "OK" | Approve | Confirm step | Acknowledge |

Ambiguity: "hmm" = wait. Unrecognized = ask for clarification. After answering
any investigation query: `"Back to the review results -- approve or tell me what to fix."`

### Common Investigation Queries

| Developer Says | Action |
|----------------|--------|
| "Show me the diff" | Display verification/diff_report.md |
| "Show me {filename}" | Read and display the modified file |
| "Compare before/after" | Show snapshot vs current |
| "Which territories updated?" | Parse operations_log |
| "Show traceability matrix" | Display verification/traceability_matrix.md |
| "Is SRD-{N} covered?" | Look up in traceability_matrix.md |

---

## 11. manifest.yaml Updates

### On Entry
```yaml
state: "VALIDATING", updated_at: "{now}"
phase_status.reviewer: {status: "in_progress"}
```

### After Review Team Completes
```yaml
phase_status.reviewer: {status: "completed", summary: "{N}/7 passed, ..."}
```

### On Minor Rework
Append to developer_decisions (phase: "gate_2", rejected with details).
Append to error_log if applicable. State remains VALIDATING.

### On Complex Rework
State -> PLANNED with rework_notes. phase_status.reviewer -> pending.

### On Approval
State -> COMPLETED. svn_revision set. gate_2 -> approved.
Append approval to developer_decisions.

### On Discard
State -> DISCARDED. gate_2 -> discarded. Note: files NOT reverted.
Also set `lifecycle.completed_at` = now, `lifecycle.archive_after` = now + 7 days.

---

## 12. Implementation Notes

### Reading manifest.yaml
Use Read tool. Parse YAML for state, SRD progress, target folders, shared modules.

### Scanning for workstreams
Bash `ls` on `.iq-workstreams/changes/`, then Read each manifest.yaml.

### Computing file hashes
```bash
python -c "import hashlib; print(hashlib.sha256(open('{filepath}','rb').read()).hexdigest())"
```

### Comparing files (diff generation)
```bash
diff -u "execution/snapshots/{file}.snapshot" "{current_file_path}"
```

### Writing YAML files
Use Write tool. Validate after:
```bash
python -c "import yaml; yaml.safe_load(open('{filepath}')); print('YAML OK')"
```

### Generating timestamps
```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

### Applying rework edits
Edit tool. Read file first. Bottom-to-top for multi-edit same-file.

### Restoring from snapshots
```bash
cp "execution/snapshots/{file}.snapshot" "{target_path}"
```

### Team cleanup on error
`TeamDelete(team_name="iq-review-{workstream-name}")` -- always attempt, ignore errors.

### Context management
1. Read state from files, not memory. Re-read manifest.yaml when needed.
2. One agent at a time -- do not carry forward previous agent's details.
3. Rely on YAML summaries, not raw agent outputs.
4. Gate 2: read validator_results.yaml and change_summary.md fresh.
