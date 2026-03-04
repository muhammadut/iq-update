# Change Engine — Strategy Reference

Reference material for common code change patterns. The Change Engine reads
the relevant section when a capsule includes a `strategy_hint`. These are NOT
dispatch targets — they are "here's how we handled this kind of change before"
guidance that helps the engine avoid pitfalls.

The engine can handle ANY change without a strategy hint. These sections simply
encode hard-won knowledge about the VB.NET rating codebase.

---

## 1. Array6 Value Changes

**Strategy hint:** `array6-multiply`

Used when the intent is to multiply all numeric arguments in Array6 calls by a
factor (e.g., "increase all liability premiums by 3%").

### What to Look For

Array6 rate values appear as variable assignments:
```vb
varRates = Array6(512.59, 28.73, 463.03, 28.73, 575.10, 28.73, 420.16, 28.73, 132.74)
liabilityPremiumArray = Array6(0, 78, 161, 189, 213, 291)
```

Array6 accepts 1 to 14+ arguments (the name is a misnomer). Arguments are
comma-separated numeric values, possibly including:
- Plain integers: `78`, `291`
- Decimals: `324.29`, `462.32`
- Zeros: `0` (sentinel — skip during multiplication)
- Variables: `basePremium` (skip — not a numeric literal)
- Arithmetic expressions: `30 + 10` (evaluate first, then multiply)
- Negative values: `-5` (valid rate value)

### What to AVOID

These Array6 calls are NOT rate values and must NEVER be modified:

| Pattern | Why | Example |
|---------|-----|---------|
| `IsItemInArray(x, Array6(...))` | Membership test | `If IsItemInArray(covCode, Array6(1, 2, 3))` |
| `varCovTypes = Array6(Enum.val, ...)` | Enum collection | `Array6(TBWApplication.BasePremEnum.bpeTPLBI, ...)` |
| `Array6(0, 0, 0, 0, 0, 0)` | All-zero default init | Skip — 0 * factor = 0 |

**Detection rules:**
- Membership test: Array6 is an argument to another function (not LHS of `=`)
- Enum collection: arguments contain member access (letter.letter pattern, using
  regex `[A-Za-z_]\.[A-Za-z_]`)
- All-zero: every argument is `0`

### Parsing Array6 Arguments

```python
import re

def parse_array6_args(line):
    """Parse numeric arguments from Array6() call.

    Returns list of parsed args:
      {"raw": str, "value": float|None, "is_variable": bool, "is_expression": bool}
    Returns None if line has no Array6.
    """
    # Find Array6( using depth-aware paren matching (Rule 8 in core.md)
    match = re.search(r'Array6\s*\(', line)
    if not match:
        return None

    open_idx = match.end() - 1
    close_idx = find_array6_close_paren(line, open_idx)
    if close_idx is None:
        return None

    args_str = line[open_idx + 1:close_idx]
    raw_args = args_str.split(",")

    parsed = []
    for raw in raw_args:
        raw = raw.strip()

        # Variable name (starts with letter, no operators)
        if re.match(r'^[a-zA-Z_]\w*$', raw):
            parsed.append({"raw": raw, "value": None,
                           "is_variable": True, "is_expression": False})

        # Arithmetic expression (has binary operator between digits)
        elif re.search(r'\d\s*[\+\-\*/]\s*\d', raw):
            try:
                evaluated = safe_eval_arithmetic(raw)
                parsed.append({"raw": raw, "value": evaluated,
                               "is_variable": False, "is_expression": True})
            except (ValueError, SyntaxError):
                parsed.append({"raw": raw, "value": None,
                               "is_variable": False, "is_expression": True})

        # Plain number (possibly negative)
        elif re.match(r'^-?\d+(\.\d+)?$', raw):
            parsed.append({"raw": raw, "value": float(raw),
                           "is_variable": False, "is_expression": False})
        else:
            parsed.append({"raw": raw, "value": None,
                           "is_variable": False, "is_expression": True})

    return parsed
```

### Multiplication and Rounding

Each target line has its own `rounding` field — the authoritative per-line decision:

| `rounding` value | Action | Example |
|-----------------|--------|---------|
| `"banker"` | Banker's rounding (round half to even) → integer output | `78 * 1.03 = 80.34 → 80` |
| `"none"` | Preserve decimal precision from original | `324.29 * 1.03 = 334.02` |
| `null` | Preserve original format (int→int, decimal→decimal) | Use as fallback |

