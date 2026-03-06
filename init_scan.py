#!/usr/bin/env python3
"""
IQ Plugin Init Scanner — Pattern Library + Codebase Profile generator.

Called by /iq-init to replace 200+ Claude tool calls with a single Python invocation.
Scans all .vb files, extracts functions, counts call sites, parses CalcOption dispatch
tables, extracts vehicle type profiles, and writes both YAML output files.

Usage:
    python init_scan.py --carrier-root PATH --config PATH --output-dir PATH [--skip-profile]
"""

import os
import re
import time
import yaml
import argparse
from datetime import datetime, timezone
from collections import defaultdict


# ── Regex patterns ──────────────────────────────────────────────────────────

FUNC_DECL_RE = re.compile(
    r'^\s*(Public|Private|Friend)?\s*(Shared\s+)?(Function|Sub)\s+(\w+)',
    re.IGNORECASE
)
PARAM_RE = re.compile(
    r'(?:ByVal|ByRef)?\s*(\w+)\s+As\s+(\w+)', re.IGNORECASE
)
RETURN_TYPE_RE = re.compile(r'\)\s*As\s+(\w+)', re.IGNORECASE)
COMMENT_LINE_RE = re.compile(r"^\s*'")
IMPORTS_RE = re.compile(r'^\s*Imports\s', re.IGNORECASE)
CASE_RE = re.compile(r'Case\s+(\d+)\s*[:\s]', re.IGNORECASE)
FUNC_CALL_IN_CASE_RE = re.compile(r'(\w+)\s*\(', re.IGNORECASE)
# VB built-ins that match \w+\( but are NOT business functions
VB_BUILTINS = frozenset({
    'If', 'CInt', 'CStr', 'CDbl', 'CBool', 'CLng', 'CSng', 'CDec', 'CDate',
    'CType', 'DirectCast', 'TryCast', 'CObj', 'CByte', 'CShort', 'CUInt',
    'Val', 'Str', 'Len', 'Mid', 'Left', 'Right', 'Trim', 'UCase', 'LCase',
    'InStr', 'Replace', 'Split', 'Join', 'Format', 'Chr', 'Asc',
    'Math', 'Int', 'Fix', 'Abs', 'Round', 'Not', 'Array',
    'MsgBox', 'InputBox', 'IsNothing', 'IsNumeric', 'IsDate',
    'dblPrem', 'intItemCalcKey',  # common assignment targets, not functions
})
VEHICLE_FUNC_RE = re.compile(
    r'(Public|Private|Friend)?\s*(Shared\s+)?Function\s+GetBasePrem_(\w+)',
    re.IGNORECASE
)


# ── File discovery ──────────────────────────────────────────────────────────

def get_latest_version_folder(lob_path):
    """Find the most recent YYYYMMDD version folder inside a LOB directory."""
    best = None
    best_date = ""
    try:
        for entry in os.scandir(lob_path):
            if entry.is_dir() and re.match(r'^\d{8}$', entry.name):
                if entry.name > best_date:
                    best_date = entry.name
                    best = entry.path
    except OSError:
        pass
    return best


def filter_latest_code_files(code_dir):
    """From a Code/ directory, return only the latest dated version of each file group.

    E.g., given mod_Common_ONHab20210301.vb, mod_Common_ONHab20220516.vb,
    mod_Common_ONHab20230601.vb — returns only the 20230601 version.
    Files without a date suffix are always included.
    """
    groups = defaultdict(list)  # base_name -> [(date_str, full_path)]
    no_date = []

    for f in os.listdir(code_dir):
        if not f.lower().endswith('.vb'):
            continue
        full_path = os.path.join(code_dir, f)
        # Try to extract YYYYMMDD date from filename
        m = re.match(r'^(.+?)(\d{8})\.vb$', f, re.IGNORECASE)
        if m:
            base = m.group(1).lower()
            date_str = m.group(2)
            groups[base].append((date_str, full_path))
        else:
            no_date.append(full_path)

    # Keep only the latest dated file per group
    latest = []
    for base, versions in groups.items():
        versions.sort(key=lambda x: x[0], reverse=True)
        latest.append(versions[0][1])

    return latest + no_date


