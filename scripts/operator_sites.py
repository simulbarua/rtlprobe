#!/usr/bin/env python3
"""Read-only source-site inventory; JSON on stdout, no simulations or case writes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtlprobe.candidates import extract_candidates, mapping_coverage
from rtlprobe.mutation import LEGACY_MAPPERS, NEW_OPERATORS, reachable_sites, safe_path, sha


def inventory(config, source_root):
    root = Path(source_root)
    sources, errors, files = {}, [], []
    all_sites = {op: [] for op in [*LEGACY_MAPPERS, *sorted(NEW_OPERATORS)]}
    for path in config['rtl']:
        relative = str(safe_path(path))
        try:
            data = (root / relative).read_bytes()
            sources[relative] = data
            found = reachable_sites(data, path=relative, reset_identifiers=config.get('reset_identifiers', []))
            files.append({'path': relative, 'sha256': sha(data),
                          'counts': {op: len(sites) for op, sites in found['sites'].items()},
                          'rejected_sites': found['rejected']})
            for op, sites in found['sites'].items():
                all_sites[op].extend(dict(t, path=relative) for t in sites)
        except (ValueError, OSError) as exc:
            errors.append({'path': relative, 'reason': str(exc)})
    candidates = extract_candidates(sources)
    return {'target': config.get('target_id', config.get('design_id')),
            'revision': config['revision'], 'source_root': str(root.resolve()),
            'status': 'partial' if errors or candidates['rejected'] else 'complete',
            'counts': {op: len(sites) for op, sites in all_sites.items()},
            'coverage': mapping_coverage(all_sites, candidates), 'files': files,
            'unavailable_files': errors, 'extractor_rejections': candidates['rejected'],
            'constructs': candidates['constructs'], 'sites': all_sites,
            'limitations': candidates['limitations'] + ['Widths resolved in standalone source with default parameter values.'],
            'fresh_simulations': 0, 'data_root_writes': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    result = inventory(json.loads(args.manifest.read_text()), args.source_root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['status'] == 'complete' else 1)
