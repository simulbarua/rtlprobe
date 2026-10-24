"""Shared Verilator build provenance, resource policy and replay discipline."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ..evidence import CODE_ROOT, filehash, identity, load, save, treehashes
from ..oracle import classify
from . import uvm_patchset


def tool(config):
    key = 'RTLPROBE_VERILATOR_UVM' if config['backend'] == 'verilator_uvm' else 'RTLPROBE_VERILATOR_PREDV'
    value = os.environ.get(key, 'verilator')
    found = shutil.which(value)
    if not found:
        raise ValueError(f'Missing {key}: {value}')
    return str(Path(found).resolve())


def build_environment():
    return {'PYTHONDONTWRITEBYTECODE': '1', **{k: os.environ[k] for k in ('SDKROOT', 'CC', 'CXX') if k in os.environ}}


def fusesoc():
    value = os.environ.get('RTLPROBE_FUSESOC', 'fusesoc')
    found = shutil.which(value)
    if not found:
        raise ValueError('Set RTLPROBE_FUSESOC to the pinned FuseSoC executable')
    return str(Path(found).absolute())


def fingerprint(config):
    exe = tool(config)
    banner = subprocess.check_output([exe, '--version'], text=True, timeout=15).strip()
    match = re.search(r'rev\s+(\S+)', banner)
    record = {'backend': config['backend'], 'verilator': {'executable': exe, 'sha256': filehash(exe),
              'version': banner, 'git_revision': match[1] if match else None},
              'build_environment': build_environment(), 'admitted_tests_sha256': identity(config['admitted_tests']),
              'uvm_tree_sha256': None, 'library_edits': [], 'patchset_manifest_sha256': None,
              'fusesoc': None, 'edalize': None}
    binary = Path(exe).with_name('verilator_bin')
    if binary.is_file():
        record['verilator']['binary_sha256'] = filehash(binary)
    if config['backend'] == 'verilator_uvm':
        source = os.environ.get('RTLPROBE_VERILATOR_UVM_SOURCE')
        if not source:
            raise ValueError('Set RTLPROBE_VERILATOR_UVM_SOURCE for the full tool Git SHA')
        sha = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip()
        if sha != config['build']['verilator_git_sha']:
            raise ValueError('Verilator source SHA differs from the pinned manifest')
        record['verilator']['git_sha'] = sha
        fs = fusesoc()
        python = Path(fs).parent / 'python'
        record['fusesoc'], record['edalize'] = subprocess.check_output(
            [str(python), '-c', 'from importlib.metadata import version; print(version("fusesoc")); print(version("edalize"))'],
            text=True, timeout=15).splitlines()
        record['fusesoc_executable_sha256'] = filehash(fs)
        record['patchset_manifest_sha256'] = filehash(uvm_patchset.MANIFEST)
        entries = load(uvm_patchset.MANIFEST)['patches']
        record['library_edits'] = [e for e in entries if e['domain'] == 'uvm']
        record['library_configuration_edit'] = 'UVM_ENABLE_DEPRECATED_API'
        record['diff_hashes'] = {e['patch']: filehash(uvm_patchset.HOME/'patches'/e['patch']) for e in entries}
        record['compat_shim_sha256'] = next(e['patched_sha256'] for e in entries if e['domain'] == 'shim')
        with tempfile.TemporaryDirectory() as temp:
            uvm = uvm_patchset.unpack(Path(temp)/'archive')
            uvm_patchset.apply(uvm, 'uvm', config['design'])
            record['uvm_tree_sha256'] = identity(treehashes(uvm))
    return record


def fresh(runner, config, name, source):
    work = runner.out / (name + '_build')
    work.mkdir(exist_ok=False)  # Never reuse a build or executable for another snapshot.
    save(work/'source_hashes.json', treehashes(source))
    return work


def finish_build(runner, config, name, source, work, command, cwd):
    rec = runner.require(name+'_compile', command, cwd, config['limits']['compile_seconds'],
                         env_extra=build_environment())
    output = (runner.out/rec['stdout']).read_text() + (runner.out/rec['stderr']).read_text()
    match = re.search(r'Walltime ([\d.]+) s \(elab=([\d.]+), cvt=([\d.]+), bld=([\d.]+)\)', output)
    timing = dict(zip(('reported_total', 'elab', 'cvt', 'bld'), map(float, match.groups()))) if match else {
        'reported_total': None, 'elab': None, 'cvt': None, 'bld': None}
    timing['command_wall_seconds'] = rec['elapsed_seconds']
    binary = work/'obj'/('V'+config['test_top'])
    hashes = load(work/'source_hashes.json')
    if hashes != treehashes(source):
        raise ValueError('Build changed original snapshot')
    save(work/'build.json', {'backend': config['backend'], 'source_hashes': hashes,
         'executable_sha256': filehash(binary), 'binary': str(binary.relative_to(runner.out)),
         'walltime_seconds': timing, 'compile_run': rec['id']})
    return binary


def run(runner, config, name, source, binary):
    binary = Path(binary)
    build = load(binary.parent.parent/'build.json')
    hashes = treehashes(source)
    executable = filehash(binary)
    if hashes != build['source_hashes'] or executable != build['executable_sha256']:
        raise ValueError('Executable is not bound to these source hashes; rebuild required')
    test = next(t for t in config['admitted_tests'] if t['id'] == config['test_id'])
    argv = [str(binary), *test['run_options']]
    if config['backend'] == 'verilator_uvm':
        argv += [f'+UVM_TESTNAME={config["design"]}_base_test', f'+UVM_TEST_SEQ={test["sequence"]}',
                 f'+verilator+seed+{test["seed"]}']
    cwd = runner.out/(name+'_runtime')
    cwd.mkdir(exist_ok=False)
    rec = runner.run(name, argv, cwd, config['limits']['simulation_seconds'], env_extra=build_environment())
    result = classify((runner.out/rec['stdout']).read_text(), (runner.out/rec['stderr']).read_text(),
                      rec['returncode'], rec['timed_out'], config=config)
    if hashes != treehashes(source) or executable != filehash(binary):
        raise ValueError('Source or executable changed during simulation')
    result.update(run_id=name, source_hashes=hashes, executable_sha256=executable,
                  test_id=test['id'], seed=test.get('seed'), oracle_kind=test['oracle_kind'],
                  run_options=test['run_options'], backend=config['backend'],
                  build_record=str((binary.parent.parent/'build.json').relative_to(runner.out)),
                  run_wall_seconds=rec['elapsed_seconds'])
    save(runner.out/(name+'.json'), result)
    return result
