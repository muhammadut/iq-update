"""
test_contract_consistency.py
Verify that contract_registry.yaml stays in sync with the actual agent/skill files.

Tests:
  1. Every review-stage artifact in the registry is referenced in SKILL.md or reviewer.md
  2. File extensions in the registry match the references
  3. Every artifact path on an "Output:" line in SKILL.md exists in the registry
  4. Gate numbering is consistent (no stale "Gate 2" without a/b suffix in review files)
  5. Resume artifact list in SKILL.md matches the registry's review-stage artifacts
     (minus corrections and changes_diff, which are optional/produced by diff agent)
"""

import os
import re

import yaml
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

REGISTRY_PATH = os.path.join(_ROOT, "contracts", "contract_registry.yaml")
SKILL_PATH = os.path.join(_ROOT, "skills", "iq-review", "SKILL.md")
REVIEWER_PATH = os.path.join(_ROOT, "agents", "reviewer.md")


def _load_registry():
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _review_stage_artifacts(registry):
    """Return {name: path} for artifacts whose path starts with verification/ or summary/."""
    return {
        name: info["path"]
        for name, info in registry["artifacts"].items()
        if info["path"].startswith("verification/") or info["path"].startswith("summary/")
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry():
    return _load_registry()


@pytest.fixture(scope="module")
def skill_text():
    return _read_text(SKILL_PATH)


@pytest.fixture(scope="module")
def reviewer_text():
    return _read_text(REVIEWER_PATH)


@pytest.fixture(scope="module")
def review_artifacts(registry):
    return _review_stage_artifacts(registry)


# ---------------------------------------------------------------------------
# Test 1: Every review-stage registry artifact is referenced somewhere
# ---------------------------------------------------------------------------

def test_review_artifacts_referenced_in_skill_or_reviewer(
    review_artifacts, skill_text, reviewer_text
):
    """Each review-stage artifact path from the registry must appear in at least
    one of iq-review/SKILL.md or agents/reviewer.md."""
    combined = skill_text + reviewer_text
    missing = []
    for name, path in review_artifacts.items():
        if path not in combined:
            missing.append(f"{name}: {path}")
    assert not missing, (
        f"Review-stage artifact(s) not referenced in SKILL.md or reviewer.md:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )


# ---------------------------------------------------------------------------
# Test 2: File extensions in registry match the actual references
# ---------------------------------------------------------------------------

def test_artifact_extensions_match(review_artifacts, skill_text, reviewer_text):
    """The file extension of each review-stage artifact must match the extension
    found in the references (no .yaml in registry but .yml in code, etc.)."""
    combined = skill_text + reviewer_text
    mismatched = []
    for name, path in review_artifacts.items():
        _, ext = os.path.splitext(path)
        # Find all references to the basename (without extension) in the combined text
        basename_no_ext = os.path.splitext(os.path.basename(path))[0]
        # Search for the directory prefix + basename with any extension
        dir_prefix = os.path.dirname(path) + "/"
        pattern = re.escape(dir_prefix) + re.escape(basename_no_ext) + r"\.\w+"
        matches = re.findall(pattern, combined)
        for match in matches:
            match_ext = os.path.splitext(match)[1]
            if match_ext != ext:
                mismatched.append(
                    f"{name}: registry has '{ext}', reference has '{match_ext}' in '{match}'"
                )
    assert not mismatched, (
        f"Extension mismatch(es):\n"
        + "\n".join(f"  - {m}" for m in mismatched)
    )


# ---------------------------------------------------------------------------
# Test 3: Every "Output:" artifact in SKILL.md exists in the registry
# ---------------------------------------------------------------------------

def test_skill_output_artifacts_in_registry(registry, skill_text):
    """Every artifact path on an 'Output:' line in iq-review/SKILL.md must
    exist as a path in the contract registry."""
    registry_paths = {
        info["path"] for info in registry["artifacts"].values()
    }

    # Match lines like: **Output:** verification/foo.yaml, verification/bar.md
    output_lines = re.findall(
        r"\*\*Output:\*\*\s*(.+)", skill_text
    )

    # Extract individual paths (comma-separated on the same line)
    missing = []
    for line in output_lines:
        # Split on comma, strip whitespace
        paths = [p.strip() for p in line.split(",")]
        for p in paths:
            # Clean trailing punctuation
            p = p.rstrip(".")
            if p and "/" in p:
                if p not in registry_paths:
                    missing.append(p)

    assert not missing, (
        f"Artifact path(s) in SKILL.md Output: lines but missing from registry:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )


# ---------------------------------------------------------------------------
# Test 4: Gate numbering consistency — no stale bare "Gate 2" in review files
# ---------------------------------------------------------------------------

def test_no_stale_gate2_references(skill_text, reviewer_text):
    """In iq-review context, 'Gate 2' should always be 'Gate 2a' or 'Gate 2b'.
    A bare 'Gate 2' (not followed by a or b) would be a stale reference.
    We also check there are no references to Gate 0 or Gate 6+ (nonexistent gates).
    'gate_2' in YAML field names (manifest keys) is allowed — only display-style
    'Gate 2' references are checked."""
    for label, text in [("SKILL.md", skill_text), ("reviewer.md", reviewer_text)]:
        # Find all "Gate N" references (case-sensitive, display format)
        gate_refs = re.findall(r"Gate (\d+[a-z]?)", text)
        valid_gates = {"1", "2a", "2b", "3", "4", "5"}
        invalid = [
            f"Gate {g}" for g in gate_refs if g not in valid_gates
        ]
        assert not invalid, (
            f"Invalid gate reference(s) in {label}: {invalid}\n"
            f"Valid gates: {sorted(valid_gates)}"
        )


# ---------------------------------------------------------------------------
# Test 5: Resume artifact list matches registry (minus exclusions)
# ---------------------------------------------------------------------------

def test_resume_artifacts_match_registry(review_artifacts, skill_text):
    """The resume detection section of SKILL.md lists 6 artifacts. These should
    be exactly the review-stage artifacts from the registry, minus:
      - corrections (optional, only created on self-correction)
      - changes_diff / changes.diff (produced by diff agent, not a resume gate)
    """
    # Extract the resume artifact list from SKILL.md
    # Look for the block between "ALL 6 are required" and the blank line after the list
    resume_match = re.search(
        r"ALL \d+ are required for a valid resume:\s*\n```\n(.*?)```",
        skill_text,
        re.DOTALL,
    )
    assert resume_match, "Could not find resume artifact list in SKILL.md"

    resume_block = resume_match.group(1)
    resume_paths = set()
    for line in resume_block.strip().splitlines():
        line = line.strip()
        if line and "/" in line:
            resume_paths.add(line)

    # Expected: all review-stage artifacts except corrections and changes.diff
    excluded_names = {"corrections", "changes_diff"}
    expected_paths = {
        path
        for name, path in review_artifacts.items()
        if name not in excluded_names
    }

    assert resume_paths == expected_paths, (
        f"Resume artifact list mismatch.\n"
        f"  In SKILL.md but not in registry: {resume_paths - expected_paths}\n"
        f"  In registry but not in SKILL.md: {expected_paths - resume_paths}"
    )


# ---------------------------------------------------------------------------
# Test 6: Registry has exactly the expected review-stage artifacts
# ---------------------------------------------------------------------------

def test_registry_review_artifact_count(review_artifacts):
    """Sanity check: the registry should have exactly 8 review-stage artifacts."""
    expected_names = {
        "validator_results",
        "diff_report",
        "changes_diff",
        "corrections",
        "semantic_verification",
        "semantic_report",
        "traceability_matrix",
        "change_summary",
    }
    assert set(review_artifacts.keys()) == expected_names, (
        f"Review-stage artifact name mismatch.\n"
        f"  Extra in registry: {set(review_artifacts.keys()) - expected_names}\n"
        f"  Missing from registry: {expected_names - set(review_artifacts.keys())}"
    )


# ---------------------------------------------------------------------------
# Test 7: Registry artifact paths match expected values
# ---------------------------------------------------------------------------

def test_registry_review_artifact_paths(review_artifacts):
    """Verify the exact paths for all review-stage artifacts."""
    expected = {
        "validator_results": "verification/validator_results.yaml",
        "diff_report": "verification/diff_report.md",
        "changes_diff": "verification/changes.diff",
        "corrections": "verification/corrections.yaml",
        "semantic_verification": "verification/semantic_verification.yaml",
        "semantic_report": "verification/semantic_report.md",
        "traceability_matrix": "verification/traceability_matrix.md",
        "change_summary": "summary/change_summary.md",
    }
    assert review_artifacts == expected, (
        f"Review-stage artifact path mismatch.\n"
        f"  Expected: {expected}\n"
        f"  Got: {review_artifacts}"
    )
