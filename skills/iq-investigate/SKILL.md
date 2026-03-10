---
name: iq-investigate
description: Ad-hoc codebase investigation tool. Ask targeted questions about the VB.NET codebase — dead code checks, pattern searches, call site analysis, value tracing. Uses the Pattern Library for instant lookups.
user-invocable: true
---

# Skill: /iq-investigate

## Purpose

Investigate the codebase interactively. Developers can ask targeted questions at
any pipeline phase — during Gate 1 review, after /iq-execute, or even before
/iq-plan. Uses the Pattern Library (from /iq-init) for instant call-count lookups
and dead-code detection.

**Key differentiator from raw Claude Code queries:** /iq-investigate understands the
carrier structure (provinces, LOBs, Code/ directories), uses the Pattern Library for
pre-indexed function data, and optionally saves findings that feed back into the
Understand agent automatically.

## Trigger

Slash command: `/iq-investigate`

Optional argument: a natural language question. If no argument is provided, the
skill prompts interactively.

Examples:
```
/iq-investigate Is CountNAFClaims_Vehicle called anywhere?
/iq-investigate How does NB Auto access claims on a vehicle?
/iq-investigate Where is GetBasePremium defined?
/iq-investigate
```

## Inputs

| Input | Source | Required | Description |
|-------|--------|----------|-------------|
| Question | User argument or interactive prompt | YES | Natural language question about the codebase |
| Pattern Library | `.iq-workstreams/pattern-library.yaml` | NO | Pre-indexed function registry (instant lookups if available) |
| config.yaml | `.iq-workstreams/config.yaml` | NO | Carrier structure (used for scope detection) |
| Active workstream | `.iq-workstreams/changes/{ws}/` | NO | If present, findings can be saved to investigation/ folder |

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Investigation report | Console output | Structured answer with code snippets, call counts, file locations |
| Finding file (optional) | `.iq-workstreams/changes/{ws}/investigation/finding-{NNN}.yaml` | Saved finding that feeds into Understand agent (Step U.9) |

## No State Requirement

Unlike /iq-plan, /iq-execute, and /iq-review, this command does NOT require an
active workstream. It works in three modes:

1. **Standalone mode** — No workstream active. Investigations use the Pattern Library
   and direct file scanning. Findings are displayed but cannot be saved.

2. **Workstream mode** — Active workstream exists. Investigations can be saved to
   `investigation/finding-*.yaml` for automatic use by the Understand agent.

3. **Degraded mode** — Neither Pattern Library nor config.yaml exists. Falls back to
   direct grep/glob scanning. Slower but functional.

---

## Execution Steps

### Step 0: Load Context

1. Read `.iq-workstreams/paths.md` if it exists — this gives you `plugin_root`,
   `carrier_root`, `python_cmd`, and all resolved paths. Use these for the session.
   Then check if `.iq-workstreams/config.yaml` exists. If yes, load carrier metadata
   (provinces, LOBs, naming patterns, codebase root).

2. Check if `.iq-workstreams/pattern-library.yaml` exists. If yes, load it for
   instant lookups. If not, note that direct scanning will be used.

3. Check if an active workstream exists (look for non-archived directories in
   `.iq-workstreams/changes/` with `manifest.yaml` where `state != COMPLETED`).
   If yes, record the workstream path for potential finding saves.

4. Report context to the developer:
   ```
   ===========================================================================
    /iq-investigate — Codebase Investigation
   ===========================================================================
    Pattern Library: {Available (N functions indexed) | Not found — using direct scan}
    Config:          {Loaded (carrier: X, N provinces) | Not found — scanning from cwd}
    Workstream:      {active-ws-name | None (findings won't be saved)}
   ===========================================================================
   ```

### Step 1: Parse Question and Detect Investigation Type

Read the developer's question and classify it into one of 6 investigation types:

