"""Pinned crypto checker sampling adapters; source transformations only, never run."""
from decimal import Decimal, InvalidOperation
import re
from .evidence_structure import name_value
from .sv_frontend import Source, kind, ancestors

PREFIX = 'RTLPROBE_OBSERVE '
WINDOW_PREFIX = 'RTLPROBE_WINDOW '


def instrument_testbench(text, target_id):
    source = Source(text.encode('ascii'))
    edits = []
    found = []
    window_found = []
    def display(checkpoint, actual, expected, width):
        return f'$display("{PREFIX}checkpoint={checkpoint} time_units=%0.17g expected=%0{width}h actual=%0{width}h", $realtime, {expected}, {actual});'
    for node in source.nodes:
        task = next((p for p in ancestors(node) if kind(p) == 'TaskDeclaration'), None)
        task_name = name_value(task.prototype.name) if task else None
        at = None
        inserted = None
        if kind(node) == 'TaskDeclaration':
            name = name_value(node.prototype.name)
            checkpoint = ({'single_block_test': 'tc1', 'double_block_test': 'tc2_block1',
                           'issue_test': 'issue9'}.get(name) if target_id == 'sha256' else
                          ('ordered_core_comparison' if name == 'run_test_case' else None))
            if checkpoint:
                body = next((n for n in node.items if kind(n) == 'SequentialBlockStatement'), None)
                statements = [n for n in body.items if kind(n) != 'DataDeclaration'] if body is not None else []
                if not statements:
                    raise ValueError('checker task body is not a supported statement block')
                token = (f'checkpoint={checkpoint}' if target_id == 'sha256' else 'ordinal=%0d')
                arg = '' if target_id == 'sha256' else 'rtlprobe_observer.comparison_ordinal + 1, '
                addition = f'$display("{WINDOW_PREFIX}{token} start_units=%0.17g", {arg}$realtime);'
                edits.append((source.span(statements[0])[0], '\n'+addition+'\n'))
                window_found.append(checkpoint)
        if target_id == 'sha256':
            if kind(node) == 'ConditionalStatement' and source.text(node.predicate).strip() == 'tb_digest == expected':
                checkpoint = {'single_block_test': 'tc1', 'issue_test': 'issue9'}.get(task_name)
                if checkpoint:
                    if kind(node.parent) != 'SequentialBlockStatement':
                        raise ValueError('sampling comparison must be a direct task block statement')
                    at = source.span(node)[0]
                    inserted = display(checkpoint, 'tb_digest', 'expected', 64)
                    found.append(checkpoint)
            elif kind(node) == 'AssignmentExpression' and task_name == 'double_block_test':
                expression = source.text(node).strip()
                for number in (1, 2):
                    if re.fullmatch(rf'db_digest{number}\s*=\s*tb_digest', expression):
                        if kind(node.parent.parent) != 'SequentialBlockStatement':
                            raise ValueError('sampling snapshot must be a direct task block statement')
                        at = source.span(node.parent)[1]
                        inserted = display(f'tc2_block{number}', 'tb_digest', f'expected{number}', 64)
                        if number == 1:
                            inserted += f'\n$display("{WINDOW_PREFIX}checkpoint=tc2_block2 start_units=%0.17g", $realtime);'
                            window_found.append('tc2_block2')
                        found.append(f'tc2_block{number}')
        elif target_id == 'chacha':
            if (kind(node) == 'ConditionalStatement' and task_name == 'run_test_case'
                    and source.text(node.predicate).strip() == 'tb_core_data_out == expected'):
                if kind(node.parent) != 'SequentialBlockStatement':
                    raise ValueError('sampling comparison must be a direct task block statement')
                at = source.span(node)[0]
                inserted = ('rtlprobe_observer.comparison_ordinal = rtlprobe_observer.comparison_ordinal + 1;\n'
                            f'$display("{PREFIX}ordinal=%0d time_units=%0.17g expected=%0128h actual=%0128h", '
                            'rtlprobe_observer.comparison_ordinal, $realtime, expected, tb_core_data_out);')
                found.append('ordered_core_comparison')
        else:
            raise ValueError('no observational checker adapter for this target')
        if at is not None:
            edits.append((at, '\n' + inserted + '\n'))
    expected = ['tc1', 'tc2_block1', 'tc2_block2', 'issue9'] if target_id == 'sha256' else ['ordered_core_comparison']
    if sorted(found) != sorted(expected) or sorted(window_found) != sorted(expected):
        raise ValueError('existing checker sampling sites do not match the bounded crypto adapter')
    changed = text
    for offset, addition in sorted(edits, reverse=True):
        changed = changed[:offset] + addition + changed[offset:]
    Source(changed.encode('ascii'))
    return changed, {'schema_version': 'checker-observer-1', 'target_id': target_id,
                     'sampling_sites': found, 'window_start_sites': window_found,
                     'edit_class': 'observation-only displays and observer-local ordinal',
                     'checker_and_stimulus_replaced': False}