def find_latest_vb_files(carrier_root, config):
    """Find .vb files from province Code/ dirs (latest only) and latest version folders."""
    vb_files = []
    provinces = config.get('provinces', {})

    for raw_prov_code, prov_data in provinces.items():
        # YAML 1.1 parses ON/OFF/YES/NO as booleans — cast to string
        prov_code = str(raw_prov_code).upper() if not isinstance(raw_prov_code, str) else raw_prov_code
        prov_folder = prov_data.get('folder', '')
        prov_path = os.path.join(carrier_root, prov_folder)

        # Province Code/ directory — LATEST dated version of each file only
        code_dir = os.path.join(prov_path, 'Code')
        if os.path.isdir(code_dir):
            vb_files.extend(filter_latest_code_files(code_dir))

        # SHARDCLASS / SharedClass directory
        shard_folder = prov_data.get('shardclass_folder')
        if shard_folder:
            shard_dir = os.path.join(prov_path, shard_folder)
            if os.path.isdir(shard_dir):
                for f in os.listdir(shard_dir):
                    if f.lower().endswith('.vb'):
                        vb_files.append(os.path.join(shard_dir, f))

        # Latest version folder per LOB
        for lob in prov_data.get('lobs', []):
            lob_folder = lob.get('folder', '')
            lob_path = os.path.join(prov_path, lob_folder)
            latest = get_latest_version_folder(lob_path)
            if latest:
                for f in os.listdir(latest):
                    if f.lower().endswith('.vb'):
                        vb_files.append(os.path.join(latest, f))

    return vb_files


# ── Function extraction ─────────────────────────────────────────────────────

def extract_functions(vb_files, carrier_root):
    """Extract all function/sub declarations from .vb files."""
    functions = {}  # name -> best (most recent) entry
    all_defs = defaultdict(list)  # name -> [all definitions]

    for filepath in vb_files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except OSError:
            continue

        rel_path = os.path.relpath(filepath, carrier_root)
        # Extract date from filename for "most recent" logic
        date_match = re.search(r'(\d{8})\.vb$', os.path.basename(filepath), re.IGNORECASE)
        file_date = date_match.group(1) if date_match else '00000000'

        for i, line in enumerate(lines):
            m = FUNC_DECL_RE.match(line)
            if not m:
                continue

            func_type = m.group(3)  # Function or Sub
            func_name = m.group(4)
            signature = line.strip()
            line_num = i + 1

            # Extract param types
            param_types = []
            for pm in PARAM_RE.finditer(line):
                param_types.append({'name': pm.group(1), 'type': pm.group(2)})

            # Extract return type
            return_type = None
            if func_type.lower() == 'function':
                rt = RETURN_TYPE_RE.search(line)
                return_type = rt.group(1) if rt else 'Variant'

            # Purpose hint from comment above
            purpose_hint = None
            if i > 0:
                prev = lines[i - 1].strip()
                if prev.startswith("'"):
                    purpose_hint = prev.lstrip("' ").strip()[:120]
            if not purpose_hint:
                # Heuristic from name
                if func_name.startswith('Get'):
                    purpose_hint = f"Returns {_split_name(func_name[3:])}"
                elif func_name.startswith('Set'):
                    purpose_hint = f"Sets {_split_name(func_name[3:])}"
                elif func_name.startswith('Calc'):
                    purpose_hint = f"Calculates {_split_name(func_name[4:])}"

            entry = {
                'file': rel_path.replace('\\', '/'),
                'line': line_num,
                'signature': signature,
                'type': func_type,
                'param_types': param_types,
                'return_type': return_type,
                'purpose_hint': purpose_hint,
                'call_sites': 0,
                'status': 'DEAD',
                '_date': file_date,
            }

            all_defs[func_name].append(entry)

            # Keep the most recent definition
            if func_name not in functions or file_date > functions[func_name].get('_date', ''):
                functions[func_name] = entry

    return functions, all_defs