**CRITICAL:** Detect original decimal precision PER ARGUMENT using
`detect_decimal_places()`. A value `0.075` (3dp) multiplied by `1.05` should
produce `0.079` (3dp), not `0.08` (2dp).

**Banker's rounding** uses `Decimal` to avoid IEEE 754 edge cases:

```python
from decimal import Decimal, ROUND_HALF_EVEN

def bankers_round(value):
    d = Decimal(str(value))
    return int(d.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
```

Verification: `bankers_round(2.5)=2`, `bankers_round(3.5)=4`,
`bankers_round(4.5)=4`, `bankers_round(5.5)=6`. Matches VB.NET `CInt()`.

### Applying the Change

Use depth-aware paren matching (not regex `(.+?)`) to find the Array6 arg list,
then rebuild:

```python
def apply_array6_change(line, parsed_args, new_values):
    """Replace Array6 arguments preserving formatting."""
    match = re.search(r'Array6\s*\(', line)
    open_idx = match.end() - 1
    close_idx = find_array6_close_paren(line, open_idx)

    prefix = line[:match.start()]
    array6_open = line[match.start():open_idx + 1]
    old_args = line[open_idx + 1:close_idx]
    suffix = line[close_idx + 1:]

    # Match separator style
    separator = ", " if ", " in old_args else ","
    new_args = separator.join(new_values)

    return prefix + array6_open + new_args + ")" + suffix
```

**Formatting rules:**
1. Copy leading whitespace from original line exactly
2. Detect separator style (`, ` vs `,`) and match it
3. Preserve everything after the closing `)` (trailing comments, etc.)
4. Preserve variable prefix (`varRates = `, etc.)

### Worked Example: Mixed Rounding (Integer + Decimal)

```
Intent: Multiply liability premiums by 1.03
Function: GetLiabilityBundlePremiums

Line 4058 (rounding: "banker"):
  Input:  Array6(0, 78, 161, 189, 213, 291)
  0→0  78*1.03=80.34→80  161*1.03=165.83→166  189*1.03=194.67→195
  213*1.03=219.39→219  291*1.03=299.73→300
  Output: Array6(0, 80, 166, 195, 219, 300)

Line 4062 (rounding: "none", 2dp):
  Input:  Array6(0, 0, 0, 0, 324.29, 462.32)
  0→0  0→0  0→0  0→0  324.29*1.03=334.02  462.32*1.03=476.19
  Output: Array6(0, 0, 0, 0, 334.02, 476.19)
```

### Common Pitfalls

1. **Don't round factors or limits.** Only rate values get rounded. Check the
   `rounding` field — `null` means exact.
2. **Don't modify all-zero Array6.** Zero stays zero.
3. **Don't confuse test Array6 with rate Array6.** Check the LHS of `=`.
4. **Handle mixed rounding per LINE, not per function.** Same function can have
   both integer and decimal Array6 branches.
5. **Preserve expression format awareness.** When `evaluated_args` is present,
   multiply those pre-evaluated values, then output clean numbers (not split
   expressions like `31.5 + 10.5`).

---

## 2. Factor Table Changes

**Strategy hint:** `factor-table`

Used when the intent is to change specific values in Select Case factor tables
or Const declarations.

### What to Look For

Factor tables appear as Select Case blocks:
```vb
Select Case deductible
    Case 500  : dblDedDiscount = 0
    Case 1000 : dblDedDiscount = -0.075
    Case 2500 : dblDedDiscount = -0.15
    Case 5000 : dblDedDiscount = -0.2
End Select
```

Constants as rate values:
```vb
Const ACCIDENTBASE = 200
Private Const dblMultiVehicleDis As Double = -0.1
```

Scalar assignments:
```vb
baseRate = 66.48
```

### Simple Value Substitution

Find the old value on the target line and replace with the new value:

```python
def compute_factor_change(line, old_value, new_value):
    """Replace old_value with new_value, preserving formatting."""
    old_str = format_vb_number(old_value)
    new_str = format_vb_number(new_value)

    # Try multiple format variations
    patterns_to_try = [old_str]
    if "." in old_str:
        patterns_to_try.append(old_str + "0")      # -0.2 vs -0.20
    if old_str.endswith("0") and "." in old_str:
        patterns_to_try.append(old_str.rstrip("0")) # -0.20 vs -0.2

    for try_str in patterns_to_try:
        escaped = re.escape(try_str)
        pattern = r'(?<![.\d\-])' + escaped + r'(?![.\d])'
        if re.search(pattern, line):
            return re.sub(pattern, new_str, line, count=1)

    return FAIL(f"old_value '{old_str}' not found on line: {line.strip()}")
```

