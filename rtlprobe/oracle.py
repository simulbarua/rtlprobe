"""Dispatch to an explicitly selected, fingerprinted checker adapter."""
import importlib.util
from pathlib import Path

from .evidence import CODE_ROOT, filehash
from .target import checker_path


def historical_checker(config, controller_root, explicit_config=None):
    root = Path(controller_root)
    if 'checker' in config or (root/'rtlprobe/oracle.py').is_file():
        return config, root, 'frozen_checker'
    if explicit_config is None:
        raise ValueError('Historical evidence predates frozen checkers; supply --target-config for an explicit compatibility reparse')
    keys = ('repository_url', 'revision', 'top', 'test_top', 'test_id', 'rtl',
            'testbench', 'collateral', 'compile_flags', 'defines', 'parameters', 'seed')
    if any(config[k] != explicit_config[k] for k in keys):
        raise ValueError('Explicit audit target does not match the historical repository/test configuration')
    # This is an explicitly labeled reparse, not reconstruction of unavailable
    # historical code. Original sealed records and approvals remain untouched.
    selected = {**config, 'checker': explicit_config['checker'], 'test_metadata': explicit_config['test_metadata']}
    return selected, CODE_ROOT, 'explicit_compatibility_reparse'


def classify(stdout, stderr='', returncode=0, timed_out=False, *, config, controller_root=None):
    root = CODE_ROOT if controller_root is None else Path(controller_root)
    if 'checker' in config:
        path = checker_path(config, root)
    elif controller_root is not None:
        # Historical bundles predate target manifests. Their sealed controller
        # contains the actual checker used then; never guess a current target.
        path = root/'rtlprobe/oracle.py'
        if not path.is_file():
            raise ValueError('Historical evidence lacks its frozen checker')
    else:
        raise ValueError('Target manifest must declare a checker adapter')
    spec = importlib.util.spec_from_file_location('_rtlprobe_checker_'+filehash(path), path)
    module = importlib.util.module_from_spec(spec)
    # Do not create bytecode inside immutable qualification evidence.
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    if config.get('backend') == 'verilator_uvm':
        test = next(t for t in config['admitted_tests'] if t['id'] == config['test_id'])
        result = module.classify(stdout, stderr, returncode, timed_out, test=test, design=config['design'])
    else:
        result = module.classify(stdout, stderr, returncode, timed_out)
    if not isinstance(result, dict) or result.get('outcome') not in {'pass', 'functional_fail', 'infrastructure_error', 'timeout_unclassified'}:
        raise ValueError('Checker returned an invalid outcome')
    if result['outcome'] == 'functional_fail' and not result.get('signature'):
        raise ValueError('Functional failure requires a checker signature')
    if result['outcome'] in {'pass', 'functional_fail'}:
        if timed_out or returncode != 0 or stderr.strip():
            raise ValueError('Functional verdict contradicts simulator status')
        if 'test_metadata' in config:
            checks = result.get('checkpoints', [])
            if [c.get('id') for c in checks] != config['test_metadata']['checkpoints']:
                raise ValueError('Checker verdict omits or reorders declared checkpoints')
            failed = [c for c in checks if c.get('outcome') == 'functional_fail']
            if (any(c.get('outcome') not in {'pass', 'functional_fail'} for c in checks)
                    or (result['outcome'] == 'pass') != (not failed)
                    or result.get('signature') != (failed or None)):
                raise ValueError('Checker verdict and checkpoint signatures disagree')
            if config.get('backend') != 'verilator_uvm' and any(not isinstance(c.get(k), str) or not c[k] for c in failed for k in ('expected', 'actual')):
                raise ValueError('Failed checkpoints require expected and actual observations')
    return result
