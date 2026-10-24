"""Explicit target manifests; no built-in repository selection."""
import os
from pathlib import Path
import re

from .evidence import CODE_ROOT, ROOT, load
from .mutation import safe_path


def selected():
    value = os.environ.get('RTLPROBE_TARGET_CONFIG')
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('RTLPROBE_TARGET_CONFIG must be absolute')
    return path.resolve()


def validate(config):
    from .backends import IDS
    backend = config.get('backend', 'icarus')
    if backend not in IDS:
        raise ValueError('Unknown backend')
    for key in ('target_id', 'case_prefix', 'split_group'):
        if not isinstance(config.get(key), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', config[key]):
            raise ValueError(f'Target manifest requires a safe {key}')
    for key in ('design_id', 'repository_url', 'top', 'test_top', 'test_id', 'scope'):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f'Target manifest requires {key}')
    for key in ('top', 'test_top'):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]*', config[key]):
            raise ValueError('This backend requires simple Verilog module identifiers')
    if not re.fullmatch(r'[0-9a-f]{40}', config.get('revision', '')):
        raise ValueError('Target revision must be a full pinned Git commit')
    vendor = safe_path(config['vendor'])
    if not (ROOT/vendor).resolve().is_relative_to(ROOT):
        raise ValueError('Vendor path escapes data directory')
    paths = config['rtl'] + [config['testbench']] + config['collateral']
    if not config['rtl'] or len(paths) != len(set(paths)):
        raise ValueError('Declare distinct RTL, existing testbench, and collateral paths')
    for path in paths:
        safe_path(path)
    if backend == 'icarus' and (config.get('defines') or config.get('parameters') or config.get('seed') is not None):
        raise ValueError('This backend supports empty defines/parameters and a deterministic unseeded TB')
    if not isinstance(config.get('compile_flags'), list) or not all(isinstance(s, str) for s in config['compile_flags']):
        raise ValueError('compile_flags must be an argument list')
    checker_path(config)
    tests = config.get('test_metadata', {})
    points = tests.get('checkpoints')
    if not isinstance(points, list) or not points or any(not isinstance(p, str) or not p for p in points) or len(set(points)) != len(points):
        raise ValueError('Target must declare its checker checkpoints')
    if not isinstance(tests.get('checker'), str) or not tests['checker']:
        raise ValueError('Target must describe its existing checker')
    control = config['control']
    if backend != 'icarus':
        validate_verilator(config)
    elif control['path'] not in config['rtl'] or not isinstance(control.get('operator'), dict):
        raise ValueError('Checker control requires declared RTL and an explicit operator')
    return config


def checker_path(config, root=CODE_ROOT):
    relative = safe_path(config['checker']['path'])
    root = Path(root).resolve()
    path = (root/relative).resolve()
    if not path.is_relative_to(root) or path.suffix != '.py' or not path.is_file():
        raise ValueError('Checker adapter must be a Python file inside the controller repository')
    return path


def configuration(path=None):
    path = path or selected()
    if path is None:
        raise ValueError('Select an explicit --target-config manifest; there is no default target')
    try:
        return validate(load(path))
    except (KeyError, TypeError) as error:
        raise ValueError(f'Incomplete or malformed target manifest: {error}') from error


def design_directory(config):
    return ROOT/'designs'/config['target_id']


def validate_verilator(config):
    tests = config.get('admitted_tests')
    if not isinstance(tests, list) or not tests:
        raise ValueError('Verilator requires an admitted-test list')
    ids = []
    for test in tests:
        if not re.fullmatch(r'[A-Za-z0-9_]+', test.get('id', '')):
            raise ValueError('Invalid admitted test id')
        ids.append(test['id'])
        kinds = {'scoreboard', 'sequence_tl_compare', 'mixed_ral_read'} if config['backend'] == 'verilator_uvm' else {'upstream_expected_file_compare'}
        if test.get('oracle_kind') not in kinds:
            raise ValueError('Every admitted test requires an oracle kind')
        if not isinstance(test.get('run_options'), list) or any(not isinstance(s, str) for s in test['run_options']):
            raise ValueError('Every admitted test requires upstream run options')
        if config['backend'] == 'verilator_uvm':
            if not isinstance(test.get('completion_pattern'), str):
                raise ValueError('UVM requires upstream progress checkpoints')
            if re.compile(test['completion_pattern']).groups != 2:
                raise ValueError('Completion pattern must capture iteration and total')
            if not re.fullmatch(r'[A-Za-z0-9_]+', test.get('sequence', '')) or type(test.get('seed')) is not int:
                raise ValueError('UVM requires an explicit sequence and integer seed')
            if any(s.startswith(('+UVM_TESTNAME=', '+UVM_TEST_SEQ=', '+verilator+seed+')) for s in test['run_options']):
                raise ValueError('Run options cannot override test identity or seed')
            if test['id'] == 'same_csr_outstanding' and (test['run_options'].count('+en_scb=0') != 1 or any(s.startswith('+en_scb=') and s != '+en_scb=0' for s in test['run_options'])):
                raise ValueError('same_csr_outstanding must keep upstream +en_scb=0')
    if len(ids) != len(set(ids)) or config['test_id'] not in ids:
        raise ValueError('Test selection must be unique and admitted')
    control = config['control']
    if control.get('pending') != 'front end' or not control.get('intended_site'):
        raise ValueError('OpenTitan controls must remain pending the front end with an intended site')
    if config.get('parameters'):
        raise ValueError('Verilator parameter overrides are not implemented')
    memory = config['limits'].get('memory_bytes')
    if memory is not None and (type(memory) is not int or memory <= 0):
        raise ValueError('memory_bytes must be a positive integer')
    build = config['build']
    if type(build.get('jobs')) is not int or build['jobs'] < 1:
        raise ValueError('Build jobs must be positive')
    if not isinstance(build.get('flags'), list) or any(not isinstance(s, str) for s in build['flags']):
        raise ValueError('Verilator flags must be an argument list')
    if config['backend'] == 'verilator_predv':
        if not build.get('file_list'):
            raise ValueError('pre_dv requires an explicit file list')
        for path in build['file_list']:
            safe_path(path)
    elif not build.get('core') or build.get('optimization', '-O0') not in ('-O0', '-O1', '-O2', '-O3'):
        raise ValueError('UVM requires a core and supported optimization level')
