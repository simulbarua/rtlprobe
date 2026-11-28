"""Pinned checker sampling adapters; source transformations only, never run."""
from decimal import Decimal, InvalidOperation
import re
from runpy import run_path
from .evidence import CODE_ROOT
from .evidence_structure import name_value
from .sv_frontend import Source, kind, ancestors

PREFIX = 'RTLPROBE_OBSERVE '
WINDOW_PREFIX = 'RTLPROBE_WINDOW '
AES_EXTENDED_TEST = 'aes_core_extended_v1'
AES_ASSERTION_TEST = 'aes_core_extended_v2'
FIFO_TEST = 'axis_fifo_frame_v1'


def fifo_checkpoints():
    return run_path(str(CODE_ROOT/'targets/axis_fifo/checker.py'))['CHECKPOINTS']


def _instrument_axis_fifo(text):
    marks = {
        '$display("FIFO BEGIN %0s", id);':
            f'$display("{WINDOW_PREFIX}checkpoint=%0s start_units=%0.17g", id, $realtime);',
        '$display("FIFO RESULT %0s expected=%08h actual=%08h", id, expected, actual);':
            f'$display("{PREFIX}checkpoint=%0s time_units=%0.17g expected=%08h actual=%08h", id, $realtime, expected, actual);',
    }
    names = list(fifo_checkpoints())
    if (names != re.findall(r'begin_check\("([a-z0-9_]+)"\);', text)
            or names != re.findall(r'check_sample\("([a-z0-9_]+)",', text)
            or any(text.count(anchor) != 1 for anchor in marks)):
        raise ValueError('FIFO sampling sites differ from the fixed checkpoint suite')
    for anchor, sample in marks.items():
        text = text.replace(anchor, anchor+'\n            '+sample)
    Source(text.encode('ascii'))
    return text, dict(schema_version='checker-observer-1', target_id='axis_fifo',
                      sampling_sites=names, window_start_sites=names,
                      edit_class='observation-only displays', checker_and_stimulus_replaced=False)


