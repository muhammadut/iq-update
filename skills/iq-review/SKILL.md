---
name: iq-review
description: Validate all changes and produce a summary report. Runs 8 validators, generates diffs, performs semantic verification, and presents Gate 2 for developer approval.
user-invocable: true
---

# Skill: /iq-review

## 1. Purpose & Trigger

Run the RIGOROUS final review after /iq-execute has applied all modifications.
This is the third and final command in the plugin's workflow -- it validates
everything, generates comprehensive reports, and presents Gate 2 for developer
approval. The orchestrator launches the review agent team, runs all 8 validators,
produces diffs and traceability reports, and walks the developer through approval
or rework.

This skill runs in a FRESH context window. It knows nothing about /iq-plan or
/iq-execute except what is written in manifest.yaml and workstream files. Those
files ARE the memory.

**Trigger:** Slash command `/iq-review`

**State transition:** `EXECUTED` --> `VALIDATING` --> `COMPLETED`
                                              `--> `VALIDATING` (minor rework loop)
                                              `--> `PLANNED` (complex rework — back to /iq-execute)

---

## 2. Precondition Checks

Execute IN ORDER. If any fails, STOP and report.

### Check 1: Read paths.md (MANDATORY FIRST STEP)

Read `.iq-workstreams/paths.md`. This file contains all absolute paths you need:
`plugin_root`, `carrier_root`, `python_cmd`, agent spec paths, validator paths, etc.

If `paths.md` does not exist, STOP: `"ERROR: Run /iq-init first to initialize the plugin."`

Use the paths from this file for the entire command. Replace `.iq-update/` with `plugin_root`.

**Auto-heal after plugin upgrade:** Verify `{plugin_root}/package.json` exists.
If not (plugin was reinstalled to a new version), glob for
`~/.claude/plugins/cache/*/iq-update/*/package.json`, read the version, and
update `paths.md` in-place (replace old plugin_root path with new one throughout).
Print `Plugin upgraded: v{old} → v{new}`. Then print `IQ Update v{version}`.

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
From /iq-plan:  manifest.yaml, input/source.md, parsed/change_requests.yaml,
                parsed/requests/ (1+ files), analysis/intent_graph.yaml,
                analysis/analyzer_output/ (1+ files),
                plan/execution_plan.md, plan/execution_order.yaml
From /iq-execute: execution/operations_log.yaml, execution/file_hashes.yaml,
                  execution/snapshots/ (1+ .snapshot files)
```

If any missing: `"ERROR: Missing {file}. Run /iq-execute if needed."`

### Check 6: Verify Modified Files on Disk

Read `execution/file_hashes.yaml`. For each listed file:
1. Confirm the file exists on disk. If missing: show which files, offer to
   check execution log or abort.
2. Compute current SHA256 hash and compare against stored `hash_after` value.
   If any mismatch: warn the developer — someone modified the file between
   `/iq-execute` and `/iq-review`:
   ```
   WARNING: {N} file(s) changed since execution:
     {filename}: expected {stored_hash}, current {actual_hash}
   Options:
     1. Show diff (snapshot vs current)
     2. Continue anyway (review current state)
     3. Restore from snapshot and re-run /iq-execute
   ```

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
2. Create 4 tasks with sequential dependencies:
   - "Run validator agent"            (no blockers)
   - "Run diff agent"                 (blocked by validator)
   - "Run semantic verifier agent"    (blocked by diff)
   - "Run report agent"              (blocked by semantic verifier)
3. Spawn each agent (see Agent Launch Protocol below)
4. Monitor for DEVELOPER_QUESTION, AGENT_COMPLETE, AGENT_ERROR messages
5. After all 4 complete: TeamDelete(), proceed to Gate 2
```

If TeamCreate fails, fall back to sequential mode. Log to error_log.

**Sequential mode (fallback):**
```
For each agent (validator, diff, semantic-verifier, report):
  1. Launch via Agent tool (no team_name)
  2. Agent runs, returns when done
  3. Read output files, proceed to next
```

### Agent Launch Protocol

**Team mode** -- include `team_name`:
```
Agent(name: "{agent}-agent", team_name: "iq-review-{workstream-name}",
      subagent_type: "general-purpose", prompt: <below>)
```