**NEVER round factor values.** Factors like `-0.22` are exact as specified by
the ticket. The `rounding` field for factor changes is always `null`.

### Const Declarations

When the target is a Const, the same value substitution logic applies:

```
Before: "        Const ACCIDENTBASE = 200"
After:  "        Const ACCIDENTBASE = 210"
```

Use `replace_value_in_line()` to preserve trailing comments:
```
Before: "    Private Const ACCIDENTBASE As Double = 0.3     'Base Surcharge"
After:  "    Private Const ACCIDENTBASE As Double = 0.35     'Base Surcharge"
```

### Limit Values

Limit changes (`If intLimit = 5000 Then` -> `If intLimit = 10000 Then`) use the
same substitution logic. Never round limits.

### Case Syntax Awareness

The intent parameters may specify `case_value` as an integer, but the actual code
may use string syntax. Understand all Case variations:

| Code Pattern | `case_value` in intent | Notes |
|-------------|----------------------|-------|
| `Case 5000` | `5000` | Numeric literal |
| `Case "5000"` | `"5000"` | String literal |
| `Case 0 To 25` | `"0 To 25"` | Range expression |
| `Case Is <= 3000` | `"Is <= 3000"` | Comparison |
| `Case Is > ACCIDENTSURCHARGEAT` | references a Const | May need Const resolution |

### Developer-Confirmed Subset

When `candidates_shown > len(target_lines)`, the developer saw multiple matching
values and chose a SUBSET. Only modify the lines listed in `target_lines`. The
other candidates were intentionally excluded.

### Common Pitfalls

1. **VB.NET format variations.** `-0.20` and `-0.2` are the same value. Try
   multiple format strings when searching.
2. **Trailing comments.** Use substring replacement, not line replacement.
3. **Multiple code paths.** A Case block may have `If/ElseIf` inside it with
   different values per branch. The intent specifies which line(s) to change.
4. **Function-local vs module-level Const.** Both exist. Same replacement logic.
5. **Negative lookbehind.** Always include `\-` to prevent matching `0.2`
   inside `-0.2`.

---

## 3. Case Block Insertion

**Strategy hint:** `case-block-insertion`

Used when the intent is to add new Case entries into existing Select Case
structures.

### What to Look For

Select Case structures where new entries need to be added:
```vb
Select Case strCoverageType
    Case PREFERRED
        ...
    Case STANDARD
        ...
    Case FARMPAK
        ...
    ' New Case goes here (before End Select, or before Case Else)
End Select
```

### Generating Case Blocks

The engine measures indentation from existing Case blocks — NEVER hardcodes indent
levels.

```python
def generate_case_block(intent, lines, anchor_idx):
    """Generate a Case block matching existing indentation."""
    params = intent["parameters"]
    constant_name = params.get("case_value", params.get("constant_name", ""))
    classifications = params.get("classifications", [])

    # Measure indentation from adjacent Case blocks
    case_indent = measure_case_indent(lines, anchor_idx)
    body_indent = case_indent + "    "

    result = []

    # Outer Case line
    result.append(f"{case_indent}Case {constant_name}")

    if classifications:
        # Nested Select Case for sub-classifications
        nested_indent = body_indent + "    "
        result.append(f"{body_indent}Select Case strClassification")
        for cls in classifications:
            result.append(
                f"{nested_indent}Case {cls['name']} : "
                f"intFileID = {cls['dat_constant']}"
            )
        result.append(f"{body_indent}End Select")
    else:
        # Simple body — use intent description for body content
        body = params.get("case_body", "")
        if body:
            for body_line in body.split("\n"):
                result.append(f"{body_indent}{body_line.strip()}")

    return result
```

### Insertion Position

**CRITICAL: Insert BEFORE `Case Else`, not before `End Select`.** `Case Else`
is the catch-all and must remain last. If the Select Case has a `Case Else`:

```vb
    Case STANDARD
        ...
    ' ← INSERT NEW CASE HERE
    Case Else
        ...
End Select
```

If there is no `Case Else`:
```vb
    Case STANDARD
        ...
    ' ← INSERT NEW CASE HERE
End Select
```

