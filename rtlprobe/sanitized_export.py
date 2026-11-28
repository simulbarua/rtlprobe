"""Condition-specific, hash-bound buggy-evidence exports.

This module never executes a target or a localizer. A sealed export directory
is an artifact boundary, not OS process isolation; agent execution additionally
requires the fail-closed isolation preflight below and the caller's launch gates.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

from .candidates import extract_candidates

SCHEMA = 'sanitized-localization-export-1'
CONDITIONS = {'C0': (), 'C1': ('structure',), 'C2': ('waveform',),
              'C3': ('specification',), 'C4': ('structure', 'waveform', 'specification'),
              'M': ('raw_structure', 'raw_waveform', 'specification')}
CONFIG_FIELDS = {'top', 'test_top', 'test_id', 'rtl', 'testbench', 'defines', 'parameters', 'seed'}
RESERVED_PARTS = {'.git', 'original', 'golden', 'restored', 'labels', 'patches', 'reviews', 'curator'}
PRIVATE_KEYS = {'case_id', 'case_path', 'proposal_id', 'mutation_key', 'operator', 'operator_id',
                'ground_truth', 'acceptance_record', 'human_review', 'plan_review', 'true_site',
                'true_sites', 'injected_line', 'control', 'qualification', 'fingerprint', 'vendor',
                'label', 'labels', 'patch', 'mutation_patch', 'original', 'restored', 'golden',
                'golden_trace', 'original_trace', 'curator_path', 'curator_root'}
PRIVATE_TEXT = re.compile(r'(?:/(?:(?:Users|home|private|tmp|var|srv|opt|mnt|root|workspace|data)/)|(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|'
                          r'\b(?:sha1|sha256|chacha|aes|opentitan_[a-z0-9_]+)-[0-9a-f]{16}\b|'
                          r'\b(?:planner|plan)-[0-9a-f]{16}\b|'
                          r'\b(?:accepted_core|accepted_auto|validated_pending_review)\b)')
EVIDENCE_KEYS = {'buggy_sources', 'source_hashes', 'candidates', 'graph', 'alignment', 'trace', 'checker'}
MANIFEST_KEYS = {'schema_version', 'neutral_id', 'condition', 'enabled_modalities', 'buggy_snapshot_sha256',
                 'candidate_inventory_id', 'candidate_count', 'evidence_binding_sha256', 'specification_sha256',
                 'ready', 'missing', 'source_hashes', 'files', 'process_isolation', 'raw_control'}
BIBLIOGRAPHY_FIELDS = {'title', 'url', 'version', 'publisher', 'license', 'redistributable',
                       'classification_of_claims', 'retrieval_date', 'sha256',
                       'sections_of_interest', 'quotation_basis'}
PUBLIC_CHECKER_SCHEMA = 'public-buggy-checker-1'
PUBLIC_CHECKER_FIELDS = {'context', 'testbench_source', 'adapter_source', 'plain_buggy_log', 'verdict'}


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Evidence paths must be plain relative POSIX paths')
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or ':' in value or '..' in path.parts
            or str(path) != value or any(p in RESERVED_PARTS for p in path.parts)):
        raise ValueError('Forbidden inference path')
    return value


def leakage_check(value, *, forbidden_tokens=()):
    """Reject private schema fields, known identifiers, and private host paths.

    Ordinary RTL words such as ``case`` and ``original`` are not blanket text
    bans. Explicit private token values must be supplied by the curator when
    logs or documentation could contain identifiers not matching known formats.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in PRIVATE_KEYS:
                raise ValueError('Private or unsupported evidence metadata')
            leakage_check(key, forbidden_tokens=forbidden_tokens)
            leakage_check(child, forbidden_tokens=forbidden_tokens)
    elif isinstance(value, list):
        for child in value:
            leakage_check(child, forbidden_tokens=forbidden_tokens)
    elif isinstance(value, str):
        if PRIVATE_TEXT.search(value) or any(token and token in value for token in forbidden_tokens):
            raise ValueError('Private host path or curator identifier in inference material')
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise ValueError('Inference material must contain JSON-compatible values')


def _sources(value):
    if not isinstance(value, dict) or not value:
        raise ValueError('Buggy source map must be nonempty')
    for path, text in value.items():
        relative_path(path)
        if not isinstance(text, str):
            raise ValueError('Buggy sources must be UTF-8 text')
    return {path: sha(text.encode()) for path, text in sorted(value.items())}


