# Module: New Endorsement/Liability File
Handles `new_endorsement_flat` and `new_liability_option`. Creates new Option_*.vb or Liab_*.vb files from templates and adds CalcOption routing.

## Input Schema — Pattern 3: new_endorsement_flat (Option file + CalcOption routing)

```yaml
id: "op-007-01"
srd: "srd-007"
title: "Create Option_Bicycle_SKHome20260101.vb endorsement handler"
file: "Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb"
file_type: "option_module"
function: "CalcOption_Bicycle"
location: "new file"
agent: "logic-modifier"
depends_on: []
blocked_by: []
pattern: "new_endorsement_flat"
parameters:
  endorsement_name: "Bicycle"
  province_code: "SK"
  lob: "Home"
  effective_date: "20260101"
  premium_structure: "flat"              # "flat" | "tiered"
  coverage_options:
    - label: "A"
      premium: 25.0
    - label: "B"
      premium: 50.0

# -- Added by Analyzer --
needs_new_file: true
template_reference:
  file: "Saskatchewan/Code/Option_IdentityTheft_SKHome20250901.vb"
  file_hash: "sha256:template123..."
target_file: "Saskatchewan/Code/Option_Bicycle_SKHome20260101.vb"
vbproj_target: "Saskatchewan/Home/20260101/Cssi.IntelliQuote.PORTSKHome20260101.vbproj"
file_hash: null                         # New file -- no existing hash
needs_copy: false                       # Not a copy, it's a creation
candidates_shown: 1
developer_confirmed: true
```

**Field semantics for new_endorsement_flat:**

| Field | Type | Description |
|-------|------|-------------|
| `parameters.endorsement_name` | string | Name of the endorsement |
| `parameters.province_code` | string | Province code (AB, SK, etc.) |
| `parameters.lob` | string | Line of business (Home, Condo, etc.) |
| `parameters.effective_date` | string | YYYYMMDD date for filename |
| `parameters.premium_structure` | string | `"flat"` or `"tiered"` |
| `parameters.coverage_options[]` | list | Label/premium pairs for Select Case |
| `needs_new_file` | bool | Always `true` for this pattern |
| `template_reference.file` | string | Existing file to use as structural template |
| `vbproj_target` | string | .vbproj file to add `<Compile Include>` to |

## Input Schema — Pattern 4: new_liability_option (CalcOption routing Case block)

```yaml
id: "op-008-01"
srd: "srd-008"
title: "Add CalcOption routing for RentedDwelling liability"
file: "Saskatchewan/Code/CalcOption_SKHome20260101.vb"
file_type: "calc_option_module"
function: "CalcOption"
location: "inside Select Case optionCode"
agent: "logic-modifier"
depends_on: ["op-008-02"]               # Rate table must exist first
blocked_by: []
pattern: "new_liability_option"
parameters:
  option_code: "RENTEDDWELLING"
  call_target: "CalcLiab_RentedDwelling"
  call_module: "Liab_RentedDwelling_SKHome"

# -- Added by Analyzer --
source_file: "Saskatchewan/Code/CalcOption_SKHome20250901.vb"
target_file: "Saskatchewan/Code/CalcOption_SKHome20260101.vb"
needs_copy: true
file_hash: "sha256:calcoption123..."
function_line_start: 10
function_line_end: 120
insertion_point:
  line: 100
  position: "before_end_select"
  context: "Inside: Select Case optionCode (line 15)"
  end_select_line: 110
existing_cases:
  - name: "SEWERBACKUP"
    line: 30
  - name: "IDENTITYTHEFT"
    line: 60
duplicate_check: "Case RENTEDDWELLING not found -- safe to add"
needs_new_file: false
template_reference: null
candidates_shown: 1
developer_confirmed: true
```

## Step 5d: CalcOption Routing (new_endorsement_flat, new_liability_option)

Insert a `Case {option_code}` block before `Case Else` in the CalcOption routing
file. The Case block calls the Option/Liab function.

> **Prerequisite:** See core.md Step 4 for anchor location and
> `measure_case_indent` helper (defined in core.md Shared Helper Functions section).

