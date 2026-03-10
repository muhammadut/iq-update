"""
Validator: Value Sanity
Severity: WARNING

Purpose:
    Check that rate value changes are within a reasonable range. Flags
    anything that looks like an error (e.g., a 500% increase, negative
    values where positive expected, or zero values).

    This is a WARNING, not a BLOCKER -- large changes might be intentional.
    The developer reviews and decides.

What it checks:
    1. Percentage change for each modified value is within threshold
       (default: flags changes > 50% as suspicious)
    2. No values went from positive to negative (or vice versa) unexpectedly
       (sign_flip)
    3. No sentinel values (-999) were modified
    4. No values went from zero to nonzero (can't compute % change)

What it does NOT check:
    - Whether the syntax is valid (that's validate_array6)
    - Whether all territories are updated (that's validate_completeness)
    - Whether the correct function was modified (that's the developer's
      judgment at Gate 1)

Configuration:
    Threshold is set in config.yaml: validation.value_sanity_threshold_percent
    Default: 50 (flags changes larger than 50%)

Return schema:
    {
        "passed": bool,           # True if no suspicious values found
        "severity": "WARNING",
        "findings": [
            {
                "file": str,      # File with suspicious value
                "line": int,      # Line number
                "operation": str, # Operation ID
                "issue": str,     # "large_change" | "zero_to_nonzero" |
                                  # "sentinel_modified" | "sign_flip"
                "arg_index": int, # optional, for Array6 args
                "before": float,
                "after": float,
                "pct_change": float,  # only for large_change
            }
        ],
        "message": str
    }
"""

from _helpers import (
    load_context,
    make_result,
    parse_array6_values,
    compute_pct_change,
    extract_numeric_value,
)


def validate(manifest_path: str) -> dict:
    """Validate that rate value changes are within reasonable bounds.

    Args:
        manifest_path: Absolute path to the workflow manifest.yaml file.
                       Used to locate operations_log with before/after
                       values and config.yaml for threshold settings.

    Returns:
        dict with keys: passed (bool), severity (str), findings (list),
        message (str). See module docstring for full return schema.
    """
    try:
        ctx = load_context(manifest_path)
    except Exception as e:
        return make_result(
            severity="WARNING",
            passed=False,
            findings=[{
                "file": "",
                "line": 0,
                "operation": "",
                "issue": "context_load_error",
                "message": f"Validator crashed during context loading: {e}",
            }],
            message=f"Validator crashed during context loading: {e}",
        )

    ops_log = ctx["ops_log"]
    config = ctx["config"]

    # Get threshold from config (default 50%)
    # Supports config.yaml: validation.value_sanity_threshold_percent
    # Also accepts string values (e.g., "50") via float() coercion.
    raw_threshold = 50.0
    if config:
        raw_threshold = config.get("validation", {}).get(
            "value_sanity_threshold_percent", 50.0
        )
    try:
        threshold = float(raw_threshold)
    except (ValueError, TypeError):
        threshold = 50.0

    findings = []
    all_pct_changes = []
    values_checked = 0

    for entry in ops_log.get("operations", []):
        change_type = entry.get("change_type", "")
        if change_type not in ("value_editing", "structure_insertion", "flow_modification"):
            continue
        if entry.get("status") != "COMPLETED":
            continue

        filepath = entry.get("file", "")
        op_id = entry.get("intent_id", entry.get("operation", ""))

        for change in entry.get("changes", []):
            before_line = change.get("before")
            after_line = change.get("after", "")
            line_num = change.get("line", 0)

            if not before_line or not after_line:
                continue

            # ---- Try Array6 value extraction first ----
            before_args = parse_array6_values(before_line)
            after_args = parse_array6_values(after_line)

            if before_args is not None and after_args is not None:
                # Compare each arg pair
                for i, (bv, av) in enumerate(zip(before_args, after_args)):
                    if bv is None or av is None:
                        continue  # unparseable arg

                    values_checked += 1

                    # Sentinel check: -999 must never change
                    if bv == -999 and av != -999:
                        findings.append({
                            "file": filepath,
                            "line": line_num,
                            "operation": op_id,
                            "issue": "sentinel_modified",
                            "arg_index": i,
                            "before": bv,
                            "after": av,
                        })
                        continue

                    # Sign flip check (skip sentinels)
                    if (bv > 0 and av < 0) or (bv < 0 and av > 0 and bv != -999):
                        findings.append({
                            "file": filepath,
                            "line": line_num,
                            "operation": op_id,
                            "issue": "sign_flip",
                            "arg_index": i,
                            "before": bv,
                            "after": av,
                        })

                    pct = compute_pct_change(bv, av)
                    if pct is None:
                        # Zero-to-nonzero
                        if bv == 0 and av != 0:
                            findings.append({
                                "file": filepath,
                                "line": line_num,
                                "operation": op_id,
                                "issue": "zero_to_nonzero",
                                "arg_index": i,
                                "before": bv,
                                "after": av,
                            })
                        continue

                    all_pct_changes.append(pct)
                    if pct > threshold:
                        findings.append({
                            "file": filepath,
                            "line": line_num,
                            "operation": op_id,
                            "issue": "large_change",
                            "arg_index": i,
                            "before": bv,
                            "after": av,
                            "pct_change": pct,
                        })
                continue  # Done with this change (Array6 path)

            # ---- Not Array6 -- try single numeric value (factor table) ----
            before_val = extract_numeric_value(before_line)
            after_val = extract_numeric_value(after_line)

            if before_val is not None and after_val is not None:
                values_checked += 1

                # Sentinel check
                if before_val == -999 and after_val != -999:
                    findings.append({
                        "file": filepath,
                        "line": line_num,
                        "operation": op_id,
                        "issue": "sentinel_modified",
                        "before": before_val,
                        "after": after_val,
                    })
                    continue

                # Sign flip check (skip sentinels)
                if ((before_val > 0 and after_val < 0) or
                        (before_val < 0 and after_val > 0 and before_val != -999)):
                    findings.append({
                        "file": filepath,
                        "line": line_num,
                        "operation": op_id,
                        "issue": "sign_flip",
                        "before": before_val,
                        "after": after_val,
                    })

                pct = compute_pct_change(before_val, after_val)
                if pct is None:
                    # Zero-to-nonzero
                    if before_val == 0 and after_val != 0:
                        findings.append({
                            "file": filepath,
                            "line": line_num,
                            "operation": op_id,
                            "issue": "zero_to_nonzero",
                            "before": before_val,
                            "after": after_val,
                        })
                    continue

                all_pct_changes.append(pct)
                if pct > threshold:
                    findings.append({
                        "file": filepath,
                        "line": line_num,
                        "operation": op_id,
                        "issue": "large_change",
                        "before": before_val,
                        "after": after_val,
                        "pct_change": pct,
                    })

    # ---- Build summary message ----
    if all_pct_changes:
        min_pct = round(min(all_pct_changes), 1)
        max_pct = round(max(all_pct_changes), 1)
        mean_pct = round(sum(all_pct_changes) / len(all_pct_changes), 1)
        summary = (
            f"{values_checked} values checked. "
            f"Range: {min_pct}% to {max_pct}%, mean {mean_pct}%."
        )
    else:
        summary = f"{values_checked} values checked. No percentage changes computed."

    if findings:
        issue_counts = {}
        for f in findings:
            issue_counts[f["issue"]] = issue_counts.get(f["issue"], 0) + 1
        summary += " Flagged: " + ", ".join(
            f"{v} {k}" for k, v in issue_counts.items()
        )

    return make_result("WARNING", len(findings) == 0, findings, summary)