Use `find_case_else()` from core.md to detect this.

### Nested Select Case

Some Case blocks contain nested Select Case structures (e.g., rate table routing):
```vb
Case ELITECOMP
    Select Case strClassification
        Case STANDARD : intFileID = DAT_Home_EliteComp_Standard
        Case PREFERRED : intFileID = DAT_Home_EliteComp_Preferred
    End Select
```

The engine discovers the nesting pattern from adjacent Case blocks and replicates
it exactly.

### Indentation Discovery

Real indentation levels found in the codebase:
- SK `GetBasePremium_Home`: Cases at 20 spaces (5 levels deep)
- Nested Cases at 28 spaces (7 levels deep)
- Other functions may differ

**ALWAYS measure from adjacent Case blocks.** Use `measure_case_indent()`.

### Common Pitfalls

1. **Case Else ordering.** Must remain last. Always check before inserting.
2. **Nesting depth.** Don't assume 4 spaces per level — measure actual indent.
3. **Duplicate detection.** Before inserting, check if the Case value already
   exists in the Select Case. Report `skipped` if duplicate.
4. **Trailing intent comments.** Add traceability: `Case ELITECOMP 'intent-005`
5. **Re-locate anchors.** If multiple insertions target the same file, re-locate
   after each one (indices shift).

---

## 4. Constant Management

**Strategy hint:** `constant-management`

Used when the intent is to add new Const declarations or modify existing ones
at module level.

### Adding New Constants

Module-level constants follow this pattern:
```vb
    Public Const PREFERRED As String = "Preferred"
    Public Const STANDARD As String = "Standard"
    ' New constant inserted after the last existing one:
    Public Const ELITECOMP As String = "Elite Comp."
```

**Formatting rules:**
- 4-space indent (module-level members are at 1 indent level)
- `Public Const NAME As Type = value` pattern
- String constants: value in double quotes
- Integer constants: plain numeric value
- Coverage type constants are always `String`

### DAT Constants (ResourceID.vb)

DAT constants in ResourceID.vb auto-increment IDs:
```vb
    Public Const DAT_Home_EliteComp_Standard = 9501
    Public Const DAT_Home_EliteComp_Preferred = 9502
```

**Option Strict awareness:** Check the target file's `Option Strict` setting:
- `Option Strict Off`: implicit typing (no `As Integer`)
- `Option Strict On`: explicit typing (`As Integer` required)

```python
def find_max_dat_id(lines):
    """Find the highest DAT constant ID in ResourceID.vb."""
    max_id = 0
    for line in lines:
        match = re.search(r'Public\s+Const\s+DAT_\w+\s*=\s*(\d+)', line)
        if match:
            val = int(match.group(1))
            if val > max_id:
                max_id = val
    return max_id
```

### Modifying Existing Constants

When changing an existing Const value, use the same value substitution as
factor table changes (Strategy 2). Preserve trailing comments.

### Common Pitfalls

1. **Duplicate detection.** Search the entire file for the constant name before
   inserting. Report `skipped` if already present.
2. **Insertion position.** Insert after the last existing constant in the same
   logical group (coverage types together, DAT IDs together).
3. **Implicit vs explicit typing.** Match the existing file's convention.
4. **Traceability comment.** Append intent reference: `'intent-005`

---

## 5. New File Creation

**Strategy hint:** `new-file-creation`

Used when the intent requires creating new Option_*.vb or Liab_*.vb files.

### Template-Based Creation

The engine reads an existing peer file (the template) and transforms it:

1. **Read the template file** — a similar Option_*.vb or Liab_*.vb
2. **Replace names:**
   - Module name: `modOption_{OldName}` -> `modOption_{NewName}`
   - Function name: `Option_{OldName}` -> `Option_{NewName}`
   - VB_Name attribute: `"modOption_{OldName}"` -> `"modOption_{NewName}"`
3. **Apply premium values** from the intent's coverage options
4. **Add traceability comment** after module declaration

### Module Naming Conventions

| File Type | Module Name | Function Name |
|-----------|------------|---------------|
| Option | `modOption_{Name}` | `Option_{Name}()` |
| Liab | `modLiab_{Name}` | `Liab_{Name}()` |

**No province, LOB, or date in module/function names.** Only in the filename:
`Option_Bicycle_SKHome20260101.vb` but the module inside is `modOption_Bicycle`.

### Return Types