```python
def generate_calcoption_case(work, lines, anchor_idx):
    """Generate a CalcOption routing Case block.

    Inserts a Case entry that dispatches to the new Option/Liab function.
    Format:
        Case {code}    '{endorsement_name}
            dblPrem = {call_target}()
    """
    p = work["parameters"]
    srd = work["srd"]

    pat = work["pattern"]
    if pat == "new_endorsement_flat":
        option_code = p.get("option_code", "0")
        endorsement_name = p["endorsement_name"]
        call_target = f"Option_{endorsement_name}"
    elif pat == "new_liability_option":
        option_code = p["option_code"]
        endorsement_name = option_code
        call_target = p["call_target"]
    else:
        return FAIL(f"generate_calcoption_case: unsupported pattern {pat}")

    # Measure indentation from existing Case blocks
    case_indent = measure_case_indent(lines, anchor_idx)
    body_indent = case_indent + "    "

    result = []
    result.append(f"{case_indent}Case {option_code}    '{endorsement_name} '{srd}")
    result.append(f"{body_indent}dblPrem = {call_target}()")

    return result
```

**Trailing comment convention:** CalcOption Case blocks have a trailing comment
with the endorsement name: `Case 2    'Bicycle`. This is consistent across AB
and SK CalcOption files.

## Step 9: Handle New File Creation

For operations with `needs_new_file: true` (Option_*.vb, Liab_*.vb), the Logic
Modifier creates the file from a template. The file-copier does NOT handle
these because structural understanding is required to generate the content.

```python
def create_new_file(work, carrier_root):
    """Create a new Option_*.vb or Liab_*.vb file from a template.

    Steps:
    1. Read template file
    2. Apply name/value transformations
    3. Write new file to target path
    """
    template_ref = work["template_ref"]
    if not template_ref or "file" not in template_ref:
        return FAIL("FILE_NOT_FOUND: template_reference.file is required "
                     "for needs_new_file operations")

    template_path = os.path.join(carrier_root, template_ref["file"])
    if not os.path.exists(template_path):
        return FAIL(f"FILE_NOT_FOUND: Template file does not exist: "
                     f"{template_ref['file']}. "
                     "Developer must provide a valid template.")

    # Read template
    with open(template_path, "rb") as f:
        raw = f.read()
    if b"\r\n" in raw:
        line_ending = "\r\n"
    else:
        line_ending = "\n"
    template_text = raw.decode("utf-8")
    template_lines = template_text.split(line_ending)

    p = work["parameters"]
    endorsement_name = p["endorsement_name"]
    srd = work["srd"]

    # Determine file type from pattern
    is_liab = work["pattern"] == "new_liability_option" or "Liab_" in work["target_file"]
    is_option = not is_liab

    # Extract template's endorsement name from the module declaration
    old_name = extract_template_name(template_lines, is_option)
    if old_name is None:
        return FAIL("Cannot determine template endorsement name from module declaration")

    # Apply transformations
    new_lines = []
    for line in template_lines:
        new_line = line

        # Module name: modOption_{OldName} -> modOption_{NewName}
        # or modLiab_{OldName} -> modLiab_{NewName}
        mod_prefix = "modOption_" if is_option else "modLiab_"
        new_line = new_line.replace(f"{mod_prefix}{old_name}", f"{mod_prefix}{endorsement_name}")

        # Function name: Option_{OldName} -> Option_{NewName}
        # or Liab_{OldName} -> Liab_{NewName}
        func_prefix = "Option_" if is_option else "Liab_"
        new_line = new_line.replace(f"{func_prefix}{old_name}", f"{func_prefix}{endorsement_name}")

        # VB_Name attribute comment
        new_line = new_line.replace(f'"{mod_prefix}{old_name}"', f'"{mod_prefix}{endorsement_name}"')

        new_lines.append(new_line)

    # Apply premium values from parameters
    coverage_options = p.get("coverage_options", [])
    if coverage_options:
        new_lines = apply_premium_values(new_lines, coverage_options, endorsement_name, is_option)

    # Add SRD traceability comment after module declaration
    for i, line in enumerate(new_lines):
        if "Module " in line and not line.strip().startswith("'"):
            new_lines.insert(i + 1, f"    '{srd}")
            break

    # Ensure Imports for Liab files, no Imports for Option files
    if is_liab and not any("Imports CodeArchitects.VB6Library" in ln for ln in new_lines):
        new_lines.insert(0, "Imports CodeArchitects.VB6Library")
    elif is_option:
        new_lines = [ln for ln in new_lines if "Imports CodeArchitects.VB6Library" not in ln]

    # Write new file
    target_path = os.path.join(carrier_root, work["target_file"])
    content = line_ending.join(new_lines)
    with open(target_path, "wb") as f:
        f.write(content.encode("utf-8"))

    return (target_path, len(new_lines), line_ending)


def extract_template_name(lines, is_option):
    """Extract the endorsement name from a template file's module declaration.

    Looks for 'Partial Public Module modOption_{Name}' or 'modLiab_{Name}'.
    Returns the Name portion, or None if not found.
    """
    prefix = "modOption_" if is_option else "modLiab_"
    for line in lines:
        match = re.search(r'Module\s+' + re.escape(prefix) + r'(\w+)', line)
        if match:
            return match.group(1)
    return None


def apply_premium_values(lines, coverage_options, endorsement_name, is_option):
    """Replace template premium values with new values from parameters.

    For simple flat-premium options with a Select Case on coverage label,
    generates new Case blocks. For single-value premiums, replaces the
    intPrem assignment.
    """
    # Simple single-premium case: replace 'intPrem = {old}' with new value
    if len(coverage_options) == 1:
        new_premium = coverage_options[0]["premium"]
        for i, line in enumerate(lines):
            if re.search(r'intPrem\s*=\s*\d+', line) and not line.strip().startswith("'"):
                lines[i] = re.sub(
                    r'(intPrem\s*=\s*)\d+',
                    f'\\g<1>{int(new_premium)}',
                    line
                )
                break
        return lines

    # Multi-option: handled by template structure (Select Case on coverage label)
    # The template should already have a Select Case structure that the developer
    # reviews. Premium values are inserted by the Planner into the operation YAML.
    return lines
```

