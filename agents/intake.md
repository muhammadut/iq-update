# Agent: Intake

## Purpose

Parse the Summary of Changes input into a structured change specification with
individually tracked change items called SRDs (Specification Requirement Details).
Each SRD represents one discrete change requirement from the source material.

## Pipeline Position

```
[INPUT] --> INTAKE --> Decomposer --> Analyzer --> Planner --> [GATE 1] --> Modifiers --> Reviewer --> [GATE 2]
            ^^^^^
```

- **Upstream:** `/iq-plan` skill (provides target folders, raw input)
- **Downstream:** Decomposer agent (consumes `change_spec.yaml` + `srds/srd-NNN.yaml`)

## Input Schema

The Intake agent receives its input from the `/iq-plan` skill via the workflow
directory and conversational interaction.

```yaml
# Input is one of the following (provided conversationally):
input_type: "text" | "pdf_path" | "excel_path" | "source_md"

# Context from /iq-plan (already in manifest.yaml):
carrier: "Portage Mutual"
province: "SK"
province_name: "Saskatchewan"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
effective_date: "20260101"

target_folders:
  - path: "Saskatchewan/Home/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  # ...

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
```

## Output Schema

```yaml
# File: parsed/change_spec.yaml
carrier: "Portage Mutual"
province: "SK"
province_name: "Saskatchewan"          # Human-readable, used in reporting
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
lob_category: "hab"                    # "hab" | "auto" | "mixed" (from Step 2.3)
effective_date: "20260101"
ticket_ref: "DevOps 24778"           # Optional, extracted from input
srd_count: 5

target_folders:
  - path: "Saskatchewan/Home/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  # ... (carried forward from manifest)

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

srds:
  - id: "srd-001"
    title: "Increase base rates by 5%"
    type: "base_rate_increase"          # See pattern library for valid types
    complexity: "SIMPLE"              # SIMPLE | MEDIUM | COMPLEX
    scope: "all_territories"
    method: "multiply"                # multiply | explicit
    factor: 1.05                      # Only for method=multiply
    rounding: "auto"                # Always "auto" from Intake -- Analyzer resolves to banker/none/mixed
    dat_file_warning: false           # True if this change targets DAT-file-based rates

  - id: "srd-002"
    title: "Change $5000 deductible factor from -20% to -22%"
    type: "factor_table_change"
    complexity: "SIMPLE"
    target_function: null  # Intake sets to null; Analyzer resolves
    case_value: 5000
    old_value: -0.20
    new_value: -0.22

  - id: "srd-003"
    title: "Add Elite Comp coverage type"
    type: "new_coverage_type"
    complexity: "COMPLEX"
    description: "New coverage type with eligibility rules, rate tables, liability tiers"
```

```yaml
# File: parsed/srds/srd-001.yaml (one file per SRD)
id: "srd-001"
title: "Increase base rates by 5%"
type: "base_rate_increase"
complexity: "SIMPLE"
scope: "all_territories"
method: "multiply"
factor: 1.05
rounding: "auto"
dat_file_warning: false
source_text: "Increase all base rates by 5%"    # Original text from the Summary of Changes
source_location: "pasted text, item 1"           # Where in the source this came from
```

# NOTE: Abbreviated schema. See Step 6 for the complete SRD field list
# including: method, lob_scope, target_lobs, source_text, source_location,
# ambiguity_flag, rounding_hint, and target_function_hint.

---

## EXECUTION STEPS: Natural Language Text Input (Sprint 1)

These are the step-by-step instructions for parsing natural language text input
into structured SRDs. Follow them in order. Each step has clear inputs, actions,
and outputs.

### Prerequisites

Before starting, confirm the following exist and are readable:

1. The workflow directory at `.iq-workstreams/changes/{workstream-name}/`
2. The `manifest.yaml` inside that directory (provides province, LOBs, target folders)
3. The `.iq-workstreams/config.yaml` (provides carrier info, province codes, hab flags)
4. The pattern YAML files at `.iq-update/patterns/*.yaml` (provides classification hints)

If any of these are missing, STOP and report:
```
[Intake] Cannot proceed — missing required file: {path}
         Was /iq-init run? Is the workstream set up via /iq-plan?
```

### Step 1: Receive and Record the Raw Input

**Action:** Accept the developer's description of rate changes.

1.1. The input arrives in one of two ways:
   - **Conversational:** The developer types or pastes the changes directly into the chat
   - **File-based:** The developer says "I pasted it in input/" — read `.iq-workstreams/changes/{workstream}/input/source.md`

1.2. Save the raw input text to `input/source.md` in the workflow directory. If the
     developer provided it conversationally, write it now. If it was already in
     `input/source.md`, leave it as-is.

1.3. Extract any ticket reference from the input text. Look for patterns like:
   - "DevOps 24778" or "DevOps #24778"
   - "Ticket 12345" or "JIRA-456"
   - "RE: [some subject line with a ticket number]"
   - If no ticket reference found, set `ticket_ref` to `null`

**Example input (developer pastes this):**

```
SK Hab changes effective Jan 1, 2026 (DevOps 24778):
- Increase all base rates by 5%
- Change the $5000 deductible factor from -20% to -22%
- Change the $2500 deductible factor from -15% to -17%
- Increase all liability premiums by 3%
```

**Example source.md output:**

```markdown
# Source: Conversational Input
# Received: 2026-02-26

SK Hab changes effective Jan 1, 2026 (DevOps 24778):
- Increase all base rates by 5%
- Change the $5000 deductible factor from -20% to -22%
- Change the $2500 deductible factor from -15% to -17%
- Increase all liability premiums by 3%
```

### Step 2: Read the Manifest for Context

**Action:** Load the workflow context from `manifest.yaml`.

