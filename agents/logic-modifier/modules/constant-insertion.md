# Module: Constant Insertion
Handles `new_coverage_type` where `constant_name` is set. Inserts module-level String constants.

## Input Schema — Pattern 1: new_coverage_type (constant variant)

```yaml
id: "op-005-01"
srd: "srd-005"
title: "Add ELITECOMP constant to mod_Common"
file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
file_type: "shared_module"
function: null                          # Module-level, not inside a function
location: "module-level constants"
agent: "logic-modifier"
depends_on: []
blocked_by: []
pattern: "new_coverage_type"
parameters:
  constant_name: "ELITECOMP"
  coverage_type_name: "Elite Comp."
  # NOTE: constant_type and constant_value are DERIVED by the Logic Modifier:
  #   constant_type = "String" (coverage type constants are always String)
  #   constant_value = '"' + coverage_type_name + '"' (quoted string literal)

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/mod_Common_SKHab20250901.vb"
target_file: "Saskatchewan/Code/mod_Common_SKHab20260101.vb"
needs_copy: true
file_hash: "sha256:a1b2c3d4..."
insertion_point:
  line: 23                              # Line after which to insert
  position: "after"                     # Insert after this line
  context: "After: Public Const STANDARD As String = \"Standard\""
  section: "module-level constants (lines 1-50)"
existing_constants:                     # For duplicate detection
  - name: "PREFERRED"
    line: 21
    value: "\"Preferred\""
  - name: "STANDARD"
    line: 22
    value: "\"Standard\""
duplicate_check: "ELITECOMP not found -- safe to add"
needs_new_file: false
template_reference: null
candidates_shown: 1
developer_confirmed: true
```

**Field semantics for new_coverage_type (constant insertion):**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.constant_name` | string | Name of the constant to add |
| `parameters.coverage_type_name` | string | Human label for the coverage type |
| *(derived)* `constant_type` | -- | Always `"String"` for coverage type constants |
| *(derived)* `constant_value` | -- | `'"' + coverage_type_name + '"'` |
| `insertion_point.line` | int | Line number HINT (may drift) |
| `insertion_point.position` | string | Always `"after"` for constant insertion |
| `insertion_point.context` | string | **Authoritative match key** for locating |
| `insertion_point.section` | string | Human-readable section description |
| `existing_constants[]` | list | Constants already present (for duplicate check) |
| `duplicate_check` | string | Analyzer's duplicate assessment |

## Step 5a: Constant Insertion (new_coverage_type pattern, constant operation)

Insert a `Public Const` declaration at module level.

> **Prerequisite:** Step 4 (locate_insertion_point) is in core.md. The anchor has
> already been located before this step runs.

```python
def generate_constant(work):
    """Generate a Public Const line for a new coverage type constant.

    Format: '    Public Const {NAME} As {Type} = {value}'
    Indentation: 4 spaces (module member level).
    """
    p = work["parameters"]
    name = p["constant_name"]
    srd = work["srd"]

    # Derive type and value from coverage_type_name
    # Coverage type constants are always String in this codebase
    coverage_name = p["coverage_type_name"]
    const_type = "String"
    value = f'"{coverage_name}"'

    line = f"    Public Const {name} As {const_type} = {value}"

    # Add SRD traceability comment
    line += f" '{srd}"

    return [line]
```

**Rules:**
- 4-space indent (module-level members are at 1 indent level)
- Match the `Public Const NAME As Type = value` pattern exactly
- Include SRD traceability comment at end of line with `'` prefix
- NO blank lines within the insertion; blank lines handled by insertion position

**After generating, proceed to Step 6 (Validate Generated Code) in core.md.**