```
TYPE 1: CALL SITE SEARCH
  Triggers: "called anywhere", "who calls", "call sites", "references to",
            "is X used", "how many times is X called"
  Example: "Is CountNAFClaims_Vehicle called anywhere?"

TYPE 2: PATTERN SEARCH
  Triggers: "how does", "how do", "pattern for", "how is X accessed",
            "what's the standard way to", "established pattern"
  Example: "How does NB Auto access claims on a vehicle?"

TYPE 3: DEFINITION SEARCH
  Triggers: "where is X defined", "find definition", "where is X declared",
            "show me the function", "find function"
  Example: "Where is GetBasePremium defined?"

TYPE 4: DEAD CODE CHECK
  Triggers: "dead code", "is X dead", "unused", "orphaned",
            "never called", "0 call sites"
  Example: "Is CountNAFClaims_Vehicle dead code?"

TYPE 5: VALUE TRACE
  Triggers: "where does X come from", "trace", "assignment chain",
            "how is X calculated", "what sets X"
  Example: "Where does intNAFClaimCount come from?"

TYPE 6: GENERAL SEARCH
  Triggers: Anything not matching Types 1-5 or 7.
  Example: "Show me all Select Case blocks in SetDisSur_Deductible"

TYPE 7: PROFILE QUERY
  Triggers: "what endorsements", "what vehicle types", "what options",
            "what's related to", "show dispatch", "show profile",
            "what codes exist", "list all", "what does the profile know"
  Example: "What endorsements exist for SK Home?"
  Example: "What vehicle types does AB Auto have?"
  Example: "What's related to Sewer Backup?"
```

If the question is ambiguous, ask the developer to clarify:
```
[Investigate] I'm not sure what type of investigation you need.

Your question: "{question}"

Options:
1. Call site search — count references to a function/variable
2. Pattern search — find established access patterns
3. Definition search — find where something is defined
4. Dead code check — verify if a function is called anywhere
5. Value trace — trace where a variable's value comes from
6. General search — grep-style search
7. Profile query — query the Codebase Knowledge Base

Which type? (or rephrase your question)
```

### Step 2: Detect Scope

Extract province, LOB, and file hints from the question to narrow the search:

1. **Province detection:** Look for province names ("NB", "New Brunswick",
   "Saskatchewan", "SK", etc.) in the question. Map to province code using
   config.yaml province definitions.

2. **LOB detection:** Look for LOB names ("Auto", "Home", "Hab", "Condo", etc.)
   in the question. "Hab" expands to all hab LOBs.

3. **File detection:** Look for specific filenames ("mod_Common", "mod_Algorithms",
   "CalcOption", "ResourceID", etc.) in the question.

4. **Function detection:** Look for function names or patterns ("GetBasePremium",
   "SetDisSur_*", "CountNAF*") in the question.

If no scope is detected, search the entire codebase (all provinces, all Code/
directories). If scope is detected, narrow the search:

```
[Investigate] Detected scope: {Province} {LOB} — narrowing search to:
  {Province}/Code/
  {Province}/{LOB}/{latest_version}/
```

### Step 3: Execute Investigation

Execute the appropriate investigation type.

#### Type 1: CALL SITE SEARCH

1. Extract the function/variable name from the question
2. **If Pattern Library is available:** Look up `functions[name]` for instant
   call_sites count and status (DEAD/ACTIVE/HIGH_USE)
3. **Verify with live scan:** Grep all `.vb` files in scope for `\b{name}\b`
4. Exclude definition lines and commented lines
5. Group results by file and show:

```
[Investigate] Call Site Search: {name}
─────────────────────────────────────────────────────
Pattern Library: {N} call sites ({STATUS})
Live scan:       {N} references found

References:
  {file1}:{line} — {context}
  {file2}:{line} — {context}
  ...

Definition:
  {file}:{line} — {signature}

Verdict: {ACTIVE — used in {N} locations | DEAD — 0 call sites found}
─────────────────────────────────────────────────────
```

#### Type 2: PATTERN SEARCH

1. Extract the access need keywords from the question
2. **If Pattern Library is available:** Query `accessor_index[keyword]` for
   ranked accessor patterns with call counts
3. Search Code/ files in scope for accessor patterns matching the keywords
4. For each pattern found, extract a 3-5 line code snippet showing usage
5. Rank by call_sites (highest first) and flag dead patterns:

```
[Investigate] Pattern Search: "{access_need}"
─────────────────────────────────────────────────────
Found {N} patterns:

PATTERN A (RECOMMENDED — {N} call sites, HIGH_USE):
  {accessor_pattern}
  Used in: {function1} ({file1}:{line}),
           {function2} ({file2}:{line}), ...
  Snippet:
    {3-5 lines of representative code}

PATTERN B (WARNING — 0 call sites, DEAD CODE):
  {dead_accessor_pattern}
  Used in: {dead_function} ({file}:{line}) — NEVER CALLED
  This pattern exists in the code but is not used by any active function.

Recommendation: Use Pattern A ({accessor_pattern})
─────────────────────────────────────────────────────
```

#### Type 3: DEFINITION SEARCH