def _split_name(name):
    """Split CamelCase/underscore name into readable string."""
    name = name.replace('_', ' ')
    words = re.sub(r'([a-z])([A-Z])', r'\1 \2', name).split()
    return ' '.join(w.lower() for w in words) if words else name


# ── Call site counting ──────────────────────────────────────────────────────

WORD_SPLIT_RE = re.compile(r'\w+')


def count_call_sites(functions, vb_files):
    """Count non-comment, non-definition references for each function.

    Uses set intersection instead of per-function regex for O(W) per line
    instead of O(M) where M = number of functions.
    """
    name_set = set(functions.keys())

    total_files = len(vb_files)
    for idx, filepath in enumerate(vb_files):
        if (idx + 1) % 100 == 0:
            print(f"  Counting call sites... ({idx + 1}/{total_files} files)",
                  flush=True)

        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except OSError:
            continue

        for line in lines:
            # Skip comments and imports
            if COMMENT_LINE_RE.match(line) or IMPORTS_RE.match(line):
                continue
            # Skip definition lines
            if FUNC_DECL_RE.match(line):
                continue

            # Tokenize line into words, intersect with function name set
            words = set(WORD_SPLIT_RE.findall(line))
            hits = words & name_set
            for name in hits:
                functions[name]['call_sites'] += 1

    # Classify
    for name, entry in functions.items():
        cs = entry['call_sites']
        if cs == 0:
            entry['status'] = 'DEAD'
        elif cs <= 2:
            entry['status'] = 'ACTIVE'
        else:
            entry['status'] = 'HIGH_USE'


# ── CalcOption dispatch table parsing ───────────────────────────────────────

def discover_calcoption_files(code_dir, prov_code):
    """Auto-discover ALL CalcOption files for a province, grouped by LOB suffix.

    Carrier-agnostic: instead of requiring the caller to guess the suffix,
    scans all CalcOption_{PROV}*.vb files, extracts the suffix between the
    province code and the 8-digit date, groups by suffix, and returns the
    latest file per suffix.

    Returns: dict of {suffix: filepath} for the latest file in each group.
    E.g., {"HOME": "/.../CalcOption_ABHOME20251201.vb", "MH": "/.../CalcOption_ABMH20251201.vb"}
    """
    if not os.path.isdir(code_dir):
        return {}

    prefix = f'CalcOption_{prov_code}'.lower()
    prefix_len = len(f'CalcOption_{prov_code}')
    groups = defaultdict(list)  # suffix -> [(date_str, full_path)]

    for f in os.listdir(code_dir):
        lower = f.lower()
        if lower.startswith(prefix) and lower.endswith('.vb'):
            # Extract suffix between province code and date
            rest = f[prefix_len:]  # e.g., "HOME20251201.vb" or "MH20251201.vb"
            date_m = re.search(r'(\d{8})\.vb$', rest, re.IGNORECASE)
            if date_m:
                suffix = rest[:date_m.start()].upper()  # e.g., "HOME", "MH"
                groups[suffix].append((date_m.group(1), os.path.join(code_dir, f)))

    # Keep only the latest file per suffix
    latest = {}
    for suffix, versions in groups.items():
        versions.sort(key=lambda x: x[0], reverse=True)
        latest[suffix] = versions[0][1]

    return latest