**Sequential mode** -- no `team_name`:
```
Agent(name: "{agent}-agent", subagent_type: "general-purpose", prompt: <below>)
```

**Standard prompt template:**

**CRITICAL:** All `{...}` placeholders below MUST be replaced with actual absolute
paths from `paths.md` (read in Check 1). NEVER use `.iq-update/` literally — it
does not exist on marketplace installs.

```
You are the {Agent} agent for the IQ Rate Update Plugin review phase.

CARRIER ROOT: {carrier_root}
PLUGIN ROOT: {plugin_root}
WORKSTREAM: {carrier_root}/.iq-workstreams/changes/{workstream-name}/
PYTHON: {python_cmd}

Read the reviewer agent spec from: {plugin_root}/agents/reviewer.md
Use it as reference for validator definitions and output schemas.

{agent-specific instructions}

ALSO READ: {carrier_root}/.iq-workstreams/config.yaml, manifest.yaml

TOOL PATHS:
  Python: {python_cmd}
  Validators: {plugin_root}/validators/

IMPORTANT: Do NOT update manifest.yaml -- the orchestrator handles that.
IMPORTANT: For file path operations, use Python (os.path). For XML parsing,
use Python (xml.etree.ElementTree). NEVER use sed, awk, or Perl.
IMPORTANT: NEVER use sleep or retry loops.
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

**Purpose:** Run all 8 validators. Attempt self-correction for BLOCKERs.

**Input:** execution/operations_log.yaml, execution/file_hashes.yaml,
execution/snapshots/*.snapshot, parsed/change_requests.yaml, parsed/requests/cr-NNN.yaml,
analysis/intent_graph.yaml, analysis/files_to_copy.yaml, all modified source
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

7. **TRACEABILITY (WARNING):** Verify every CR maps to at least one intent in
   operations_log. Report untraced CRs and orphan changes.

8. **VBPROJ INTEGRITY (BLOCKER):** Verify every `<Compile Include>` path in
   modified .vbproj files resolves to an existing file on disk. Check for
   duplicate entries. Uses `validate_vbproj.py`.

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
1. For each snapshot: generate unified diff, annotate with intent ID and CR.
2. Cross-check: logged-but-no-change and undocumented-change detection.
3. Intended-vs-actual comparison against execution_order.yaml. Flag discrepancies.
4. Write diff_report.md (human-readable, annotated, per-file sections, summary).
5. Write changes.diff (standard unified diff, file paths relative to carrier root).
6. If validator flagged issues or self-corrections: highlight at TOP of diff report.

**After diff-agent completes:** Confirm diff_report.md exists. Proceed to semantic-verifier-agent.

### Agent 3: SEMANTIC VERIFIER

**Purpose:** For each intent, read the before/after code and reason about whether
the change matches the original intent description. Produce a reasoning chain
showing arithmetic checks (for value edits) and structural checks (for insertions).

**Input:** analysis/intent_graph.yaml, analysis/analyzer_output/cr-NNN-analysis.yaml,
execution/operations_log.yaml, execution/snapshots/*.snapshot, plan/execution_order.yaml,
parsed/requests/cr-NNN.yaml, verification/corrections.yaml (if exists — from validator
self-corrections), all modified source files.

**Output:** verification/semantic_verification.yaml, verification/semantic_report.md

**Agent-specific instructions (included in agent prompt):**
```
Read the semantic verifier agent spec from: {plugin_root}/agents/semantic-verifier.md
Follow ALL steps in that spec.

For each intent in intent_graph.yaml:
  1. Read the snapshot (before) and modified file (after)
  2. Apply verification method based on capability type:
     - value_editing: arithmetic check (old × factor = new? within rounding)
     - structure_insertion: placement + content + no collateral damage
     - file_creation: file exists + .vbproj updated + source unchanged
     - flow_modification: control flow structure matches plan
  3. Produce reasoning chain with MATCH or MISMATCH verdict
  4. Write results to verification/semantic_verification.yaml
  5. Write human-readable report to verification/semantic_report.md

