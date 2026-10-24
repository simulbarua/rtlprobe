"""Execution backends; absence of a backend field preserves Icarus selection."""
from importlib import import_module

IDS = ('icarus', 'verilator_predv', 'verilator_uvm')


def select(config):
    name = config.get('backend', 'icarus')
    if name not in IDS:
        raise ValueError(f'Unknown execution backend: {name}')
    return import_module('.' + name, __name__)
