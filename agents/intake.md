# Agent: Intake

## Purpose

Parse any ticket input into a structured set of change requests. Each change
request represents one discrete thing the ticket is asking for — described in
plain language with extracted concrete values, but NO forced classification into
predefined types.

The Intake agent accepts any input format: pasted text, ADO ticket content
(from fetch-ticket.sh), Jira exports, plain developer notes, formal "Summary of
Changes" documents, or conversational descriptions. It extracts WHAT needs to
change and captures concrete values (percentages, dollar amounts, old→new values)
without forcing the change into a category. Downstream agents (Discovery, Analyzer,
Decomposer) determine HOW to implement it based on actual code understanding.

## Pipeline Position

```
[INPUT] --> INTAKE --> Discovery --> Analyzer --> Decomposer --> Planner --> [GATE 1]
            ^^^^^^
```

- **Upstream:** `/iq-plan` skill (provides target folders, raw input)
- **Downstream:** Discovery agent (uses change requests to target code tracing),
  then Decomposer (forms intents from change requests + code understanding)

## Input Schema

The Intake agent receives its input from the `/iq-plan` skill via the workflow
directory and conversational interaction.

```yaml
# Input arrives as one of the following:
# 1. Conversational: developer types or pastes into chat
# 2. File-based: developer says "I pasted it in input/" → read input/source.md
# 3. ADO ticket: fetched via fetch-ticket.sh → input/ticket-data/llm-context.md
# 4. Any other format: the agent reads and interprets it

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

### Ticket Understanding (from Step 0)

```markdown
# File: parsed/ticket_understanding.md
# Human-readable ticket comprehension document.
# Written BEFORE CR extraction. Confirmed by developer.
# See Step 0.3 for full structure.
```

### Change Requests (from Steps 3-6)

```yaml
# File: parsed/change_requests.yaml
carrier: "Portage Mutual"
province: "SK"
province_name: "Saskatchewan"
lobs: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]
lob_category: "hab"                    # "hab" | "auto" | "mixed"
effective_date: "20260101"
ticket_ref: "DevOps 24778"            # Optional, extracted from input
request_count: 4

target_folders:
  - path: "Saskatchewan/Home/20260101"
    vbproj: "Cssi.IntelliQuote.PORTSKHOME20260101.vbproj"
  # ... (carried forward from manifest)

shared_modules:
  - file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
    shared_by: ["Home", "Condo", "Tenant", "FEC", "Farm", "Seasonal"]

requests:
  - id: "cr-001"
    title: "Increase liability premiums by 3%"
    description: "All liability bundle premiums should increase by 3% across all territories"
    source_text: "Increase all liability premiums by 3%"
    source_location: "pasted text, item 4"

    # Extracted concrete values (whatever is available from the text)
    extracted:
      percentage: 3.0
      factor: 1.03              # Computed: 1 + (3/100)
      method: "multiply"        # "multiply" | "explicit" | null
      scope: "all_territories"
      lob_scope: "all"

    # Domain intelligence (hints for downstream agents — NOT gates)
    domain_hints:
      keyword_matches: ["liability", "premium", "increase"]
      glossary_match: "GetLiabilityBundlePremiums"    # From codebase glossary, if matched
      glossary_confidence: "high"                      # "high" | "medium" | null
      involves_rates: true
      involves_percentages: true
      involves_new_code: false
      rounding_hint: null        # "banker" if developer said "round to nearest dollar"

    dat_file_warning: false
    ambiguity_flag: false
    complexity_estimate: "SIMPLE"  # SIMPLE | MEDIUM | COMPLEX (estimate, not gate)

  - id: "cr-002"
    title: "Change $5000 deductible factor from -20% to -22%"
    description: "Update the $5000 deductible discount factor"
    source_text: "Change the $5000 deductible factor from -20% to -22%"
    source_location: "pasted text, item 2"

    extracted:
      case_value: 5000
      old_value: -0.20
      new_value: -0.22
      method: "explicit"
      scope: null
      lob_scope: "all"
      target_function_hint: null  # Set if developer names a function

    domain_hints:
      keyword_matches: ["deductible", "factor"]
      glossary_match: "SetDisSur_Deductible"
      glossary_confidence: "medium"
      involves_rates: false
      involves_percentages: false
      involves_new_code: false

    dat_file_warning: false
    ambiguity_flag: false
    complexity_estimate: "SIMPLE"

  - id: "cr-003"
    title: "Add sewer backup coverage at $50,000"
    description: "New sewer backup coverage tier at $50,000"
    source_text: "Add $50,000 sewer backup coverage option"
    source_location: "pasted text, item 5"

    extracted:
      coverage_amount: 50000
      premium: null               # Not specified in ticket
      method: null
      lob_scope: "all"

    domain_hints:
      keyword_matches: ["sewer backup", "coverage", "add"]
      glossary_match: "GetSewerBackupPremium"
      glossary_confidence: "high"
      involves_rates: false
      involves_percentages: false
      involves_new_code: true

    dat_file_warning: false
    ambiguity_flag: true
    ambiguity_note: "Premium amount for $50K tier not specified in ticket"
    complexity_estimate: "MEDIUM"
