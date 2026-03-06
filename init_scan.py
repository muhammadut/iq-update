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
import sys
import yaml
import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
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
SELECT_CASE_CATEGORY_RE = re.compile(
    r'Select\s+Case\s+\w*(Category|TheCategory)\w*', re.IGNORECASE
)
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


def find_latest_vb_files(carrier_root, config):
    """Find .vb files from province Code/ dirs and latest version folders only."""
    vb_files = []
    provinces = config.get('provinces', {})

    for prov_code, prov_data in provinces.items():
        prov_folder = prov_data.get('folder', '')
        prov_path = os.path.join(carrier_root, prov_folder)

        # Province Code/ directory — all .vb files
        code_dir = os.path.join(prov_path, 'Code')
        if os.path.isdir(code_dir):
            for f in os.listdir(code_dir):
                if f.lower().endswith('.vb'):
                    vb_files.append(os.path.join(code_dir, f))

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

def count_call_sites(functions, vb_files):
    """Count non-comment, non-definition references for each function."""
    # Build a set of names to search for
    names = set(functions.keys())
    # Build word boundary patterns (compiled once)
    patterns = {}
    for name in names:
        try:
            patterns[name] = re.compile(r'\b' + re.escape(name) + r'\b')
        except re.error:
            continue

    total_files = len(vb_files)
    for idx, filepath in enumerate(vb_files):
        if (idx + 1) % 100 == 0:
            print(f"  Counting call sites... ({idx + 1}/{total_files} files)")

        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except OSError:
            continue

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip comments and imports
            if COMMENT_LINE_RE.match(line) or IMPORTS_RE.match(line):
                continue
            # Skip definition lines
            if FUNC_DECL_RE.match(line):
                continue

            for name, pat in patterns.items():
                if pat.search(line):
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

def find_latest_calcoption(code_dir, prov_code, lob_suffix):
    """Find the latest CalcOption file for a province+LOB."""
    pattern = f'CalcOption_{prov_code}{lob_suffix}'.lower()
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

    for line in lines:
        stripped = line.strip()

        # Detect category Select Case
        if re.search(r'Case\s+"?(MISCPROPERTY|LIABILITY|ENDORSEMENTEXTENSION|VEHICLES|'
                      r'COMMERCIALCOVERAGE|FARMCOVERAGE|TENANTCOVERAGE|CONDOCOVERAGE|'
                      r'GENERALCOVERAGE|HOMECOVERAGE|MOBILEHOMECOVERAGE|WATERCRAFTCOVERAGE|'
                      r'PACKAGEOPTION|PACKAGECOVERAGE)"?', stripped, re.IGNORECASE):
            cat_match = re.search(r'Case\s+"?(\w+)"?', stripped, re.IGNORECASE)
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
                # Find function call on same or next significant token
                func_m = FUNC_CALL_IN_CASE_RE.search(stripped[case_m.end():])
                func_name = func_m.group(1) if func_m else None
                # Extract inline comment
                comment = None
                comment_idx = stripped.find("'")
                if comment_idx >= 0:
                    comment = stripped[comment_idx + 1:].strip()

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

    carrier_root = os.path.normpath(args.carrier_root)
    output_dir = os.path.normpath(args.output_dir)

    # Load config
    print(f"Loading config from {args.config}")
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    carrier_name = config.get('carrier_name', 'Unknown')

    # Step 1: Find .vb files
    print("Scanning for .vb files...")
    vb_files = find_latest_vb_files(carrier_root, config)
    print(f"  Found {len(vb_files)} .vb files")

    # Step 2: Extract function declarations
    print("Extracting function declarations...")
    functions, all_defs = extract_functions(vb_files, carrier_root)
    print(f"  Found {len(functions)} unique functions/subs")

    # Step 3: Count call sites
    print("Counting call sites...")
    count_call_sites(functions, vb_files)
    active = sum(1 for f in functions.values() if f['call_sites'] >= 1)
    print(f"  {active} active, {len(functions) - active} dead code candidates")

    # Step 4: Write pattern library
    print("Writing pattern-library.yaml...")
    stats = write_pattern_library(output_dir, functions, all_defs, len(vb_files))

    if not args.skip_profile:
        # Step 5: Parse dispatch tables
        print("Parsing CalcOption dispatch tables...")
        dispatch_tables = {}
        provinces = config.get('provinces', {})
        for prov_code, prov_data in provinces.items():
            code_dir = os.path.join(carrier_root, prov_data.get('folder', ''), 'Code')
            for lob in prov_data.get('lobs', []):
                lob_suffix = lob.get('lob_code', '').replace(prov_code, '')
                co_file = find_latest_calcoption(code_dir, prov_code, lob_suffix)
                if co_file:
                    table = parse_calcoption(co_file, carrier_root)
                    if table:
                        key = f"{prov_code}_{lob_suffix}"
                        dispatch_tables[key] = table
                        total_codes = sum(len(v) for v in table['categories'].values())
                        print(f"  {key}: {total_codes} option codes in {len(table['categories'])} categories")

        # Step 6: Extract vehicle types
        print("Extracting vehicle type profiles...")
        vehicle_profiles = {}
        for prov_code, prov_data in provinces.items():
            has_auto = any(l.get('folder', '').lower() == 'auto' for l in prov_data.get('lobs', []))
            if not has_auto:
                continue
            code_dir = os.path.join(carrier_root, prov_data.get('folder', ''), 'Code')
            algo_file = find_latest_algorithms(code_dir, prov_code)
            if algo_file:
                vt = extract_vehicle_types(algo_file, carrier_root)
                if vt:
                    key = f"{prov_code}_AUTO"
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
    print("\n" + "=" * 60)
    print("  Init scan complete!")
    print(f"  Functions: {stats['total_functions']} total, {stats['active_functions']} active, {stats['dead_functions']} dead")
    if not args.skip_profile:
        print(f"  Dispatch tables: {len(dispatch_tables)} province+LOB combinations")
        print(f"  Vehicle profiles: {len(vehicle_profiles)} provinces")
        print(f"  Glossary terms: {len(glossary)}")
    print("=" * 60)


if __name__ == '__main__':
    main()
