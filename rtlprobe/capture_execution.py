"""Private capture work integrity and command provenance, bound by an external hash.

This verifier executes nothing. A trusted guarded caller must supply the proof
hash; files alone are not a cryptographic attestation of physical execution.
Offline companions remain readable but cannot satisfy this operational check.
"""
from datetime import datetime
import math
from pathlib import Path
import shutil
import sys

from .evidence import CODE_ROOT, filehash, identity, save

PROOF = 'capture-execution.json'


def runtime_binding():
    files = sorted((CODE_ROOT/'rtlprobe').rglob('*.py')) + sorted((CODE_ROOT/'rtlprobe').rglob('*.json'))
    files += sorted((CODE_ROOT/'targets').glob('*/checker.py')) + [CODE_ROOT/'requirements-dataset.lock.txt']
    tools = {}
    for name in ('iverilog', 'vvp'):
        executable = shutil.which(name)
        if executable is None:
            raise ValueError('Capture execution tool missing: '+name)
        path = Path(executable).resolve()
        tools[name] = {'path': str(path), 'sha256': filehash(path)}
    return {'files': {str(p.relative_to(CODE_ROOT)): filehash(p) for p in files},
            'tools': tools, 'python': str(Path(sys.executable).absolute()),
            'python_sha256': filehash(sys.executable)}


