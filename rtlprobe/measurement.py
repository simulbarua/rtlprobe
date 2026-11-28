"""Opt-in serial-process measurements; never an authorization or resource limit.

CPU deltas cover this process and reaped children, not Docker daemon descendants.
Nested spans are inclusive; summarize() subtracts direct children exactly once.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import resource
import sys
import time
import uuid

_active = ContextVar('rtlprobe_measurement', default=None)


def _sample():
    own = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    scale = 1 if sys.platform == 'darwin' else 1024
    return dict(monotonic_ns=time.monotonic_ns(), self_cpu=own.ru_utime+own.ru_stime,
                child_cpu=child.ru_utime+child.ru_stime,
                self_peak_rss_bytes=own.ru_maxrss*scale,
                reaped_child_max_rss_bytes=child.ru_maxrss*scale,
                io_in_blocks=own.ru_inblock+child.ru_inblock,
                io_out_blocks=own.ru_oublock+child.ru_oublock)


class Recorder:
    def __init__(self, directory, metadata):
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory/(uuid.uuid4().hex+'.jsonl')
        self.stream = self.path.open('x', encoding='utf-8')
        os.chmod(self.path, 0o600)
        self.stack = []
        self.contexts = []
        self.sequence = 0
        self.failed = False
        self.emit(dict(event='session', schema='rtlprobe-serial-measurement-1',
                       pid=os.getpid(), platform=sys.platform, logical_cpus=os.cpu_count(),
                       started_at=datetime.now(timezone.utc).isoformat(), metadata=metadata,
                       cpu_scope='self and reaped children; excludes Docker daemon work',
                       memory_scope='lifetime high-water marks; not concurrent tree peak'))

    def emit(self, event):
        if self.failed:
            return
        try:
            self.stream.write(json.dumps(event, sort_keys=True)+'\n')
            self.stream.flush()
        except (OSError, ValueError):
            self.failed = True
            print('RTLProbe measurement unavailable; execution policy is unchanged.', file=sys.stderr)


@contextmanager
def session(directory, **metadata):
    """Use an external directory. Telemetry failures must not interrupt a case."""
    if not directory or _active.get() is not None:
        yield
        return
    try:
        recorder = Recorder(directory, metadata)
    except (OSError, ValueError):
        print('RTLProbe measurement could not open its output directory.', file=sys.stderr)
        yield
        return
    token = _active.set(recorder)
    try:
        with span('session', 'unattributed'):
            yield
    finally:
        _active.reset(token)
        try:
            recorder.stream.close()
        except OSError:
            pass


@contextmanager
def span(name, category, **attributes):
    recorder = _active.get()
    if recorder is None or recorder.failed:
        yield
        return
    recorder.sequence += 1
    ident = recorder.sequence
    parent = recorder.stack[-1] if recorder.stack else None
    attributes = {**(recorder.contexts[-1] if recorder.contexts else {}), **attributes}
    start = _sample()
    recorder.emit(dict(event='start', id=ident, parent=parent, name=name,
                       category=category, attributes=attributes, sample=start))
    recorder.stack.append(ident)
    recorder.contexts.append(attributes)
    outcome = 'complete'
    try:
        yield
    except BaseException:
        outcome = 'error'
        raise
    finally:
        end = _sample()
        recorder.stack.pop()
        recorder.contexts.pop()
        recorder.emit(dict(event='end', id=ident, outcome=outcome, sample=end))


def measured(category, name=None):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with span(name or function.__qualname__, category):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def command_category(name):
    if name in {'original', 'control', 'restored', 'mutant_1', 'mutant_2', 'mutant_3',
                'plain_buggy_run', 'observed_buggy_run'}:
        return 'simulation'
    if 'compile' in name or 'lint' in name or 'synthesis' in name:
        return 'compile_lint_synthesis'
    return 'tool_other'


def disk_snapshot(path, **attributes):
    """Logical regular-file bytes at a boundary, not peak disk or allocated bytes."""
    recorder = _active.get()
    if recorder is None or recorder.failed:
        return
    with span('output_disk_inventory', 'measurement_overhead'):
        try:
            if not Path(path).is_dir():
                raise FileNotFoundError(path)
            count = size = 0
            for directory, _, names in os.walk(path, followlinks=False):
                for name in names:
                    item = Path(directory)/name
                    if item.is_file() and not item.is_symlink():
                        size += item.stat().st_size
                        count += 1
            recorder.emit(dict(event='disk', path=str(path), logical_bytes=size, files=count,
                               attributes=attributes, monotonic_ns=time.monotonic_ns()))
        except OSError:
            recorder.emit(dict(event='disk', path=str(path), logical_bytes=None,
                               attributes=attributes, error='inventory_unavailable'))


def summarize(events):
    """Strict tree validation; partial/crashed traces cannot satisfy coverage."""
    events = list(events)
    starts, ends, stack = {}, {}, []
    for event in events:
        if event['event'] == 'start':
            ident = event['id']
            if ident in starts or event['parent'] != (stack[-1] if stack else None):
                raise ValueError('Invalid measurement nesting or duplicate span')
            starts[ident] = event
            stack.append(ident)
        elif event['event'] == 'end':
            ident = event['id']
            if not stack or stack.pop() != ident or ident in ends:
                raise ValueError('Invalid measurement completion')
            ends[ident] = event
    incomplete = sorted(set(starts)-set(ends))
    if incomplete:
        return dict(complete=False, incomplete_spans=incomplete, coverage=None)
    totals, exclusive, categories, cases = {}, {}, {}, {}
    for ident, start in starts.items():
        a, b = start['sample'], ends[ident]['sample']
        values = dict(elapsed_seconds=(b['monotonic_ns']-a['monotonic_ns'])/1e9,
                      self_cpu_seconds=b['self_cpu']-a['self_cpu'],
                      child_cpu_seconds=b['child_cpu']-a['child_cpu'])
        if any(v < -1e-9 for v in values.values()):
            raise ValueError('Measurement counters decreased')
        totals[ident] = values
        exclusive[ident] = values.copy()
    for ident, start in starts.items():
        if start['parent'] is not None:
            parent = start['parent']
            if (start['sample']['monotonic_ns'] < starts[parent]['sample']['monotonic_ns'] or
                    ends[ident]['sample']['monotonic_ns'] > ends[parent]['sample']['monotonic_ns']):
                raise ValueError('Measurement child outside parent')
            for key, value in totals[ident].items():
                exclusive[parent][key] -= value
    for ident, values in exclusive.items():
        category = starts[ident]['category']
        dest = categories.setdefault(category, dict.fromkeys(values, 0.0))
        for key, value in values.items():
            if value < -1e-6:
                raise ValueError('Measurement children exceed parent')
            dest[key] += max(0, value)
        case_id = starts[ident]['attributes'].get('case_id')
        if case_id:
            dest = cases.setdefault(case_id, {}).setdefault(category, dict.fromkeys(values, 0.0))
            for key, value in values.items():
                dest[key] += max(0, value)
    roots = [ident for ident, s in starts.items() if s['parent'] is None]
    if len(roots) != 1:
        raise ValueError('Expected one measurement session')
    total = totals[roots[0]]
    unknown = categories.get('unattributed', {}).get('elapsed_seconds', 0)
    by_case = {}
    for cid, groups in cases.items():
        wall = sum(v['elapsed_seconds'] for v in groups.values())
        gap = groups.get('unattributed', {}).get('elapsed_seconds', 0)
        by_case[cid] = dict(categories=groups, elapsed_seconds=wall, coverage=1-gap/wall if wall else None)
    model = [i for i, s in starts.items() if s['category'] == 'model_submission_wait']
    return dict(complete=True, total=total, categories=categories, cases=by_case,
                metadata=[e for e in events if e['event'] == 'session'],
                model_transport_attempts=len(model),
                model_transport_completed=sum(ends[i]['outcome'] == 'complete' for i in model),
                output_disk_snapshots=[e for e in events if e['event'] == 'disk'],
                coverage=1-unknown/total['elapsed_seconds'] if total['elapsed_seconds'] else None,
                self_peak_rss_bytes=max(e['sample']['self_peak_rss_bytes'] for e in ends.values()),
                reaped_child_max_rss_bytes=max(e['sample']['reaped_child_max_rss_bytes'] for e in ends.values()),
                spans=[dict(id=i, name=s['name'], category=s['category'], attributes=s['attributes'],
                            inclusive=totals[i], exclusive=exclusive[i], outcome=ends[i]['outcome'])
                       for i, s in starts.items()])