| File Type | Return Type | Assignment Pattern |
|-----------|------------|-------------------|
| Option | `Short` | `Option_Name = intPrem` |
| Liab | `Short` | `Liab_Name = intPrem` |

### Imports

| File Type | Imports Required |
|-----------|-----------------|
| Option | None (no Imports line) |
| Liab | `Imports CodeArchitects.VB6Library` |

### VBPROJ Entry

Every new file requires a `<Compile Include>` entry in the .vbproj:
```xml
<Compile Include="..\..\Code\Option_Bicycle_SKHome20260101.vb"/>
```

See core.md VBPROJ MANAGEMENT section for the insertion logic.

### Live Investigation Fallback

If no template file is specified, the engine reads 3 similar files via Glob:
- For Option files: `{Province}/Code/Option_*_{PROV}{LOB}*.vb`
- For Liab files: `{Province}/Code/Liab_*_{PROV}{LOB}*.vb`

From each file, extract:
- Function signature pattern (params, types)
- Parameter handling (ByVal/ByRef)
- Return statement pattern
- ReportLine calls (if any)
- Error handling pattern (if any)

Use the extracted structure as the generation template.

### Common Pitfalls

1. **Never add Try/Catch** to Option/Liab files. The codebase doesn't use them.
2. **Never use line continuation** (`_`). Keep long lines as-is.
3. **Never introduce GoTo.** Handle existing GoTo but don't create new ones.
4. **Match exactly.** Copy structure, naming, comment style from the template.
5. **Idempotent vbproj.** Check if `<Compile Include>` already exists before adding.

---

## 6. Expressions and Arithmetic

**Strategy hint:** `expressions`

Used when Array6 arguments contain arithmetic expressions (e.g., `30 + 10`).

### What to Look For

```vb
liabilityPremiumArray = Array6(30 + 10, 36 + 13, 40 + 14, 36, 72)
```

Historical artifact — base + adjustment. After a rate update, the expression
should be REPLACED with the single computed result, not preserved as split
arithmetic.

### How to Handle

When the intent's target lines have `has_expressions: true`:

1. **Use `evaluated_args`** from the Analyzer (pre-computed values for each arg)
2. **Multiply the evaluated values** by the factor
3. **Replace the entire expression** with the computed result

```
Before: Array6(30 + 10, 36 + 13, 40 + 14, 36, 72)
evaluated_args: [40, 49, 54, 36, 72]
factor: 1.05

40*1.05=42  49*1.05=51.45→51  54*1.05=56.7→57  36*1.05=37.8→38  72*1.05=75.6→76

After: Array6(42, 51, 57, 38, 76)
```

**Key:** Output is a clean Array6 with no arithmetic. Expressions are historical
artifacts and don't need to be preserved in updated rate tables.

### Fallback Without evaluated_args

If `evaluated_args` is not present, use `safe_eval_arithmetic()` (AST-based)
to evaluate each expression at edit time. This is less reliable — the Analyzer
should have provided pre-evaluated values.

### Disambiguation: Expression vs Negative Number

```
-10          → negative number (value = -10.0)
30 + 10      → expression (value = 40.0)
-0.2         → negative number (value = -0.2)
30 - 10      → expression (value = 20.0)
```

Test: if the string starts with optional minus + digits (possibly decimal) and
contains NO binary operators between digits, it's a plain number.

### Common Pitfalls

1. **Don't preserve split arithmetic.** `30 + 10` at factor 1.05 becomes `42`,
   not `31.5 + 10.5`. The split form is misleading after a rate update.
2. **Watch for variable names in expressions.** If an arg is `basePremium`, skip
   it — it's a variable reference, not arithmetic.
3. **Apply correct rounding** after multiplication, same as plain Array6 values.

---

## 7. Flow Modification

**Strategy hint:** `flow-modification`

Used when the intent involves modifying control flow: If/ElseIf branches,
Select Case restructuring, or general logic refactoring (bug fixes, condition
reordering, guard clause insertion).

### If/ElseIf Branch Modification

Common operations:
- **Add a new branch:** Insert `ElseIf` before the final `Else` (or before
  `End If` if no `Else` exists). Measure indentation from adjacent branches.
- **Remove a branch:** Delete the `ElseIf` line and its body. Verify no
  downstream code references the removed branch's variable assignments.
- **Reorder conditions:** Move an `ElseIf` block (condition + body) to a
  different position. Preserve exact indentation and blank-line conventions.
