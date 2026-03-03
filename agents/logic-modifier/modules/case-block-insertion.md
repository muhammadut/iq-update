# Module: Case Block Insertion
Handles `new_coverage_type` with `case_block_type`. Inserts Case blocks into Select Case structures.

## Input Schema — Pattern 2: new_coverage_type (Case block insertion)

```yaml
id: "op-005-02"
srd: "srd-005"
title: "Add Elite Comp rate table routing Case block"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "GetRateTableID"
location: "inside Select Case strCoverageType"
agent: "logic-modifier"
depends_on: ["op-005-01"]               # Constant must exist first
blocked_by: []
pattern: "new_coverage_type"
parameters:
  constant_name: "ELITECOMP"
  case_block_type: "rate_table_routing"  # rate_table_routing | defaults | validation
  classifications:                       # Sub-classifications for nested Select Case
    - name: "STANDARD"
      dat_constant: "DAT_Home_EliteComp_Standard"
    - name: "PREFERRED"
      dat_constant: "DAT_Home_EliteComp_Preferred"

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
function_line_start: 400
function_line_end: 480
insertion_point:
  line: 440
  position: "before_end_select"         # Insert before the End Select
  context: "Inside: Select Case strCoverageType (line 405)"
  section: "GetRateTableID function (lines 400-480)"
  end_select_line: 445                  # The End Select to insert before
existing_cases:                         # For duplicate detection
  - name: "PREFERRED"
    line: 410
  - name: "STANDARD"
    line: 420
  - name: "FARMPAK"
    line: 430
duplicate_check: "Case ELITECOMP not found in Select Case -- safe to add"
needs_new_file: false
template_reference: null
candidates_shown: 1
developer_confirmed: true
```

**Field semantics for new_coverage_type (Case block):**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.constant_name` | string | The Case constant (e.g., `ELITECOMP`) |
| `parameters.case_block_type` | string | What kind of Case block to generate |
| `parameters.classifications[]` | list | Sub-cases for nested Select Case |
| `insertion_point.position` | string | `"before_end_select"` for Case blocks |
| `insertion_point.end_select_line` | int | Line number of the End Select |
| `existing_cases[]` | list | Cases already in the Select Case |
| `function_line_start` | int | First line of function (hint) |
| `function_line_end` | int | Last line of function (hint) |

## Step 5b: Case Block Insertion (new_coverage_type pattern, rate_table_routing)

Generate a nested Select Case block for rate table routing. This is the most
complex common operation because indentation must match existing Case blocks in
the same Select Case.

> **Prerequisite:** See core.md Step 4 for anchor location and
> find_end_select/find_end_function helpers.

```python
def generate_case_block(work, lines, anchor_idx):
    """Generate a Case block for rate table routing.

    Reads indentation from existing Case blocks in the same Select Case
    to ensure the generated block matches exactly.

    Args:
        work: operation work dictionary
        lines: file lines array
        anchor_idx: index of the End Select (insertion will be before it)

    Returns: list of code lines to insert.
    """
    p = work["parameters"]
    constant_name = p["constant_name"]
    classifications = p.get("classifications", [])
    srd = work["srd"]

    # Measure indentation from existing Case blocks
    # Look backward from End Select to find a Case line
    case_indent = measure_case_indent(lines, anchor_idx)
    body_indent = case_indent + "    "        # +4 spaces for Case body
    nested_case_indent = body_indent + "    " # +4 more for nested Case items

    result = []

    # Outer Case line
    result.append(f"{case_indent}Case {constant_name}")

    if classifications:
        # Nested Select Case for classifications
        result.append(f"{body_indent}Select Case strClassification")
        for cls in classifications:
            cls_name = cls["name"]
            dat_const = cls["dat_constant"]
            result.append(
                f"{nested_case_indent}Case {cls_name} : intFileID = {dat_const}"
            )
        result.append(f"{body_indent}End Select")
    else:
        # Simple Case body (no nested Select Case)
        # Use parameters for the body content
        body_line = p.get("case_body", f"intFileID = {p.get('dat_constant', 'DAT_UNKNOWN')}")
        result.append(f"{body_indent}{body_line}")

    # Add SRD traceability as a comment on the outer Case line
    result[0] += f" '{srd}"

    return result


```

**NOTE:** `measure_case_indent()` is defined in **core.md** (Shared Helper Functions
section). It is available to this module because workers always load core.md first.

**Indentation discovery:** The agent NEVER hardcodes indentation levels. It reads
the indentation of existing `Case` blocks in the same `Select Case` and replicates
it exactly. From the research, SK GetBasePremium_Home has Cases at 20 spaces (5
levels deep) with nested Cases at 28 spaces (7 levels). Other functions may differ.

**After generating, proceed to Step 6 (Validate Generated Code) in core.md.**
