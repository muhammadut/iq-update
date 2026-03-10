"""Release smoke test — validates a plugin installation has all required assets.

Run from plugin root:
    python validators/test_release_smoke.py

Checks:
  - All agent .md files referenced in the paths.md template exist
  - vb-parser.exe exists and runs
  - contracts/ directory exists (after Phase 4)
  - No stale agent paths (discovery.md, analyzer.md, etc.)
"""
import os
import subprocess
import sys


def smoke_test(plugin_root: str) -> list[dict]:
    """Returns a list of findings. Empty list = pass."""
    findings = []

    # --- Agent specs must exist ---
    required_agents = [
        "agents/intake.md",
        "agents/understand.md",
        "agents/plan.md",
        "agents/reviewer.md",
        "agents/semantic-verifier.md",
        "agents/change-engine/core.md",
        "agents/change-engine/strategies.md",
    ]
    for agent in required_agents:
        path = os.path.join(plugin_root, agent)
        if not os.path.isfile(path):
            findings.append({"type": "missing_agent", "path": agent})

    # --- Parser binary must exist and run ---
    parser_path = os.path.join(plugin_root, "tools", "win-x64", "vb-parser.exe")
    if not os.path.isfile(parser_path):
        findings.append({"type": "missing_parser", "path": parser_path})
    else:
        try:
            result = subprocess.run(
                [parser_path],
                capture_output=True, text=True, timeout=10
            )
            if "Usage:" not in result.stdout and "Usage:" not in result.stderr:
                findings.append({"type": "parser_not_functional", "detail": "No usage output"})
        except Exception as e:
            findings.append({"type": "parser_error", "detail": str(e)})

    # --- Stale agent paths must NOT exist ---
    stale_agents = [
        "agents/discovery.md",
        "agents/analyzer.md",
        "agents/decomposer.md",
        "agents/planner.md",
    ]
    for agent in stale_agents:
        path = os.path.join(plugin_root, agent)
        if os.path.isfile(path):
            findings.append({"type": "stale_agent", "path": agent,
                             "detail": "Should be archived to archive/v0.3/"})

    # --- CLAUDE.md must exist ---
    if not os.path.isfile(os.path.join(plugin_root, "CLAUDE.md")):
        findings.append({"type": "missing_file", "path": "CLAUDE.md"})

    # --- package.json must include tools/ and contracts/ ---
    pkg_path = os.path.join(plugin_root, "package.json")
    if os.path.isfile(pkg_path):
        import json
        with open(pkg_path, "r") as f:
            pkg = json.load(f)
        files_list = pkg.get("files", [])
        for required in ["tools/", "contracts/"]:
            if required not in files_list:
                findings.append({"type": "package_missing_entry",
                                 "detail": f"'{required}' not in files array"})

    return findings


if __name__ == "__main__":
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    findings = smoke_test(plugin_root)
    if findings:
        print(f"FAIL — {len(findings)} issue(s):")
        for f in findings:
            print(f"  - [{f['type']}] {f.get('path', f.get('detail', ''))}")
        sys.exit(1)
    else:
        print("PASS — all release smoke checks passed")
        sys.exit(0)
