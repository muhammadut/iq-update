# IQ Plugin Review: Ticket Understanding and Plan Clarity

## Findings

### 1. High: screenshots embedded in the ticket description or repro steps can still be missed

- Evidence:
  - `fetch-ticket.sh:194` only builds the attachment manifest from work-item relations.
  - `fetch-ticket.sh:207` only scans comment HTML for embedded attachment URLs.
  - `fetch-ticket.sh:382` and `fetch-ticket.sh:383` convert description and repro HTML to markdown, but do not download images referenced there.
  - `agents/intake.md:236` and `agents/intake.md:247` tell Intake to read the full ticket and all image attachments.
- Impact:
  - The pipeline can claim it read "all screenshots" while missing the most important screenshots if they were embedded directly in the main ticket body or repro steps.
  - Tickets with rate tables pasted into the description are still vulnerable to misunderstanding before planning starts.
- Recommendation:
  - Extend `fetch-ticket.sh` to extract image references from `System.Description` and `Microsoft.VSTS.TCM.ReproSteps`, not just comments and `AttachedFile` relations.
  - Materialize every image into `attachments/` and include origin metadata so Intake can cite it.
  - If an image reference cannot be downloaded, surface that as missing evidence instead of silently continuing.

### 2. High: attachment provenance is dropped, so the model cannot tell which comment a screenshot came from

- Evidence:
  - `fetch-ticket.sh:207` records comment-derived attachments as generic `comment` sources with the display name `embedded-attachment`.
  - `fetch-ticket.sh:271` through `fetch-ticket.sh:286` write only `index`, `source`, `name`, `downloadUrl`, `localPath`, `status`, and `sizeBytes`.
  - `fetch-ticket.sh:393` through `fetch-ticket.sh:402` reduce the final attachment payload to `index`, `name`, `source`, `localPath`, and `sizeBytes`.
  - `agents/intake.md:314` through `agents/intake.md:326` expect the model to explain what each screenshot means and how it relates to the ticket.
- Impact:
  - Once the image is downloaded, the evidence chain is broken. The model can see the screenshot, but it cannot reliably answer "which comment added this?" or "does this screenshot supersede the earlier description?"
  - This is exactly the kind of gap that produces a wrong ticket understanding and then a wrong plan.
- Recommendation:
  - Preserve provenance for every attachment:
    - `origin_kind`: `relation`, `description_image`, `repro_image`, `comment_image`
    - `origin_field`
    - `comment_id`
    - `comment_author`
    - `comment_created_at`
    - `attachment_id`
    - `mime_type`
    - `sha256`
  - Add an attachment index artifact that Intake can cite directly in `ticket_understanding.md`.

### 3. High: the Planner is explicitly allowed to generate a plan with unresolved questions

- Evidence:
  - `agents/planner.md:818` starts the Q&A flow.
  - `agents/planner.md:904` through `agents/planner.md:918` warn if questions remain, but still proceed with plan generation.
- Impact:
  - Gate 1 can show an execution plan even when important values, scope decisions, or insertion choices are still unresolved.
  - That directly conflicts with the goal of making the plan unambiguous.
- Recommendation:
  - Split planner questions into:
    - `blocking_questions`: scope, value, target, insertion-point, dependency questions
    - `non_blocking_questions`: optional notes or lower-risk preferences
  - Do not produce an approvable Gate 1 plan while any blocking question remains unresolved.
  - If you want a draft plan anyway, mark it as `DRAFT - DECISION REQUIRED` and place the unresolved items at the top.

### 4. High: the Planner is disconnected from the confirmed ticket understanding

- Evidence:
  - `agents/planner.md:33` through `agents/planner.md:286` define Planner inputs as `manifest.yaml`, `config.yaml`, `analysis/intent_graph.yaml`, `analysis/files_to_copy.yaml`, `analysis/blast_radius.md`, and source files.
  - There is no Planner input contract for `parsed/ticket_understanding.md` or `parsed/change_requests.yaml`.
  - `agents/decomposer.md:773` through `agents/decomposer.md:799` build intents from CRs but do not carry `source_text`, `source_location`, or screenshot/comment evidence into the intent.