def compiled_timebase(vvp_text, test_top):
    escaped = re.escape(test_top)
    matches = re.findall(r'\.scope module, "'+escaped+r'"[^\n]*\n\s*\.timescale (-?\d+) (-?\d+);', vvp_text)
    if len(matches) != 1:
        raise ValueError('compiled testbench timebase is missing or ambiguous')
    unit, precision = map(int, matches[0])
    if not -15 <= precision <= unit <= 0:
        raise ValueError('unsupported compiled timebase')
    return {'time_unit_exponent': unit, 'time_precision_exponent': precision,
            'source': 'Icarus compiled testbench scope; no inferred physical unit'}


def observation_lines(stdout, checkpoints, *, permitted_memory_warnings=()):
    cleaned, observations, windows = [], [], []
    for line in stdout.splitlines():
        if line in permitted_memory_warnings:
            continue
        if line.startswith(WINDOW_PREFIX):
            match = re.fullmatch(WINDOW_PREFIX+r'(?:checkpoint=([A-Za-z0-9_]+)|ordinal=(\d+)) start_units=([0-9.eE+\-]+)', line)
            if not match:
                raise ValueError('malformed observer window diagnostic')
            checkpoint = match[1]
            if match[2]:
                ordinal = int(match[2])
                if not 1 <= ordinal <= len(checkpoints):
                    raise ValueError('observer window ordinal outside suite')
                checkpoint = checkpoints[ordinal-1]
            windows.append({'checkpoint': checkpoint, 'start_units': match[3]})
            continue
        if not line.startswith(PREFIX):
            if line != 'VCD info: dumpfile buggy.vcd opened for output.':
                cleaned.append(line)
            continue
        match = re.fullmatch(PREFIX+r'(?:checkpoint=([A-Za-z0-9_]+)|ordinal=(\d+)) time_units=([0-9.eE+\-]+) expected=([0-9a-fA-F]+) actual=([0-9a-fA-FxXzZ]+)', line)
        if not match:
            raise ValueError('malformed observer diagnostic')
        checkpoint = match[1]
        if match[2]:
            ordinal = int(match[2])
            if not 1 <= ordinal <= len(checkpoints):
                raise ValueError('observer ordinal outside declared checker suite')
            checkpoint = checkpoints[ordinal-1]
        try:
            time = Decimal(match[3])
            if not time.is_finite() or time < 0 or time > Decimal('1e30'):
                raise ValueError('invalid observer timestamp')
        except InvalidOperation as error:
            raise ValueError('invalid observer timestamp') from error
        observations.append({'checkpoint': checkpoint, 'time_units': match[3],
                             'expected': match[4].lower(), 'actual': match[5].lower()})
    if observations and [o['checkpoint'] for o in observations] != checkpoints:
        raise ValueError('observer observations omit/reorder checker checkpoints')
    if windows and [w['checkpoint'] for w in windows] != checkpoints:
        raise ValueError('observer windows omit/reorder checker checkpoints')
    return '\n'.join(cleaned)+'\n', observations, windows


