# Module: Validation Function
Handles `eligibility_rules`. Generates new Boolean validation functions.

## Input Schema — Pattern 5: eligibility_rules (guard clause / validation function)

```yaml
id: "op-009-01"
srd: "srd-009"
title: "Add ValidateData_EliteComp validation function"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: null                          # New function at module level
location: "after ValidateData_Standard function"
agent: "logic-modifier"
depends_on: ["op-005-01"]               # Constant must exist
blocked_by: []
pattern: "eligibility_rules"
parameters:
  function_name: "ValidateData_EliteComp"
  function_type: "validation"           # "validation" | "guard_clause"
  coverage_type: "ELITECOMP"
  validations:
    - field: "Territory"
      condition: "= \"\""
      message: "Territory is required"
      action: "aanotrated"
    - field: "Classification"
      condition: "= \"\""
      message: "Classification is required"
      action: "aanotrated"

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
insertion_point:
  line: 890
  position: "after"
  context: "After: End Function  ' ValidateData_Standard"
  section: "validation functions (lines 800-900)"
existing_functions:
  - name: "ValidateData_Preferred"
    line_start: 750
    line_end: 800
  - name: "ValidateData_Standard"
    line_start: 850
    line_end: 890
duplicate_check: "ValidateData_EliteComp not found -- safe to add"
needs_new_file: false
template_reference: null
candidates_shown: 1
developer_confirmed: true
```

**Field semantics for eligibility_rules:**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.function_name` | string | Name of the function to create |
| `parameters.function_type` | string | `"validation"` or `"guard_clause"` |
| `parameters.coverage_type` | string | Coverage type constant referenced |
| `parameters.validations[]` | list | Field/condition/message/action tuples |
| `insertion_point.context` | string | Anchor line to insert after |
| `existing_functions[]` | list | Nearby functions (for style reference) |

## Step 5e: Validation Function (eligibility_rules pattern)

Generate a complete validation function matching the `ValidateData_*` pattern.

> **Prerequisite:** See core.md Step 4 for anchor location. The anchor has
> already been located before this step runs.

```python
def generate_validation_function(work):
    """Generate a ValidateData_{Name} function skeleton.

    Structure matches existing ValidateData_* functions in mod_Common:
      - Function declaration at 4-space indent
      - Body at 8-space indent
      - AlertHab calls for each validation rule
      - Return via function name assignment
      - End Function at 4-space indent
    """
    p = work["parameters"]
    func_name = p["function_name"]
    coverage_type = p.get("coverage_type", "")
    validations = p.get("validations", [])
    srd = work["srd"]

    result = []
    result.append("")    # Blank line separator before new function
    result.append(f"    Function {func_name}(ByVal p_objCovItem As TBWApplication.ICoverageItem) As Boolean '{srd}")
    result.append(f"        {func_name} = True")
    result.append("")

    for i, v in enumerate(validations):
        field = v["field"]
        condition = v["condition"]
        message = v["message"]
        action = v["action"]

        keyword = "If" if i == 0 else "ElseIf"
        result.append(f"        {keyword} p_objCovItem.Fields.Item(\"{field}\").Value {condition} Then")
        result.append(f"            AlertHab(\"{message}\", aaAlertAction.{action})")
        result.append(f"            {func_name} = False")

    if validations:
        result.append("        End If")

    result.append("")
    result.append(f"    End Function")

    return result
```

**Function signature:** Uses `ByVal p_objCovItem As TBWApplication.ICoverageItem`
matching the pattern from existing ValidateData_* functions. Return type is
`Boolean`. Return is via function name assignment (VB.NET convention for legacy
code: `FunctionName = value`).

**After generating, proceed to Step 6 (Validate Generated Code) in core.md.**