```

```yaml
# File: parsed/requests/cr-NNN.yaml (one file per change request)
id: "cr-001"
title: "Increase liability premiums by 3%"
description: "All liability bundle premiums should increase by 3% across all territories"
source_text: "Increase all liability premiums by 3%"
source_location: "pasted text, item 4"
extracted:
  percentage: 3.0
  factor: 1.03
  method: "multiply"
  scope: "all_territories"
  lob_scope: "all"
domain_hints:
  keyword_matches: ["liability", "premium", "increase"]
  glossary_match: "GetLiabilityBundlePremiums"
  glossary_confidence: "high"
  involves_rates: true
  involves_percentages: true
  involves_new_code: false
  rounding_hint: null
dat_file_warning: false
ambiguity_flag: false
complexity_estimate: "SIMPLE"
```

---

## EXECUTION STEPS

### Prerequisites

Before starting, confirm the following exist and are readable:

1. The workflow directory at `.iq-workstreams/changes/{workstream-name}/`
2. The `manifest.yaml` inside that directory (provides province, LOBs, target folders)
3. The `.iq-workstreams/config.yaml` (provides carrier info, province codes, hab flags)

If any of these are missing, STOP and report:
```
[Intake] Cannot proceed — missing required file: {path}
         Was /iq-init run? Is the workstream set up via /iq-plan?
```

### Step 0: Deep Ticket Comprehension (MANDATORY for ADO tickets)

**Purpose:** Before extracting structured change requests, demonstrate a thorough
understanding of the ticket. This step reads EVERYTHING — full description, ALL
comments, ALL image attachments — and presents a human-readable understanding
document for the developer to confirm. This catches misunderstandings BEFORE the
pipeline wastes time extracting the wrong CRs.

**When to run this step:**
- **ADO tickets (auto-fetched):** ALWAYS run. The full ticket data is available.
- **Pasted text / manual input:** Run a LIGHTER version (no comment/attachment
  scanning, but still present the understanding for confirmation).

#### Step 0.1: Gather ALL Ticket Content

**For auto-fetched ADO tickets:**

The orchestrator has moved the full ticket data to `input/ticket-data/`. Read the
FULL context, not the brief:

1. Read `input/ticket-data/llm-context.md` (contains ALL comments, not just first 3).
   If this file does not exist, fall back to `input/ticket-data/llm-context-brief.md`.
   If neither exists, fall back to `input/source.md` and skip to Step 0.1c.

2. Read `input/ticket-data/llm-context.json` to get structured comment data and
   attachment metadata. This gives you:
   - `ticket.markdown` — full ticket description
   - `ticket.reproStepsMarkdown` — repro steps (if present)
   - `comments[]` — ALL comments, each with `.author`, `.createdDate`, `.markdown`
   - `attachments[]` — list of downloaded attachments with `.localPath`

3. **Read ALL image attachments:** Scan `input/ticket-data/attachments/` for image
   files (`.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`). For EACH image found,
   use the Read tool to view the image. Claude Code is multimodal — it can see and
   interpret screenshots, rate tables, annotated diagrams, and Excel/PDF screenshots.

   For each image, extract:
   - What the image shows (screenshot of a UI, rate table, error message, etc.)
   - Any rate values, numbers, or data visible in the image
   - Any annotations, highlights, or circled areas
   - How this image relates to the ticket description

   **Image interpretation is CRITICAL.** Actuarial tickets frequently include:
   - Screenshots of rate comparison spreadsheets (old vs new values)
   - Screenshots of the IntelliQuote UI showing incorrect behavior
   - Scanned or photographed paper rate schedules
   - Annotated screenshots highlighting what needs to change

**For pasted text / manual input (Step 0.1c):**

Read `input/source.md`. If `input/attachments/` has image files, read those too.

#### Step 0.2: Synthesize Understanding

Analyze ALL gathered content and produce a comprehensive understanding document.
Think step-by-step about:

1. **What is the ticket actually asking for?** Read the description AND the comments.
   Comments often contain:
   - Clarifications that change or refine the original description
   - Corrections to values in the description
   - Additional requirements added after the ticket was created
   - Developer discussions that reveal the real intent behind vague descriptions
   - Links to actuarial memos or rate filings with the actual numbers

2. **What do the images/screenshots reveal?** Screenshots often contain the most
   precise information — exact values, column headers, row labels that tell you
   which functions and territories are affected.

3. **What is the business context?** Why is this change being made? Regulatory
   filing? Competitive adjustment? Bug fix? This context helps downstream agents
   make better decisions about scope and approach.

4. **What is the scope?** Which provinces, LOBs, effective dates are affected?
   Sometimes the ticket description says one thing but comments narrow or expand
   the scope.

5. **Are there contradictions?** Description says X but a comment says Y. The
   most RECENT comment or the most senior person's comment usually wins, but
   flag contradictions for the developer.

#### Step 0.3: Write Ticket Understanding Document

The ticket understanding document shows the **reasoning journey** — not just a
polished summary, but the step-by-step evidence trail that led to each conclusion.
The developer sees exactly what came from the description, what was corrected by
comments, and what was extracted from images. This transparency catches
misunderstandings early AND gives downstream agents (Discovery, Analyzer, Planner)
a rich evidence chain to link code changes back to ticket evidence.

Write `parsed/ticket_understanding.md` with this structure:

```markdown
# Ticket Understanding: {ticket_ref or "Ad-hoc Request"}