- Impact:
  - The plan can be code-correct while still being business-wrong.
  - Gate 1 has no durable tie back to the confirmed ticket understanding, so the developer cannot quickly tell whether each phase still matches the ticket evidence.
- Recommendation:
  - Make the Planner read:
    - `parsed/ticket_understanding.md`
    - `parsed/change_requests.yaml`
  - Extend the intent contract to carry:
    - `source_text`
    - `source_location`
    - `evidence_refs`
    - `ambiguity_note`
    - `developer_decisions_applied`
    - `done_when`
  - The plan should render both the business intent and the code action for each CR.

### 5. Medium: Intake's confirmation checkpoint is underspecified for sequential mode

- Evidence:
  - `skills/iq-plan/SKILL.md:885` through `skills/iq-plan/SKILL.md:895` say that in sequential mode an agent must return pending-confirmation artifacts and let the orchestrator handle developer interaction.
  - `skills/iq-plan/SKILL.md:988` through `skills/iq-plan/SKILL.md:995` repeat that sequential agents should write pending confirmations rather than wait interactively.
  - `agents/intake.md:352` through `agents/intake.md:381` tell Intake to present the understanding and wait for confirmation.
  - `skills/iq-plan/SKILL.md:1072` through `skills/iq-plan/SKILL.md:1087` tell the orchestrator to present the understanding again after the agent completes.
- Impact:
  - The contract is unclear about who owns the checkpoint in sequential mode.
  - In practice this can produce duplicate confirmations, or worse, a sub-agent prompt that expects an interaction pattern the orchestrator never implemented.
- Recommendation:
  - Define a concrete checkpoint artifact, for example `parsed/ticket_understanding.yaml`, with fields like:
    - `status: pending_confirmation | confirmed`
    - `questions`
    - `corrections`
    - `confirmed_at`
  - In sequential mode, Intake should stop after Step 0 and return `pending_confirmation`.
  - The orchestrator should be the only component that presents Gate-like checkpoints to the developer.

### 6. Medium: HTML tables and other structured ticket content are flattened too aggressively

- Evidence:
  - `fetch-ticket.sh:317` through `fetch-ticket.sh:367` define `html_to_md`.
  - The function handles headings, lists, links, and images, but strips all remaining tags with `gsub("(?i)<[^>]+>"; "")`.
- Impact:
  - HTML tables pasted from Excel or ADO can collapse into ambiguous text with no row or column boundaries.
  - That makes it harder for Intake to distinguish territory, deductible, coverage, and old/new value columns.
- Recommendation:
  - Preserve tables as markdown tables or TSV blocks.
  - Preserve code/preformatted blocks.
  - Keep raw HTML alongside normalized markdown so the agent has a fallback when normalization is lossy.

### 7. Medium: missing evidence can be hidden from the model instead of being called out explicitly

- Evidence:
  - `fetch-ticket.sh:288` through `fetch-ticket.sh:305` record failed downloads.
  - `fetch-ticket.sh:395` filters the final attachment list to `status == "downloaded"`.
  - `fetch-ticket.sh:459` and `fetch-ticket.sh:460` build the brief from the earliest three comments, not the latest three.
- Impact:
  - If an attachment fails to download, the LLM-facing context makes it look as if the attachment never existed.
  - If the system ever falls back to the brief, it will show the oldest comments instead of the final clarifications.
- Recommendation:
  - Keep failed attachments in `llm-context.json` with `status: failed` and a warning section in `llm-context.md`.
  - Count and display `downloaded`, `failed`, and `skipped` attachments separately.
  - If the brief must exist, prefer latest comments or a balanced sample that includes the final state.

## Recommended Contract Changes

### Ticket evidence contract

Add a normalized evidence artifact, for example `input/ticket-data/ticket-evidence.json`, with:

