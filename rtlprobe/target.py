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
    if config.get('defines') or config.get('parameters') or config.get('seed') is not None:
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
    if control['path'] not in config['rtl'] or not isinstance(control.get('operator'), dict):
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
