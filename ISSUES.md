# Plugin Issues — Multi-User Testing

Created: 2026-03-06
Status: IN PROGRESS

---

## CRITICAL — Blocks basic usage

### C1: Plugin root lost after /clear (marketplace installs)
**Impact:** Every command after /clear fails with "plugin not installed"
**Root cause:** On marketplace installs, plugin files live in `~/.claude/plugins/cache/...`,
not in `{carrier_root}/.iq-update/`. Each fresh context has no memory of where the plugin is.
We added instructions to discover it, but Claude doesn't follow complex discovery chains
reliably, especially in sub-agents.
**Proper fix:** `/iq-init` must create `.iq-workstreams/paths.md` — a simple flat file with
ALL resolved paths. Every downstream command reads this file FIRST, before doing anything.
No discovery needed — just read the file.
**Status:** [x] Fixed — paths.md written by /iq-init Step 0.9, read by all downstream commands

### C2: Edits old dated files instead of copy-first
**Impact:** Changes applied to wrong file — corrupts previous version
**Root cause:** During /iq-plan, the plan may not explicitly include file-copy steps when
working with an existing folder that already has files. The Change Engine then edits whatever
file is referenced in the .vbproj, which may be the OLD dated file.
**Proper fix:** Discovery agent must check: "Does the .vbproj reference a file with the
OLD date?" If yes, the plan MUST include a copy step. This must be a hard requirement in
the Planner, not just a suggestion.
**Status:** [ ] Not fixed

### C3: Sub-agents lose context and improvise
**Impact:** Perl scripts, wrong paths, sleep loops, stuck agents
**Root cause:** Sub-agents get a fresh context window and may not load CLAUDE.md or
config.yaml. They improvise with whatever tools they find (Perl, sed, etc.)
**Proper fix:** Eliminate sub-agents in /iq-init entirely (already done). For /iq-plan
and /iq-execute, capsule briefs must include the full plugin_root path and python_cmd
so workers never need to discover anything.
**Status:** [x] Partially fixed (guardrails added but not tested)

---

## HIGH — Major UX friction

### H1: Tool paths rediscovered every command
**Impact:** 2-5 minutes wasted per command probing for Python, jq, bash, curl
**Root cause:** Each command starts fresh. config.yaml has the paths but Claude doesn't
always read it first, or reads it too late after already trying to discover.
**Proper fix:** Part of C1 fix — paths.md contains all tool paths. Every command reads
it as the FIRST step.
**Status:** [x] Fixed with C1 — paths.md has all tool paths

### H2: /iq-init takes 30-40 minutes
**Impact:** Developers avoid re-running init, stale config persists
**Root cause:** Pattern Library scans hundreds of .vb files + counts call sites.
Codebase Profile parses all CalcOption files. Both are done by Claude reading files
one at a time instead of using Python scripts.
**Proper fix:**
1. config.yaml scan only: ~3 minutes (just directory listing)
2. Pattern Library: Use a single Python script that scans all .vb files and writes YAML
3. Codebase Profile: Use a Python script for CalcOption parsing
4. Re-init fast path: If config.yaml exists and folder structure hasn't changed, skip scan
5. `/iq-init --quick` flag: Only write config.yaml, skip pattern library + codebase profile
**Status:** [x] Fixed — init_scan.py ships with plugin. Scans 1,031 files in ~30 seconds.
Three bugs fixed during real-carrier testing: YAML boolean trap (ON→True), CalcOption
qualified constants regex, next-line function lookup.

### H3: .env search path looks in carrier root
**Impact:** .env not found on marketplace installs
**Root cause:** Steps 5a-5e reference `.iq-update/.env` but on marketplace installs
there is no `.iq-update/` in the carrier root.
**Proper fix:** .env should live in `.iq-workstreams/.env` (the workspace, not the plugin).
This directory always exists after /iq-init regardless of install type.
**Status:** [x] Fixed — .env now created in .iq-workstreams/, search order updated

---

## MEDIUM — Quality of life

### M1: No testing before pushing fixes
**Impact:** Fixes that don't work get shipped, eroding trust
**Root cause:** Fixes are written and pushed without running through a real /iq-init cycle
**Proper fix:** Before pushing, at minimum:
1. Read the modified files to verify correctness
2. Trace the logic path mentally
3. For path-related fixes, verify against BOTH local and marketplace install scenarios
**Status:** This document is the fix — structured approach going forward

### M2: fetch-ticket.sh path incorrect
**Impact:** Ticket auto-fetch fails
**Root cause:** Script lives in plugin dir but references pointed to carrier root
**Proper fix:** Already pushed (commit b768bb2) but .env location needs to change too (see H3)
**Status:** [x] Partially fixed

### M3: Hardcoded "rivalitinc" in .env defaults
**Impact:** Other carriers/orgs get wrong defaults
**Proper fix:** Make the .env template carrier-agnostic or read org from config
**Status:** [ ] Not fixed (low priority — only affects non-Rival orgs)

---

## Fix Priority Order

1. **C1 + H1: paths.md file** — This alone fixes 60% of the friction
2. **C2: Copy-first enforcement** — Prevents data corruption
3. **H2: Init speed** — Python scripts for heavy scanning
4. **H3: .env location** — Move to .iq-workstreams/
5. **C3: Sub-agent stability** — Already partially addressed

---

## Testing Checklist (before each push)

- [ ] Read every modified file after editing
- [ ] Verify paths work for BOTH local and marketplace installs
- [ ] Trace the logic: "What does Claude see when it starts a fresh /iq-plan?"
- [ ] Check that all referenced files/paths actually exist
- [ ] Run validators if Python changes were made