def parse_calcoption(filepath, carrier_root):
    """Parse a CalcOption file into a dispatch table."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return None

    rel_path = os.path.relpath(filepath, carrier_root).replace('\\', '/')
    categories = {}
    current_category = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect category Select Case — matches both:
        #   Case "MISCPROPERTY"     (string literal)
        #   Case Cssi.ResourcesConstants.CategoryCodes.CATEGORY_MISCPROPERTY  (qualified const)
        if re.search(r'(?:CATEGORY_|")(MISCPROPERTY|LIABILITY|ENDORSEMENTEXTENSION|VEHICLES|'
                      r'COMMERCIALCOVERAGE|FARMCOVERAGE|TENANTCOVERAGE|CONDOCOVERAGE|'
                      r'GENERALCOVERAGE|HOMECOVERAGE|MOBILEHOMECOVERAGE|WATERCRAFTCOVERAGE|'
                      r'PACKAGEOPTION|PACKAGECOVERAGE)', stripped, re.IGNORECASE):
            cat_match = re.search(r'(?:CATEGORY_|")(\w+)"?', stripped, re.IGNORECASE)
            if cat_match:
                current_category = cat_match.group(1).upper()
                if current_category not in categories:
                    categories[current_category] = []
            continue

        # Inside a category, look for Case <number>
        if current_category:
            case_m = CASE_RE.match(stripped)
            if case_m:
                code = int(case_m.group(1))

                # Extract inline comment from Case line
                comment = None
                comment_idx = stripped.find("'")
                if comment_idx >= 0:
                    comment = stripped[comment_idx + 1:].strip()

                # Find function call — first check after the comment on same line,
                # excluding comment text (look before the comment)
                func_name = None
                before_comment = stripped[:comment_idx] if comment_idx >= 0 else stripped
                after_case = before_comment[case_m.end():]
                # Find all function-call candidates, skip VB built-ins
                for func_m in FUNC_CALL_IN_CASE_RE.finditer(after_case):
                    candidate = func_m.group(1)
                    if candidate not in VB_BUILTINS:
                        func_name = candidate
                        break

                # If no function on same line, check the next non-blank line
                if not func_name:
                    for j in range(i + 1, min(i + 4, len(lines))):
                        next_stripped = lines[j].strip()
                        if not next_stripped or next_stripped.startswith("'"):
                            continue
                        if next_stripped.lower().startswith('case ') or next_stripped.lower().startswith('end select'):
                            break
                        for nf in FUNC_CALL_IN_CASE_RE.finditer(next_stripped):
                            candidate = nf.group(1)
                            if candidate not in VB_BUILTINS:
                                func_name = candidate
                                break
                        break

                categories[current_category].append({
                    'code': code,
                    'function': func_name,
                    'description': comment,
                })

            # End of category
            if stripped.lower().startswith('end select'):
                current_category = None

    if not categories:
        return None

    return {
        'source_file': rel_path,
        'categories': categories,
    }


# ── Vehicle type extraction ─────────────────────────────────────────────────

def find_latest_algorithms(code_dir, prov_code):
    """Find the latest mod_Algorithms file for a province's Auto LOB."""
    pattern = f'mod_Algorithms_{prov_code}Auto'.lower()
    best = None
    best_date = ''
    if not os.path.isdir(code_dir):
        return None
    for f in os.listdir(code_dir):
        if f.lower().startswith(pattern) and f.lower().endswith('.vb'):
            date_m = re.search(r'(\d{8})\.vb$', f, re.IGNORECASE)
            if date_m and date_m.group(1) > best_date:
                best_date = date_m.group(1)
                best = os.path.join(code_dir, f)
    return best