- `description`
- `repro_steps`
- `comments[]` sorted chronologically
- `attachments[]` with full provenance
- `image_attachments[]` with stable IDs
- `missing_evidence[]` for failed downloads or unreadable files

This should become the source of truth for Intake rather than asking the model to reconstruct provenance from markdown.

### Intake output contract

Keep `parsed/ticket_understanding.md`, but add a machine-readable companion such as `parsed/ticket_understanding.yaml`:

- `status`
- `problem_statement`
- `facts`
- `conflicts`
- `final_interpretation`
- `blocking_questions`
- `evidence_refs`
- `developer_confirmation`

Also strengthen each CR in `parsed/change_requests.yaml`:

- `evidence_refs`
- `assumptions`
- `blocking_questions`
- `done_when`
- `non_goals`

### Planner input contract

Update the Planner so it consumes the confirmed ticket understanding and CR evidence, not just the intent graph.

The Planner should be able to answer, for every phase:

- Why is this change needed?
- Which ticket evidence justifies it?
- What ambiguity was resolved?
- What still needs developer input?
- How will we verify success?

## Recommended Gate 1 Plan Format

The current plan format is code-centric. It needs one more layer: business intent and evidence.

Suggested top-level structure:

1. `Confirmed Ticket Understanding`
   - one-paragraph restatement
   - latest clarifications that changed scope
   - screenshot findings that matter
   - explicit non-goals

2. `Decisions Already Applied`
   - developer answers collected during Intake, Analyzer, or Planner
   - any overrides of the raw ticket text

3. `Blocking Questions`
   - must be empty before the plan is approvable

4. `Plan By Change Request`
   - `CR-001`
   - `What the ticket is asking for`
   - `Evidence`
   - `Files/functions affected`
   - `Code action`
   - `Validation / done when`
   - `Risks / assumptions`

5. `Execution Order`
   - phase ordering and dependencies
   - why this order is necessary

6. `Impact Summary`
   - files copied
   - files modified
   - vbproj updates
   - shared-module blast radius

7. `Approval Statement`
   - explicit note that approval means agreement with both the business interpretation and the code plan

## Recommended Per-CR Plan Card

For each CR, the plan should read more like this:

```markdown
CR-002: Change $5000 deductible factor from -0.20 to -0.22

What this means:
- Update the deductible factor for the $5000 case only.

Why I believe this:
- Ticket description: ...
- Comment 7 from Jane Doe on 2026-03-02: ...
- Screenshot att-03 shows ...

Implementation:
- File: Saskatchewan/Code/mod_Common_SKHab20260101.vb
- Function: SetDisSur_Deductible()
- Change: `Case 5000 : dblDedDiscount = -0.2` -> `Case 5000 : dblDedDiscount = -0.22`

Validation:
- Only the $5000 case changes.
- No other deductible cases change.
- Shared module impact: Home, Condo, Tenant, FEC, Farm, Seasonal.

Assumptions:
- None.
```

That format removes the common Gate 1 failure mode where the code edit looks plausible but is solving the wrong business problem.

## Recommended Regression Tests

Add end-to-end tests or fixture-based dry runs for these cases:

1. Ticket with the decisive screenshot embedded in `System.Description`.
2. Ticket with a later comment that overrides an earlier percentage.
3. Ticket with an HTML table pasted from Excel.
4. Ticket where one screenshot download fails.
5. Sequential-mode Intake confirmation.
6. Planner with unresolved blocking questions.
7. Gate 1 plan rendering that includes evidence refs, assumptions, and validation text.

## Suggested Implementation Order

1. Fix evidence capture in `fetch-ticket.sh`.
2. Add machine-readable ticket-understanding and evidence artifacts.
3. Carry evidence refs from Intake into Decomposer and Planner.
4. Change Planner so unresolved blocking questions stop Gate 1.
5. Redesign `execution_plan.md` around CR-level intent, evidence, and validation.