- **Modify a condition:** Replace the boolean expression on an existing
  `If` or `ElseIf` line. Keep the `Then` keyword and trailing comments.

### Select Case Restructuring

- **Add new Case block:** See Strategy 3 (case-block-insertion) for detailed
  guidance. Prefer that strategy hint when the change is purely additive.
- **Modify existing Case body:** Replace lines within a Case block. Use
  line-range anchoring (start line of Case, end at next Case/End Select).
- **Reorder Case blocks:** Move a Case block and its body as a unit. The
  runtime evaluates Case blocks top-to-bottom, so order can matter for
  overlapping ranges.

### GoTo Statement Handling

The codebase contains legacy `GoTo` statements. Rules:
- **Preserve existing GoTo** if it appears in the target function. Do not
  remove or refactor GoTo unless the intent explicitly requests it.
- **Never introduce new GoTo.** Use structured control flow (If/ElseIf,
  Select Case, Do/Loop) for any new logic.
- **Label preservation:** If a GoTo target label exists, do not rename or
  move it unless the intent explicitly says to.

### Safety Rules

1. **Preserve surrounding logic.** Only modify the lines specified by the
   intent. Do not "clean up" adjacent code, even if it looks improvable.
2. **Do not delete code** unless the intent explicitly instructs deletion.
   When in doubt, comment out with `'` and add a traceability note.
3. **Maintain variable scope.** If a branch assigns a variable used after
   the If/Select block, ensure the variable is still assigned on all paths.
4. **Watch for fall-through effects.** In Select Case, removing a Case block
   may cause values to hit `Case Else`. Verify this is intentional.
5. **Indentation:** Always measure from adjacent branches — never hardcode.

### Worked Example: Adding an ElseIf Branch

```
Intent: Add a "Senior" discount tier (age >= 65) before the Else block.
Function: GetAgeFactor

Before:
        If intAge < 25 Then
            dblFactor = 1.25
        ElseIf intAge < 50 Then
            dblFactor = 1.0
        Else
            dblFactor = 0.95
        End If

After:
        If intAge < 25 Then
            dblFactor = 1.25
        ElseIf intAge < 50 Then
            dblFactor = 1.0
        ElseIf intAge >= 65 Then       'intent-007
            dblFactor = 0.85
        Else
            dblFactor = 0.95
        End If
```

### Common Pitfalls

1. **Don't insert after `Else`.** New `ElseIf` goes BEFORE `Else`, not after.
2. **Nested If inside Case.** Some functions nest If/ElseIf inside Case blocks.
   Verify you're editing the right nesting level.
3. **Implicit line continuation.** VB.NET 10+ allows implicit continuation
   after operators and commas. A condition like `If x > 0 And` may continue
   on the next line — don't split the edit.
4. **Boolean operator precedence.** `And`/`Or` vs `AndAlso`/`OrElse` have
   different short-circuit behavior. Match the existing style in the function.

---

## Cross-Cutting Guidance

These notes apply across all strategies.

### Carrier-Agnostic Design

All strategies reference `config.yaml` for carrier-specific values:
- `carrier_prefix` (e.g., "PORT" for Portage Mutual)
- `cross_province_shared_files` (never auto-modify)
- Province codes, LOB lists, naming patterns

The strategies themselves are carrier-agnostic. The same Array6 multiply logic
works for any TBW/IntelliQuote carrier with manufactured rating.

### Configuration Sources

| Source | What | When |
|--------|------|------|
| `config.yaml` | Province codes, LOB lists, naming patterns | Always available |
| `pattern-library.yaml` | Function registry with params/return types | From /iq-init |
| `codebase-profile.yaml` | Dispatch tables, vehicle profiles, glossary | From /iq-init |
| `.vbproj` files | Authoritative file references | Parsed at runtime |
| FUB | Branch tree, hazards, adjacent context | From Analyzer |
| Peer examples | Active function bodies for structural reference | From capsule |

### When No Strategy Matches

The Change Engine is a reasoning agent. If the intent doesn't match any known
strategy, the engine:

1. Reads the target code carefully
2. Reads the intent description
3. Uses FUB hazards and branch tree for structural awareness
4. Reads peer examples (if provided) for style reference
5. Reasons about the minimal edit needed
6. Makes the change, preserving all formatting
7. Flags with `needs_review: true` if confidence is low

No classification gate. No "doesn't fit a template." The engine reads and reasons.