## 1. What the Ticket Description Says
{Walk through the ticket description in order. Quote specific values,
percentages, and dollar amounts directly from the text. Present each
distinct ask as a numbered item:

1. "{Quoted text from description}" — This is asking for {interpretation}.
   Key values: {extracted numbers, percentages, dollar amounts}

2. "{Quoted text}" — This means {interpretation}.
   Key values: {extracted numbers}

If the description is vague or uses business jargon, say so:
"The description says 'update rates per filing' but does not specify
which rates or by how much. Looking to comments for clarification."}

## 2. What the Comments Add ({N} total)
{Read ALL comments chronologically. Show how the understanding EVOLVED.
This is the critical section — comments frequently override the description.

**Comment 1** — {Author} ({date}):
> "{Quoted excerpt}"
Impact on understanding: {what this changes or confirms}

**Comment 3** — {Author} ({date}):
> "{Quoted excerpt}"
Impact on understanding: **CORRECTION** — Description said 5% but this
comment says 3%. Using 3% going forward.

**Comment 5** — {Author} ({date}):
> "{Quoted excerpt}"
Impact on understanding: Adds new requirement not in original description.

If no comments exist: "No comments on this ticket."

**Net effect of comments:** {1-2 sentences summarizing what the comments
changed vs the original description. e.g., "Comments corrected the percentage
from 5% to 3% and added a deductible factor change not in the description."}}

## 3. What the Screenshots/Images Show ({N} found)
{For EACH image, describe what it contains and what data was extracted:

**Image 1:** {filename}
Shows: {description — e.g., "Excel screenshot of rate comparison table"}
Extracted values:
  - Territory 1: $233 → $245
  - Territory 2: $274 → $288
  - ...
Relevance: {how this connects to the ticket asks}

**Image 2:** {filename}
Shows: {description}
Extracted values: {data}

If no images: "No image attachments found."}

## 4. My Understanding (Synthesized)
{Based on the reasoning journey above (description → comments → images),
here is what I believe needs to change. Each item traces back to its
evidence source:

1. **{Change description}**
   - Source: {which evidence — "ticket description item 2, confirmed by
     comment 3 from John Smith" or "screenshot Image 1, row 5" or
     "comment 5 (not in original description)"}
   - Specific values: {old → new, or percentage, or new values}
   - Scope: {all territories / specific territories / specific LOBs}
   - Confidence: {HIGH/MEDIUM/LOW for this specific item}

2. **{Change description}**
   - Source: {evidence trail}
   - ...

**What changed from description to final understanding:**
{Explicitly call out any differences between what the description said
and what the final understanding is after incorporating comments/images.
e.g., "Description said 5% increase; Comment 3 corrected to 3%.
Description did not mention deductible changes; Comment 5 added them."
If nothing changed: "Comments and images confirmed the description as-is."}}

## 5. Ambiguities & Open Questions
{Things that are unclear or contradictory. Things the developer needs to
clarify before we can proceed. If none: "None — the ticket is clear."}

## 6. Confidence Assessment
{HIGH / MEDIUM / LOW}
{Brief explanation of confidence level. HIGH = ticket is clear, values are
explicit, comments confirm description. MEDIUM = most things clear but some
gaps or minor contradictions. LOW = significant ambiguity, contradictions
between description and comments, or missing information.}
```

**Why this structure matters:** By showing the journey (description → comments →
images → synthesis), the developer can instantly see WHERE each value came from
and catch errors like "you used the value from comment 2 but comment 5 superseded
it." The synthesis section (4) makes it easy to confirm the final understanding
without re-reading everything. Downstream agents use the evidence trails in
section 4 to populate `source_location` and `evidence_refs` on each CR.

#### Step 0.4: Present Understanding to Developer

Present the ticket understanding document to the developer:

```
[Intake] TICKET UNDERSTANDING
=================================

{Full content of parsed/ticket_understanding.md}

=================================

Does this match your understanding of the ticket?
  - "yes" / "correct" → I'll proceed to extract structured change requests
  - Tell me what I got wrong → I'll update my understanding
  - "show me comment N" → I'll show you the full comment text
```

**Wait for developer confirmation.** The developer may:
- **Confirm:** "yes" / "looks right" / "correct" → proceed to Step 1
- **Correct:** "No, the ticket is actually about X" or "You missed the part
  about Y" or "Comment 5 supersedes the description" → update the understanding
  document, re-present, wait for confirmation again
- **Add context:** "Also, the actuary mentioned Z in a meeting" → incorporate
  and re-present
- **Ask to see more:** "Show me all the comments" or "What does image 3 show?"
  → display the requested content, return to confirmation prompt

**CRITICAL:** Do NOT proceed to Step 1 until the developer confirms the
understanding is correct. This is the most important checkpoint in the pipeline.

#### Step 0.5: Save Confirmed Understanding

Once the developer confirms:
1. Update `parsed/ticket_understanding.md` with any corrections (mark as confirmed)
2. Append `\n\n## Developer Confirmation\nConfirmed by developer at {timestamp}.\n`
   and any corrections or additional context they provided.
3. Proceed to Step 1 using the CONFIRMED understanding to guide CR extraction.

**For subsequent steps:** When extracting CRs in Steps 3-4, reference the confirmed
ticket understanding. If the understanding says "3% increase per comment by John"
but the raw text says "5%", use the confirmed understanding (the developer agreed
that 3% is correct).

---

### Step 1: Receive and Record the Raw Input

**Action:** Accept the developer's description of changes. Any format.

**NOTE:** If Step 0 ran (ADO ticket), the raw input is already saved and the ticket
understanding is confirmed. Step 1 ensures the raw input is recorded in `source.md`
and extracts the ticket reference. For non-ADO inputs, this is where the raw text
is first captured.

1.1. The input arrives in one of these ways:
   - **Conversational:** The developer types or pastes the changes directly into the chat
   - **File-based:** The developer says "I pasted it in input/" — read `.iq-workstreams/changes/{workstream}/input/source.md`
   - **ADO ticket:** If the workstream key is numeric AND the orchestrator has already
     fetched the ticket, the full ticket data is at `input/ticket-data/`. Read
     `input/ticket-data/llm-context.md` for the full context (all comments, all
     metadata). Fall back to `input/ticket-data/llm-context-brief.md` if the full
     version is unavailable.
   - **Structured document:** PDF, Excel, or markdown with tables of values
   - **Image attachments:** Screenshots, scanned rate tables, annotated diagrams.
     Claude Code is multimodal — use the Read tool on image files (PNG, JPG, etc.)
     to extract rate values, annotations, or visual context. Common in actuarial
     tickets where rate tables are shared as screenshots rather than structured data.

1.2. **Check for image attachments:** Scan `input/attachments/` AND
     `input/ticket-data/attachments/` for image files (`.png`, `.jpg`, `.jpeg`,
     `.gif`, `.bmp`, `.tiff`). If found, Read each image to extract any rate values,
     table data, or annotations. Incorporate extracted information into the change
     request parsing. If an image contains a rate table, treat the extracted values
     as structured input alongside the text description. If an image is decorative
     or not relevant to rate changes, note it and move on.

1.3. Save the raw input text to `input/source.md` in the workflow directory. If the
     developer provided it conversationally, write it now. If it was already in
     `input/source.md`, leave it as-is.

1.4. Extract any ticket reference from the input text. Look for patterns like:
   - "DevOps 24778" or "DevOps #24778"
   - "Ticket 12345" or "JIRA-456"
   - Work item IDs from ADO URLs
   - If no ticket reference found, set `ticket_ref` to `null`

### Step 2: Read the Manifest for Context

**Action:** Load the workflow context from `manifest.yaml`.

2.1. Read `manifest.yaml` from the workflow directory. Extract:
   - `carrier`, `province`, `province_name`, `lobs`, `effective_date`
   - `target_folders`, `shared_modules`

2.2. Read `config.yaml` from `.iq-workstreams/`. Extract:
   - `provinces.{province_code}.lobs[].is_hab` — hab flag per LOB
   - `provinces.{province_code}.hab_code` — the hab code (e.g., "SKHab")

2.3. Determine the **LOB category**:
   - If ALL target LOBs have `is_hab: true` → `lob_category: "hab"`
   - If target LOBs include "Auto" → `lob_category: "auto"`
   - If both → `lob_category: "mixed"` (flag for developer — unusual)

### Step 2.5: Glossary Pre-Lookup (Codebase Profile)

**Action:** Check the Codebase Knowledge Base glossary for early resolution of
business terms to canonical function names.

2.5.1. Read the `glossary` section from `.iq-workstreams/codebase-profile.yaml`.
   If the file does not exist or the `glossary` section is empty, skip this step.

2.5.2. For each term in the glossary, check if it appears in the raw input text:

```python
def resolve_from_glossary(text, glossary):
    """Match business terms against the glossary.
    Returns matches sorted by specificity (longest match first).
    """
    matches = []
    text_lower = text.lower()
    for term, entry in glossary.items():
        if term in text_lower:
            matches.append({
                "term": term,
                "canonical_function": entry.get("canonical_function"),
                "confidence": "high"
            })
        elif any(s in text_lower for s in entry.get("synonyms", [])):
            matches.append({
                "term": term,
                "canonical_function": entry.get("canonical_function"),
                "confidence": "medium"
            })
    matches.sort(key=lambda m: len(m["term"]), reverse=True)
    return matches
```

2.5.3. Store glossary matches as `glossary_hints` in-memory. These are used in
Step 4 to populate `domain_hints.glossary_match` on each change request.

### Step 3: Segment the Input into Individual Change Items

**Action:** Break the raw text into discrete change items. Each item becomes one
change request.

3.1. **Identify change boundaries.** Look for:
   - Bullet points (-, *, numbered lists)
   - Line breaks separating distinct changes
   - Conjunctions joining distinct changes ("and also", "additionally")
   - Table rows (each row = one change)
   - Paragraph breaks
   - ADO ticket sections (description vs comments may have different changes)

3.2. **Segmentation rules:**
   - Each distinct modification = 1 change request
   - A percentage change applied to ONE type of rate = 1 request, even if it spans many territories
   - A new feature/coverage/endorsement = 1 request (even if it involves multiple files)
   - If the developer gives a grouped instruction like "increase all base rates and
     all liability premiums by 5%", split into separate requests per rate type because
     they target different functions
   - Multiple values changing in the SAME function = 1 request per distinct value
     UNLESS the developer groups them (e.g., "update all deductible factors" = 1 request)

3.3. **Ambiguity detection.** If you cannot clearly segment, ask the developer:

```
[Intake] I see "increase all rates by 5%". In this codebase, there are different
         types of rates:
  1. Base rates (dwelling base premiums) — in DAT files for hab, VB code for auto
  2. Liability premiums (Array6 in mod_Common)
  3. Factor/discount percentages (Select Case in mod_Common)

Which rates does this 5% increase apply to?
```

3.4. **Assign sequential IDs** starting from `cr-001`, zero-padded to 3 digits.

### Step 4: Extract Details from Each Change Item

**Action:** For each change item, extract concrete values, detect domain signals,
and assess complexity. This is NOT classification — it's extraction.

#### 4.1 Value Extraction

Scan the change item text and extract any concrete values present:

**Percentages and multipliers:**
```yaml
# From: "Increase all base rates by 5%"
extracted:
  percentage: 5.0
  factor: 1.05        # Computed: 1 + (5/100)
  method: "multiply"
```

Conversion rules:
- "increase by X%" → factor = 1 + (X / 100)
- "decrease by X%" → factor = 1 - (X / 100)
- "multiply by X" → factor = X
- "double" → factor = 2.0
- "reduce by half" → factor = 0.5

**Old → New value pairs:**
```yaml
# From: "Change $5000 deductible factor from -20% to -22%"
extracted:
  case_value: 5000
  old_value: -0.20     # Convert "-20%" → -0.20
  new_value: -0.22     # Convert "-22%" → -0.22
  method: "explicit"
```

Conversion rules:
- "-20%" → -0.20 (percentage to decimal)
- "0.075" → 0.075 (already decimal)
- "$50" → 50 (dollar amount)
- "no discount" / "0%" → 0.0

**New item values:**
```yaml
# From: "Add water damage endorsement at $75"
extracted:
  endorsement_name: "Water Damage"
  premium: 75.0
  method: null
```

**Territory-specific values (table format):**
```yaml
# From: "Territory 1: $233 → $245, Territory 2: $274 → $288"
extracted:
  method: "explicit"
  explicit_values:
    1: 245
    2: 288
```

If values match a single multiplier within banker's rounding tolerance, note it:
```
[Intake] These territory values appear to match a ~5% increase (1.05x).
         Should I treat this as a uniform 5% multiplier, or use the exact
         values you provided?
```

**If the developer names a specific function:**
```yaml
extracted:
  target_function_hint: "SetDisSur_Deductible"   # Developer-provided hint
```

**If required values are missing, ask:**
```
[Intake] For the new endorsement "Water Damage" at $75:
         1. What is the TBW option code? (or "TBD" if unknown)
         2. What category? (e.g., ENDORSEMENTEXTENSION, OPTIONALCOVERAGE)
```

#### 4.2 Domain Hint Detection

For each change item, detect domain signals (these are HINTS for downstream agents,
not classification gates):

```python
domain_hints = {
    "keyword_matches": [],          # Matched keywords from the text
    "glossary_match": None,         # Canonical function from codebase glossary
    "glossary_confidence": None,    # "high" | "medium" | None
    "involves_rates": False,        # Text mentions rates, premiums, values
    "involves_percentages": False,  # Text mentions %, multiply, increase/decrease
    "involves_new_code": False,     # Text mentions add, new, create, insert
    "rounding_hint": None,          # "banker" if developer says "round to nearest dollar"
}
```

Keyword detection (scan for any of these):
- **Rate signals:** "rate", "premium", "Array6", "base rate", "liability", "factor"
- **Percentage signals:** "%", "percent", "increase by", "decrease by", "multiply"
- **New code signals:** "add", "new", "create", "insert", "introduce", "implement"
- **Specific terms:** "deductible", "endorsement", "coverage", "eligibility",
  "alert", "surcharge", "discount", "limit"

If glossary_hints from Step 2.5 matched this change item's text, populate
`glossary_match` and `glossary_confidence`.

#### 4.3 DAT-File Warning Detection

This is CRITICAL. Hab dwelling base rates live in external DAT files, not VB code.
The plugin CANNOT edit DAT files. Detect this early.

```
Q1: Does the change mention base rates / dwelling rates / base premiums?
  NO  → dat_file_warning = false

  YES → Q2: What is the lob_category?
          "auto" → dat_file_warning = false
                   Auto base rates are in VB code (mod_Algorithms).

          "hab"  → Q3: Does it specifically say "liability premiums"?
                     YES → dat_file_warning = false
                           Hab liability premiums are Array6 in mod_Common.

                     NO  → Q4: Does it say "base rates" or "dwelling rates"?
                             YES → dat_file_warning = true
                             NO  → ASK for clarification (see below)

          "mixed" → Apply hab rules for hab LOBs, auto for auto.
```

When dat_file_warning = true, tell the developer immediately:

```
[Intake] WARNING: "{title}" targets hab dwelling base rates. In this codebase,
         hab dwelling base rates are in external DAT files, NOT in VB code.
         This plugin CANNOT edit DAT files.

         Do you want me to:
           1. Keep this request for tracking but mark as out-of-scope
           2. Remove it entirely
           3. Actually, this is about liability premiums (let me re-read)
```

When ambiguous (hab, says "rates" without qualifying):

```
[Intake] You mentioned "increase all rates by 5%" for Saskatchewan Habitational.
         There are two types of hab rates:
         1. Dwelling base rates — in DAT files (NOT editable by this plugin)
         2. Liability premiums — in VB code Array6 tables (editable)

         Which rates should the 5% increase apply to?
```

#### 4.4 Rounding Detection

**The Intake agent does NOT make the final rounding decision.** It has not read
the actual VB code.

Rule: Set `rounding_hint: null` unless the developer explicitly mentions rounding.
- "round to nearest dollar" → `rounding_hint: "banker"`
- "keep exact decimals" → `rounding_hint: "none"`
- No mention of rounding → `rounding_hint: null` (Analyzer decides later)

#### 4.5 Scope Detection

Determine what the change applies to:

**Territory scope:**
- "all base rates" / "across the board" → `scope: "all_territories"`
- "Territory 1 and 5" → `scope: "specific_territories"`, `territories: [1, 5]`
- Different rates per territory → split into separate requests per distinct value,
  or use `method: "explicit"` with values map

**LOB scope (multi-LOB workflows):**
- "all LOBs" / no qualifier → `lob_scope: "all"`
- "Home and Condo only" → `lob_scope: "specific"`, `target_lobs: ["Home", "Condo"]`
- If not stated for multi-LOB workflow, confirm:
  ```
  [Intake] This is a 6-LOB hab workflow. Does this change apply to all 6 LOBs?
  ```

#### 4.6 Complexity Estimate

A rough estimate (NOT a gate — downstream agents refine this):

| Estimate | Criteria |
|----------|----------|
| SIMPLE | Single value change or uniform multiplier. One function. No new code. |
| MEDIUM | Multiple value changes, OR adding something from a template. |
| COMPLEX | New code structures, cross-file changes, logic modifications, or anything ambiguous. |

#### 4.7 Ambiguity Detection

Set `ambiguity_flag: true` when:
- "approximately", "about", "roughly" + a number
- "TBD", "to be determined"
- Missing required values (e.g., new coverage but no premium specified)
- Contradictory statements

```
[Intake] The ticket says "approximately 5%". Using exactly 1.05 as the multiplier.
         If this should be different, tell me now.
```

### Step 5: Present the Parsed Results to the Developer

**Action:** Show a formatted summary for confirmation. Connect each CR back to the
ticket understanding so the developer can see the traceability.

5.1. Present in this format:

```
[Intake] Parsed {N} change request(s) from your input:

  CR-001: "Increase liability premiums by 3%" (SIMPLE)
          → 3% multiplier across all territories
          → Glossary match: GetLiabilityBundlePremiums
          → Source: {where this came from — e.g., "ticket description, item 2"
            or "comment by John Smith on 2026-01-15" or "screenshot showing
            rate comparison table"}

  CR-002: "Change $5000 deductible factor from -0.20 to -0.22" (SIMPLE)
          → Explicit old→new value replacement
          → Source: {evidence trail}

  CR-003: "[DAT FILE] Increase dwelling base rates by 5%" (SIMPLE)
          *** OUT OF SCOPE: Hab dwelling base rates are in DAT files ***
          → Source: {evidence trail}

  CR-004: "Add $50,000 sewer backup coverage tier" (MEDIUM)
          → Premium amount not specified — will ask during planning
          → Source: {evidence trail}
          ⚠ ambiguity: missing premium value

  Totals: 4 requests (2 SIMPLE, 1 MEDIUM, 0 COMPLEX)
          1 DAT-file warning (CR-003)
          1 ambiguity (CR-004 — missing premium)

  Traceability: All CRs trace back to the confirmed ticket understanding above.
  Does this look correct? I'll proceed to write the change spec.
```

**Traceability rule:** Every CR MUST have a `source_location` that points back to
the specific evidence in the ticket (description line, comment ID, image filename).
If a CR cannot be traced to evidence, flag it as `confidence: low` and explain why
you think this change is needed.

5.2. **Wait for developer confirmation.** The developer may:
- **Confirm:** "yes" / "looks good" → go to Step 6
- **Correct:** "CR-002 should be -0.25, not -0.22" → update, re-present
- **Add:** "I forgot, also change the $1000 deductible" → add, re-present
- **Remove:** "Remove CR-003, I'll do that manually" → remove, re-present
- **Clarify:** "What's a DAT file?" → explain, re-present

### Step 6: Write Output Files

**Action:** Once confirmed, write output files.

6.1. **Ensure directory structure exists:**
```
.iq-workstreams/changes/{workstream}/parsed/
.iq-workstreams/changes/{workstream}/parsed/requests/
```

6.2. **Write `parsed/change_requests.yaml`** with the full schema shown above.

6.3. **Write individual request files** to `parsed/requests/cr-NNN.yaml` (one per
change request), with the full per-request schema.

6.4. **Title construction rules:**
- Be specific: "Increase hab liability premiums by 3%" not "Rate change"
- Include key parameters: "Change $5000 deductible from -0.20 to -0.22"
- For DAT-file changes, prefix with "[DAT FILE]"
- Keep under 80 characters

6.5. **Validate YAML before proceeding:**
```bash
{python_cmd} -c "import yaml; yaml.safe_load(open('parsed/change_requests.yaml')); print('OK')"
```

6.6. **Do NOT update `manifest.yaml`** — the orchestrator handles that.

### Step 7: Report Completion

```
[Intake] COMPLETE.
         - ticket_understanding.md (confirmed by developer)
         - change_requests.yaml (master spec)
         - requests/cr-001.yaml through cr-{N}.yaml
         - {M} out-of-scope (DAT file)
         - {K} ambiguities

         Next: Discovery will trace the codebase to find relevant functions.
```

---

## WORKED EXAMPLES

### Example A: Simple Rate Increase (Auto)

**Input:** `AB Auto, effective 2026-01-01. Increase all base rates by 5%.`

**Context:** province = AB, lobs = [Auto], lob_category = auto

**Extraction:**
- "base rates" + "5%" → percentage: 5.0, factor: 1.05, method: "multiply"
- lob_category = auto → dat_file_warning = false (auto base rates are in VB code)
- scope = all_territories, complexity_estimate = SIMPLE

**Output:**
```yaml
id: "cr-001"
title: "Increase AB Auto base rates by 5%"
extracted:
  percentage: 5.0
  factor: 1.05
  method: "multiply"
  scope: "all_territories"
  lob_scope: "all"
domain_hints:
  keyword_matches: ["base rate", "increase"]
  involves_rates: true
  involves_percentages: true
dat_file_warning: false
complexity_estimate: "SIMPLE"
```

### Example B: Factor Table Changes (Multiple Cases)

**Input:**
```
NB Home 20260701. Update deductible factors:
- $500: 0 (no change)
- $1000: -0.075 → -0.08
- $2500: -0.15 → -0.16
- $5000: -0.20 → -0.22
```

**Extraction:**
- $500 says "no change" → skip, do not create a request
- Three distinct case values changing → 3 requests
- All are method = "explicit" (developer gave exact old→new values)

**Output:** 3 requests (cr-001 through cr-003), each with `extracted.case_value`,
`extracted.old_value`, `extracted.new_value`.

### Example C: Mixed Changes with DAT File Warning

**Input:**
```
SK Hab Jan 2026 (DevOps 24778):
1. Increase dwelling base rates by 5%
2. Increase liability premiums by 3%
3. Change $5000 deductible factor from -20% to -22%
```

**Process:**
- Item 1: "dwelling base rates" + hab → dat_file_warning = true → warn developer
- Item 2: "liability premiums" + hab → in VB code (Array6) → OK
- Item 3: "$5000 deductible factor" + old→new → OK

**Presentation:**
```
[Intake] Parsed 3 changes:

  CR-001: "[DAT FILE] Increase dwelling base rates by 5%" (SIMPLE)
          *** OUT OF SCOPE — hab dwelling base rates are in DAT files ***

  CR-002: "Increase liability premiums by 3%" (SIMPLE)
          → 3% multiplier, all territories
          → Glossary: GetLiabilityBundlePremiums

  CR-003: "Change $5000 deductible from -0.20 to -0.22" (SIMPLE)
          → Explicit value replacement
```

### Example D: Bug Fix Ticket (Non-Rate Change)

**Input (from ADO ticket):**
```
Bug: GetSewerBackupPremium returns wrong premium for $25K coverage when
policy category is "Seasonal". The Select Case for Seasonal is missing
the $25K branch — it falls through to Case Else which returns 0.

Expected: $25K Seasonal should return same premium as $25K Home (currently $89).
```

**Extraction:**
- No percentages, no multipliers
- Mentions specific function: GetSewerBackupPremium → target_function_hint
- Describes a bug: missing Case block for a specific scenario
- Desired outcome: add the missing Case branch

**Output:**
```yaml
id: "cr-001"
title: "Fix missing $25K Seasonal case in GetSewerBackupPremium"
description: |
  GetSewerBackupPremium is missing the $25K coverage branch for Seasonal
  policy category. Falls through to Case Else (returns 0). Should return
  same premium as Home ($89).
extracted:
  target_function_hint: "GetSewerBackupPremium"
  case_value: 25000
  new_value: 89
  method: null
  lob_scope: "specific"
  target_lobs: ["Seasonal"]
domain_hints:
  keyword_matches: ["sewer backup", "Select Case", "missing"]
  glossary_match: "GetSewerBackupPremium"
  glossary_confidence: "high"
  involves_rates: false
  involves_percentages: false
  involves_new_code: true
dat_file_warning: false
ambiguity_flag: false
complexity_estimate: "MEDIUM"
```

### Example E: Complex Logic Change

**Input:**
```
Implement new multi-vehicle discount structure for AB Auto:
- 2 vehicles: 10% discount (currently 10%, no change)
- 3 vehicles: 15% discount (currently 12%)
- 4+ vehicles: 20% discount (currently 15%)
Also add a cap: total multi-vehicle discount cannot exceed $500.
```

**Extraction:**
- Two distinct changes: (1) update discount percentages, (2) add discount cap
- Values for discount changes are explicit old→new
- Cap is new logic (doesn't exist yet)

**Output:** 2 requests:
```yaml
# cr-001: Update existing discount values
id: "cr-001"
title: "Update multi-vehicle discount percentages"
description: "Change 3-vehicle discount from 12% to 15%, 4+ from 15% to 20%"
extracted:
  values:
    - case_value: 3
      old_value: -0.12
      new_value: -0.15
    - case_value: 4  # "4+"
      old_value: -0.15
      new_value: -0.20
  method: "explicit"
domain_hints:
  keyword_matches: ["multi-vehicle", "discount"]
  involves_rates: false
  involves_new_code: false
complexity_estimate: "SIMPLE"

# cr-002: Add new discount cap logic
id: "cr-002"
title: "Add $500 cap on multi-vehicle discount"
description: "After applying multi-vehicle discount, cap the total at $500"
extracted:
  cap_value: 500
  method: null
domain_hints:
  keyword_matches: ["cap", "discount", "exceed"]
  involves_rates: false
  involves_new_code: true
complexity_estimate: "COMPLEX"
ambiguity_flag: true
ambiguity_note: "Cap logic doesn't exist yet — Discovery needs to find where to add it"
```

---

## SPECIAL CASES

### Case 1: "No change" items in a list

When the developer lists values with some marked "no change" or "(unchanged)",
do NOT create requests for those items. Only create requests for actual changes.

### Case 2: Grouped instruction vs. individual items

If the developer says "increase all deductible factors by 10%", create ONE request
with method=multiply, scope=all. Do NOT split per Case value — that is the
Decomposer's job after reading the code.

But if the developer gives individual old→new values for each Case, create
individual requests because each has its own explicit target value.

### Case 3: Contradictory instructions

If two items contradict, flag both and ask:
```
[Intake] I found contradictory instructions:
         Item 2: "Change $5000 deductible factor to -0.22"
         Item 5: "Change $5000 deductible factor to -0.25"
         Which value should I use?
```

### Case 4: Developer provides a specific function name

Record in `extracted.target_function_hint`. Discovery and Analyzer will use this
as a search hint but still verify the function exists.

### Case 5: Territory-specific values table

If values match a single multiplier within banker's rounding tolerance:
→ Suggest ONE request with method=multiply

If values do NOT match a single multiplier:
→ Create ONE request with method=explicit and values map
→ Tell the developer which values don't match

### Case 6: Change mentions a file path

If the developer says "in CalcOption_SKHome20260101.vb", record it in
`extracted.target_file_hint`. The Analyzer verifies.
