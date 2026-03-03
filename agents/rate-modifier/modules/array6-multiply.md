# Module: Array6 Multiply

Handles `base_rate_increase` pattern -- multiply Array6 values by a factor with
banker's rounding.

**Prerequisites:** The worker MUST have already loaded `core.md` and `dispatch.md`.

---

## Step 6: Validate Current Values (base_rate_increase)

Before modifying anything, verify that the current line content matches what the
operation YAML expects. See core.md Step 6 for the shared `value_appears_on_line`
helper.

```python
def validate_current_values(lines, located_targets, op):
    """Verify current values match the operation's expectations.

    For base_rate_increase: check that Array6 values parse correctly.
    """
    pattern = op["pattern"]

    for tl, line_idx in located_targets:
        current_line = lines[line_idx]

        # Skip commented lines -- safety check (Analyzer should have excluded)
        if current_line.strip().startswith("'"):
            return FAIL(
                f"Line {line_idx + 1} is commented out. "
                "Analyzer should have excluded this. Aborting."
            )

        if pattern == "base_rate_increase":
            # Verify we can parse Array6 args from this line
            args = parse_array6_args(current_line)
            if args is None:
                return FAIL(
                    f"Cannot parse Array6 args from line {line_idx + 1}: "
                    f"{current_line.strip()}"
                )
            # Verify arg count matches expected
            if tl.get("value_count") and len(args) != tl["value_count"]:
                return FAIL(
                    f"Array6 arg count mismatch at line {line_idx + 1}: "
                    f"expected {tl['value_count']}, found {len(args)}"
                )

    return OK
```

---

## Step 7a: Parse, Multiply, Round

For `base_rate_increase` operations, parse Array6 arguments, multiply each by the
factor, and apply rounding according to the per-line rounding field.

**Array6 Parsing:**

```python
import re

def parse_array6_args(line):
    """Parse numeric arguments from an Array6() call.

    Handles:
      - Integer values: Array6(0, 78, 161, 189, 213, 291)
      - Decimal values: Array6(0, 0, 0, 0, 324.29, 462.32)
      - Arithmetic expressions: Array6(30 + 10, 36 + 13, 40 + 14)
      - Variable as first arg: Array6(basePremium, 233, 274, 319)
      - 1-14+ arguments (NOT limited to 6)
      - Negative values: Array6(-5, 10, -20)

    Returns list of parsed arguments, each as:
      {"raw": str, "value": float_or_None, "is_variable": bool, "is_expression": bool}
    Returns None if line does not contain Array6.
    """
    # Find Array6(...) call — use [^)]+ to match up to FIRST closing paren
    # (avoids grabbing content from trailing comments with parentheses)
    match = re.search(r'Array6\s*\(([^)]+)\)', line)
    if not match:
        return None

    args_str = match.group(1)
    raw_args = split_array6_args(args_str)

    parsed = []
    for raw in raw_args:
        raw = raw.strip()

        # Check if it's a variable name (starts with letter, no operators)
        if re.match(r'^[a-zA-Z_]\w*$', raw):
            parsed.append({
                "raw": raw,
                "value": None,
                "is_variable": True,
                "is_expression": False
            })
        # Check if it's an arithmetic expression (binary operator between digits)
        # Use digit-operator-digit pattern to detect "30 + 10" but NOT "-10"
        # This correctly handles "-30 + 10" (negative-leading expressions)
        elif re.search(r'\d\s*[\+\-\*/]\s*\d', raw):
            # Expression like "30 + 10" or "-30 + 10" (has a binary operator)
            try:
                # Safe evaluation of simple arithmetic (see definition below)
                evaluated = safe_eval_arithmetic(raw)
                parsed.append({
                    "raw": raw,
                    "value": evaluated,
                    "is_variable": False,
                    "is_expression": True
                })
            except (ValueError, SyntaxError):
                parsed.append({
                    "raw": raw,
                    "value": None,
                    "is_variable": False,
                    "is_expression": True
                })
        # Negative number starting with minus
        elif re.match(r'^-?\d+(\.\d+)?$', raw):
            parsed.append({
                "raw": raw,
                "value": float(raw),
                "is_variable": False,
                "is_expression": False
            })
        else:
            # Unknown format -- treat as expression
            parsed.append({
                "raw": raw,
                "value": None,
                "is_variable": False,
                "is_expression": True
            })

    return parsed


def safe_eval_arithmetic(expr):
    """Evaluate simple arithmetic expressions (+ - * /) with numbers only.

    Used as a FALLBACK when evaluated_args is not available from the Analyzer.
    Uses Python's ast module to ensure only safe numeric operations are evaluated.

    Examples:
        "30 + 10"    -> 40
        "-30 + 10"   -> -20
        "36 + 13"    -> 49
        "40 + 14"    -> 54

    Raises ValueError if expression contains anything other than numbers and operators.
    """
    import ast
    node = ast.parse(expr.strip(), mode='eval')
    # Whitelist: only allow numeric expressions and basic arithmetic operators
    for n in ast.walk(node):
        if isinstance(n, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant)):
            continue
        if isinstance(n, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)):
            continue
        # Python 3.7 compat: ast.Num is deprecated but may appear
        if hasattr(ast, 'Num') and isinstance(n, ast.Num):
            continue
        raise ValueError(f"Unsafe expression element: {type(n).__name__} in '{expr}'")
    return eval(compile(node, '<string>', 'eval'))


def split_array6_args(args_str):
    """Split Array6 arguments by comma, respecting parentheses.

    Simple split by comma works for all known patterns.
    Nested function calls inside Array6 args are NOT expected
    in rate-bearing code (those would be in IsItemInArray tests,
    which the Analyzer already filters out).
    """
    return args_str.split(",")
```