def instrument_testbench(text, target_id, *, test_id=None):
    if (target_id, test_id) == ('axis_fifo', FIFO_TEST):
        return _instrument_axis_fifo(text)
    if target_id == 'aes' and test_id in {AES_EXTENDED_TEST, AES_ASSERTION_TEST}:
        return _instrument_aes_extended(text, terminal=test_id == AES_ASSERTION_TEST)
    if target_id == 'aes':
        source = Source(text.encode('ascii'))
        names = re.findall(r"ecb_mode_single_block_test\(8'h([0-9a-f]{2}),", text)
        begins = []
        comparisons = []
        for node in source.nodes:
            task = next((p for p in ancestors(node) if kind(p) == 'TaskDeclaration'), None)
            if task is None or name_value(task.prototype.name) != 'ecb_mode_single_block_test':
                continue
            if (kind(node) == 'ExpressionStatement' and kind(node.parent) == 'SequentialBlockStatement'
                    and source.text(node) == '$display("*** TC %0d ECB mode test started.", tc_number);'):
                begins.append(source.span(node)[0])
            if (kind(node) == 'ConditionalStatement' and kind(node.parent) == 'SequentialBlockStatement'
                    and source.text(node.predicate).strip() == 'tb_result == expected'):
                comparisons.append(source.span(node)[0])
        native_dump = (
            '      $display("tb: Dumping all variables to tb_aes_core vcd file.");\n'
            '      $dumpfile("tb_aes_core.vcd");\n'
            '      $dumpvars(0, tb_aes_core);\n'
        )
        expected = [f'{n:02x}' for n in (*range(1, 11), *range(16, 26))]
        if names != expected or len(begins) != 1 or len(comparisons) != 1 or text.count(native_dump) != 1:
            raise ValueError('AES sampling or upstream waveform anchors differ from the pinned suite')
        for offset, statement in sorted([
            (begins[0], f'$display("{WINDOW_PREFIX}checkpoint=tc_%02x start_units=%0.17g", tc_number, $realtime);'),
            (comparisons[0], f'$display("{PREFIX}checkpoint=tc_%02x time_units=%0.17g expected=%032h actual=%032h", tc_number, $realtime, expected, tb_result);'),
        ], reverse=True):
            text = text[:offset] + statement + '\n     ' + text[offset:]
        text = text.replace(native_dump, '')
        Source(text.encode('ascii'))
        points = ['tc_'+name for name in names]
        return text, dict(schema_version='checker-observer-1', target_id=target_id,
                          sampling_sites=points, window_start_sites=points,
                          edit_class='sample existing comparisons and replace the competing upstream VCD writer',
                          checker_and_stimulus_replaced=False)
    if target_id == 'sha1' and 'module tb_sha1_extended;' in text:
        marks = {
            '$display("SHA1 BEGIN %0s", id);':
                f'$display("{WINDOW_PREFIX}checkpoint=%0s start_units=%0.17g", id, $realtime);',
            '$display("SHA1 DIGEST %0s expected=%040h actual=%040h", id, expected, digest);':
                f'$display("{PREFIX}checkpoint=%0s time_units=%0.17g expected=%040h actual=%040h", id, $realtime, expected, digest);',
        }
        names = re.findall(r'begin_check\("([a-z0-9_]+)"\);', text)
        if (not names or len(set(names)) != len(names)
                or names != re.findall(r'check_digest\("([a-z0-9_]+)",', text)
                or any(text.count(anchor) != 1 for anchor in marks)):
            raise ValueError('Extended SHA-1 sampling sites differ from the checked transactions')
        for anchor, sample in marks.items():
            text = text.replace(anchor, anchor+'\n      '+sample)
        Source(text.encode('ascii'))
        return text, dict(schema_version='checker-observer-1', target_id=target_id,
                          sampling_sites=names, window_start_sites=names, edit_class='observation-only displays',
                          checker_and_stimulus_replaced=False)
    digest_target = target_id in {'sha1', 'sha256'}
    digest_width = 40 if target_id == 'sha1' else 64
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
                           'issue_test': 'issue9'}.get(name) if digest_target else
                          ('ordered_core_comparison' if name == 'run_test_case' else None))
            if checkpoint:
                body = next((n for n in node.items if kind(n) == 'SequentialBlockStatement'), None)
                statements = [n for n in body.items if kind(n) != 'DataDeclaration'] if body is not None else []
                if not statements:
                    raise ValueError('checker task body is not a supported statement block')
                token = (f'checkpoint={checkpoint}' if digest_target else 'ordinal=%0d')
                arg = '' if digest_target else 'rtlprobe_observer.comparison_ordinal + 1, '
                addition = f'$display("{WINDOW_PREFIX}{token} start_units=%0.17g", {arg}$realtime);'
                edits.append((source.span(statements[0])[0], '\n'+addition+'\n'))
                window_found.append(checkpoint)
        if digest_target:
            if kind(node) == 'ConditionalStatement' and source.text(node.predicate).strip() == 'tb_digest == expected':
                checkpoint = {'single_block_test': 'tc1', 'issue_test': 'issue9'}.get(task_name)
                if checkpoint:
                    if kind(node.parent) != 'SequentialBlockStatement':
                        raise ValueError('sampling comparison must be a direct task block statement')
                    at = source.span(node)[0]
                    inserted = display(checkpoint, 'tb_digest', 'expected', digest_width)
                    found.append(checkpoint)
            elif kind(node) == 'AssignmentExpression' and task_name == 'double_block_test':
                expression = source.text(node).strip()
                for number in ((1,) if target_id == 'sha1' else (1, 2)):
                    if re.fullmatch(rf'db_digest{number}\s*=\s*tb_digest', expression):
                        if kind(node.parent.parent) != 'SequentialBlockStatement':
                            raise ValueError('sampling snapshot must be a direct task block statement')
                        at = source.span(node.parent)[1]
                        inserted = display(f'tc2_block{number}', 'tb_digest', f'expected{number}', digest_width)
                        if target_id == 'sha256' and number == 1:
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
    if target_id == 'sha1':
        expected = ['tc1', 'tc2_block1']
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


def observation_lines(stdout, checkpoints, *, permitted_memory_warnings=(), terminal=False):
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
        match = re.fullmatch(PREFIX+r'(?:checkpoint=([A-Za-z0-9_]+)|ordinal=(\d+)) time_units=([0-9.eE+\-]+) expected=([0-9a-fA-F]+) actual=([0-9a-fA-FxXzZ]+)(?: signal=(ready|result_valid))?', line)
        if not match:
            raise ValueError('malformed observer diagnostic')
        if match[6] and not terminal:
            raise ValueError('unexpected terminal observer signal')
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
        if match[6]:
            observations[-1]['signal'] = match[6]
    if terminal and (not observations or not windows or not observations[-1].get('signal')
                     or any('signal' in observation for observation in observations[:-1])):
        raise ValueError('terminal observer requires exactly one final interface sample')
    if observations and [o['checkpoint'] for o in observations] != checkpoints:
        raise ValueError('observer observations omit/reorder checker checkpoints')
    if windows and [w['checkpoint'] for w in windows] != checkpoints:
        raise ValueError('observer windows omit/reorder checker checkpoints')
    return '\n'.join(cleaned)+'\n', observations, windows