2.1. Read `manifest.yaml` from the workflow directory. Extract:
   - `carrier` (e.g., "Portage Mutual")
   - `province` (e.g., "SK")
   - `province_name` (e.g., "Saskatchewan")
   - `lobs` (e.g., ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"])
   - `effective_date` (e.g., "20260101")
   - `target_folders` (list of path + vbproj entries)
   - `shared_modules` (list of shared files and which LOBs use them)

2.2. Read `config.yaml` from `.iq-workstreams/`. Extract:
   - `provinces.{province_code}.lobs[].is_hab` — flag on each LOB entry indicating if it is habitational
   - `provinces.{province_code}.hab_code` — the hab code (e.g., "SKHab")
   - `naming` patterns — for understanding file naming conventions

2.3. Determine the **LOB category** for this workflow:
   - If ALL target LOBs have `is_hab: true` in config.yaml → this is a **hab** workflow
   - If target LOBs include "Auto" → this is an **auto** workflow
   - If target LOBs include both hab and auto → this is a **mixed** workflow (flag for developer — unusual)

   Store this as `lob_category: "hab" | "auto" | "mixed"` for use in later steps.

### Step 2.5: Glossary Pre-Lookup (Codebase Profile)

**Action:** Before pattern keyword matching, check the Codebase Knowledge Base
glossary for early, high-confidence business term resolution.

2.5.1. Read the `glossary` section from `.iq-workstreams/codebase-profile.yaml`.

- If the file does not exist or the `glossary` section is empty, skip this step
  entirely (graceful degradation — fall through to Step 3 keyword matching).

2.5.2. For each raw change item text (not yet segmented — scan the full input):

```python
def resolve_from_glossary(text, glossary):
    """Match business terms in developer text against the glossary.

    Returns list of {term, canonical_function, file_pattern, pattern, confidence}
    sorted by specificity (longest match first).
    """
    matches = []
    text_lower = text.lower()
    for term, entry in glossary.items():
        if term in text_lower:
            matches.append({
                "term": term,
                "canonical_function": entry.get("canonical_function"),
                "file_pattern": entry.get("file_pattern"),
                "pattern": entry.get("pattern"),
                "confidence": "high"
            })
        elif any(s in text_lower for s in entry.get("synonyms", [])):
            matched_synonym = next(s for s in entry["synonyms"] if s in text_lower)
            matches.append({
                "term": term,
                "canonical_function": entry.get("canonical_function"),
                "file_pattern": entry.get("file_pattern"),
                "pattern": entry.get("pattern"),
                "confidence": "medium",
                "matched_via": matched_synonym
            })

    # Sort by specificity: longer term matches are more specific
    matches.sort(key=lambda m: len(m["term"]), reverse=True)
    return matches
```

2.5.3. Store glossary matches as `glossary_hints` in-memory. These are consumed
in Step 5.1 (Classification Procedure) to:
- **Confirm** the keyword match (glossary agrees → higher confidence)
- **Override** ambiguous keyword matches (glossary provides canonical function)
- **Provide target_function early** (Intake can set `target_function` in the SRD
  instead of leaving it `null` for the Analyzer)

2.5.4. Log glossary matches:
```
[Intake] Glossary pre-lookup: {N} term(s) resolved
  - "{term}" → {canonical_function} ({pattern}) [confidence: {high|medium}]
```

**Impact:** When developer writes "update the distinct client discount by 5%":
- WITHOUT glossary: Intake matches "discount" → guesses `factor_table_change`
  (correct pattern but no function hint; Analyzer must search)
- WITH glossary: Intake matches "distinct client discount" → resolves to
  `SetDiscountDistinctClient` + `factor_table_change` (correct pattern AND function)

### Step 3: Load Classification Hints from Patterns

**Action:** Read the pattern YAML files to build a classification lookup table.

3.1. Read all `.yaml` files from `.iq-update/patterns/`. For each file, extract:
   - `name` — the pattern type identifier
   - `classification_hints` — list of keyword phrases
   - `complexity` — default complexity level
   - `parameters` — what parameters this pattern needs

3.2. Build an in-memory lookup table mapping hint phrases to pattern types:

```
CLASSIFICATION LOOKUP TABLE
─────────────────────────────────────────────
Hint Phrase                → Pattern Type         → Default Complexity
"base rate"                → base_rate_increase    → SIMPLE
"rate increase"            → base_rate_increase    → SIMPLE
"multiply rates"           → base_rate_increase    → SIMPLE
"percentage increase"      → base_rate_increase    → SIMPLE
"across the board increase"→ base_rate_increase    → SIMPLE
"deductible factor"        → factor_table_change   → SIMPLE
"discount factor"          → factor_table_change   → SIMPLE
"surcharge"                → factor_table_change   → SIMPLE
"Select Case"              → factor_table_change   → SIMPLE
"factor table"             → factor_table_change   → SIMPLE
"change factor"            → factor_table_change   → SIMPLE
"included limit"           → included_limits       → SIMPLE
"coverage limit"           → included_limits       → SIMPLE
"medical payments"         → included_limits       → SIMPLE
"additional living expense"→ included_limits       → SIMPLE
"change limit"             → included_limits       → SIMPLE
"new endorsement"          → new_endorsement_flat  → MEDIUM
"flat rate endorsement"    → new_endorsement_flat  → MEDIUM
"add endorsement"          → new_endorsement_flat  → MEDIUM
"endorsement premium"      → new_endorsement_flat  → MEDIUM
"optional coverage"        → new_endorsement_flat  → MEDIUM
"liability option"         → new_liability_option  → MEDIUM
"new liability"            → new_liability_option  → MEDIUM
"liability premium"        → new_liability_option  → MEDIUM
"liability sub-option"     → new_liability_option  → MEDIUM
"liability tier"           → new_liability_option  → MEDIUM
"new coverage type"        → new_coverage_type     → COMPLEX
"add coverage"             → new_coverage_type     → COMPLEX
"coverage constant"        → new_coverage_type     → COMPLEX
"DAT IDs"                  → new_coverage_type     → COMPLEX
"rate table routing"       → new_coverage_type     → COMPLEX
"eligibility"              → eligibility_rules     → COMPLEX
"validation rule"          → eligibility_rules     → COMPLEX
"alert message"            → eligibility_rules     → COMPLEX
"not rated"                → eligibility_rules     → COMPLEX
"restrict"                 → eligibility_rules     → COMPLEX
"minimum requirement"      → eligibility_rules     → COMPLEX
```

This table is rebuilt each run from the pattern files, so new patterns added to
`.iq-update/patterns/` are automatically picked up.

### Step 4: Segment the Input into Individual Change Items

**Action:** Break the raw text into discrete change items. Each item becomes one SRD.

4.1. **Identify change boundaries.** Look for these structural signals:
   - Bullet points (-, *, numbered lists)
   - Line breaks separating distinct changes
   - Conjunctions joining distinct changes ("and also", "additionally", "as well as")
   - Table rows (each row = one change)
   - Paragraph breaks

4.2. **Segmentation rules:**
   - Each distinct rate modification = 1 SRD
   - A percentage change applied to ONE type of rate = 1 SRD, even if it spans many territories
   - Multiple values changing in the SAME factor table function = 1 SRD per distinct case value UNLESS the developer groups them (e.g., "update all deductible factors" = 1 SRD)
   - A new coverage type = 1 SRD (even though it involves multiple files)
   - If the developer gives a grouped instruction like "increase all base rates and all liability premiums by 5%", split into separate SRDs per rate type (base rates = SRD-001, liability premiums = SRD-002) because they target different functions

4.3. **Ambiguity detection.** If you cannot clearly segment, ask the developer:

```
[Intake] I see "increase all rates by 5%". In this codebase, there are different types of rates:
  1. Base rates (dwelling base premiums) — these are in DAT files for hab, VB code for auto
  2. Liability premiums (Array6 in mod_Common)
  3. Factor/discount percentages (Select Case in mod_Common)

Which rates does this 5% increase apply to?
  a) Only base rates
  b) Only liability premiums
  c) Both base and liability rates
  d) Everything — all rate values across the board
  e) Something else — please clarify
```

4.4. **Assign sequential SRD IDs** starting from `srd-001`, zero-padded to 3 digits.

**Example:** The input from Step 1 produces 4 change items:

```
Item 1: "Increase all base rates by 5%"           → srd-001
Item 2: "Change $5000 deductible factor -20% → -22%" → srd-002
Item 3: "Change $2500 deductible factor -15% → -17%" → srd-003
Item 4: "Increase all liability premiums by 3%"    → srd-004
```

### Step 5: Classify Each Change Item

**Action:** For each segmented change item, determine the SRD type, complexity,
and required parameters by matching against the classification lookup table and
applying the decision trees below.

#### 5.1 Classification Procedure (per item)

For each change item extracted in Step 4, execute this procedure:

**5.1.0. Check glossary hints.** If Step 2.5 produced `glossary_hints` for this
change item's text, use the highest-confidence match as a strong signal:
- If glossary provides `pattern` → use as the initial classification (skip 5.1.1)
- If glossary provides `canonical_function` → set `target_function` in the SRD
  (Analyzer still validates, but has a head start)
- If NO glossary match → proceed to 5.1.1 as normal

**5.1.1. Keyword matching.** Scan the change item text for matches against the
classification lookup table from Step 3. Use case-insensitive substring matching.
If multiple patterns match, prefer the one with the LONGEST matching hint phrase
(more specific match wins). If Step 5.1.0 already resolved a pattern, use keyword
matching as a cross-check (glossary and keywords should agree; log if they differ).

**5.1.2. Apply the Type Decision Tree** (see Section 5.2 below) to confirm or
override the keyword match (or glossary match from 5.1.0).

**5.1.3. Extract parameters** required by the matched pattern (see Section 5.3).

**5.1.4. Detect method** — multiply vs explicit (see Section 5.4).

**5.1.5. Detect DAT-file warning** (see Section 5.5).

**5.1.6. Assess complexity** (see Section 5.6).

**5.1.7. Detect scope** — all territories, specific territories, or all LOBs (see Section 5.7).

#### 5.2 Type Decision Tree

Use this tree to determine the SRD type. Start at the top and follow the branches.

```
INPUT: One segmented change item text + lob_category from Step 2

Q1: Does the change mention ADDING something new that doesn't exist yet?
  YES ──► Q1a: What is being added?
           ├─ New coverage type / coverage constant / DAT IDs
           │  → type = "new_coverage_type", complexity = COMPLEX
           ├─ New endorsement / optional coverage with a flat premium
           │  → type = "new_endorsement_flat", complexity = MEDIUM
           ├─ New liability option / liability tier / liability premium array
           │  → type = "new_liability_option", complexity = MEDIUM
           ├─ New eligibility rule / validation / restriction / alert
           │  → type = "eligibility_rules", complexity = COMPLEX
           └─ Something else entirely new
              → type = UNKNOWN, complexity = COMPLEX, flag for review

  NO ──► Q2: Does the change mention a PERCENTAGE or MULTIPLIER applied to rates?
           YES ──► Q2a: What kind of rates?
                    ├─ "base rates" / "dwelling rates" / "base premiums"
                    │  → type = "base_rate_increase"
                    │    (but check DAT-file warning in Step 5.5)
                    ├─ "liability premiums" / "liability rates"
                    │  → type = "base_rate_increase"
                    │    (these are Array6 in mod_Common — fully editable)
                    ├─ "deductible factors" / "discount factors" / "surcharge factors"
                    │  → type = "factor_table_change"
                    │    (Note: multiplying ALL factor values is unusual — ask developer to confirm)
                    └─ "all rates" / ambiguous
                       → ASK for clarification (see Step 4.3)

           NO ──► Q3: Does the change specify an OLD value → NEW value replacement?
                    YES ──► Q3a: What kind of value?
                             ├─ A factor/discount/surcharge in a specific function
                             │  (mentions deductible, discount, factor, surcharge)
                             │  → type = "factor_table_change"
                             ├─ An included limit (medical payments, additional living, etc.)
                             │  → type = "included_limits"
                             ├─ A Const value (accident base, specific named constant)
                             │  → type = "factor_table_change"
                             │    (Const changes use the same SRD type — Analyzer finds it)
                             └─ Something else
                                → type = UNKNOWN, complexity = MEDIUM, flag for review

                    NO ──► Q4: Does the change describe a LOGIC modification?
                             (new condition, eligibility rule, validation, workflow change)
                             YES → type = "eligibility_rules", complexity = COMPLEX
                             NO  → type = UNKNOWN, complexity = COMPLEX, flag for review
```

When the type resolves to `UNKNOWN`, set a flag `needs_review: true` on the SRD
and tell the developer:

```
[Intake] I couldn't classify this change into a known pattern:
         "{original change text}"

         It doesn't match any of my known change types:
           - base_rate_increase (percentage applied to Array6 rate values)
           - factor_table_change (old→new value in a Select Case or Const)
           - included_limits (change a coverage limit value)
           - new_endorsement_flat (add a flat-rate endorsement)
           - new_liability_option (add a liability sub-option)
           - new_coverage_type (add a new coverage type with DAT IDs)
           - eligibility_rules (add validation/eligibility logic)

         How would you describe this change? I'll classify it as COMPLEX
         and flag it for manual review unless you can help me categorize it.
```

#### 5.3 Parameter Extraction

Once the type is determined, extract the parameters required by that pattern.
Refer to the pattern YAML files for the parameter list.

**For `base_rate_increase`:**
```yaml
# From text: "Increase all base rates by 5%"
factor: 1.05        # Convert "5%" → 1.05, "10% decrease" → 0.90
scope: "all_territories"  # or "specific_territories" if territories listed
territories: []     # populated only when scope = specific_territories
```

Conversion rules for factor:
- "increase by X%" → factor = 1 + (X / 100)
- "decrease by X%" → factor = 1 - (X / 100)
- "multiply by X" → factor = X
- "X% increase" → factor = 1 + (X / 100)
- "double" → factor = 2.0
- "reduce by half" → factor = 0.5
- "approximately X%" → factor = 1 + (X / 100), but flag as ambiguous (see Step 5.8)

**For `factor_table_change`:**
```yaml
# From text: "Change $5000 deductible factor from -20% to -22%"
target_function: null            # Intake does NOT know the exact function name.
                                 # Set to null — the Decomposer/Analyzer will find it.
case_value: 5000                 # The Select Case value
old_value: -0.20                 # Convert "-20%" → -0.20
new_value: -0.22                 # Convert "-22%" → -0.22
```

Conversion rules for factor values:
- "-20%" → -0.20 (percentage to decimal)
- "0.075" → 0.075 (already decimal, keep as-is)
- "-7.5%" → -0.075
- "$50" → 50 (dollar amount, keep as numeric)
- "no discount" or "0%" → 0.0

IMPORTANT: If the developer says "change deductible factor" but does not specify
which Case value, enter interactive mode:

```
[Intake] You want to change a deductible factor, but I need to know which
         deductible amount. For example, in this codebase deductible cases
         are typically: $500, $1000, $2500, $5000.

         Which deductible amount are we changing?
         Or are we changing ALL deductible factors?
```

**For `included_limits`:**
```yaml
# From text: "Change medical payments limit from $5000 to $10000"
limit_name: "Medical Payments"
old_limit: 5000.0
new_limit: 10000.0
```

**For `new_endorsement_flat`:**
```yaml
# From text: "Add water damage endorsement at $75"
endorsement_name: "Water Damage"
option_code: null      # Intake does NOT know the TBW option code — ask or set null
premium: 75.0
category: null         # Ask developer if not stated
```

If option_code or category is missing, ask:

```
[Intake] For the new endorsement "Water Damage" at $75:
         1. What is the TBW option code? (Enter the code, or "TBD" if unknown)
         2. What category? (e.g., ENDORSEMENTEXTENSION, OPTIONALCOVERAGE)
```

**For `new_liability_option`:**
```yaml
# From text: "Add Rented Dwelling liability at $0, $0, $0, $0, $324, $462"
liability_name: "RentedDwelling"
premium_array: [0, 0, 0, 0, 324, 462]
```

**For `new_coverage_type`:**
```yaml
# From text: "Add Elite Comp coverage type"
coverage_type_name: "Elite Comp."
constant_name: "ELITECOMP"        # Infer from name, or ask
classifications: null              # Must ask developer
dat_ids: null                      # Must ask developer
```

If classifications or dat_ids are missing, ask:

```
[Intake] For the new coverage type "Elite Comp":
         1. What classifications does it have? (e.g., Preferred, Standard)
         2. What are the DAT resource IDs for each classification?
            Example: Preferred = 9501, Standard = 9502
```

**For `eligibility_rules`:**
```yaml
# From text: "Elite Comp requires minimum $500K dwelling and $5M liability"
rules:
  - condition_description: "Coverage type is Elite Comp"
    enforcement: "Minimum dwelling $500,000"
    alert_message: null   # Ask developer for exact wording
  - condition_description: "Coverage type is Elite Comp"
    enforcement: "Minimum liability $5,000,000"
    alert_message: null
```

#### 5.4 Rounding Mode Detection

**IMPORTANT: The Intake agent does NOT make the final rounding decision.**

The Intake agent has not read the actual VB code. It doesn't know whether the target
Array6 values are integers (233, 274, 319) or decimals (0.075, 0.082). Making a
rounding assumption here risks catastrophic errors — for example, banker's rounding
on decimal factor values could round 0.07875 to 0 instead of keeping it as 0.079.

**Rule: Always set `rounding: "auto"` for multiply-method SRDs.**

The Analyzer agent (which actually reads the target files and sees the values) will
determine the correct rounding mode and update the SRD before the Planner builds
the execution plan. The Analyzer uses this logic:
- If the existing Array6 values are all integers → rounding = "banker"
- If the existing values contain decimals → rounding = "none"
- Factor values (dblFactor, dblDiscount, etc.) → rounding = "none" always

**What Intake DOES set:**
```
method = "multiply"  → rounding = "auto" (Analyzer decides later)
method = "explicit"  → rounding = "none" (developer gave exact values, no rounding)
```

**The Intake agent MAY add a `rounding_hint` field** when the input gives a strong
signal — for example, if the developer says "round to nearest dollar", set
`rounding_hint: "banker"`. But this is a HINT for the Analyzer, not a decision.

#### 5.5 DAT-File Warning Detection

This is CRITICAL. Hab dwelling base rates live in external DAT files, not in
VB code. The plugin CANNOT edit DAT files. The Intake agent must detect this
early and warn the developer.

**Decision tree:**

```
Q1: Is the SRD type "base_rate_increase"?
  NO  → dat_file_warning = false (only base rate changes can hit DAT files)

  YES → Q2: What is the lob_category (from Step 2)?
          "auto" → dat_file_warning = false
                   Auto base rates are ALWAYS in VB code (mod_Algorithms Array6 tables).
                   Fully editable by the plugin.

          "hab"  → Q3: Does the change specifically say "liability premiums" or
                       "liability rates" or "endorsement rates"?
                     YES → dat_file_warning = false
                           Hab liability premiums are Array6 in mod_Common — in VB code.
                           Fully editable by the plugin.

                     NO ──► Q4: Does the change say "base rates" or "dwelling rates"
                                or "base premiums" or "dwelling premiums"?
                              YES → dat_file_warning = true
                                    Hab dwelling base rates are almost always in
                                    external DAT files loaded via GetPremFromResourceFile().
                                    The plugin CANNOT edit these.

                              NO ──► Q5: Is the change ambiguous? (just says "rates"
                                         without specifying which type)
                                       YES → ASK the developer (see below)
                                       NO  → dat_file_warning = false

          "mixed" → Apply the hab rules for hab LOBs, auto rules for auto LOBs.
                    If the same SRD applies to both, create separate SRDs.
```

**When dat_file_warning = true, tell the developer immediately:**

```
[Intake] WARNING: SRD-001 ("Increase all base rates by 5%") targets hab dwelling
         base rates. In this codebase, hab dwelling base rates are stored in
         external DAT resource files, NOT in VB source code.

         This plugin CANNOT edit DAT files. This change must be done manually
         using the DAT file editor.

         I will still record this SRD with dat_file_warning: true so it's tracked,
         but the Rate Modifier will skip it during execution.

         Do you want me to:
           1. Keep this SRD in the spec (for tracking) but mark it as out-of-scope
           2. Remove it from the spec entirely
           3. Actually, this change is about liability premiums, not dwelling base rates
              (let me re-classify)
```

**When the change is ambiguous (hab LOBs, says "rates" without qualifying):**

```
[Intake] You mentioned "increase all rates by 5%" for Saskatchewan Habitational.
         In this codebase, there are two types of hab rates:

         1. Dwelling base rates — stored in DAT files (NOT editable by this plugin)
         2. Liability premiums — stored in VB code Array6 tables (editable)

         Which rates should the 5% increase apply to?
           a) Dwelling base rates (DAT files — I'll flag this as out-of-scope)
           b) Liability premiums (Array6 in mod_Common — I can handle this)
           c) Both (I'll create two SRDs — one flagged, one editable)
           d) Something else — please clarify
```

#### 5.6 Complexity Assessment

Complexity determines which downstream agents are needed and helps the developer
understand the risk level.

**Complexity rules:**

| Complexity | Criteria | Examples |
|------------|----------|---------|
| SIMPLE | Single value change or uniform multiplier across one rate type. Targets one function or one set of Array6 calls. No new code structures. | "5% base rate increase", "change $5000 deductible from -20% to -22%", "change medical payments limit from $5000 to $10000" |
| MEDIUM | Multiple related value changes, OR adding a new file (endorsement, liability option) that follows an existing template. | "Add water damage endorsement at $75", "Add rented dwelling liability option", "Update all deductible factors (5+ values)" |
| COMPLEX | New code structures (functions, constants, Select Case blocks), cross-file changes, eligibility logic, or anything that doesn't fit an existing template. | "Add Elite Comp coverage type", "Add eligibility rule for minimum dwelling", "New rating algorithm for commercial vehicles" |

**Override rules:**
- If a change is classified as `base_rate_increase` but targets specific territories
  with DIFFERENT multipliers per territory → upgrade from SIMPLE to MEDIUM
- If a `factor_table_change` involves more than 5 individual Case value changes
  → upgrade from SIMPLE to MEDIUM
- If any change type resolves to UNKNOWN → always COMPLEX
- If `dat_file_warning = true` → keep the pattern's default complexity (informational
  only, since the plugin won't execute this SRD)

#### 5.7 Scope Detection

Determine what the change applies to.

**For base_rate_increase:**
```
"all base rates" / "across the board" / no territory qualifier
  → scope = "all_territories"

"Territory 1 and 5" / "territories 1-5" / specific territory list
  → scope = "specific_territories"
    territories = [1, 5]  (or [1, 2, 3, 4, 5] for ranges)

"Territory 1: +5%, Territory 2: +3%" / different rates per territory
  → This is NOT a single SRD. Split into one SRD per distinct multiplier.
    srd-001: scope = "specific_territories", territories = [1], factor = 1.05
    srd-002: scope = "specific_territories", territories = [2], factor = 1.03
    OR: if there are many territories with different factors, create one SRD
    with method = "explicit" and a values map (see below)
```

**For factor_table_change:**
```
scope = the specific Case value (e.g., case_value: 5000)
If "all deductible factors" → scope = "all_cases" and list known case values if possible
```

**For LOB scope (multi-LOB workflows):**
```
"all LOBs" / "all hab LOBs" / no LOB qualifier
  → lob_scope = "all"

"Home and Condo only" / specific LOBs listed
  → lob_scope = "specific"
    target_lobs = ["Home", "Condo"]

If not stated and this is a multi-LOB workflow, default to "all" but confirm:
```

```
[Intake] This is a multi-LOB hab workflow (Home, Condo, Tenant, FEC, Farm, Seasonal).
         Does the 5% liability increase apply to ALL 6 LOBs, or only specific ones?
```

#### 5.8 Ambiguity Flags

Mark any SRD where the input text contains uncertain language. Set
`ambiguity_flag: true` and include an `ambiguity_note` explaining what was unclear.

**Triggers:**
- "approximately", "about", "roughly", "around" + a number
- "TBD", "to be determined", "to be confirmed"
- "possibly", "maybe", "if applicable"
- Contradictory statements within the input
- Missing required parameters that could not be extracted

**Example:**

```yaml
# SRD with ambiguity
id: "srd-003"
title: "Increase rates by approximately 5%"
type: "base_rate_increase"
complexity: "SIMPLE"
method: "multiply"
factor: 1.05
ambiguity_flag: true
ambiguity_note: "Source says 'approximately 5%'. Using exactly 1.05. Developer should confirm."
```

When an ambiguity is detected, tell the developer:

```
[Intake] The source says "approximately 5%". I'll use exactly 1.05 as the multiplier.
         If this should be a different value, tell me now.
         Otherwise, you'll see the exact before/after values at plan approval (Gate 1).
```

### Step 6: Build the SRD Records

**Action:** Assemble the complete SRD record for each change item using the
classification, parameters, and flags from Step 5.

6.1. For each change item, build a YAML record with these fields:

```yaml
id: "srd-NNN"                      # Sequential, zero-padded to 3 digits
title: "..."                        # Human-readable summary (max 80 chars)
type: "..."                         # Pattern type from Step 5.2
complexity: "SIMPLE|MEDIUM|COMPLEX" # From Step 5.6
method: "multiply|explicit"         # From Step 5.4 (only for rate changes)
scope: "..."                        # From Step 5.7
lob_scope: "all|specific"           # Which LOBs this applies to
target_lobs: [...]                  # Only if lob_scope = "specific"
dat_file_warning: false|true        # From Step 5.5
ambiguity_flag: false|true          # From Step 5.8
source_text: "..."                  # Exact text from the input that produced this SRD
source_location: "..."              # Where in the source (e.g., "pasted text, item 2")

# Pattern-specific fields (varies by type):
factor: 1.05                        # For base_rate_increase
rounding: "banker|none"             # From Step 5.4
case_value: 5000                    # For factor_table_change
old_value: -0.20                    # For factor_table_change / included_limits
new_value: -0.22                    # For factor_table_change / included_limits
# ... other fields as defined in the pattern YAML
```

6.2. **Title construction rules:**
- Be specific: "Increase hab liability premiums by 5%" not "Rate change"
- Include the key parameters: "Change $5000 deductible factor from -20% to -22%"
- For DAT-file changes, prefix with "[DAT FILE]": "[DAT FILE] Increase hab dwelling base rates by 5%"
- Keep under 80 characters

6.3. **Verify completeness.** For each SRD, check that all REQUIRED parameters
from the pattern YAML are populated. If any are missing and could not be inferred
from the input, enter interactive mode to ask.

### Step 7: Present the Parsed Results to the Developer

**Action:** Show the developer a formatted summary of all parsed SRDs for
confirmation before writing to disk.

7.1. Present the summary in this format:

```
[Intake] Parsed {N} change(s) from your input:

  SRD-001: base_rate_increase — all territories x 1.05 (SIMPLE)
           "Increase all base rates by 5%"
           WARNING: dat_file_warning = true — hab dwelling base rates are in DAT files

  SRD-002: factor_table_change — $5000 deductible: -0.20 → -0.22 (SIMPLE)
           "Change the $5000 deductible factor from -20% to -22%"

  SRD-003: factor_table_change — $2500 deductible: -0.15 → -0.17 (SIMPLE)
           "Change the $2500 deductible factor from -15% to -17%"

  SRD-004: base_rate_increase — all territories x 1.03 (SIMPLE)
           "Increase all liability premiums by 3%"
           Applies to: Array6 liability premium tables in mod_Common

  Totals: 4 SRDs (3 SIMPLE, 0 MEDIUM, 0 COMPLEX)
          1 DAT-file warning (SRD-001 — will be flagged for manual handling)
          0 ambiguities

  Does this look correct? I'll proceed to write the change spec.
  If anything is wrong or missing, tell me now.
```

7.2. **Wait for developer confirmation.** The developer may:
- **Confirm:** "yes" / "looks good" / "proceed" → go to Step 8
- **Correct:** "SRD-002 should be -0.25, not -0.22" → update the SRD, re-present
- **Add:** "I forgot, also change the $1000 deductible to -0.10" → add a new SRD, re-present
- **Remove:** "Remove SRD-001, I'll handle that manually" → remove the SRD, re-present
- **Re-classify:** "SRD-004 is about endorsement premiums, not liability" → re-classify, re-present
- **Ask questions:** "What's the difference between base rates and liability premiums?" → explain, then re-present

7.3. **On correction:** Update the affected SRD(s), renumber if items were
added/removed, and re-present the full summary. Continue the confirm/correct loop
until the developer approves.

### Step 8: Write Output Files

**Action:** Once the developer confirms, write the output files to the
`parsed/` directory of the workflow.

8.1. **Ensure directory structure exists:**
```
.iq-workstreams/changes/{workstream}/parsed/
.iq-workstreams/changes/{workstream}/parsed/srds/
```

8.2. **Write `parsed/change_spec.yaml`:**

```yaml
# Generated by Intake Agent
# Source: conversational input
# Date: 2026-02-26

carrier: "Portage Mutual"
province: "SK"
province_name: "Saskatchewan"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
lob_category: "hab"
effective_date: "20260101"
ticket_ref: "DevOps 24778"
srd_count: 4

# Portage Mutual example -- LOB list comes from config.yaml
target_folders:
  - path: "Saskatchewan/Home/20260101"
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

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

srds:
  - id: "srd-001"
    title: "[DAT FILE] Increase hab dwelling base rates by 5%"
    type: "base_rate_increase"
    complexity: "SIMPLE"
    scope: "all_territories"
    lob_scope: "all"
    method: "multiply"
    factor: 1.05
    rounding: "auto"
    dat_file_warning: true

  - id: "srd-002"
    title: "Change $5000 deductible factor from -0.20 to -0.22"
    type: "factor_table_change"
    complexity: "SIMPLE"
    lob_scope: "all"
    case_value: 5000
    old_value: -0.20
    new_value: -0.22
    dat_file_warning: false

  - id: "srd-003"
    title: "Change $2500 deductible factor from -0.15 to -0.17"
    type: "factor_table_change"
    complexity: "SIMPLE"
    lob_scope: "all"
    case_value: 2500
    old_value: -0.15
    new_value: -0.17
    dat_file_warning: false

  - id: "srd-004"
    title: "Increase hab liability premiums by 3%"
    type: "base_rate_increase"
    complexity: "SIMPLE"
    scope: "all_territories"
    lob_scope: "all"
    method: "multiply"
    factor: 1.03
    rounding: "auto"
    dat_file_warning: false
```

8.3. **Write individual SRD files** to `parsed/srds/srd-NNN.yaml`:

```yaml
# File: parsed/srds/srd-001.yaml
id: "srd-001"
title: "[DAT FILE] Increase hab dwelling base rates by 5%"
type: "base_rate_increase"
complexity: "SIMPLE"
scope: "all_territories"
lob_scope: "all"
method: "multiply"
factor: 1.05
rounding: "auto"
dat_file_warning: true
source_text: "Increase all base rates by 5%"
source_location: "pasted text, item 1"
ambiguity_flag: false
```

```yaml
# File: parsed/srds/srd-002.yaml
id: "srd-002"
title: "Change $5000 deductible factor from -0.20 to -0.22"
type: "factor_table_change"
complexity: "SIMPLE"
lob_scope: "all"
case_value: 5000
old_value: -0.20
new_value: -0.22
dat_file_warning: false
source_text: "Change the $5000 deductible factor from -20% to -22%"
source_location: "pasted text, item 2"
ambiguity_flag: false
```

```yaml
# File: parsed/srds/srd-003.yaml
id: "srd-003"
title: "Change $2500 deductible factor from -0.15 to -0.17"
type: "factor_table_change"
complexity: "SIMPLE"
lob_scope: "all"
case_value: 2500
old_value: -0.15
new_value: -0.17
dat_file_warning: false
source_text: "Change the $2500 deductible factor from -15% to -17%"
source_location: "pasted text, item 3"
ambiguity_flag: false
```

```yaml
# File: parsed/srds/srd-004.yaml
id: "srd-004"
title: "Increase hab liability premiums by 3%"
type: "base_rate_increase"
complexity: "SIMPLE"
scope: "all_territories"
lob_scope: "all"
method: "multiply"
factor: 1.03
rounding: "auto"
dat_file_warning: false
source_text: "Increase all liability premiums by 3%"
source_location: "pasted text, item 4"
ambiguity_flag: false
```

8.4. **Validate all written YAML files** before proceeding:

For each file written (change_spec.yaml, each srd-NNN.yaml), verify it is valid YAML:
```bash
python -c "import yaml; yaml.safe_load(open('parsed/change_spec.yaml')); print('OK')"
```
If validation fails, the file has a structural error (bad indentation, unclosed quotes).
Fix the error and re-write the file. Do NOT proceed to Step 9 with malformed YAML —
the Decomposer will fail if it reads broken YAML.

8.5. **Do NOT update `manifest.yaml`** — the orchestrator handles manifest updates
after each agent completes (see skills/iq-plan/SKILL.md Manifest Update Protocol). The summary
counts (srd_count, dat_file_warnings, ambiguities) are derivable from the output
files you already wrote (change_spec.yaml, srd-*.yaml).

### Step 9: Report Completion

**Action:** Confirm to the developer (and the pipeline) that Intake is done.

9.1. Print the completion message:

```
[Intake] COMPLETE. Wrote 4 SRDs to parsed/.
         - change_spec.yaml (master spec)
         - srds/srd-001.yaml through srd-004.yaml (individual SRDs)
         - 1 SRD flagged as DAT-file (out of plugin scope)
         - 0 ambiguities

         Next: Decomposer will break these into atomic operations.
```

9.2. The Decomposer agent reads `parsed/change_spec.yaml` and the individual
SRD files from `parsed/srds/` to begin its work. No further Intake action needed.

---

## WORKED EXAMPLES

These examples demonstrate the full Intake flow for common scenarios.

### Example A: Simple Auto Rate Increase

**Input (developer types):**
```
AB Auto, effective 2026-01-01. Increase all base rates by 5%.
```

**Context from manifest:** province = AB, lobs = [Auto], lob_category = auto

**Classification:**
- "base rates" + "5%" → base_rate_increase
- lob_category = auto → dat_file_warning = false (auto base rates are in VB code)
- method = multiply, factor = 1.05
- rounding = auto (Analyzer determines banker vs none after reading actual code)
- scope = all_territories
- complexity = SIMPLE

**Output SRD:**
```yaml
id: "srd-001"
title: "Increase AB Auto base rates by 5%"
type: "base_rate_increase"
complexity: "SIMPLE"
scope: "all_territories"
lob_scope: "all"
method: "multiply"
factor: 1.05
rounding: "auto"
dat_file_warning: false
source_text: "Increase all base rates by 5%"
source_location: "pasted text"
ambiguity_flag: false
```

### Example B: Factor Table Changes (Multiple Cases)

**Input (developer types):**
```
NB Home 20260701. Update deductible factors:
- $500: 0 (no change)
- $1000: -0.075 → -0.08
- $2500: -0.15 → -0.16
- $5000: -0.20 → -0.22
```

**Context from manifest:** province = NB, lobs = [Home], lob_category = hab

**Classification:**
- "deductible factors" → factor_table_change
- $500 says "no change" → skip, do not create an SRD
- Three distinct case values changing → 3 SRDs
- All are method = explicit, rounding = none (factor values are NEVER rounded)
- complexity = SIMPLE (each is a single value change)

**Output SRDs:**
```yaml
# method and rounding omitted for explicit old→new factor changes

# srd-001
id: "srd-001"
title: "Change $1000 deductible factor from -0.075 to -0.08"
type: "factor_table_change"
complexity: "SIMPLE"
lob_scope: "all"
case_value: 1000
old_value: -0.075
new_value: -0.08
dat_file_warning: false
source_text: "$1000: -0.075 → -0.08"
source_location: "pasted text, item 2"
ambiguity_flag: false

# srd-002
id: "srd-002"
title: "Change $2500 deductible factor from -0.15 to -0.16"
type: "factor_table_change"
complexity: "SIMPLE"
lob_scope: "all"
case_value: 2500
old_value: -0.15
new_value: -0.16
dat_file_warning: false
source_text: "$2500: -0.15 → -0.16"
source_location: "pasted text, item 3"
ambiguity_flag: false

# srd-003
id: "srd-003"
title: "Change $5000 deductible factor from -0.20 to -0.22"
type: "factor_table_change"
complexity: "SIMPLE"
lob_scope: "all"
case_value: 5000
old_value: -0.20
new_value: -0.22
dat_file_warning: false
source_text: "$5000: -0.20 → -0.22"
source_location: "pasted text, item 4"
ambiguity_flag: false
```

### Example C: Mixed Changes with DAT File Warning

**Input (developer types):**
```
SK Hab Jan 2026 (DevOps 24778):
1. Increase dwelling base rates by 5%
2. Increase liability premiums by 3%
3. Change $5000 deductible factor from -20% to -22%
```

**Context from manifest:** province = SK, lobs = [Home, Condo, Tenant, FEC, Farm, Seasonal], lob_category = hab

**Classification process:**

Item 1: "dwelling base rates" + "5%" + lob_category=hab
→ base_rate_increase, but "dwelling base rates" in hab = DAT file
→ dat_file_warning = true
→ IMMEDIATELY tell developer about DAT file issue
→ Developer chooses to keep SRD for tracking

Item 2: "liability premiums" + "3%" + lob_category=hab
→ base_rate_increase (liability premiums are Array6 in mod_Common)
→ dat_file_warning = false (liability premiums are in VB code)
→ method = multiply, factor = 1.03, rounding = auto

Item 3: "$5000 deductible factor" + old/new values
→ factor_table_change
→ dat_file_warning = false
→ method = explicit, rounding = none

**Presentation:**
```
[Intake] Parsed 3 changes from your input:

  SRD-001: base_rate_increase — all territories x 1.05 (SIMPLE)
           "Increase dwelling base rates by 5%"
           *** DAT FILE WARNING: Hab dwelling base rates are in DAT files,
               not VB code. This plugin cannot edit them. ***

  SRD-002: base_rate_increase — all territories x 1.03 (SIMPLE)
           "Increase liability premiums by 3%"
           Targets: Array6 liability premium tables in mod_Common_SKHab

  SRD-003: factor_table_change — $5000 deductible: -0.20 → -0.22 (SIMPLE)
           "Change $5000 deductible factor from -20% to -22%"

  Totals: 3 SRDs (3 SIMPLE), 1 DAT-file warning
```

### Example D: Ambiguous Input Requiring Clarification

**Input (developer types):**
```
SK Home — increase all rates by about 5%
```

**Classification process:**

Problem 1: "all rates" is ambiguous — could mean base rates, liability premiums,
factor tables, or everything.

Problem 2: "about 5%" is ambiguous — is it exactly 5% or approximately?

Problem 3: lob_category = hab, and "rates" could include DAT-file-based dwelling
base rates.

**Interactive clarification sequence:**

```
[Intake] I need to clarify a few things about "increase all rates by about 5%":

  1. WHICH RATES? In SK Home (habitational), there are several types:
     a) Dwelling base rates — stored in DAT files (NOT editable by this plugin)
     b) Liability premiums — Array6 values in mod_Common (editable)
     c) Deductible/discount factors — Select Case values in mod_Common (editable)
     d) Endorsement premiums — values in Option_*.vb files (editable)

     Which of these should get the 5% increase?

> Just the liability premiums

[Intake] 2. EXACT MULTIPLIER? The source says "about 5%". I'll use exactly 1.05.
            Is that correct, or should it be a different number?

> Yes, exactly 5%

[Intake] Got it. Parsed 1 change:

  SRD-001: base_rate_increase — all territories x 1.05 (SIMPLE)
           "Increase liability premiums by 5%"
           Targets: Array6 liability premium tables in mod_Common_SKHab

  Does this look correct?
```

---

## SPECIAL CASES

### Case 1: "No change" items in a list

When the developer lists values with some marked "no change" or "(unchanged)",
do NOT create SRDs for those items. Only create SRDs for actual changes.

```
Input: "Update deductible factors:
        $500: 0 (no change)
        $1000: -0.075 → -0.08
        $2500: -0.15 (no change)
        $5000: -0.20 → -0.22"

Result: 2 SRDs (for $1000 and $5000 only)
```

### Case 2: Grouped instruction vs. individual items

If the developer says "increase all deductible factors by 10%", create ONE SRD
with method=multiply, scope=all_cases, factor=1.10. Do NOT split into one SRD
per Case value — that is the Decomposer's job.

But if the developer gives individual old→new values for each Case, create
individual SRDs because each has its own explicit target value.

If the developer provides individual old→new values for each Case value,
create individual SRDs (one per Case), even if they frame it as "update all."
The distinction is: multiplier instruction = 1 SRD, explicit per-value list = N SRDs.

### Case 3: Contradictory instructions

If two items in the input contradict each other, flag both and ask:

```
[Intake] I found contradictory instructions:
         Item 2: "Change $5000 deductible factor to -0.22"
         Item 5: "Change $5000 deductible factor to -0.25"

         Which value should I use for the $5000 deductible?
```

### Case 4: Change mentions a specific function name

If the developer names a specific function (e.g., "update SetDisSur_Deductible"),
record the function name in `target_function_hint` on the SRD. The Decomposer/Analyzer
will use this as a search hint, but still verifies it exists.

```yaml
target_function_hint: "SetDisSur_Deductible"   # Developer-provided hint
```

### Case 5: Developer provides a table of territory-specific values

If the input contains a table with different values per territory:

```
Territory 1: $233 → $245
Territory 2: $274 → $288
Territory 3: $319 → $335
```

Determine if these are consistent with a single multiplier:
- $233 * 1.05 = $244.65 → rounds to $245 (matches)
- $274 * 1.05 = $287.70 → rounds to $288 (matches)
- $319 * 1.05 = $334.95 → rounds to $335 (matches)

If all values match a single multiplier within rounding tolerance (banker's rounding):
→ Create ONE SRD with method=multiply, factor=1.05

If values do NOT match a single multiplier:
→ Create ONE SRD with method=explicit and a values map:

```yaml
method: "explicit"
explicit_values:
  1: 245
  2: 288
  3: 340    # This doesn't match 319 * 1.05 = 335
```

And tell the developer:

```
[Intake] I checked if these territory values match a single multiplier.
         Most match 1.05x, but Territory 3 ($319 → $340) gives 1.0658x.

         Options:
           a) Use explicit values as you provided them
           b) Territory 3 should be $335 (= $319 * 1.05, rounded) — use 1.05 multiplier for all
           c) Something else
```

### Case 6: Multiple LOBs with different changes per LOB

If some changes apply to all LOBs and others to specific LOBs:

```
Input: "For all SK hab LOBs:
        - Increase liability premiums by 3%
        For Home and Condo only:
        - Add water damage endorsement at $75"
```

Create SRDs with appropriate `lob_scope`:

```yaml
# srd-001: applies to all
lob_scope: "all"

# srd-002: Home and Condo only
lob_scope: "specific"
target_lobs: ["Home", "Condo"]
```

---

## KEY RESPONSIBILITIES (Summary)

- Accept pasted text or read from `input/source.md`
- Identify individual change items and classify their type and complexity
- Detect DAT-file-based rate changes early (hab dwelling base rates are in DAT files, not VB code)
- Ask clarifying questions when input is ambiguous (interactive mode)
- Separate data changes (automatable) from logic changes (need review)
- Detect rounding mode: multiply+round vs explicit values
- Factor values (like `dblFactor = -0.05`) are NEVER rounded
- Match each change item to a pattern from `patterns/*.yaml`
- Write `input/source.md` with the original input text
- Save each SRD as both an entry in `change_spec.yaml` and its own `srds/srd-NNN.yaml` file
- Present results to developer for confirmation before writing files
- Signal completion to orchestrator (orchestrator updates manifest.yaml)

## Complexity Classification

| Classification | Criteria | Downstream Agents |
|---------------|---------|-------------------|
| SIMPLE | Single Array6 or Select Case value change | Rate Modifier only |
| MEDIUM | Multiple related value changes or new option file | Rate Modifier + possibly Logic Modifier |
| COMPLEX | New functions, conditionals, cross-file logic | Rate Modifier + Logic Modifier |

## Edge Cases

1. **Ambiguous percentage:** "approximately 5%" -- flag and ask developer to confirm exact multiplier
2. **DAT file rates:** Hab dwelling base rate changes -- set `dat_file_warning: true`, tell developer this is outside plugin scope
3. **Multiple LOBs with different changes:** Some SRDs apply to all LOBs, others to specific ones -- tag each SRD with its scope
4. **Missing information:** If the input says "update deductible factors" but doesn't specify which values, enter interactive mode and ask
5. **Conflicting instructions:** Two statements in the source contradict each other -- flag both and ask developer
6. **Unrecognized change type:** Change doesn't match any known pattern -- classify as COMPLEX, flag for review
7. **No changes needed:** Source document describes changes already applied -- report "0 SRDs, values already match"
8. **Mixed input:** Developer provides both a file and additional verbal instructions -- merge into unified spec

---

## NOT YET IMPLEMENTED (Future Sections)

The following sections will be added in later sprints:

- **PDF Parsing (Sprint 4):** Extract change tables from Summary of Changes PDFs
- **Excel Parsing (Sprint 4):** Parse rate tables from Excel spreadsheets
- **Attachment Handling:** Copy PDF/Excel files to `input/attachments/`
- **Multi-Format Merge:** Combine PDF + verbal corrections into unified spec
- **OCR Fallback:** Handle scanned PDFs where text extraction fails

<!-- IMPLEMENTATION: Phase 03 -->