def _public_log_text(text, testbenches):
    """Relativize only Icarus finish diagnostics at a bound TB finish statement."""
    result = []
    for line in text.splitlines(keepends=True):
        match = re.fullmatch(r'(.+):([1-9][0-9]*): (\$finish called at [0-9]+ \([^\r\n()]+\))(\r?\n)?', line)
        if match and match[1].startswith('/') and '..' not in PurePosixPath(match[1]).parts:
            for path, source in testbenches.items():
                relative_path(path)
                lines = source.splitlines()
                number = int(match[2])
                if (match[1].endswith('/'+path) and number <= len(lines)
                        and re.search(r'\$finish\s*(?:\(|;)', lines[number-1])):
                    line = f'{path}:{match[2]}: {match[3]}' + (match[4] or '')
                    break
        result.append(line)
    return ''.join(result)


def _common(common, sources, snapshot):
    """Project common evidence; a complete target manifest is never copied."""
    if not isinstance(common, dict) or set(common) != {'configuration', 'sources', 'logs', 'hierarchy'}:
        raise ValueError('Common context requires configuration, sources, logs and hierarchy only')
    config = common['configuration']
    if not isinstance(config, dict) or not CONFIG_FIELDS <= config.keys():
        raise ValueError('Common context lacks safe compilation/test identity fields')
    selected = {key: config[key] for key in sorted(CONFIG_FIELDS)}
    if (not isinstance(selected['rtl'], list) or set(selected['rtl']) != set(sources)
            or any(not isinstance(selected[key], str) or not selected[key] for key in ('top', 'test_top', 'test_id'))):
        raise ValueError('Common configuration does not describe the buggy source set')
    for path in selected['rtl'] + [selected['testbench']]:
        relative_path(path)
    if (not isinstance(selected['defines'], list) or any(not isinstance(v, str) for v in selected['defines'])
            or not isinstance(selected['parameters'], dict)
            or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]*', key)
                   or value is None or not isinstance(value, (str, int, float, bool))
                   for key, value in selected['parameters'].items())
            or (selected['seed'] is not None and type(selected['seed']) is not int)):
        raise ValueError('Malformed common configuration')
    files, roles = {}, set()
    for entry in common['sources']:
        if not isinstance(entry, dict) or set(entry) != {'path', 'roles', 'content', 'snapshot_sha256'}:
            raise ValueError('Unexpected common source fields')
        path = relative_path(entry['path'])
        if path in sources or path in files or not isinstance(entry['content'], str):
            raise ValueError('Common source path collision or non-text source')
        if entry['snapshot_sha256'] != snapshot:
            raise ValueError('Common source is not bound to this buggy snapshot')
        if (not isinstance(entry['roles'], list) or not entry['roles']
                or not set(entry['roles']) <= {'testbench', 'checker', 'documentation', 'firmware'}):
            raise ValueError('Common source role is outside the allowlist')
        roles.update(entry['roles'])
        files[path] = {'roles': sorted(set(entry['roles'])), 'sha256': sha(entry['content'].encode()),
                       'content': entry['content']}
    missing = sorted({'testbench', 'checker', 'documentation'} - roles)
    if selected['testbench'] not in files or 'testbench' not in files[selected['testbench']]['roles']:
        missing.append('declared_testbench_source')
    logs = common['logs']
    if not isinstance(logs, list):
        raise ValueError('Common logs must be a typed list')
    for log in logs:
        if (not isinstance(log, dict) or set(log) != {'test_id', 'outcome', 'text', 'snapshot_sha256'}
                or log['outcome'] not in {'pass', 'functional_fail'} or log['snapshot_sha256'] != snapshot
                or not isinstance(log['test_id'], str) or not isinstance(log['text'], str)):
            raise ValueError('Log lacks a declared buggy-run provenance or verdict')
    if not any(log['outcome'] == 'functional_fail' for log in logs):
        missing.append('failing_run_log')
    testbenches = {path: row['content'] for path,row in files.items() if 'testbench' in row['roles']}
    logs = [{**log, 'text': _public_log_text(log['text'], testbenches)} for log in logs]
    hierarchy = common['hierarchy']
    if not isinstance(hierarchy, list):
        raise ValueError('Hierarchy must be a source-only instance list')
    seen = set()
    for row in hierarchy:
        if (not isinstance(row, dict) or set(row) != {'instance', 'module', 'path'}
                or row['path'] not in sources or not isinstance(row['instance'], str)
                or not isinstance(row['module'], str) or row['instance'] in seen):
            raise ValueError('Hierarchy row is not a source-only instance mapping')
        seen.add(row['instance'])
    if not hierarchy:
        missing.append('source_hierarchy')
    if selected['defines'] or selected['parameters']:
        missing.append('checked_define_and_parameter_elaboration_context')
    return {'configuration': selected, 'sources': files, 'logs': logs, 'hierarchy': hierarchy}, missing