def _files(root):
    if any(p.is_symlink() for p in [root, *root.parents]) or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Capture execution work cannot contain symlinks')
    return {str(p.relative_to(root)): filehash(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p != root/PROOF}


def _load(path):
    from .evidence_capture import _json, _read
    return _json(_read(path))


def command_plan(root, config, file_limit):
    work = root/'work'; paths = config['rtl']+[config['testbench']]
    result = []
    for name, observed in [('plain_buggy', False), ('observed_buggy', True)]:
        binary = work/(name+'.vvp')
        command = ['iverilog', *config['compile_flags'], '-s', config['test_top'], '-o', str(binary),
                   *[str(work/'observed_tb.v') if observed and p == config['testbench'] else str(work/p) for p in paths]]
        if observed:
            command += ['-s', 'rtlprobe_observer', str(work/'observer.v')]
        result.append((name+'_compile', command, config['limits']['compile_seconds']))
        result.append((name+'_run', [sys.executable, str(CODE_ROOT/'rtlprobe/evidence_limits.py'),
            '--bytes', str(file_limit), '--', 'vvp', '-N', str(binary)], config['limits']['simulation_seconds']))
    return result


def verify_capture_execution(proof_path, *, expected_sha256, config, expected_hashes):
    from .evidence_capture import load_inference_evidence
    from .evidence_observer import instrument_testbench, compiled_timebase
    from .evidence_structure import observer_source
    if config.get('target_id') not in {'sha256', 'chacha'} or config.get('backend', 'icarus') != 'icarus':
        raise ValueError('Capture execution verification supports only crypto Icarus targets')
    proof_path = Path(proof_path)
    if (not proof_path.is_absolute() or '..' in proof_path.parts or proof_path.name != PROOF
            or proof_path.is_symlink() or not proof_path.is_file() or filehash(proof_path) != expected_sha256):
        raise ValueError('Missing, changed or unsafe capture execution proof')
    root = proof_path.parent
    proof = _load(proof_path)
    if (set(proof) != {'schema_version', 'files', 'runtime', 'target_config_sha256', 'input_hashes', 'companion_manifest_sha256'}
            or proof['schema_version'] != 'capture-execution-1'
            or proof['files'] != _files(root) or proof['runtime'] != runtime_binding()
            or proof['target_config_sha256'] != identity(config) or proof['input_hashes'] != expected_hashes
            or proof['companion_manifest_sha256'] != filehash(root/'companion/manifest.json')):
        raise ValueError('Capture execution work/runtime/input binding changed')
    if set(expected_hashes) != set(config['rtl']+[config['testbench']]):
        raise ValueError('Capture execution input set differs from the selected target')
    work = root/'work'
    for path, digest in expected_hashes.items():
        from .mutation import safe_path
        if filehash(work/safe_path(path)) != digest:
            raise ValueError('Capture execution source/checker bytes changed')
    value = load_inference_evidence(root/'companion')
    if (value['source_hashes'] != {p: expected_hashes[p] for p in config['rtl']}
            or any(value[k]['status'] != 'complete' for k in ('graph', 'alignment', 'trace', 'checker'))):
        raise ValueError('Capture execution companion is partial or belongs to different source bytes')
    provenance = _load(root/'companion/provenance.json')
    observed_tb, checker_policy = instrument_testbench((work/config['testbench']).read_bytes().decode('ascii'), config['target_id'])
    observer, policy = observer_source(value['graph'])
    file_limit = min(64*1024*1024, config['limits'].get('disk_bytes', 256*1024*1024)//4)
    if (provenance.get('schema_version') != 'capture-provenance-1' or provenance.get('snapshot_kind') != 'buggy'
            or provenance.get('input_hashes') != expected_hashes or provenance.get('target_config_sha256') != identity(config)
            or provenance.get('checker_adapter_sha256') != filehash(CODE_ROOT/f"targets/{config['target_id']}/checker.py")
            or provenance.get('capture_status') != 'complete' or policy['missingness']
            or provenance.get('observer_policy') != policy or provenance.get('checker_observer_policy') != checker_policy
            or (work/'observed_tb.v').read_bytes() != observed_tb.encode()
            or (work/'observer.v').read_bytes() != observer.encode()
            or provenance.get('observed_testbench_sha256') != filehash(work/'observed_tb.v')
            or provenance.get('compiled_vvp_sha256') != filehash(work/'observed_buggy.vvp')
            or (work/'buggy.vcd').read_bytes() != value['trace']['raw_vcd'].encode()
            or value['checker']['timebase'] != compiled_timebase((work/'observed_buggy.vvp').read_text(), config['test_top'])
            or provenance.get('runtime_file_limit', {}).get('mechanism') != 'RLIMIT_FSIZE'
            or provenance.get('runtime_file_limit', {}).get('bytes') != file_limit):
        raise ValueError('Actual capture provenance/observer/timebase evidence is incomplete or inconsistent')
    records = provenance.get('records')
    planned = command_plan(root, config, file_limit)
    if not isinstance(records, list) or len(records) != 4 or _load(root/'commands.json') != records:
        raise ValueError('Four actual ordered capture command records are required')
    for record, (name, command, timeout) in zip(records, planned):
        directory = root/'commands'/name
        if (record != _load(directory/'run.json') or record.get('id') != name
                or record.get('command') != command or record.get('cwd') != str(work)
                or record.get('timed_out') is not False or record.get('interrupted') is not False
                or type(record.get('returncode')) is not int
                or (name.endswith('_compile') and record['returncode'] != 0)):
            raise ValueError('Capture command differs from the bounded actual command plan')
        for field in ('elapsed_seconds', 'cpu_seconds', 'timeout_seconds'):
            n = record.get(field)
            if type(n) not in (int, float) or not math.isfinite(n) or n < 0:
                raise ValueError('Capture command resource accounting missing or invalid')
        if not 0 < record['timeout_seconds'] <= timeout or record['elapsed_seconds'] > record['timeout_seconds']+1:
            raise ValueError('Capture command exceeded its declared bound')
        start = _load(directory/'started.json'); process = _load(directory/'process.json')
        when = datetime.fromisoformat(record['started_at'])
        if (when.tzinfo is None or when > datetime.now(when.tzinfo)
                or start != {k: record[k] for k in ('id','command','cwd','started_at','timeout_seconds')}
                or type(process.get('pid')) is not int or process['pid'] < 1):
            raise ValueError('Capture command start/process provenance is missing')
        for stream in ('stdout', 'stderr'):
            expected_path = f'commands/{name}/{stream}.log'
            if record.get(stream) != expected_path or record.get(stream+'_sha256') != filehash(root/expected_path):
                raise ValueError('Capture raw command log/hash differs')
        if name.endswith('_run'):
            log = value['checker']['observed_buggy_log' if name.startswith('observed') else 'plain_buggy_log']
            if (log != {'stdout': (directory/'stdout.log').read_text(), 'stderr': (directory/'stderr.log').read_text(),
                        'returncode': record['returncode'], 'timed_out': record['timed_out']}):
                raise ValueError('Capture raw run logs differ from the companion checker')
    if (sum(r['elapsed_seconds'] for r in records) > config['limits']['campaign_seconds']
            or sum(r['cpu_seconds'] for r in records) > config['limits']['cpu_seconds']
            or sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > config['limits']['disk_bytes']):
        raise ValueError('Capture execution exceeds its aggregate resource policy')
    if proof['files'] != _files(root) or filehash(proof_path) != expected_sha256:
        raise ValueError('Capture execution work changed during verification')
    return value


def seal_capture_execution(directory, *, config, expected_hashes):
    """Called only after guarded capture; no approval or execution is issued."""
    root = Path(directory).resolve(); proof = root/PROOF
    if proof.exists() or proof.is_symlink():
        raise ValueError('Capture execution proof must be new')
    value = {'schema_version': 'capture-execution-1', 'files': _files(root), 'runtime': runtime_binding(),
             'target_config_sha256': identity(config), 'input_hashes': expected_hashes,
             'companion_manifest_sha256': filehash(root/'companion/manifest.json')}
    save(proof, value)
    digest = filehash(proof)
    verify_capture_execution(proof, expected_sha256=digest, config=config, expected_hashes=expected_hashes)
    return {'path': str(proof), 'sha256': digest}