def align_observations(observations, *, verdict, timebase, trace, target_id):
    if not observations or timebase is None:
        return []
    if set(timebase) != {'time_unit_exponent', 'time_precision_exponent', 'source'}:
        raise ValueError('unexpected timebase fields')
    unit, precision = timebase['time_unit_exponent'], timebase['time_precision_exponent']
    if (type(unit) is not int or type(precision) is not int or not -15 <= precision <= unit <= 0
            or timebase['source'] != 'Icarus compiled testbench scope; no inferred physical unit'):
        raise ValueError('unverified timebase representation')
    if Decimal(trace['tick_seconds']) > Decimal(10)**precision:
        raise ValueError('VCD resolution is coarser than the compiled testbench precision')
    suffix = '.digest' if target_id == 'sha256' else '.data_out'
    signals = [s for s in trace['signals'] if s['normalized_reference'].endswith(suffix)]
    if len(signals) != 1:
        raise ValueError('checker output signal is not uniquely observed')
    signal = signals[0]
    anchors = []
    for observed, checkpoint in zip(observations, verdict['checkpoints']):
        digits = (signal['width']+3)//4
        if len(observed['actual']) != digits or len(observed['expected']) != digits:
            raise ValueError('observer value width differs from checker signal')
        ticks = Decimal(observed['time_units']) * Decimal(10)**unit / Decimal(trace['tick_seconds'])
        tick = int(ticks.to_integral_value())
        if abs(ticks-Decimal(tick)) > Decimal('0.00001') or not trace['capture_start_tick'] <= tick <= trace['capture_end_tick']:
            raise ValueError('checker observation does not align with captured VCD ticks')
        events = [value for at, value in signal['events'] if at <= tick]
        if not events:
            raise ValueError('no waveform value at checker observation')
        bits = events[-1]
        bits = bits.rjust(signal['width'], bits[0] if bits[0] in 'xz' else '0')
        actual = ''.join(c*4 if c in 'xz' else format(int(c,16),'04b') for c in observed['actual'])
        if bits != actual[-signal['width']:].rjust(signal['width'], '0'):
            raise ValueError('checker actual observation disagrees with captured waveform')
        failed = observed['actual'] != observed['expected']
        if failed != (checkpoint['outcome'] == 'functional_fail'):
            raise ValueError('observer comparison disagrees with unchanged checker verdict')
        if failed and (checkpoint['actual'] != observed['actual'] or checkpoint['expected'] != observed['expected']):
            raise ValueError('observer values disagree with checker failure signature')
        anchors.append({**observed, 'signal': signal['normalized_reference'], 'tick': tick,
                        'outcome': checkpoint['outcome'], 'value_match': 'matched'})
    return anchors


def reset_failure_window(trace, anchors):
    resets = [s for s in trace['signals'] if s['normalized_reference'].endswith('.reset_n')]
    failures = [a for a in anchors if a['outcome'] == 'functional_fail']
    window = None
    reset = {'status': 'unavailable', 'signal': None, 'asserted_tick': None, 'released_tick': None,
             'reason': 'no unique observed active-low crypto reset and subsequent failing anchor'}
    if len(resets) == 1:
        signal = resets[0]
        asserted = next((at for at, value in signal['events'] if value == '0'), None)
        released = next((at for at, value in signal['events'] if asserted is not None and at >= asserted and value == '1'), None)
        if asserted is not None and released is not None:
            reset = {'status': 'observed', 'signal': signal['normalized_reference'], 'asserted_tick': asserted,
                     'released_tick': released, 'reason': None}
            if failures and failures[0]['tick'] >= released:
                window = {'start_tick': asserted, 'end_tick': failures[0]['tick'],
                          'selection': 'observed reset through first unchanged-checker failure; no hidden-site input'}
    return reset, window


def align_test_windows(windows, anchors, timebase, trace):
    if not windows or not anchors or timebase is None:
        return []
    result = []
    for start, end in zip(windows, anchors):
        time = Decimal(start['start_units'])
        if not time.is_finite() or time < 0 or time > Decimal('1e30'):
            raise ValueError('invalid checker window timestamp')
        value = time * Decimal(10)**timebase['time_unit_exponent'] / Decimal(trace['tick_seconds'])
        tick = int(value.to_integral_value())
        if (not value.is_finite() or abs(value-Decimal(tick)) > Decimal('0.00001')
                or tick < trace['capture_start_tick'] or tick > end['tick']):
            raise ValueError('checker task window does not align with its captured comparison')
        result.append({'checkpoint': start['checkpoint'], 'start_tick': tick,
                       'end_tick': end['tick'], 'outcome': end['outcome']})
    return result
