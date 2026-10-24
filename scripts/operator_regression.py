#!/usr/bin/env python3
"""Read-only accepted-case patch gate. Prints JSON; never writes into data root."""
import argparse
import difflib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rtlprobe.evidence import load
from rtlprobe.lifecycle import verify_index
from rtlprobe.mutation import apply, safe_path


def gate(root):
    root = Path(root)
    results = []
    for path in sorted((root / 'data/manifests').glob('*.json')):
        summary = load(path)
        if summary.get('state') not in {'accepted_core', 'accepted_auto'}:
            continue
        row = {'case_id': summary['case_id'], 'state': summary['state']}
        try:
            record = verify_index(root, summary)
            out = root / safe_path(summary['case_path'])
            proposal = record['proposal']
            relative = str(safe_path(proposal['path']))
            before = (out / 'rtl/original' / relative).read_bytes()
            changed = apply(before, proposal['target'], dict(proposal['operator'], status='approved'))
            derived = b''.join(difflib.diff_bytes(difflib.unified_diff,
                before.splitlines(True), changed.splitlines(True),
                fromfile=('a/' + relative).encode(), tofile=('b/' + relative).encode()))
            sealed = (out / 'mutation.patch').read_bytes()
            row['match'] = derived == sealed
            if not row['match']:
                row['diff'] = ''.join(difflib.unified_diff(sealed.decode().splitlines(True),
                    derived.decode().splitlines(True), fromfile='sealed.patch', tofile='derived.patch'))
        except (ValueError, KeyError, OSError) as exc:
            row.update(match=False, error=str(exc))
        results.append(row)
    return {'accepted_cases': len(results), 'matches': sum(r['match'] for r in results),
            'mismatches': sum(not r['match'] for r in results), 'cases': results,
            'fresh_simulations': 0, 'data_root_writes': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    result = gate(parser.parse_args().data_root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['accepted_cases'] and not result['mismatches'] else 1)