def specification_files(directory):
    """Project an entire fixed store independently of any mutation.

    Requirements, schema and sections retain their exact bytes. Local retrieval
    paths and original RTL file hashes are curator provenance, not bibliography.
    The full input-store identity is returned only to the curator caller.
    """
    directory = Path(directory).resolve()
    all_files, exposed = {}, {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Specification stores cannot contain symlinks')
        if not path.is_file():
            continue
        name = relative_path(path.relative_to(directory).as_posix())
        allowed = (name in {'README.md', 'sources.json', 'requirements.jsonl', 'schema.json', 'coverage.json'}
                   or (name.startswith('sections/') and name.endswith('.md') and len(PurePosixPath(name).parts) == 2))
        if not allowed:
            raise ValueError('Unexpected file in the fixed specification store')
        data = path.read_bytes()
        data.decode('utf-8')
        all_files[name] = sha(data)
        if name not in {'coverage.json', 'sources.json', 'README.md'}:
            exposed[name] = data
    if not {'sources.json', 'requirements.jsonl', 'schema.json', 'README.md'} <= all_files.keys():
        raise ValueError('Incomplete specification store')
    bibliography = json.loads((directory/'sources.json').read_text())
    if not isinstance(bibliography, dict) or any(not isinstance(row, dict) for row in bibliography.values()):
        raise ValueError('Specification bibliography must be a source-ID map')
    public_sources = {source_id: {key: row[key] for key in sorted(BIBLIOGRAPHY_FIELDS) if key in row}
                      for source_id, row in sorted(bibliography.items())}
    exposed['sources.json'] = encoded(public_sources)
    exposed['README.md'] = (
        '# Specification evidence\n\n'
        'This fixed per-target view includes every curated requirement and section.\n'
        'Bibliographic metadata uses an explicit public-field projection. Local\n'
        'retrieval paths, source snapshot pointers and per-file RTL hashes remain\n'
        'in the curator archive. Requirements and section text are unchanged.\n').encode()
    return exposed, identity(all_files)


def _validate_evidence(evidence):
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
        raise ValueError('Inference evidence has private or unsupported top-level fields')
    hashes = _sources(evidence['buggy_sources'])
    if hashes != evidence['source_hashes']:
        raise ValueError('Buggy source hashes do not match evidence')
    # Re-extraction prevents curator-only fields being smuggled into public rows.
    if extract_candidates(evidence['buggy_sources']) != evidence['candidates']:
        raise ValueError('Candidate inventory is not the source-only buggy inventory')
    from .evidence_capture import validate_inference_evidence
    validate_inference_evidence(evidence)
    return hashes


def public_checker(checker):
    """Expose the same unchanged checker source/log/verdict in every condition.

    Observer diagnostics, waveform anchors and capture-verification metadata
    remain in the private companion. Copying the complete checker object would
    give baseline/raw conditions additional time/signal alignment evidence.
    """
    value = {'schema_version': PUBLIC_CHECKER_SCHEMA,
             **{key: checker[key] for key in sorted(PUBLIC_CHECKER_FIELDS)}}
    value['plain_buggy_log'] = {**checker['plain_buggy_log'],
        'stdout': _public_log_text(checker['plain_buggy_log']['stdout'], checker['testbench_source'])}
    return validate_public_checker(value)


def validate_public_checker(value):
    """Reject extra nested proof fields by rederiving the public verdict from log.

    Only the installed, admitted crypto checker is executed as Python code;
    exported adapter source is compared as data, never dynamically executed.
    """
    if (not isinstance(value, dict) or set(value) != PUBLIC_CHECKER_FIELDS | {'schema_version'}
            or value.get('schema_version') != PUBLIC_CHECKER_SCHEMA):
        raise ValueError('Unsupported public checker projection or extra capture metadata')
    try:
        context = value['context']
        if (not isinstance(context, dict) or set(context) != {'target_id', 'test_id', 'checkpoints'}
                or not isinstance(context['test_id'], str) or not context['test_id']
                or not isinstance(context['checkpoints'], list) or not context['checkpoints']
                or any(not isinstance(p, str) or not p for p in context['checkpoints'])
                or len(set(context['checkpoints'])) != len(context['checkpoints'])):
            raise ValueError('Malformed public checker context')
        from .evidence_capture import checker_evidence
        from .evidence_observer import PREFIX, WINDOW_PREFIX
        log = value['plain_buggy_log']
        if any(line.startswith((PREFIX, WINDOW_PREFIX)) for line in log['stdout'].splitlines()):
            raise ValueError('Observer diagnostics cannot enter the public unchanged checker log')
        derived = checker_evidence(context=context, testbench_source=value['testbench_source'],
            plain_buggy_log=log, observed_buggy_log=log)
        expected = {'schema_version': PUBLIC_CHECKER_SCHEMA,
                    **{key: derived[key] for key in sorted(PUBLIC_CHECKER_FIELDS)}}
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Malformed public checker projection') from error
    if value != expected:
        raise ValueError('Public checker differs from unchanged source/log/verdict rederivation')
    return value


def _vcd_window(raw_vcd, start, end):
    """Keep raw within-window record order and seed state immediately before it.

    This bounded adapter supports the one-record-per-line Icarus dumps produced
    by the capture observer, including comments and dumpvars/dumpall blocks.
    Other layouts/directives fail explicitly. The full
    untouched dump remains in the curator companion.
    """
    from vcdvcd import VCDVCD
    marker = re.search(r'\$enddefinitions\s+\$end', raw_vcd)
    if marker is None or type(start) is not int or type(end) is not int or start < 0 or end < start:
        raise ValueError('Unsupported raw waveform/window')
    header, body = raw_vcd[:marker.end()], raw_vcd[marker.end():]
    seeded, selected, current = [], [], 0
    comment, dump = False, None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if comment or re.match(r'\$comment(?:\s|$)', line):
            end_comment = re.search(r'\$end(?:\s|$)', line)
            if end_comment and line[end_comment.end():].strip():
                raise ValueError('Unsupported trailing record after raw VCD comment')
            comment = end_comment is None
            continue
        if line in {'$dumpvars', '$dumpall'}:
            if dump is not None:
                raise ValueError('Nested raw VCD dump directive')
            dump = line
            continue
        if line == '$end':
            if dump is None:
                raise ValueError('Unmatched raw VCD end directive')
            dump = None
            continue
        tick = re.fullmatch(r'#([0-9]+)', line)
        if tick:
            if dump is not None:
                raise ValueError('Timestamp inside raw VCD dump block')
            current = int(tick[1])
            if start <= current <= end:
                selected.append(line)
            continue
        if not (re.fullmatch(r'[01xXzZ][!-~]+', line) or re.fullmatch(r'[bB][01xXzZ]+\s+[!-~]+', line)):
            raise ValueError('Unsupported raw VCD value record/directive in window projection')
        if start <= current <= end:
            selected.append(line)
    if comment or dump is not None:
        raise ValueError('Unterminated raw VCD comment/dump block')
    # Validate directive framing first: the third-party reader can wait forever
    # for an $end on a truncated comment, even for an in-memory string.
    parsed = VCDVCD(vcd_string=raw_vcd)
    if start < parsed.begintime or end > parsed.endtime:
        raise ValueError('Waveform window exceeds the captured buggy run')
    for code, signal in sorted(parsed.data.items()):
        previous = [bits for tick, bits in signal.tv if tick < start]
        if previous:
            seeded.append(previous[-1]+code if int(signal.size) == 1 else 'b'+previous[-1]+' '+code)
    return header+'\n#'+str(start)+'\n$dumpvars\n'+'\n'.join(seeded)+'\n$end\n'+'\n'.join(selected)+'\n#'+str(end)+'\n'


def waveform_views(evidence):
    """Project the same checker-selected windows for aligned and raw conditions."""
    from .evidence_capture import trace_index
    trace = evidence['trace']
    failure = trace.get('analysis_window')
    passing = trace.get('passing_test_windows')
    if not failure or passing is None:
        return None
    requested = [('failure', 'reset_to_first_failure', None, failure)]
    requested.extend((f'pass-{index:03d}', 'passing_checkpoint_task', row['checkpoint'], row)
                     for index, row in enumerate(passing, 1))
    raw_files, windows, indexes = {}, [], []
    for name, kind, checkpoint, window in requested:
        raw = _vcd_window(trace['raw_vcd'], window['start_tick'], window['end_tick'])
        path = 'raw/'+name+'.vcd'
        raw_files[path] = raw.encode()
        metadata = {'kind': kind, 'checkpoint': checkpoint, 'start_tick': window['start_tick'],
                    'end_tick': window['end_tick'], 'path': path, 'sha256': sha(raw.encode())}
        index = trace_index(raw, evidence['graph'])
        index.pop('raw_vcd')
        windows.append(metadata)
        indexes.append({'window': metadata, 'history': index})
    selection = {'schema_version': 'public-buggy-windows-1', 'windows': windows,
                 'selection': 'observed reset through first checker failure plus unchanged-checker passing task windows',
                 'full_capture_exported': False, 'truncation_within_selected_windows': 'none'}
    return raw_files, selection, {'schema_version': 'public-aligned-waveforms-1', 'windows': indexes,
        'reset': trace['reset'], 'missing_signals': trace['missing_signals'],
        'status': trace['status'], 'selection': selection['selection']}


def export_evidence(destination, *, evidence, condition, neutral_id, common_context,
                    curator_root, evidence_binding_sha256, specification=None,
                    specification_sha256=None, raw_vcd=None, forbidden_tokens=(), allow_partial=False):
    """Create one write-once tree. All supplied inputs must already be audited.

    ``evidence`` comes from evidence_capture.load_inference_evidence; private
    capture provenance is not exported. Declaration/hash checks do not establish
    that a supplied waveform was produced by an executed buggy DUT.
    """
    if condition not in CONDITIONS or not re.fullmatch(r'sample-[0-9a-f]{16}', neutral_id):
        raise ValueError('Explicit supported condition and neutral sample ID required')
    if not re.fullmatch(r'[0-9a-f]{64}', evidence_binding_sha256):
        raise ValueError('Audited evidence manifest hash required')
    destination = Path(destination).absolute()
    curator_root = Path(curator_root).resolve()
    if (destination.exists() or destination.is_symlink() or curator_root == destination.resolve()
            or curator_root in destination.resolve().parents or destination.resolve() in curator_root.parents):
        raise ValueError('Export must be a new directory outside the curator root')
    if any((parent/'.git').exists() for parent in destination.resolve().parents):
        raise ValueError('Inference exports must be outside source repositories')
    hashes = _validate_evidence(evidence)
    snapshot = identity(hashes)
    common, missing = _common(common_context, evidence['buggy_sources'], snapshot)
    if (common['configuration']['top'] != evidence['graph']['context']['top']
            or common['hierarchy'] != evidence['graph']['instances']
            or common['configuration']['test_id'] != evidence['checker']['context']['test_id']):
        raise ValueError('Common configuration/hierarchy differs from the audited buggy capture')
    for path, row in common['sources'].items():
        for role, capture_key in [('testbench', 'testbench_source'), ('checker', 'adapter_source')]:
            if role in row['roles'] and evidence['checker'][capture_key].get(path) != row['content']:
                raise ValueError('Common testbench/checker source differs from the audited capture')
    for log in common['logs']:
        if (log['test_id'] != evidence['checker']['context']['test_id']
                or log['outcome'] != evidence['checker']['verdict']['outcome']
                or log['text'] != _public_log_text(evidence['checker']['plain_buggy_log']['stdout'],
                                                 evidence['checker']['testbench_source'])):
            raise ValueError('Common log does not match an audited buggy-run checker observation')
    if evidence['checker'].get('status') != 'complete':
        missing.append('complete_checker_evidence_and_observational_parity')
    enabled = CONDITIONS[condition]
    if any(modality in enabled for modality in ('structure', 'waveform', 'raw_structure', 'raw_waveform')):
        if not evidence['checker'].get('anchors') or evidence['checker'].get('anchor_status') != 'complete':
            missing.append('checker_signal_and_simulation_time_anchor')
    files = {'candidates.json': encoded(evidence['candidates']), 'common.json': encoded(common),
             'checker.json': encoded(public_checker(evidence['checker']))}
    for path, content in evidence['buggy_sources'].items():
        files['rtl/'+relative_path(path)] = content.encode()
    if 'structure' in enabled or 'raw_structure' in enabled:
        if evidence['graph'] is None or evidence['alignment'] is None:
            missing.append('buggy_structure_and_alignment')
        else:
            # Raw graph and aligned views originate from the same graph artifact;
            # neither representation can select a different signal/edge set.
            name = 'raw/graph.json' if condition == 'M' else 'structure/graph.json'
            files[name] = encoded(evidence['graph'])
            if condition != 'M':
                files['structure/alignment.json'] = encoded(evidence['alignment'])
            if evidence['graph'].get('status') != 'complete' or evidence['alignment'].get('status') != 'complete':
                missing.append('complete_structure_and_candidate_signal_alignment')
    if 'waveform' in enabled or 'raw_waveform' in enabled:
        if evidence['trace'] is None or raw_vcd is None:
            missing.append('buggy_waveform_and_index')
        else:
            if not isinstance(raw_vcd, str):
                raise ValueError('Raw VCD must be verified UTF-8 text, never a host path')
            if (raw_vcd != evidence['trace'].get('raw_vcd')
                    or sha(raw_vcd.encode()) != evidence['trace'].get('raw_vcd_sha256')):
                raise ValueError('Raw waveform differs from the audited buggy trace index')
            views = waveform_views(evidence)
            if views is None:
                missing.append('checked_reset_failure_and_passing_test_windows')
            else:
                raw_files, selection, aligned = views
                files.update(raw_files)
                files['raw/windows.json'] = encoded(selection)
                if condition != 'M':
                    files['waveform/trace.json'] = encoded(aligned)
            if evidence['trace'].get('status') != 'complete':
                missing.append('complete_buggy_trace_mapping')
    spec_hash = None
    if 'specification' in enabled:
        if specification is None or specification_sha256 is None:
            missing.append('independently_frozen_specification_store')
        else:
            spec_files, full_spec_hash = specification_files(specification)
            if full_spec_hash != specification_sha256:
                raise ValueError('Specification store differs from its independent frozen binding')
            spec_hash = identity({name: sha(data) for name, data in sorted(spec_files.items())})
            files.update({'specification/'+name: data for name, data in spec_files.items()})
    missing = sorted(set(missing))
    if missing and not allow_partial:
        raise ValueError('Incomplete condition evidence: '+', '.join(missing))
    manifest = {'schema_version': SCHEMA, 'neutral_id': neutral_id, 'condition': condition,
                'enabled_modalities': list(enabled), 'buggy_snapshot_sha256': snapshot,
                'candidate_inventory_id': evidence['candidates'].get('inventory_id'),
                'candidate_count': len(evidence['candidates']['candidates']),
                'evidence_binding_sha256': evidence_binding_sha256,
                'specification_sha256': spec_hash, 'ready': not missing, 'missing': missing,
                'source_hashes': hashes, 'files': {name: sha(data) for name, data in sorted(files.items())},
                'process_isolation': 'not_established_by_directory_export',
                'raw_control': {'information_set': 'same_buggy_graph_and_checker_selected_waveform_windows',
                                'truncation': 'none', 'protocol_adoption': 'pending'} if condition == 'M' else None}
    for name, data in files.items():
        relative_path(name)
        text = data.decode('utf-8')
        if name.endswith('.json'):
            leakage_check(json.loads(text), forbidden_tokens=forbidden_tokens)
        else:
            leakage_check(text, forbidden_tokens=forbidden_tokens)
    leakage_check(manifest, forbidden_tokens=forbidden_tokens)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserving the final name with mkdir is exclusive. A partial construction
    # never passes verify_export (manifest-last plus read-only directory checks).
    # This avoids portable rename() replacing a concurrently created empty dir.
    destination.mkdir(exist_ok=False)
    stage = destination
    try:
        for name, data in {**files, 'manifest.json': encoded(manifest)}.items():
            path = stage/name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data)
            path.chmod(0o444)
        for path in sorted((p for p in stage.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            path.chmod(0o555)
        stage.chmod(0o555)
    except Exception:
        for path in [stage, *(p for p in stage.rglob('*') if p.is_dir())]:
            path.chmod(0o755)
        shutil.rmtree(stage)
        raise
    verify_export(destination, forbidden_tokens=forbidden_tokens)
    return manifest


def verify_export(directory, *, expected_manifest_sha256=None, forbidden_tokens=()):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Export root must be a real directory')
    paths = list(directory.rglob('*'))
    if any(path.is_symlink() for path in paths):
        raise ValueError('Export contains a symlink')
    manifest_path = directory/'manifest.json'
    if expected_manifest_sha256 is not None and sha(manifest_path.read_bytes()) != expected_manifest_sha256:
        raise ValueError('Export manifest differs from its trusted external binding')
    manifest = json.loads(manifest_path.read_text())
    if (set(manifest) != MANIFEST_KEYS or manifest.get('schema_version') != SCHEMA
            or manifest.get('condition') not in CONDITIONS):
        raise ValueError('Unsupported export manifest')
    actual = {relative_path(path.relative_to(directory).as_posix()): sha(path.read_bytes())
              for path in paths if path.is_file() and path != manifest_path}
    if actual != manifest['files']:
        raise ValueError('Export files differ from the sealed manifest')
    if not {'candidates.json', 'common.json', 'checker.json'} <= actual.keys():
        raise ValueError('Export is missing common inference inputs')
    specific = set()
    if manifest['condition'] in {'C1', 'C4'}:
        specific.update({'structure/graph.json', 'structure/alignment.json'})
    if manifest['condition'] in {'C2', 'C4'}:
        specific.update({'waveform/trace.json', 'raw/windows.json'})
    if manifest['condition'] == 'M':
        specific.update({'raw/graph.json', 'raw/windows.json'})
    for name in actual:
        waveform_path = re.fullmatch(r'raw/(?:failure|pass-[0-9]{3})\.vcd', name)
        if (name in {'candidates.json', 'common.json', 'checker.json'} or name in specific or name.startswith('rtl/')
                or waveform_path and manifest['condition'] in {'C2', 'C4', 'M'}):
            continue
        if name.startswith('specification/') and 'specification' in CONDITIONS[manifest['condition']]:
            leaf = name[len('specification/'):]
            if (leaf in {'README.md', 'sources.json', 'requirements.jsonl', 'schema.json'}
                    or (leaf.startswith('sections/') and leaf.endswith('.md') and len(PurePosixPath(leaf).parts) == 2)):
                continue
        raise ValueError('Export file is outside the inference allowlist')
    if manifest['ready'] and (manifest['missing'] or not specific <= actual.keys()):
        raise ValueError('Ready export lacks its declared condition inputs')
    if any(path.stat().st_mode & 0o222 for path in [directory, *paths]):
        raise ValueError('Export content is not sealed read-only')
    leakage_check(manifest, forbidden_tokens=forbidden_tokens)
    for name in actual:
        content = (directory/name).read_text()
        if name.endswith('.json'):
            leakage_check(json.loads(content), forbidden_tokens=forbidden_tokens)
        else:
            leakage_check(content, forbidden_tokens=forbidden_tokens)
    expected_modalities = list(CONDITIONS[manifest['condition']])
    if manifest.get('enabled_modalities') != expected_modalities:
        raise ValueError('Condition modality declaration changed')
    if manifest['condition'] in {'C0', 'C2', 'C3'} and any(name.startswith(('structure/', 'raw/graph')) for name in actual):
        raise ValueError('Structure exposed to a condition without structure access')
    if manifest['condition'] in {'C0', 'C1', 'C3'} and any(name.startswith(('waveform/', 'raw/')) for name in actual):
        raise ValueError('Waveform exposed to a condition without waveform access')
    if 'specification' not in expected_modalities and any(name.startswith('specification/') for name in actual):
        raise ValueError('Specification exposed to a condition without specification access')
    spec_hashes = {name[len('specification/'):]: digest for name, digest in actual.items() if name.startswith('specification/')}
    if ((spec_hashes and identity(spec_hashes) != manifest['specification_sha256'])
            or (not spec_hashes and manifest['specification_sha256'] is not None)):
        raise ValueError('Public specification projection binding changed')
    if manifest['condition'] == 'M' and any(name.startswith(('structure/', 'waveform/')) for name in actual):
        raise ValueError('Aligned-only views exposed to the raw condition')
    sources = {name[4:]: (directory/name).read_text() for name in actual if name.startswith('rtl/')}
    if _sources(sources) != manifest['source_hashes'] or identity(manifest['source_hashes']) != manifest['buggy_snapshot_sha256']:
        raise ValueError('Export source snapshot binding changed')
    inventory = json.loads((directory/'candidates.json').read_text())
    if inventory != extract_candidates(sources) or inventory.get('inventory_id') != manifest['candidate_inventory_id']:
        raise ValueError('Export candidate universe changed')
    validate_public_checker(json.loads((directory/'checker.json').read_text()))
    return manifest


def isolation_preflight(directory, *, expected_manifest_sha256=None, backend=None, timeout=10):
    """Probe an enforced offline runtime/evidence-only namespace or refuse.

    The returned prefix must wrap the actual localizer process. No /home,
    /Users, /opt, credentials, repository, curator tree, or host network is
    mounted. A provider/network bridge and active project launch decisions are
    separate prerequisites; this does not authorize an inference run.
    """
    if expected_manifest_sha256 is None:
        raise RuntimeError('Agent execution requires a trusted external export-manifest hash')
    manifest = verify_export(directory, expected_manifest_sha256=expected_manifest_sha256)
    if not manifest.get('ready') or manifest.get('missing'):
        raise RuntimeError('Partial evidence export cannot start an agent')
    if backend != 'bubblewrap':
        raise RuntimeError('Agent execution requires an explicitly selected enforced OS isolation backend')
    executable = shutil.which('bwrap')
    if executable is None:
        raise RuntimeError('bubblewrap is unavailable; agent execution remains blocked')
    prefix = [executable, '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
              '--setenv', 'PATH', '/usr/bin:/bin', '--tmpfs', '/tmp', '--dev', '/dev']
    for runtime in ('/usr/bin', '/usr/lib', '/lib', '/lib64', '/bin'):
        if Path(runtime).exists():
            prefix += ['--ro-bind', runtime, runtime]
    prefix += ['--ro-bind', str(Path(directory).resolve()), '/evidence', '--chdir', '/evidence']
    probe = 'test -r /evidence/manifest.json && test ! -e /home && test ! -e /Users && test ! -e /opt'
    try:
        result = subprocess.run([*prefix, '/bin/sh', '-c', probe], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError('OS isolation preflight failed; agent execution remains blocked') from error
    if result.returncode:
        raise RuntimeError('OS isolation preflight rejected execution: '+result.stderr.strip())
    return {'backend': 'bubblewrap', 'export_manifest_sha256': sha((Path(directory)/'manifest.json').read_bytes()),
            'launch_prefix': prefix, 'network': 'unshared', 'credentials': 'not_mounted',
            'project_execution_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--common-context', type=Path, required=True)
    parser.add_argument('--curator-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--condition', choices=sorted(CONDITIONS), required=True)
    parser.add_argument('--neutral-id', required=True)
    parser.add_argument('--specification', type=Path)
    parser.add_argument('--specification-sha256')
    parser.add_argument('--provenance-output', type=Path, required=True,
                        help='New curator receipt outside the inference directory')
    parser.add_argument('--private-token-file', type=Path,
                        help='Optional curator-only JSON list of additional private identifier strings')
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    provenance = args.provenance_output.absolute()
    if (provenance.exists() or provenance.is_symlink()
            or args.curator_root.resolve() not in provenance.resolve().parents
            or args.output.resolve() == provenance.resolve()
            or args.output.resolve() in provenance.resolve().parents):
        raise ValueError('Curator receipt must be a new file under the curator root, outside inference inputs')
    from .evidence_capture import load_inference_evidence
    evidence = load_inference_evidence(args.bundle)
    forbidden = set()
    private_provenance = json.loads((args.bundle/'provenance.json').read_text())
    def collect_private_ids(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'case_id', 'case_path', 'proposal_id', 'mutation_key', 'acceptance_record', 'human_review_record'} and isinstance(child, str):
                    forbidden.add(child)
                else:
                    collect_private_ids(child)
        elif isinstance(value, list):
            for child in value:
                collect_private_ids(child)
    collect_private_ids(private_provenance)
    if args.private_token_file is not None:
        extra = json.loads(args.private_token_file.read_text())
        if not isinstance(extra, list) or any(not isinstance(token, str) or not token for token in extra):
            raise ValueError('Private-token file must contain a list of nonempty strings')
        forbidden.update(extra)
    raw_vcd = evidence['trace'].get('raw_vcd') if evidence['trace'] is not None else None
    manifest = export_evidence(args.output, evidence=evidence, condition=args.condition,
        neutral_id=args.neutral_id, common_context=json.loads(args.common_context.read_text()),
        curator_root=args.curator_root, evidence_binding_sha256=sha((args.bundle/'manifest.json').read_bytes()),
        specification=args.specification, specification_sha256=args.specification_sha256,
        raw_vcd=raw_vcd, forbidden_tokens=sorted(forbidden), allow_partial=args.allow_partial)
    receipt = {'schema_version': 'sanitized-export-receipt-1', 'neutral_id': args.neutral_id,
               'manifest_sha256': sha((args.output/'manifest.json').read_bytes()),
               'evidence_binding_sha256': manifest['evidence_binding_sha256'],
               'full_specification_store_sha256': args.specification_sha256,
               'public_specification_sha256': manifest['specification_sha256']}
    provenance.parent.mkdir(parents=True, exist_ok=True)
    with provenance.open('xb') as stream:
        stream.write(encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