If verification/corrections.yaml exists, read it first. These are self-corrections
applied by the validator agent. Account for corrected lines when comparing
before/after state — do NOT flag them as mismatches.

IMPORTANT: You are READ-ONLY except for your output files. Do NOT modify
any source code, snapshots, or plan files.
```

**After semantic-verifier-agent completes:**

Read semantic_verification.yaml. If any MISMATCH has severity "BLOCKER":
```
SEMANTIC MISMATCH detected:
  {intent_id}: {description}
    {reasoning summary}

This may indicate a calculation error or wrong edit location.
Options:
  1. Show me the full reasoning
  2. Show me the affected file
  3. I'll fix it manually -- then say "re-validate"
  4. Proceed anyway (log as accepted deviation)
```

If all verdicts are MATCH or WARNING: proceed to report-agent. Pass the
semantic_report.md path to the report-agent so it can include semantic
findings in the final summary.

### Agent 4: REPORT

**Purpose:** Produce traceability matrix and final change summary. Incorporate
semantic verification findings.

**Input:** manifest.yaml, parsed/change_requests.yaml, parsed/requests/cr-NNN.yaml,
analysis/intent_graph.yaml, execution/operations_log.yaml,
verification/validator_results.yaml, verification/diff_report.md,
verification/semantic_verification.yaml, verification/semantic_report.md.

**Output:** verification/traceability_matrix.md, summary/change_summary.md

**Steps (included in agent prompt):**
1. **Traceability matrix:** For each CR, list all intents, map to file:line
   changes, mark [OK] or [MISSING]. Count UNTRACED CRs and ORPHAN CHANGES.
2. **Change summary:** Use EXACT format from reviewer.md -- RATE UPDATE header,
   ticket ref, workflow ID, bullet per CR, files modified/created, .vbproj count,
   validation pass count.

**After report-agent completes:**
1. Read traceability_matrix.md, change_summary.md, and semantic_report.md
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
  [{OK_or_FAIL}] Vbproj Integrity: {PASS_or_FAIL} {detail}

{passed}/8 validators passed. {blockers} BLOCKER(s), {warnings} WARNING(s).

Semantic Verification:
  {matched}/{total} intents verified as MATCH
  {mismatched} MISMATCH(es): {blocker_count} BLOCKER, {warning_count} WARNING
  {For each MISMATCH:}
  [{severity}] {intent_id}: {description}
    {1-line reasoning summary}
```

**Semantic reasoning preview:** After validators, show the semantic verifier's
reasoning INLINE for the developer. For value_editing intents with MATCH verdicts,
show the arithmetic proof chain so the developer can see the verification was real:

```
Semantic Verification (per-intent proof):
  intent-001 (CR-001): Multiply liability premiums by 1.03
    Territory 1: Array6(233, 274, ...) x 1.03 = Array6(240, 282, ...) -- MATCH
    Territory 2: Array6(198, 233, ...) x 1.03 = Array6(204, 240, ...) -- MATCH
    ... ({N} territories verified)

  intent-002 (CR-002): Change $5000 deductible factor
    Case 5000: -0.20 -> -0.22 -- MATCH (exact value replacement)
```

For structure_insertion intents, show placement confirmation:
```
  intent-003 (CR-003): Add $50K sewer backup tier
    Inserted after Case 25000 block, before Case Else -- MATCH
    New Case 50000 block: 5 lines added -- structure verified
```

For MISMATCH intents, show the full reasoning chain with the discrepancy highlighted.

Only fall back to the compact `"Full reasoning: verification/semantic_report.md"`
for plans with 10+ intents where inline display would be overwhelming.

**Inline diff preview:** After semantic results, show a summary of key changes inline
(not just in the file). Read `verification/changes.diff` and display the first
50 lines or 3 file sections (whichever is shorter). End with:
`"Full diff: verification/changes.diff ({N} lines total)"`

