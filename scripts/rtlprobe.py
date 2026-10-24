#!/usr/bin/env python3
"""Deterministic RTLProbe command-line runner."""
import argparse
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
    parser.add_argument('action', choices=['paths', 'fetch', 'check', 'qualify', 'run', 'audit', 'audit-data',
                                         'accept', 'promote-auto', 'sample-auto'])
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
        from rtlprobe.curation import audit_data
        if args.arguments:
            parser.error('audit-data takes no arguments')
        print(json.dumps(audit_data(data_root), indent=2))
    elif args.action in {'accept', 'promote-auto', 'sample-auto'}:
        from rtlprobe import curation
        action = argparse.ArgumentParser(prog=f'{parser.prog} {args.action}')
        if args.action == 'accept':
            action.add_argument('case_id')
            action.add_argument('--reviewer', required=True)
            action.add_argument('--decision', required=True, choices=['approve', 'reject'])
            action.add_argument('--evidence', required=True)
            action.add_argument('--document', type=Path)
            options = action.parse_args(args.arguments)
            print(json.dumps(curation.accept(data_root, **vars(options)), indent=2))
        elif args.action == 'promote-auto':
            action.add_argument('--first-n', type=int, default=curation.DEFAULT_FIRST_N)
            action.add_argument('--dry-run', action='store_true')
            options = action.parse_args(args.arguments)
            for result in curation.promote_auto(data_root, **vars(options)):
                print(f"{result['action']} {result['case_id']} "
                      f"pair=({result['pair']['design_id']}, {result['pair']['operator_id']}) "
                      f"rank={result['rank']} reasons={json.dumps(result['reasons'])}")
        else:
            action.add_argument('--fraction', type=float, default=curation.DEFAULT_FRACTION)
            options = action.parse_args(args.arguments)
            path, sample = curation.sample_auto(data_root, **vars(options))
            print(json.dumps({'record': str(path.relative_to(data_root)), **sample}, indent=2))
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
