# Module: Alert Message
Handles `alert_message`. Inserts AlertHab calls into existing validation functions.

## Input Schema — Pattern 6: alert_message (AlertHab call insertion)

```yaml
id: "op-010-01"
srd: "srd-010"
title: "Add $5M liability warning for Elite Comp"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: "ValidateData_EliteComp"
location: "inside validation function"
agent: "logic-modifier"
depends_on: ["op-009-01"]               # Validation function must exist
blocked_by: []
pattern: "alert_message"
parameters:
  alert_text: "$5M liability only available for Elite Comp"
  alert_action: "aanotrated"            # aaAlertAction enum value
  condition: "dblLiabilityLimit > 5000000"
  condition_type: "If"                  # "If" | "ElseIf"

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
function_line_start: 900
function_line_end: 935
insertion_point:
  line: 930
  position: "before_end_function"
  context: "Before: End Function  ' ValidateData_EliteComp"
  section: "ValidateData_EliteComp (lines 900-935)"
needs_new_file: false
template_reference: null
candidates_shown: 1
developer_confirmed: true
```

**Field semantics for alert_message:**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.alert_text` | string | Message text for AlertHab call |
| `parameters.alert_action` | string | aaAlertAction enum value |
| `parameters.condition` | string | VB.NET condition expression |
| `parameters.condition_type` | string | `"If"` or `"ElseIf"` |
| `insertion_point.position` | string | `"before_end_function"` typical |

## Step 5f: Alert Message Insertion (alert_message pattern)

Insert an If/ElseIf block with an AlertHab call inside an existing function.

> **Prerequisite:** See core.md Step 4 for anchor location and
> find_end_function helper.

```python
def generate_alert_message(work, lines, anchor_idx):
    """Generate an If/ElseIf block with AlertHab call.

    Inserts before End Function with the function's body indentation.
    """
    p = work["parameters"]
    condition = p["condition"]
    alert_text = p["alert_text"]
    alert_action = p["alert_action"]
    condition_type = p.get("condition_type", "If")
    srd = work["srd"]

    # Measure body indentation from surrounding code
    body_indent = measure_body_indent(lines, anchor_idx)

    result = []
    result.append(f"{body_indent}{condition_type} {condition} Then '{srd}")
    result.append(f"{body_indent}    AlertHab(\"{alert_text}\", aaAlertAction.{alert_action})")
    if condition_type == "If":
        result.append(f"{body_indent}End If")
    # ElseIf blocks are NOT closed here -- they chain with existing If blocks

    return result


def measure_body_indent(lines, end_func_idx):
    """Measure the body indentation level of a function.

    Scans backward from End Function to find a non-blank, non-comment line,
    and returns its leading whitespace.
    """
    for i in range(end_func_idx - 1, max(end_func_idx - 30, -1), -1):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("'"):
            continue
        match = re.match(r'^(\s+)', lines[i])
        if match:
            return match.group(1)
    # Fallback: 8 spaces (standard function body indent)
    return "        "
```

**After generating, proceed to Step 6 (Validate Generated Code) in core.md.**
