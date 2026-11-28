"""Buggy-only observational evidence companions, isolated from case acceptance.

Offline construction and strict revalidation are executable now. The optional
capture API uses the existing bounded Runner and checker, and requires a live
caller-supplied execution guard. This module never mutates a sealed case, derives
an edit, reads labels, compares golden traces, or records acceptance.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

from vcdvcd import VCDVCD
from .candidates import extract_candidates
from .evidence import CODE_ROOT, Runner, filehash, identity
from .evidence_structure import (build_structure, observer_source, IDENT, SCOPE,
                                 MAX_MEMORY_WORDS, memory_capture_reason)
from .evidence_observer import (AES_ASSERTION_TEST, AES_EXTENDED_TEST, instrument_testbench, compiled_timebase, observation_lines,
                                align_observations, align_test_windows, reset_failure_window)
from .mutation import safe_path, sha
from .oracle import classify
from .evidence_limits import supported as file_limit_supported
from .sv_frontend import Source, kind

MAX_VCD_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 256 * 1024 * 1024
PAYLOAD_KEYS = {'buggy_sources', 'source_hashes', 'candidates', 'graph', 'alignment', 'trace', 'checker'}
FILES = {'inference.json', 'buggy.vcd', 'observer.v', 'observer-policy.json', 'ast.json', 'provenance.json'}


def _json(text):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError('duplicate evidence JSON key')
            out[key] = value
        return out
    def nonfinite(value):
        raise ValueError('nonfinite evidence JSON number')
    return json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)


def _read(path, limit=MAX_JSON_BYTES):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError('symlink or oversized evidence artifact')
    return path.read_text()


def source_hashes(sources):
    if not isinstance(sources, dict) or not sources:
        raise ValueError('nonempty buggy source mapping required')
    result = {}
    for path, text in sorted(sources.items()):
        safe_path(path)
        if not isinstance(text, str):
            raise ValueError('source text must be UTF-8 strings')
        if len(text.encode()) > 512 * 1024:
            raise ValueError('source exceeds evidence syntax byte budget')
        result[path] = sha(text.encode())
    if len(result) > 30 or sum(len(text.encode()) for text in sources.values()) > 2 * 1024 * 1024:
        raise ValueError('source set exceeds evidence syntax budget')
    return result


def resolve_dut_scope(testbench, *, top, test_top, fixed_parameters=False):
    """Resolve exactly one unparameterized static top instance in the existing TB."""
    if not IDENT.fullmatch(top) or not IDENT.fullmatch(test_top):
        raise ValueError('simple module names required')
    parsed = Source(testbench.encode('ascii'))
    candidates = []
    for module in parsed.nodes:
        if kind(module) != 'ModuleDeclaration' or module.header.name.valueText != test_top:
            continue
        from .sv_frontend import walk, ancestors
        for node in walk(module):
            if kind(node) == 'HierarchyInstantiation' and node.type.valueText == top:
                if any('Generate' in kind(p) for p in ancestors(node)):
                    raise ValueError('DUT instantiation must be static and outside generates')
                if node.parameters is not None and not fixed_parameters:
                    raise ValueError('DUT instantiation must be static and unparameterized')
                if node.parameters is not None and not re.fullmatch(
                        r"#\s*\(\s*\.[A-Za-z_]\w*\s*\(\d+\s*\)(?:\s*,\s*\.[A-Za-z_]\w*\s*\(\d+\s*\))*\s*\)",
                        ' '.join(parsed.text(node.parameters).split())):
                    raise ValueError('Fixed DUT requires literal named parameter overrides')
                for child in node.instances:
                    if hasattr(child, 'decl'):
                        if child.decl.dimensions:
                            raise ValueError('DUT instance arrays unsupported')
                        candidates.append(test_top + '.' + child.decl.name.valueText)
    if len(candidates) != 1:
        raise ValueError('existing testbench must contain exactly one selected DUT instance')
    return candidates[0]


def _normalized_reference(reference):
    # Keep unpacked word indices; remove only a packed vector range suffix.
    reference = re.sub(r'\[\d+:\d+\]$', '', reference)
    return reference.replace('.\\', '.')


def trace_index(raw_vcd, graph, *, max_vcd_bytes=MAX_VCD_BYTES):
    if not isinstance(raw_vcd, str) or len(raw_vcd.encode()) > max_vcd_bytes:
        raise ValueError('raw VCD exceeds capture byte budget')
    try:
        vcd = VCDVCD(vcd_string=raw_vcd)
    except Exception as error:
        raise ValueError('invalid VCD') from error
    if not vcd.timescale or not vcd.data:
        raise ValueError('VCD requires explicit resolution and signal declarations')
    scope = graph['context']['dut_scope']
    all_nodes = {n['signal']: n for n in graph['nodes']}
    nodes = {name: node for name, node in all_nodes.items() if node['kind'] == 'signal'}
    required, unavailable, memory_words = {}, [], 0
    for name, node in nodes.items():
        ranges = node['unpacked_ranges']
        reason = memory_capture_reason(ranges, MAX_MEMORY_WORDS-memory_words)
        if reason:
            unavailable.append({'signal': name, 'reason': reason})
            continue
        if len(ranges) == 1:
            a, b = ranges[0]
            memory_words += abs(a-b)+1
            for index in range(min(a,b), max(a,b)+1):
                required[f'{name}[{index}]'] = name
        elif not ranges:
            required[name] = name
    observed, signals = set(), []
    for value in vcd.data.values():
        if value.var_type not in {'wire', 'reg', 'integer', 'parameter', 'logic'}:
            raise ValueError('unsupported VCD variable type: ' + value.var_type)
        for reference in sorted(value.references):
            normalized = _normalized_reference(reference)
            if not normalized.startswith(scope + '.'):
                raise ValueError('raw waveform contains evidence outside the declared buggy DUT')
            if normalized in observed:
                raise ValueError('ambiguous normalized waveform reference')
            observed.add(normalized)
            width = int(value.size)
            events = []
            previous = -1
            for tick, bits in value.tv:
                if tick < previous or not re.fullmatch('[01xXzZ]+', bits) or len(bits) > width:
                    raise ValueError('invalid waveform event/time/width')
                previous = tick
                events.append([tick, bits.lower()])
            source = required.get(normalized) or (normalized if normalized in all_nodes else None)
            if source and all_nodes[source]['kind'] == 'signal' and all_nodes[source]['width'] is not None and width != all_nodes[source]['width']:
                raise ValueError('waveform declaration width differs from buggy source')
            signals.append({'reference': reference, 'normalized_reference': normalized, 'width': width,
                            'var_type': value.var_type, 'events': events,
                            'source_signals': [source] if source else [],
                            'status': 'mapped' if source else 'observed_without_source_mapping'})
    missing = sorted((set(required) - observed) | {row['signal'] for row in unavailable})
    return {'schema_version': 'buggy-trace-1', 'raw_vcd': raw_vcd, 'raw_vcd_sha256': sha(raw_vcd.encode()),
            'timescale': str(vcd.timescale['magnitude']) + vcd.timescale['unit'],
            'tick_seconds': str(vcd.timescale['timescale']),
            'capture_start_tick': vcd.begintime, 'capture_end_tick': vcd.endtime,
            'signals': sorted(signals, key=lambda s: s['reference']), 'missing_signals': missing,
            'unavailable_signals': unavailable,
            'limitations': ['all recorded times/values retained; no injected-site window or golden comparison',
                            'ticks use VCD simulation resolution; no inferred nanoseconds or physical delay',
                            'raw VCD retains ordering; indexed settled values are not delta-cycle causality',
                            'extra DUT-local references remain raw evidence with explicit absent source mappings'],
            'status': 'partial' if missing else 'complete'}


def _log(value):
    if not isinstance(value, dict) or set(value) != {'stdout', 'stderr', 'returncode', 'timed_out'}:
        raise ValueError('log must contain only stdout/stderr/returncode/timed_out')
    if (not all(isinstance(value[k], str) for k in ('stdout', 'stderr'))
            or type(value['returncode']) is not int or type(value['timed_out']) is not bool):
        raise ValueError('invalid observed log types')
    return value


def capture_adapter(context):
    target_id = context['target_id']
    if (target_id, context['test_id']) == ('aes', AES_ASSERTION_TEST):
        return 'targets/aes/extended_v2/checker.py'
    if (target_id, context['test_id']) in {('sha1', 'sha1_extended_v1'), ('aes', AES_EXTENDED_TEST)}:
        return f'targets/{target_id}/extended/checker.py'
    return f'targets/{target_id}/checker.py'


def checker_evidence(*, context, testbench_source, plain_buggy_log, observed_buggy_log,
                     timebase=None, trace=None):
    if set(context) != {'target_id', 'test_id', 'checkpoints'} or context['target_id'] not in {'sha1', 'sha256', 'chacha', 'aes', 'axis_fifo'}:
        raise ValueError('only declared checker contexts are available')
    adapter = capture_adapter(context)
    config = {'target_id':context['target_id'], 'test_id':context['test_id'],
              'checker': {'path': adapter}, 'test_metadata': {'checkpoints': context['checkpoints']}}
    plain, observed = _log(plain_buggy_log), _log(observed_buggy_log)
    memory_warnings = []
    if trace is not None:
        memory_warnings = [f"VCD warning: array word {s['normalized_reference']} will conflict with an escaped identifier."
                           for s in trace['signals'] if s['source_signals']
                           and re.search(r'\[\d+\]$', s['normalized_reference'])]
    before = classify(**plain, config=config)
    terminal = before.get('terminal_failure') is True
    observed_checkpoints = [point['id'] for point in before['checkpoints']] if terminal else context['checkpoints']
    # The public checker rederives the verdict from the unchanged log alone.
    # An actual observation or trace still requires the terminal interface sample.
    require_terminal_sample = terminal and (trace is not None or observed != plain)
    cleaned, observations, windows = observation_lines(observed['stdout'], observed_checkpoints,
                                                       permitted_memory_warnings=memory_warnings,
                                                       terminal=require_terminal_sample)
    after = classify(**{**observed, 'stdout': cleaned}, config=config)
    if before != after or before['outcome'] not in {'pass', 'functional_fail'}:
        raise ValueError('observational instrumentation changed checker semantics or logs are incomplete')
    if not isinstance(testbench_source, dict) or len(testbench_source) != 1:
        raise ValueError('one unchanged existing testbench source required')
    for path, text in testbench_source.items():
        safe_path(path)
        if not isinstance(text, str):
            raise ValueError('invalid testbench source')
    anchors = align_observations(observations, verdict=before, timebase=timebase, trace=trace,
                                 target_id=context['target_id'], test_id=context['test_id']) if trace is not None else []
    test_windows = align_test_windows(windows, anchors, timebase, trace) if trace is not None else []
    return {'schema_version': 'buggy-checker-1', 'context': context,
            'testbench_source': testbench_source, 'adapter_source': {adapter: (CODE_ROOT/adapter).read_text()},
            'plain_buggy_log': plain, 'observed_buggy_log': observed, 'verdict': before,
            'observational_parity': 'matched', 'anchors': anchors, 'test_windows': test_windows,
            'timebase': timebase, 'anchor_status': 'complete' if anchors and test_windows else 'unavailable',
            'status': 'complete',
            'limitations': ['both runs use the same buggy snapshot and unchanged checker/stimulus',
                            'anchors compare checker samples to settled VCD values; delta-cycle disagreement is rejected',
                            'only exact naming warnings for mapped captured memory words are normalized; raw logs retained',
                            'missing sampling/timebase evidence is explicit and cannot establish an analysis window']}


def build_inference_evidence(*, buggy_sources, top, dut_scope, raw_vcd, checker_context,
                             testbench_source, plain_buggy_log, observed_buggy_log, timebase=None):
    hashes = source_hashes(buggy_sources)
    if not isinstance(testbench_source, dict) or len(testbench_source) != 1:
        raise ValueError('one unchanged existing testbench source required')
    testbench = next(iter(testbench_source.values()))
    fixed = (checker_context.get('target_id'), checker_context.get('test_id')) == ('axis_fifo', 'axis_fifo_frame_v1')
    if resolve_dut_scope(testbench, top=top, test_top=dut_scope.split('.')[0], fixed_parameters=fixed) != dut_scope:
        raise ValueError('DUT scope differs from existing testbench hierarchy')
    graph, alignment = build_structure(buggy_sources, top=top, dut_scope=dut_scope,
                                       testbench=testbench if fixed else None)
    trace = trace_index(raw_vcd, graph)
    checker = checker_evidence(context=checker_context, testbench_source=testbench_source,
        plain_buggy_log=plain_buggy_log, observed_buggy_log=observed_buggy_log, timebase=timebase, trace=trace)
    reset, window = reset_failure_window(trace, checker['anchors'], dut_scope=dut_scope,
                                         target_id=checker_context['target_id'])
    trace.update(reset=reset, analysis_window=window,
                 passing_test_windows=[w for w in checker['test_windows'] if w['outcome'] == 'pass'])
    if window is None or checker['anchor_status'] != 'complete':
        trace['status'] = 'partial'
    return {'buggy_sources': buggy_sources, 'source_hashes': hashes, 'candidates': extract_candidates(buggy_sources),
            'graph': graph, 'alignment': alignment, 'trace': trace, 'checker': checker}


def validate_inference_evidence(value):
    """Fail closed by rederiving every nested field from source/raw buggy evidence."""
    if not isinstance(value, dict) or set(value) != PAYLOAD_KEYS:
        raise ValueError('unexpected or missing evidence payload fields')
    try:
        context = value['graph']['context']
        if set(context) != {'top', 'dut_scope'}:
            raise ValueError('unexpected source graph context')
        checker = value['checker']
        expected = build_inference_evidence(buggy_sources=value['buggy_sources'], top=context['top'],
            dut_scope=context['dut_scope'], raw_vcd=value['trace']['raw_vcd'], checker_context=checker['context'],
            testbench_source=checker['testbench_source'], plain_buggy_log=checker['plain_buggy_log'],
            observed_buggy_log=checker['observed_buggy_log'], timebase=checker['timebase'])
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('incomplete or malformed evidence payload') from error
    if value != expected:
        raise ValueError('evidence fields differ from strict buggy-source/raw-trace/checker rederivation')
    return value


def publish_companion(destination, evidence, *, provenance):
    """Atomic additive publication; original case trees and receipts are untouched."""
    validate_inference_evidence(evidence)
    destination = Path(destination).resolve()
    if destination.exists() or any((parent/'manifest.json').exists() for parent in destination.parents):
        raise ValueError('companion must be a new directory outside sealed bundles')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.evidence-', dir=destination.parent))
    try:
        observer, policy = observer_source(evidence['graph'])
        values = {'inference.json': evidence, 'observer-policy.json': policy,
                  'ast.json': evidence['graph']['ast'], 'provenance.json': provenance}
        for name, value in values.items():
            (stage/name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
        (stage/'observer.v').write_text(observer)
        (stage/'buggy.vcd').write_text(evidence['trace']['raw_vcd'])
        (stage/'manifest.json').write_text(json.dumps({'schema_version': 'evidence-companion-1',
            'snapshot_kind': 'buggy', 'snapshot_sha256': identity(evidence['source_hashes']),
            'files': {name: filehash(stage/name) for name in sorted(FILES)}}, indent=2)+'\n')
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination


def load_inference_evidence(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('evidence companion must be a real directory')
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
    if any(p.is_symlink() for p in directory.rglob('*')) or actual != FILES | {'manifest.json'}:
        raise ValueError('unexpected, missing or symlinked companion artifact')
    manifest = _json(_read(directory/'manifest.json'))
    if (set(manifest) != {'schema_version', 'snapshot_kind', 'snapshot_sha256', 'files'}
            or manifest['schema_version'] != 'evidence-companion-1' or manifest['snapshot_kind'] != 'buggy'
            or manifest['files'] != {name: filehash(directory/name) for name in sorted(FILES)}):
        raise ValueError('invalid buggy companion manifest or changed artifact')
    value = _json(_read(directory/'inference.json'))
    validate_inference_evidence(value)
    if manifest['snapshot_sha256'] != identity(value['source_hashes']):
        raise ValueError('buggy snapshot binding mismatch')
    observer, policy = observer_source(value['graph'])
    if (_read(directory/'buggy.vcd', MAX_VCD_BYTES) != value['trace']['raw_vcd']
            or _read(directory/'observer.v') != observer
            or _json(_read(directory/'observer-policy.json')) != policy
            or _json(_read(directory/'ast.json')) != value['graph']['ast']):
        raise ValueError('companion capture artifacts disagree with buggy evidence')
    return value


def _guard(callback):
    if not callable(callback) or callback() is not True:
        raise PermissionError('capture requires an affirmative current execution/dependency guard')


def capture_observation(*, config, buggy_root, destination, expected_hashes, execution_guard,
                        runner_factory=Runner, require_complete=True):
    """Later-release bounded capture using the existing Icarus checker and Runner.

    Every command and publication rechecks the caller's live hold/dependency guard.
    No standalone live CLI is exposed. Tests inject a synthetic Runner; production
    integration must bind expected_hashes to the validated buggy case snapshot.
    """
    _guard(execution_guard)
    if config.get('backend', 'icarus') != 'icarus' or config.get('target_id') not in {'sha1', 'sha256', 'chacha', 'aes', 'axis_fifo'}:
        raise ValueError('observational capture currently supports only admitted Icarus targets')
    if not file_limit_supported():
        raise RuntimeError('capture requires enforced per-file RLIMIT_FSIZE support')
    source_root, output = Path(buggy_root).resolve(), Path(destination).resolve()
    if output.exists() or source_root == output or source_root in output.parents or output in source_root.parents:
        raise ValueError('capture output must be a fresh separate companion work directory')
    if any((parent/'manifest.json').exists() for parent in output.parents):
        raise ValueError('capture cannot write under a sealed case')
    file_limit=min(MAX_VCD_BYTES, config['limits'].get('disk_bytes',4*MAX_VCD_BYTES)//4)
    if file_limit < 1024:
        raise ValueError('capture disk budget cannot accommodate bounded files')
    paths = config['rtl'] + [config['testbench']]
    if set(expected_hashes) != set(paths):
        raise ValueError('expected hashes must bind all and only configured buggy RTL and unchanged testbench')
    for relative in paths:
        safe_path(relative)
        path = source_root/relative
        if path.is_symlink() or not path.resolve().is_relative_to(source_root) or filehash(path) != expected_hashes[relative]:
            raise ValueError('buggy source binding mismatch or unsafe source path')
    sources = {path: (source_root/path).read_bytes().decode('ascii') for path in config['rtl']}
    testbench = (source_root/config['testbench']).read_bytes().decode('ascii')
    fixed = (config['target_id'], config['test_id']) == ('axis_fifo', 'axis_fifo_frame_v1')
    scope = resolve_dut_scope(testbench, top=config['top'], test_top=config['test_top'], fixed_parameters=fixed)
    graph, _ = build_structure(sources, top=config['top'], dut_scope=scope,
                               testbench=testbench if fixed else None)
    observer, policy = observer_source(graph)
    observed_testbench, checker_policy = instrument_testbench(testbench, config['target_id'], test_id=config['test_id'])
    _guard(execution_guard)
    output.mkdir(parents=True, exist_ok=False)
    run_root = output/'work'
    for relative in paths:
        _guard(execution_guard)
        target = run_root/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root/relative, target)
    _guard(execution_guard)
    (run_root/'observer.v').write_text(observer)
    (run_root/'observed_tb.v').write_text(observed_testbench)
    runner = runner_factory(output, config['limits'])
    records, logs = [], []
    from .capture_execution import command_plan
    plan = iter(command_plan(output, config, file_limit))
    for compile_step, run_step in zip(plan, plan, strict=True):
        _guard(execution_guard)
        if any(filehash(run_root/path) != expected_hashes[path] for path in paths):
            raise ValueError('copied buggy source/testbench binding changed before compilation')
        name, command, timeout = compile_step
        records.append(runner.require(name, command, run_root, timeout))
        _guard(execution_guard)
        name, command, timeout = run_step
        result = runner.run(name, command, run_root, timeout)
        records.append(result)
        _guard(execution_guard)
        logs.append({'stdout': (output/result['stdout']).read_text(), 'stderr': (output/result['stderr']).read_text(),
                     'returncode': result['returncode'], 'timed_out': result['timed_out']})
        if any(filehash(run_root/path) != expected_hashes[path] for path in paths):
            raise ValueError('capture changed source/testbench bytes')
    evidence = build_inference_evidence(buggy_sources=sources, top=config['top'], dut_scope=scope,
        raw_vcd=_read(run_root/'buggy.vcd', file_limit),
        checker_context={'target_id': config['target_id'], 'test_id': config['test_id'],
                         'checkpoints': config['test_metadata']['checkpoints']},
        testbench_source={config['testbench']: testbench}, plain_buggy_log=logs[0], observed_buggy_log=logs[1],
        timebase=compiled_timebase((run_root/'observed_buggy.vvp').read_text(), config['test_top']))
    provenance = {'schema_version': 'capture-provenance-1', 'snapshot_kind': 'buggy',
                  'input_hashes': expected_hashes, 'target_config_sha256': identity(config),
                  'checker_adapter_sha256': filehash(CODE_ROOT/capture_adapter(config)),
                  'records': records, 'observer_policy': policy,
                  'checker_observer_policy': checker_policy,
                  'observed_testbench_sha256': sha(observed_testbench.encode()),
                  'compiled_vvp_sha256': filehash(run_root/'observed_buggy.vvp'),
                  'runtime_file_limit': {'mechanism': 'RLIMIT_FSIZE', 'bytes': file_limit,
                                        'scope': 'per-process file size including waveform/stdout/stderr',
                                        'aggregate_disk_limit': 'pre/post checks, not an in-flight filesystem quota'},
                  'capture_status': 'complete' if all(evidence[k]['status'] == 'complete' for k in ('graph','alignment','trace','checker')) else 'partial',
                  'automatic_batch_integration': False}
    projected = (len(json.dumps(evidence).encode()) + len(evidence['trace']['raw_vcd'].encode())
                 + len(json.dumps(evidence['graph']['ast']).encode()) + len(json.dumps(provenance).encode()) + 1048576)
    current = sum(path.stat().st_size for path in output.rglob('*') if path.is_file())
    if current + projected > config['limits'].get('disk_bytes', 2 * MAX_JSON_BYTES):
        raise RuntimeError('capture companion would exceed the declared disk budget; raw work retained')
    _guard(execution_guard)
    companion = publish_companion(output/'companion', evidence, provenance=provenance)
    _guard(execution_guard)
    if require_complete and (provenance['capture_status'] != 'complete' or policy['missingness']):
        raise RuntimeError('capture incomplete; preserved companion at ' + str(companion))
    return companion


def main():
    parser = argparse.ArgumentParser(description='Offline buggy evidence assembly/verification; never simulates')
    subs = parser.add_subparsers(dest='action', required=True)
    p = subs.add_parser('verify'); p.add_argument('companion', type=Path)
    p = subs.add_parser('assemble'); p.add_argument('input_json', type=Path); p.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        value = load_inference_evidence(args.companion)
        print(json.dumps({'snapshot_sha256': identity(value['source_hashes']),
                          'status': {k: value[k]['status'] for k in ('graph','alignment','trace','checker')}}))
    else:
        value = _json(_read(args.input_json))
        print(publish_companion(args.destination, build_inference_evidence(**value),
                                provenance={'schema_version': 'offline-import-1', 'snapshot_kind': 'buggy',
                                            'fresh_simulations': 0, 'automatic_batch_integration': False}))


if __name__ == '__main__':
    main()