def extract_vehicle_types(filepath, carrier_root):
    """Extract vehicle type sub-functions from mod_Algorithms."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return None

    rel_path = os.path.relpath(filepath, carrier_root).replace('\\', '/')
    types = []

    for i, line in enumerate(lines):
        m = VEHICLE_FUNC_RE.match(line.strip())
        if m:
            vtype = m.group(3)
            types.append({
                'name': vtype,
                'entry_function': f'GetBasePrem_{vtype}',
                'line_start': i + 1,
            })

    if not types:
        return None

    return {
        'source_file': rel_path,
        'types': types,
    }


# ── Glossary generation ─────────────────────────────────────────────────────

SYNONYM_MAP = {
    'deductible': ['ded', 'deductable'],
    'liability': ['liab', 'CGL'],
    'premium': ['rate', 'pricing'],
    'endorsement': ['rider', 'optional coverage'],
    'surcharge': ['loading', 'penalty'],
    'discount': ['credit', 'reduction'],
    'base rate': ['base premium', 'manual rate'],
    'territory': ['terr', 'location factor'],
}


def build_glossary(functions, dispatch_tables):
    """Generate business term glossary from function names."""
    glossary = {}

    for func_name, entry in functions.items():
        if entry['status'] == 'DEAD':
            continue

        # Parse function name into business terms
        readable = _split_name(func_name)
        if len(readable) < 4:
            continue  # Skip very short names

        # Determine file pattern
        file_path = entry.get('file', '')
        if 'mod_Common' in file_path:
            file_pattern = 'mod_Common_{PROV}Hab*.vb'
        elif 'mod_Algorithms' in file_path:
            file_pattern = 'mod_Algorithms_{PROV}Auto*.vb'
        elif 'Option_' in file_path:
            file_pattern = 'Option_*_{PROV}{LOB}*.vb'
        elif 'Liab_' in file_path:
            file_pattern = 'Liab_*_{PROV}{LOB}*.vb'
        else:
            file_pattern = None

        # Build synonyms
        synonyms = []
        for key, syns in SYNONYM_MAP.items():
            if key in readable.lower():
                synonyms.extend(syns)

        glossary[readable] = {
            'canonical_function': func_name,
            'file_pattern': file_pattern,
            'synonyms': synonyms if synonyms else None,
            'provenance': 'init',
        }

    return glossary


# ── YAML writers ────────────────────────────────────────────────────────────

def write_pattern_library(output_dir, functions, all_defs, vb_file_count):
    """Write pattern-library.yaml."""
    active = sum(1 for f in functions.values() if f['call_sites'] >= 1)
    dead = sum(1 for f in functions.values() if f['call_sites'] == 0)
    high_use = sum(1 for f in functions.values() if f['call_sites'] >= 3)

    # Build output dict (remove internal _date field)
    funcs_out = {}
    for name, entry in sorted(functions.items()):
        out = {k: v for k, v in entry.items() if not k.startswith('_')}
        # Add all_definitions if multiple
        if len(all_defs.get(name, [])) > 1:
            out['all_definitions'] = [
                {'file': d['file'], 'line': d['line']}
                for d in all_defs[name]
            ]
        funcs_out[name] = out

    data = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scan_stats': {
            'total_vb_files': vb_file_count,
            'total_functions': len(functions),
            'active_functions': active,
            'dead_functions': dead,
            'high_use_functions': high_use,
        },
        'functions': funcs_out,
    }

    outpath = os.path.join(output_dir, 'pattern-library.yaml')
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write("# IQ Rate Update Plugin -- Pattern Library (Function Registry)\n")
        f.write("# Auto-generated by init_scan.py. To rebuild: /iq-init --refresh\n\n")
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"  Wrote {outpath} ({len(functions)} functions)")
    return data['scan_stats']


def write_codebase_profile(output_dir, dispatch_tables, vehicle_profiles, glossary, carrier_name):
    """Write codebase-profile.yaml."""
    data = {
        '_meta': {
            'version': 1,
            'carrier': carrier_name,
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'built_by': '/iq-init (init_scan.py)',
        },
        'dispatch_tables': dispatch_tables,
        'vehicle_type_profiles': vehicle_profiles,
        'glossary': glossary,
    }

    outpath = os.path.join(output_dir, 'codebase-profile.yaml')
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write("# IQ Rate Update Plugin -- Codebase Knowledge Base\n")
        f.write("# Auto-generated by init_scan.py. To rebuild: /iq-init --refresh\n\n")
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"  Wrote {outpath}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='IQ Plugin Init Scanner')
    parser.add_argument('--carrier-root', required=True, help='Absolute path to carrier folder')
    parser.add_argument('--config', required=True, help='Path to config.yaml')
    parser.add_argument('--output-dir', required=True, help='Path to .iq-workstreams/')
    parser.add_argument('--skip-profile', action='store_true', help='Skip codebase profile (dispatch tables, vehicle types, glossary)')
    args = parser.parse_args()

    t0 = time.time()
    carrier_root = os.path.normpath(args.carrier_root)
    output_dir = os.path.normpath(args.output_dir)

    # Load config
    print(f"Loading config from {args.config}")
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    carrier_name = config.get('carrier_name', 'Unknown')

    # Step 1: Find .vb files
    print("Scanning for .vb files...", flush=True)
    vb_files = find_latest_vb_files(carrier_root, config)
    print(f"  Found {len(vb_files)} .vb files", flush=True)

    # Step 2: Extract function declarations
    print("Extracting function declarations...", flush=True)
    functions, all_defs = extract_functions(vb_files, carrier_root)
    print(f"  Found {len(functions)} unique functions/subs", flush=True)

    # Step 3: Count call sites
    print("Counting call sites...", flush=True)
    count_call_sites(functions, vb_files)
    active = sum(1 for f in functions.values() if f['call_sites'] >= 1)
    print(f"  {active} active, {len(functions) - active} dead code candidates", flush=True)

    # Step 4: Write pattern library
    print("Writing pattern-library.yaml...")
    stats = write_pattern_library(output_dir, functions, all_defs, len(vb_files))

    if not args.skip_profile:
        # Step 5: Parse dispatch tables (carrier-agnostic — auto-discovers LOB suffixes)
        print("Parsing CalcOption dispatch tables...")
        dispatch_tables = {}
        provinces = config.get('provinces', {})
        for raw_pc, prov_data in provinces.items():
            pc = str(raw_pc).upper() if not isinstance(raw_pc, str) else raw_pc
            code_dir = os.path.join(carrier_root, prov_data.get('folder', ''), 'Code')
            # Discover ALL CalcOption files for this province (no suffix guessing)
            co_files = discover_calcoption_files(code_dir, pc)
            for suffix, co_file in sorted(co_files.items()):
                table = parse_calcoption(co_file, carrier_root)
                if table:
                    key = f"{pc}_{suffix}"
                    dispatch_tables[key] = table
                    total_codes = sum(len(v) for v in table['categories'].values())
                    print(f"  {key}: {total_codes} option codes in {len(table['categories'])} categories")

        # Step 6: Extract vehicle types
        print("Extracting vehicle type profiles...")
        vehicle_profiles = {}
        for raw_pc, prov_data in provinces.items():
            pc = str(raw_pc).upper() if not isinstance(raw_pc, str) else raw_pc
            has_auto = any(l.get('folder', '').lower() == 'auto' for l in prov_data.get('lobs', []))
            if not has_auto:
                continue
            code_dir = os.path.join(carrier_root, prov_data.get('folder', ''), 'Code')
            algo_file = find_latest_algorithms(code_dir, pc)
            if algo_file:
                vt = extract_vehicle_types(algo_file, carrier_root)
                if vt:
                    key = f"{pc}_AUTO"
                    vehicle_profiles[key] = vt
                    print(f"  {key}: {len(vt['types'])} vehicle types")

        # Step 7: Build glossary
        print("Building glossary...")
        glossary = build_glossary(functions, dispatch_tables)
        print(f"  {len(glossary)} business terms mapped")

        # Step 8: Write codebase profile
        print("Writing codebase-profile.yaml...")
        write_codebase_profile(output_dir, dispatch_tables, vehicle_profiles, glossary, carrier_name)

    # Final summary
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("  Init scan complete!")
    print(f"  Functions: {stats['total_functions']} total, {stats['active_functions']} active, {stats['dead_functions']} dead")
    if not args.skip_profile:
        print(f"  Dispatch tables: {len(dispatch_tables)} province+LOB combinations")
        print(f"  Vehicle profiles: {len(vehicle_profiles)} provinces")
        print(f"  Glossary terms: {len(glossary)}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print("=" * 60)


if __name__ == '__main__':
    main()