1. Extract the function/class/variable name from the question
2. **If Pattern Library is available:** Look up `functions[name]` for file and line
3. **Verify with live scan:** Grep for the definition pattern:
   - Functions/Subs: `^\s*(Public|Private|Friend)?\s*(Shared)?\s*(Function|Sub)\s+{name}`
   - Constants: `\bConst\s+{name}\b`
   - Variables: `\b(Dim|Public|Private)\s+{name}\b`
4. Show all definitions found (there may be multiple across provinces/dates):

```
[Investigate] Definition Search: {name}
─────────────────────────────────────────────────────
Found {N} definition(s):

  1. {file1}:{line} — {signature}
     Call sites: {N} ({STATUS})

  2. {file2}:{line} — {signature}
     (older dated file — likely previous version)
─────────────────────────────────────────────────────
```

#### Type 4: DEAD CODE CHECK

1. Extract the function name from the question
2. Run a Call Site Search (Type 1) for that function
3. Classify the result:

```
[Investigate] Dead Code Check: {name}
─────────────────────────────────────────────────────
Definition: {file}:{line}
Call sites: {N}

Verdict: {
  "DEAD CODE — This function has 0 call sites. It is never called by any
   active code path. Do NOT use patterns from this function." |
  "ACTIVE — This function has {N} call sites. It is called by: {callers}." |
  "HIGH_USE — This function has {N} call sites. It is a canonical/established
   pattern used throughout the codebase."
}
─────────────────────────────────────────────────────
```

#### Type 5: VALUE TRACE

1. Extract the variable name and optional function/file context from the question
2. Find the variable's assignment(s) in the target function or file:
   - Direct assignment: `{varname} = {expression}`
   - Parameter: function parameter list
   - Loop variable: `For Each {varname} In {collection}`
3. For each assignment, trace one level deeper:
   - If assigned from a function call, show that function's definition
   - If assigned from a collection iteration, show how the collection is accessed
4. Show the trace chain:

```
[Investigate] Value Trace: {varname}
─────────────────────────────────────────────────────
In function: {function_name} ({file}:{line})

Assignment chain:
  1. {varname} = {expression}                    [{file}:{line}]
  2. {source_expression} comes from {origin}     [{file}:{line}]
  3. {deeper_origin} ...                         [{file}:{line}]

Access pattern: {summary of how the value is ultimately obtained}
─────────────────────────────────────────────────────
```

#### Type 6: GENERAL SEARCH

1. Extract the search term or pattern from the question
2. Grep all `.vb` files in scope for the pattern
3. Group results by file and show with context:

```
[Investigate] General Search: "{pattern}"
─────────────────────────────────────────────────────
Found {N} matches in {M} files:

  {file1}:
    {line}: {content}
    {line}: {content}

  {file2}:
    {line}: {content}
─────────────────────────────────────────────────────
```

#### Type 7: PROFILE QUERY

Query the Codebase Knowledge Base (`codebase-profile.yaml`) directly. This provides
instant answers about the codebase structure without file scanning.

1. Determine the query type from the question:

   a. **Dispatch table query** ("what endorsements/options exist for {PROV} {LOB}?"):
      ```
      Read dispatch_tables.{PROV}_{LOB} from codebase-profile.yaml
      Format as table: Code | Function | Category | Description
      ```

   b. **Vehicle type query** ("what vehicle types does {PROV} Auto have?"):
      ```
      Read vehicle_type_profiles.{PROV}_AUTO from codebase-profile.yaml
      Format as table: Type | Entry Function | Factor Functions
      ```

   c. **Glossary/relationship query** ("what's related to {term}?"):
      ```
      Search glossary for term matches (exact + synonym)
      Search rule_dependencies for functions containing the term
      Combine into a relationship map
      ```

   d. **Factor cardinality query** ("how many cases does {function} have?"):
      ```
      Read factor_cardinality.{function} from codebase-profile.yaml
      Show: Variable | Count | Min | Max | Has Case Else?
      ```

2. Display results:

```
[Investigate] Profile Query: "{question}"
─────────────────────────────────────────────────────
{formatted results as table or list}

Profile data source: codebase-profile.yaml
Last updated: {_meta.last_updated}
─────────────────────────────────────────────────────
```

3. If `codebase-profile.yaml` does not exist:

```
[Investigate] No Codebase Knowledge Base found.
              Run /iq-init to build the profile, then try this query again.
              Meanwhile, I'll search the codebase directly...
```
Then fall back to Type 6 (GENERAL SEARCH) for the query.

### Step 4: Offer to Save Finding

After displaying results, if an active workstream exists, offer to save the finding:

```
Save this finding for the Understand agent to use automatically? [Y/n]
```

If the developer says yes (or the finding is particularly useful — e.g., a canonical
pattern discovery or dead code confirmation):

1. Create the investigation directory if it doesn't exist:
   ```
   .iq-workstreams/changes/{workstream}/investigation/
   ```

2. Assign a finding number: `finding-{NNN}.yaml` where NNN is the next sequential
   number (001, 002, etc.)

3. Write the finding file:

```yaml
# Investigation Finding
# Saved by /iq-investigate — auto-consumed by Understand agent (Step U.9)
finding_id: "finding-{NNN}"
saved_at: "{ISO 8601 timestamp}"
question: "{original question}"
investigation_type: "{type_1_call_site|type_2_pattern|type_3_definition|type_4_dead_code|type_5_value_trace|type_6_general|type_7_profile_query}"

# Scope
scope:
  province: "{province_code or null}"
  lob: "{lob_name or null}"
  file: "{specific file or null}"

# Results
result:
  verdict: "{DEAD|ACTIVE|HIGH_USE|PATTERN_FOUND|NOT_FOUND}"
  summary: "{1-2 sentence summary}"

  # For pattern searches (Type 2) — feeds directly into Understand agent canonical_access
  canonical_pattern:
    need: "{access_need_id}"
    pattern: "{established accessor pattern}"
    call_sites: {N}
    confidence: "high"
    example_function: "{FunctionName}"
    example_snippet: |
      {code snippet showing the canonical pattern}

  # For dead code checks (Type 4) — feeds into Understand agent warnings
  dead_code:
    function_name: "{name}"
    file: "{file}"
    line: {N}
    call_sites: 0
    warning: "{name} has 0 call sites — DEAD CODE, do not use"

  # For call site searches (Type 1) — general reference
  call_sites:
    target: "{function_name}"
    count: {N}
    status: "{DEAD|ACTIVE|HIGH_USE}"
    references:
      - file: "{file}"
        line: {N}
        context: "{surrounding code}"

developer_validated: true    # Always true — developer saw and approved the finding
```

### Step 5: Promote to Codebase Profile (Optional)

After saving a finding (Step 4), check if it contains reusable knowledge that should
be promoted to the Codebase Knowledge Base. This is the learning loop that makes the
plugin smarter over time.

**Trigger:** Offer promotion when the finding contains ANY of:
- A canonical pattern discovery (Type 2)
- A business term → function mapping
- A function relationship (call dependency, validation pair)
- A factor table cardinality observation

**Prompt:**
```
[Investigate] This finding contains reusable knowledge:
  - {list of promotable items}

Promote to Codebase Knowledge Base? This makes it available to
ALL future workstreams automatically. [Y/n]
```

**If developer approves promotion:**

```python
profile_path = ".iq-workstreams/codebase-profile.yaml"
if not file_exists(profile_path):
    log("[Investigate] No codebase-profile.yaml found. "
        "Run /iq-init first, then re-run this investigation to promote.")
    return

# Determine what to promote based on finding type:

# 1. Glossary entries (business term → function)
if finding.has_glossary_candidate:
    # Add to glossary section
    entry = {
        "canonical_function": finding.function_name,
        "file_pattern": finding.file_pattern,
        "pattern": finding.srd_type,
        "synonyms": finding.discovered_synonyms,
        "provenance": "investigation",
        "validated_by": "developer",
        "promoted_at": timestamp
    }
    # Merge into glossary (don't overwrite existing entries)

# 2. Rule dependencies (function relationships)
if finding.has_relationship:
    entry = {
        "name": finding.relationship_name,
        "functions": finding.related_functions,
        "relationship": finding.relationship_type,
        "impact": finding.impact_description,
        "provenance": "investigation",
        "validated_by": "developer",
        "promoted_at": timestamp
    }
    # Append to rule_dependencies (dedup by function pair)

# 3. Factor cardinality (Case branch counts)
if finding.has_cardinality:
    # Add to factor_cardinality section
    # Same schema as Understand agent (Step U.12) but with provenance: "investigation"
```

**Confirmation:**
```
[Investigate] Promoted to codebase-profile.yaml:
  {list of items promoted}
  These will be used automatically by Intake, Understand agent, and Plan agent
  in all future workstreams.
```

**If developer declines promotion:** Continue to Step 6. The finding is still saved
in the workstream's investigation/ folder (Step 4) for local use.

### Step 6: Report and Suggest Next Steps

