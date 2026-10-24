"""Strict UVM completion and failure provenance; no exit-code-only verdicts."""
import re


def failure(line):
    # Both Verilator's compact formatter and ordinary UVM file(line) format.
    compact = re.match(r'UVM_(ERROR|FATAL)\s+@\s*(.*?)\s*:\s*\((.*?):(\d+)\)\s*(.*?)\s*\[([^]]+)\]\s*(.*)', line)
    normal = re.match(r'UVM_(ERROR|FATAL)\s+(.*?)\((\d+)\)\s*@\s*(.*?)\s*:\s*(.*?)\s*\[([^]]+)\]\s*(.*)', line)
    if compact:
        severity, time, file, number, component, report_id, message = compact.groups()
    elif normal:
        severity, file, number, time, component, report_id, message = normal.groups()
    else:
        return {'id': 'uvm_checks', 'outcome': 'functional_fail', 'source': 'other',
                'file': None, 'line': None, 'simulation_time': None, 'report_id': None,
                'message': line, 'expected': None, 'actual': None, 'raw': line}
    source = 'other'
    expected_left = None
    base = file.rsplit('/', 1)[-1]
    if base.endswith('_scoreboard.sv'):
        source = 'scoreboard_check'
        if 'get_mirrored_value() == item.d_data' in message:
            expected_left = True
    elif base == 'cip_base_vseq.sv' and any(expression in message for expression in
            ('masked_data == exp_data', 'rsp.d_error == exp_err_rsp')):
        source, expected_left = 'sequence_tl_compare', False
    elif ((base == 'uart_smoke_vseq.sv' and 'rx_byte == dut_rdata' in message) or
          (base == 'cip_base_vseq.sv' and 'exp_val == act_val' in message)):
        source, expected_left = 'register_model_read_compare', True
    elif base == 'uart_base_vseq.sv' and 'rdata == exp_data' in message:
        source, expected_left = 'register_model_read_compare', False
    elif base == 'cip_base_vseq.sv' and 'data & ~ro_mask == 0' in message:
        source, expected_left = 'register_model_read_compare', False
    elif base == 'csr_utils_pkg.sv' and ('obs' in message or 'csr_rd_check' in component):
        source = 'register_model_read_compare'
    if expected_left is None:
        expression = message.split('Check failed ', 1)[-1].split(' (', 1)[0]
        sides = re.split(r' ===? ', expression)
        if len(sides) == 2:
            expected_side = [bool(re.search(r'exp|predict|mirrored|gmv', side, re.I)) for side in sides]
            if expected_side.count(True) == 1:
                expected_left = expected_side[0]
            elif sides[1].strip() in ('0', '1', "'0", "'1"):
                expected_left = False
    # Preserve both operands even when their expected/actual orientation is unknown.
    values = re.search(r'\(([^()]*)\s+vs\s+([^()]*)\)', message)
    operands = list(values.groups()) if values else None
    expected = actual = None
    if operands and expected_left is not None:
        normalized = []
        for v in operands:
            hex_value = re.search(r'\[(0x[0-9a-fA-FxXzZ]+)\]', v)
            normalized.append(hex_value[1].lower() if hex_value else v.strip())
        expected, actual = normalized if expected_left else normalized[::-1]
    # csr_rd_check formats exp/obs separately rather than using DV_CHECK_EQ.
    if source == 'register_model_read_compare' and expected is None:
        exp = re.search(r'\bexp(?:ected)?\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)', message)
        obs = re.search(r'\bobs(?:erved)?\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)', message)
        expected, actual = exp[1] if exp else None, obs[1] if obs else None
    return {'id': 'uvm_checks', 'outcome': 'functional_fail', 'severity': severity,
            'source': source, 'file': file, 'line': int(number), 'simulation_time': time.strip(),
            'report_id': report_id, 'component': component.strip(), 'message': message,
            'expected': expected, 'actual': actual, 'operands': operands, 'raw': line}


def classify(stdout, stderr='', returncode=0, timed_out=False, *, test=None, design=None):
    result = {'outcome': 'infrastructure_error', 'reason': 'incomplete_or_inconsistent_log',
              'signature': None, 'checkpoints': [], 'failures': []}
    if timed_out:
        return dict(result, outcome='timeout_unclassified', reason='wall_clock_timeout')
    lines = stdout.splitlines()
    result['failures'] = [failure(s) for s in lines if re.match(r'^UVM_(ERROR|FATAL)\s+(?!\s*:)', s)]
    verdicts = [(i, s.strip()) for i, s in enumerate(lines) if s.strip() in ('TEST PASSED CHECKS', 'TEST FAILED CHECKS')]
    summaries = [i for i, s in enumerate(lines) if s.strip() == '--- UVM Report Summary ---']
    finishes = [i for i, s in enumerate(lines) if re.match(r'^- .*:\d+: Verilog \$finish$', s)]
    if len(verdicts) != 1 or len(summaries) != 1 or len(finishes) != 1:
        return result
    if not summaries[0] < verdicts[0][0] < finishes[0]:
        return result
    counts = {}
    for severity in ('INFO', 'WARNING', 'ERROR', 'FATAL'):
        entries = re.findall(r'^UVM_'+severity+r'\s*:\s*(\d+)\s*$', stdout, re.M)
        if len(entries) != 1:
            return result
        counts[severity] = int(entries[0])
    result['report_counts'] = counts
    if counts['ERROR'] + counts['FATAL'] != len(result['failures']):
        return result
    bad = bool(result['failures'])
    if (verdicts[0][1] == 'TEST FAILED CHECKS') != bad:
        return result
    if returncode or stderr.strip() or re.search(r'^%Error', stdout, re.M):
        return dict(result, reason='simulator_error')
    iterations = None
    if test is not None:
        if len(re.findall(r'\[RNTST\] Running test '+re.escape(design)+r'_base_test\.\.\.', stdout)) != 1:
            return dict(result, reason='wrong_or_missing_test_start')
        relevant = '\n'.join(s for s in lines if '['+'uvm_test_top.env.virtual_sequencer.'+test['sequence']+']' in s)
        hits = re.findall(test['completion_pattern'], relevant)
        if not bad:
            if not hits:
                return dict(result, reason='missing_test_checkpoints')
            total = int(hits[0][1])
            if total < 1 or [(int(i),int(n)) for i,n in hits] != [(i,total) for i in range(1,total+1)]:
                return dict(result, reason='incomplete_test_checkpoints')
        iterations = [list(map(int, hit)) for hit in hits]
    check = result['failures'][0] if bad else {'id': 'uvm_checks', 'outcome': 'pass'}
    return dict(result, outcome='functional_fail' if bad else 'pass', reason='checker_completed',
                signature=[check] if bad else None, checkpoints=[check], comparisons_completed=None,
                completion={'summary': True, 'verdict': verdicts[0][1], 'finish': True, 'iterations': iterations})