**Negative number vs arithmetic expression disambiguation:**

```
-10          -> negative number (value = -10.0)
30 + 10      -> expression (value = 40.0)
-0.2         -> negative number (value = -0.2)
30 - 10      -> expression (value = 20.0)
```

The key test: if the string starts with an optional minus sign followed by digits
(possibly with a decimal point) and contains NO other operators, it's a plain
number. Otherwise it's an expression.

**Multiplication and Rounding:**

```python
import math

def compute_new_array6_values(parsed_args, factor, rounding_mode, evaluated_args=None):
    """Multiply Array6 values by factor, apply rounding.

    Args:
        parsed_args: list from parse_array6_args()
        factor: multiplicative factor (e.g., 1.05)
        rounding_mode: "banker" | "none" | null
        evaluated_args: optional pre-evaluated values (for expressions)

    Returns list of new string values to substitute.
    """
    new_values = []

    for i, arg in enumerate(parsed_args):
        # Variable args (e.g., basePremium) -- leave unchanged
        if arg["is_variable"]:
            new_values.append(arg["raw"])
            continue

        # Get the numeric value to multiply
        if evaluated_args and i < len(evaluated_args):
            value = evaluated_args[i]
        elif arg["value"] is not None:
            value = arg["value"]
        else:
            # Cannot evaluate -- leave unchanged and warn
            new_values.append(arg["raw"])
            continue

        # Skip zero values (sentinel / default initialization)
        if value == 0:
            new_values.append(format_vb_number(0))
            continue

        # Multiply
        new_value = value * factor

        # Apply rounding
        # CRITICAL: Detect original decimal precision per argument, NOT default.
        # 0.075 (3dp) * 1.05 should produce 0.079 (3dp), not 0.08 (2dp).
        arg_precision = detect_decimal_places(arg["raw"])  # from core.md

        if rounding_mode == "banker":
            new_value = bankers_round(new_value)
            new_values.append(str(int(new_value)))
        elif rounding_mode == "none":
            new_values.append(format_vb_decimal(new_value, arg_precision))
        else:
            # null rounding -- preserve original format
            if arg["is_expression"]:
                # Expression: output the evaluated, multiplied integer
                new_value = bankers_round(new_value)
                new_values.append(str(int(new_value)))
            elif "." in arg["raw"]:
                new_values.append(format_vb_decimal(new_value, arg_precision))
            else:
                new_value = bankers_round(new_value)
                new_values.append(str(int(new_value)))

    return new_values


def bankers_round(value):
    """Banker's rounding (round half to even) -- equivalent to VB.NET CInt().

    Uses decimal.Decimal to avoid IEEE 754 floating-point representation errors
    near .5 boundaries (e.g., 50 * 1.05 = 52.50000000000001 in float, which
    would round to 53 instead of 52 with banker's rounding).

    Examples (banker's rounding = round half to EVEN):
        2.5  -> 2   (round to even: 2)
        3.5  -> 4   (round to even: 4)
        4.5  -> 4   (round to even: 4)
        5.5  -> 6   (round to even: 6)
        0.5  -> 0   (round to even: 0)
        1.5  -> 2   (round to even: 2)
        244.65 -> 245  (not a .5 case -- normal rounding)
        287.7  -> 288  (not a .5 case -- normal rounding)
    """
    from decimal import Decimal, ROUND_HALF_EVEN
    # Convert via string to avoid float precision loss (e.g., 52.5 vs 52.50000001)
    d = Decimal(str(value))
    return int(d.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))


```

