# Module: DAT Constants (ResourceID.vb)
Handles `new_coverage_type` targeting ResourceID.vb. Auto-increments DAT IDs.

## Step 5c: DAT Constant Insertion (ResourceID.vb)

DAT constants in ResourceID.vb may use implicit or explicit typing depending on
the file's `Option Strict` setting. Check the target file at runtime.

> **Prerequisite:** See core.md Step 4 for anchor location. The anchor has
> already been located before this step runs.

```python
def generate_dat_constants(work, lines, file_content):
    """Generate DAT constant lines for ResourceID.vb.

    Checks Option Strict setting to determine whether to include 'As Integer'.
    - Option Strict Off (e.g., Portage Mutual): implicit typing (no 'As Integer')
    - Option Strict On: explicit typing required ('As Integer')
    """
    p = work["parameters"]
    classifications = p.get("classifications", [])
    srd = work["srd"]

    # Read Option Strict setting from target file
    option_strict = "Option Strict On" in file_content

    # Find the highest existing DAT constant ID
    max_id = find_max_dat_id(lines)

    result = []
    next_id = max_id + 1

    for cls in classifications:
        dat_name = cls["dat_constant"]
        if option_strict:
            line = f"    Public Const {dat_name} As Integer = {next_id}"
        else:
            line = f"    Public Const {dat_name} = {next_id}"
        line += f" '{srd}"
        result.append(line)
        next_id += 1

    return result


def find_max_dat_id(lines):
    """Find the highest DAT constant integer ID in ResourceID.vb.

    Scans all lines matching 'Public Const DAT_* = {int}'.
    """
    max_id = 0
    for line in lines:
        match = re.search(
            r'Public\s+Const\s+DAT_\w+\s*=\s*(\d+)',
            line
        )
        if match:
            val = int(match.group(1))
            if val > max_id:
                max_id = val
    return max_id
```

**IMPORTANT:** The `Option Strict` setting varies by carrier. Check the target
ResourceID.vb file header to determine which format to use:
- `Option Strict Off`: generate without `As Integer` (implicit typing)
- `Option Strict On`: generate WITH `As Integer` (explicit typing required)

**After generating, proceed to Step 6 (Validate Generated Code) in core.md.**