def _instrument_aes_extended(text, *, terminal=False):
    marks = {
        '$display("AES_EXT BEGIN %0s", id);':
            f'$display("{WINDOW_PREFIX}checkpoint=%0s start_units=%0.17g", id, $realtime);',
        '$display("AES_EXT RESULT %0s expected=%032h actual=%032h", id, expected, result);':
            f'$display("{PREFIX}checkpoint=%0s time_units=%0.17g expected=%032h actual=%032h", id, $realtime, expected, result);',
    }
    if terminal:
        marks['$display("AES_EXT TERMINAL %0s %0s %0s expected=%b actual=%b", active_checkpoint, phase, signal_name, expected_bit, actual_bit);'] = (
            f'$display("{PREFIX}checkpoint=%0s time_units=%0.17g expected=%b actual=%b signal=%0s", '
            'active_checkpoint, $realtime, expected_bit, actual_bit, signal_name);')
    native_dump = '  initial begin\n    $dumpfile("tb_aes_extended.vcd");\n    $dumpvars(0, tb_aes_extended);\n  end\n'
    names = re.findall(r'begin_check\("([a-z0-9_]+)"\);', text)
    if ('module tb_aes_extended;' not in text or not names or len(set(names)) != len(names)
            or names != re.findall(r'check_block\("([a-z0-9_]+)",', text)
            or text.count(native_dump) != 1 or any(text.count(anchor) != 1 for anchor in marks)):
        raise ValueError('Extended AES sampling sites differ from the checked transactions')
    text = text.replace(native_dump, '')
    for anchor, sample in marks.items():
        text = text.replace(anchor, anchor+'\n      '+sample)
    Source(text.encode('ascii'))
    return text, dict(schema_version='checker-observer-1', target_id='aes',
                      sampling_sites=names, window_start_sites=names,
                      edit_class='sample existing comparisons and replace the competing native VCD writer',
                      checker_and_stimulus_replaced=False)


def align_observations(observations, *, verdict, timebase, trace, target_id, test_id=None):
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
    fifo = (target_id, test_id) == ('axis_fifo', FIFO_TEST)
    aes_assertions = (target_id, test_id) == ('aes', AES_ASSERTION_TEST)
    if fifo:
        references = {name: signal for name, (_, signal) in fifo_checkpoints().items()}
        signals = [s for s in trace['signals'] if s['normalized_reference'] in references.values()]
    elif target_id == 'aes':
        test_top = 'tb_aes_extended' if test_id in {AES_EXTENDED_TEST, AES_ASSERTION_TEST} else 'tb_aes_core'
        ports = ('result', 'ready', 'result_valid') if aes_assertions else ('result',)
        signals = [s for s in trace['signals'] if s['normalized_reference'] in {f'{test_top}.dut.{port}' for port in ports}]
    else:
        suffix = '.digest' if target_id in {'sha1', 'sha256'} else '.data_out'
        signals = [s for s in trace['signals'] if s['normalized_reference'].endswith(suffix)]
    if not fifo and not aes_assertions and len(signals) != 1:
        raise ValueError('checker output signal is not uniquely observed')
    anchors = []
    for observed, checkpoint in zip(observations, verdict['checkpoints']):
        matches = [s for s in signals if s['normalized_reference'] == references[checkpoint['id']]] if fifo else signals
        if aes_assertions:
            port = checkpoint.get('signal', 'result')
            if observed.get('signal', 'result') != port:
                raise ValueError('observer signal differs from the AES assertion')
            matches = [s for s in signals if s['normalized_reference'] == f'{test_top}.dut.{port}']
        if len(matches) != 1:
            raise ValueError('checker output signal is not uniquely observed')
        signal = matches[0]
        digits = 8 if fifo else (signal['width']+3)//4
        if len(observed['actual']) != digits or len(observed['expected']) != digits:
            raise ValueError('observer value width differs from checker signal')
        if fifo and any(int(observed[key], 16) >= 1 << signal['width'] for key in ('expected', 'actual')):
            raise ValueError('FIFO observation exceeds its public signal width')
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


def reset_failure_window(trace, anchors, *, dut_scope, target_id=None):
    # Select the public DUT interface, independently of child aliases and labels.
    # A matching child waveform cannot substitute for a missing interface signal.
    active, inactive, port = ('1', '0', '.rst') if target_id == 'axis_fifo' else ('0', '1', '.reset_n')
    resets = [s for s in trace['signals'] if s['normalized_reference'] == dut_scope + port]
    failures = [a for a in anchors if a['outcome'] == 'functional_fail']
    window = None
    reset = {'status': 'unavailable', 'signal': None, 'asserted_tick': None, 'released_tick': None,
             'reason': ('no unique observed DUT-interface reset and subsequent failing anchor'
                        if target_id == 'axis_fifo'
                        else 'no unique observed DUT-interface active-low crypto reset and subsequent failing anchor')}
    if len(resets) == 1:
        signal = resets[0]
        asserted = next((at for at, value in signal['events'] if value == active), None)
        released = next((at for at, value in signal['events'] if asserted is not None and at >= asserted and value == inactive), None)
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