**NOTE:** `format_vb_number()`, `format_vb_decimal()`, and `detect_decimal_places()`
are defined in **core.md** (Shared Helper Functions section). They are available to
this module because workers always load core.md first.

**CRITICAL: Python's `round()` implements banker's rounding (round half to even).**
This matches VB.NET's `CInt()` behavior. Do NOT use `math.floor(x + 0.5)` or
`int(x + 0.5)` -- those use "round half up" which gives WRONG results.

Verification examples:

```
round(2.5)   = 2   (even)     CInt(2.5)   = 2    MATCH
round(3.5)   = 4   (even)     CInt(3.5)   = 4    MATCH
round(4.5)   = 4   (even)     CInt(4.5)   = 4    MATCH
round(5.5)   = 6   (even)     CInt(5.5)   = 6    MATCH
round(244.65) = 245            CInt(244.65) = 245  MATCH
round(287.7)  = 288            CInt(287.7)  = 288  MATCH
```

---

## Step 8: Apply Array6 Change (String Replacement Preserving Formatting)

```python
def apply_array6_change(line, parsed_args, new_values):
    """Replace Array6 arguments in the line with new values.

    CRITICAL: Preserve the exact formatting pattern:
      - Leading whitespace (indentation)
      - Variable name and assignment operator
      - Array6( prefix
      - Comma-space separation between args
      - Closing parenthesis
      - Any trailing comment

    Args:
        line: original full line
        parsed_args: list from parse_array6_args()
        new_values: list of new string values from compute_new_array6_values()

    Returns: new line string with substituted values.
    """
    import re

    # Find the Array6(...) portion of the line using DEPTH-AWARE paren matching.
    # The simple regex `(Array6\s*\()(.+?)(\))` breaks when arguments contain
    # nested function calls like `CInt(30 + 10)` because it stops at the inner `)`.
    # Instead, find `Array6(` then count parenthesis depth to find the matching `)`.
    array6_start = re.search(r'Array6\s*\(', line)
    if not array6_start:
        return FAIL("Array6 pattern not found on line")

    open_paren_idx = array6_start.end() - 1  # Index of the opening `(`
    depth = 1
    close_paren_idx = None
    in_string = False
    for ci in range(open_paren_idx + 1, len(line)):
        ch = line[ci]
        if ch == '"':
            in_string = not in_string
        if in_string:
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                close_paren_idx = ci
                break

    if close_paren_idx is None:
        return FAIL("Unbalanced parentheses in Array6 call -- possible multi-line")

    prefix = line[:array6_start.start()]                    # Everything before Array6(
    array6_open = line[array6_start.start():open_paren_idx + 1]  # "Array6(" or "Array6 ("
    old_args_str = line[open_paren_idx + 1:close_paren_idx]     # Original arg string
    close_paren = ")"
    suffix = line[close_paren_idx + 1:]                    # Everything after )

    # Detect spacing pattern from original: "0, 78, 161" vs "0,78,161"
    if ", " in old_args_str:
        separator = ", "
    elif "," in old_args_str:
        separator = ","
    else:
        separator = ", "  # Default

    # Build new arg string
    new_args_str = separator.join(new_values)

    # Reconstruct the line
    new_line = prefix + array6_open + new_args_str + close_paren + suffix

    return new_line
```

**Formatting preservation rules:**

1. **Indentation:** Copy the leading whitespace from the original line exactly
   (spaces, tabs, or mixed). Never re-indent.
2. **Separator:** Detect whether the original uses `", "` (comma-space) or `","`
   (comma only) and match it.
3. **Trailing content:** Preserve anything after the closing parenthesis (could be
   a comment, continuation, or nothing).
4. **Variable prefix:** The text before `Array6(` includes the variable assignment
   (e.g., `varRates = `) -- preserve it exactly.

After applying changes, proceed to core.md Step 9 (write-back) and Step 10
(verification).