**Module naming rules (from research):**
- Module name uses `mod` prefix: `modOption_{Name}` or `modLiab_{Name}`
- NO province, LOB, or date in the module name
- Function name: `Option_{Name}()` or `Liab_{Name}()` -- also no province/date
- Return type is `Short` (assigned via function name: `Option_Name = intPrem`)
- Option files have NO Imports; Liab files have `Imports CodeArchitects.VB6Library`

## Step 10: Handle .vbproj Entry

For `needs_new_file: true` operations, add a `<Compile Include>` entry to the
target .vbproj so the new file is compiled into the DLL.

```python
import xml.etree.ElementTree as ET

def update_vbproj(work, carrier_root):
    """Add a <Compile Include> entry to the .vbproj for a new file.

    Finds the ItemGroup containing other Option/Liab Compile Include entries
    and appends the new entry before </ItemGroup>.
    """
    vbproj_path = os.path.join(carrier_root, work["vbproj_target"])
    if not os.path.exists(vbproj_path):
        return FAIL(f"VBPROJ_PARSE_ERROR: .vbproj not found: {work['vbproj_target']}")

    # Read .vbproj as raw text (preserve formatting exactly)
    with open(vbproj_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Build the Compile Include path
    # New file is in Code/ -> relative path is "..\..\Code\{filename}"
    target_file = work["target_file"]
    filename = os.path.basename(target_file)
    include_path = f"..\\..\\Code\\{filename}"

    # Check if already present (idempotency)
    if include_path in content:
        return SKIPPED(f"Compile Include already exists for {filename}")

    # Find the last ItemGroup that contains Option_ or Liab_ Compile Include entries
    # Insert before its closing </ItemGroup>
    pattern = re.compile(
        r'(<ItemGroup>\s*\n'
        r'(?:.*?<Compile\s+Include="[^"]*(?:Option_|Liab_)[^"]*"[^/]*/>\s*\n)+)'
        r'(.*?)(</ItemGroup>)',
        re.DOTALL
    )

    match = None
    for m in pattern.finditer(content):
        match = m    # Take the last matching ItemGroup

    if not match:
        # Fallback: find any ItemGroup with Code\ references
        fallback = re.compile(
            r'(.*<Compile\s+Include="[^"]*\\Code\\[^"]*"[^/]*/>\s*\n)'
            r'(\s*)(</ItemGroup>)',
            re.DOTALL
        )
        match = None
        for m in fallback.finditer(content):
            match = m
        if not match:
            return FAIL("VBPROJ_PARSE_ERROR: Cannot find suitable ItemGroup "
                         "for Compile Include insertion")

    # Build the new entry (tab indentation matching .vbproj convention)
    new_entry = f'\t\t<Compile Include="{include_path}"/>\n'

    # Insert before </ItemGroup>
    insert_pos = match.start(match.lastindex)
    new_content = content[:insert_pos] + new_entry + content[insert_pos:]

    with open(vbproj_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return OK
```

**Key conventions:**
- Tab indentation for XML elements (2 tabs for `<Compile Include>` lines)
- Self-closing tag: `<Compile Include="..\..\Code\{filename}.vb"/>`
- Backslashes in paths (Windows convention in .vbproj)
- No `<Link>` child element needed for standard Code/ files
- Insert before `</ItemGroup>`, not alphabetically sorted

**After Step 9 + Step 10, proceed to Step 11 (Build Log Entry) in core.md.**
