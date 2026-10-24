#!/usr/bin/env python3
"""Deterministic RTLProbe command-line runner."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

CODE_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--bundle-sha256')
    parser.add_argument('--target-config', type=Path)
    parser.add_argument('action', choices=['paths', 'fetch', 'check', 'qualify', 'run', 'audit', 'audit-data'])
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.data_root.is_absolute():
        parser.error('--data-root must be absolute')
    data_root = args.data_root.resolve()
    if data_root == CODE_ROOT or CODE_ROOT in data_root.parents or data_root in CODE_ROOT.parents:
        parser.error('Data directory must be separate from the RTLProbe code repository')
    os.environ['RTLPROBE_DATA_ROOT'] = str(data_root)
    if args.target_config is not None:
        if not args.target_config.is_absolute():
            parser.error('--target-config must be absolute')
        os.environ['RTLPROBE_TARGET_CONFIG'] = str(args.target_config.resolve())
    else:
        os.environ.pop('RTLPROBE_TARGET_CONFIG', None)
    sys.path.insert(0, str(CODE_ROOT))
    from rtlprobe import pilot, execution
    from rtlprobe.evidence import workspace_lock
    from rtlprobe.lifecycle import existing_cases
    if args.action == 'paths':
        print(json.dumps({'rtlprobe_root': str(CODE_ROOT), 'data_root': str(data_root),
                          'config': str(pilot.CONFIG) if pilot.CONFIG else None}, indent=2))
    elif args.action == 'fetch':
        from rtlprobe.fetch import fetch
        with workspace_lock(data_root):
            fetch(pilot.target.configuration(pilot.CONFIG))
    elif args.action == 'check':
        design, _, _ = pilot.qualified()
        print(json.dumps({'status': 'qualified', 'evidence': design['evidence']}))
    elif args.action == 'qualify':
        with workspace_lock(data_root):
            pilot.qualify()
    elif args.action == 'audit-data':
        with workspace_lock(data_root):
            cases = existing_cases(data_root)
            print(json.dumps({'scope': 'saved_metadata_and_manifests', 'fresh_simulations': 0,
                              'cases': len(cases), 'counts': dict(Counter(s['state'] for s in cases.values()))}, indent=2))
    elif args.action == 'audit':
        if len(args.arguments) != 1:
            parser.error('audit requires a case directory')
        pilot.audit(args.arguments[0])
    else:
        if len(args.arguments) != 1:
            parser.error('run requires a proposal file or sealed bundle directory')
        execution.run(args.arguments[0], args.bundle_sha256)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