After the investigation (and optional save/promote), suggest relevant next steps:

```
─────────────────────────────────────────────────────
Next steps:
  - Ask another question: /iq-investigate {new question}
  - {If finding saved}: Run /iq-plan — the Understand agent will use this finding automatically
  - {If finding promoted}: Knowledge is now in the Codebase Profile for all future work
  - {If dead code found}: The Pattern Library marks this as DEAD (0 callers)
  - {If no Pattern Library}: Run /iq-init --refresh to build the Pattern Library
  - {If no profile}: Run /iq-init to build the Codebase Knowledge Base
─────────────────────────────────────────────────────
```

---

## Feedback Loops: Investigation → Pipeline

When the developer saves a finding, it creates TWO feedback paths:

### Path A: Workstream-Local (Step 4 — Save Finding)
```
Developer runs /iq-investigate "How are claims accessed?"
  → Finds GetClaimsVehicles (12 call sites, HIGH_USE)
  → Saves finding to investigation/finding-001.yaml
                    │
Developer runs /iq-plan
  → Understand agent (Step U.9) reads investigation/finding-001.yaml
  → Matches access need "claims" → uses pre-validated pattern
  → Skips Pattern Library lookup + confirmation (developer already validated)
  → Change Engine gets the correct pattern in intent capsule
```

### Path B: Global Knowledge (Step 5 — Promote to Profile)
```
Developer runs /iq-investigate "What's related to Sewer Backup?"
  → Finds GetSewerBackupPremium calls GetWaterDamagePremium
  → Saves finding → Promotes to codebase-profile.yaml
                    │
ANY future /iq-plan (any workstream, any ticket):
  → Understand agent (Step U.12) reads rule_dependencies from profile
  → If targeting Water Coverage → warns about Sewer Backup
  → Plan agent (Section 8) elevates risk level to HIGH
  → Developer sees the warning BEFORE approving the plan
```

Path A is workstream-local (one ticket). Path B is global (all future work).
Together they ensure the plugin gets smarter with every investigation.

---

## Implementation Notes for Claude Code

When executing this skill, use these specific tool strategies:

### Pattern Library lookups
Use the Read tool to read `.iq-workstreams/pattern-library.yaml`. For specific
function lookups, use Grep with the function name on the YAML file (faster than
reading the entire file for large libraries).

### Code file scanning
Use Grep for searching `.vb` files. Use Glob to find files matching patterns.
Run multiple Grep calls in parallel when searching across provinces.

### Scope narrowing
When province/LOB is detected, construct the specific Code/ directory path from
config.yaml and restrict searches to that path. This dramatically reduces search
time on large carriers.

### Finding file writes
Use the Write tool to create finding YAML files. Do NOT use Bash echo/cat.

### Interactive mode
If no question is provided as an argument, use AskUserQuestion to prompt:
```
What would you like to investigate? (Examples:
  "Is CountNAFClaims_Vehicle called anywhere?"
  "How does NB Auto access claims on a vehicle?"
  "Where is GetBasePremium defined?")
```

---

## Error Handling

### Resilience Rules

1. **Missing Pattern Library is not an error.** Fall back to direct scanning with
   a note suggesting /iq-init --refresh.

2. **Missing config.yaml is not an error.** Fall back to scanning from the current
   working directory. Province/LOB detection will be less accurate.

3. **No matches found is not an error.** Report "no matches found" and suggest
   alternative search terms or broader scope.

4. **Large result sets are truncated.** If more than 50 matches are found, show
   the first 20 and report the total count with a note:
   ```
   Showing 20 of {N} matches. Narrow your search with a province or file hint.
   ```

---

## Design Decisions

1. **Stateless by default.** Unlike other /iq-* commands, /iq-investigate works
   without any prior setup. This makes it useful for new carriers before /iq-init.

2. **Pattern Library is optional but recommended.** The library provides instant
   call-count lookups; without it, every investigation requires full file scanning.

3. **Findings are opt-in.** The developer chooses whether to save findings. Not
   every investigation needs to feed back into the pipeline.

4. **Seven types cover 95%+ of needs.** Types 1-6 search the codebase directly.
   Type 7 queries the Codebase Knowledge Base. Type 6 (General) is the escape hatch.

5. **Scope detection is best-effort.** Province/LOB hints improve performance but
   are not required. Wrong scope detection is caught by empty results.

6. **Dead code warnings are prominent.** Every investigation that touches a 0-caller
   function gets a clear "DEAD CODE" label. This is the primary defense against
   dead-code poisoning in the pipeline.