This lets the developer see actual changes without opening a separate file.

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
5. RE-VALIDATE: Re-launch all 4 review agents (or inline if simple)
6. RE-PRESENT at Gate 2 with updated results
```

### Complex Rework (Re-Execution Needed)

Multiple files, shifted line numbers, scope change, or re-analysis needed:

```
"This requires re-planning. Saving rework notes to manifest."
1. Set state: PLANNED with rework_notes
2. Delete stale execution artifacts to prevent /iq-execute from resuming old work:
   - Delete execution/checkpoint.yaml
   - Delete execution/capsules/*.yaml
   - Delete execution/results/*.yaml
   (Keep execution/snapshots/ — those are the pre-edit backups)
3. Developer runs /iq-execute (reads rework_notes, rebuilds capsules fresh)
4. Developer runs /iq-review again
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

On developer approval at Gate 2, read `summary/change_summary.md`,
`plan/execution_plan.md` (for the Verification Strategy), and
`verification/semantic_verification.yaml` (for per-intent results).
Present the CR-linked completion checklist:

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
 Validation: {N}/8 checks passed

---------------------------------------------------------------------------
 Completion Checklist (per Change Request)
---------------------------------------------------------------------------

 CR-001: {title}
   [AUTO] Array6 syntax verified -- arg counts preserved
   [AUTO] {N} territories x {M} values = {total} changes applied
   [AUTO] Values within {min%} to {max%} of target (rounding variation)
   [AUTO] Semantic proof: old x {factor} = new -- MATCH for all territories
   [DEV]  Build {project_name} in VS -- confirm compile
   [DEV]  Run {Province} {LOB} quote -- verify {specific field} shows ~{expected%} change

 CR-002: {title}
   [AUTO] Value replacement verified: {old} -> {new}
   [AUTO] Traceability: CR -> intent -> file:line confirmed
   [DEV]  Build in VS -- confirm compile
   [DEV]  Run quote with ${case_value} deductible -- verify discount shows {new_value}

 {... one section per CR ...}

 General:
   [AUTO] No old files modified
   [AUTO] No commented code modified
   [AUTO] .vbproj integrity verified
   [AUTO] Cross-LOB consistency verified
   [DEV]  svn commit (use suggested message below)

---------------------------------------------------------------------------
 Suggested SVN commit message:
---------------------------------------------------------------------------

 RATE UPDATE: {Province_Name} {LOB(s)} {effective_date}
 Ticket: {ticket_ref or "N/A"}
 IQ-Workflow: {workflow_id}

   - {bullet per CR}

 Files modified:
   - {list}

===========================================================================
```

**Building the checklist:** For each CR in `change_requests.yaml`, look up the
corresponding intents in `semantic_verification.yaml`. For each intent:
- If `verdict == "MATCH"` and capability is `value_editing`: show the automated
  arithmetic proof as `[AUTO]` with the factor and territory count.
- If `verdict == "MATCH"` and capability is `structure_insertion`: show placement
  confirmation as `[AUTO]`.
- Always add `[DEV]` items from the Verification Strategy section of the plan.

The `[AUTO]` vs `[DEV]` prefix makes it immediately clear what was machine-verified
vs what still needs human verification. The developer can use this as a literal
checklist for their testing round before committing.

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
  reviewer: {status: "completed", summary: "{N}/8 passed, {b} BLOCKERs, {w} WARNINGs"}
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
| "Is CR-{N} covered?" | Look up in traceability_matrix.md |

---

## 11. manifest.yaml Updates

### On Entry
```yaml
state: "VALIDATING", updated_at: "{now}"
phase_status.reviewer: {status: "in_progress"}
```

### After Review Team Completes
```yaml
phase_status.reviewer: {status: "completed", summary: "{N}/8 passed, ..."}
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
Use Read tool. Parse YAML for state, CR progress, target folders, shared modules.

### Scanning for workstreams
Bash `ls` on `.iq-workstreams/changes/`, then Read each manifest.yaml.

### Computing file hashes
Use `python_cmd` from config.yaml (discovered by /iq-init). Never hardcode `python` or `python3`.
```bash
{python_cmd} -c "import hashlib; print(hashlib.sha256(open('{filepath}','rb').read()).hexdigest())"
```

### Comparing files (diff generation)
```bash
diff -u "execution/snapshots/{file}.snapshot" "{current_file_path}"
```

### Writing YAML files
Use Write tool. Validate after:
```bash
{python_cmd} -c "import yaml; yaml.safe_load(open('{filepath}')); print('YAML OK')"
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
