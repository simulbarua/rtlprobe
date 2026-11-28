"""Classify the fixed FIFO checkpoint transcript without executing HDL."""

import re


CHECKPOINTS = {
    'uncommitted_hidden': ('00000000', 'tb_axis_fifo.dut.m_axis_tvalid'),
    'commit_pulse': ('00000001', 'tb_axis_fifo.dut.status_good_frame'),
    'stalled_valid': ('00000001', 'tb_axis_fifo.dut.m_axis_tvalid'),
    'stalled_data': ('000051a3', 'tb_axis_fifo.dut.m_axis_tdata'),
    'first_not_last': ('00000000', 'tb_axis_fifo.dut.m_axis_tlast'),
    'id_forwarded': ('00000039', 'tb_axis_fifo.dut.m_axis_tid'),
    'dest_forwarded': ('000000a6', 'tb_axis_fifo.dut.m_axis_tdest'),
    'user_forwarded': ('00000001', 'tb_axis_fifo.dut.m_axis_tuser'),
    'second_data': ('00000097', 'tb_axis_fifo.dut.m_axis_tdata'),
    'partial_keep': ('00000001', 'tb_axis_fifo.dut.m_axis_tkeep'),
    'final_last': ('00000001', 'tb_axis_fifo.dut.m_axis_tlast'),
    'bad_frame_pulse': ('00000001', 'tb_axis_fifo.dut.status_bad_frame'),
    'bad_frame_hidden': ('00000000', 'tb_axis_fifo.dut.m_axis_tvalid'),
    'oversize_pulse': ('00000001', 'tb_axis_fifo.dut.status_overflow'),
    'oversize_hidden': ('00000000', 'tb_axis_fifo.dut.m_axis_tvalid'),
    'rollback_recovers': ('000014d9', 'tb_axis_fifo.dut.m_axis_tdata'),
    'pause_deferred': ('00000000', 'tb_axis_fifo.dut.pause_ack'),
    'pause_at_boundary': ('00000001', 'tb_axis_fifo.dut.pause_ack'),
    'pause_valid_suppressed': ('00000000', 'tb_axis_fifo.dut.m_axis_tvalid'),
    'resume_valid': ('00000001', 'tb_axis_fifo.dut.m_axis_tvalid'),
    'reset_discards_queued': ('00000000', 'tb_axis_fifo.dut.m_axis_tvalid'),
    'reset_discards_partial': ('00000000', 'tb_axis_fifo.dut.status_depth_commit'),
    'reset_accepts_clean_frame': ('00009812', 'tb_axis_fifo.dut.m_axis_tdata'),
    'wrap_preserves_data': ('0000772c', 'tb_axis_fifo.dut.m_axis_tdata'),
}


def classify(stdout, stderr='', returncode=0, timed_out=False):
    invalid = dict(outcome='infrastructure_error', reason='incomplete_or_inconsistent_log',
                   checkpoints=[], signature=None)
    if timed_out:
        return dict(invalid, outcome='timeout_unclassified', reason='wall_clock_timeout')
    if returncode or stderr.strip():
        return dict(invalid, reason='simulator_error')
    lines = list(map(str.strip, stdout.splitlines()))
    if any(re.search(r'\b(?:error|fatal|warning)\b|\$stop', line, re.I) for line in lines):
        return dict(invalid, reason='unexpected_diagnostic')
    events = iter(line for line in lines if line.startswith('FIFO '))
    if next(events, None) != 'FIFO START v1':
        return invalid
    checks, failures = [], []
    for name, (expected, _) in CHECKPOINTS.items():
        if next(events, None) != f'FIFO BEGIN {name}':
            return invalid
        event = next(events, '')
        if event == 'FIFO ABORT input_handshake' and next(events, None) is None:
            return dict(invalid, outcome='timeout_unclassified', reason='input_handshake_cycle_limit')
        match = re.fullmatch(rf'FIFO RESULT {name} expected={expected} actual=([0-9a-f]{{8}})', event)
        if match is None:
            return invalid
        actual = match[1]
        check = dict(id=name, outcome='pass')
        if actual != expected:
            check.update(outcome='functional_fail', expected=expected, actual=actual)
            failures.append(check)
        checks.append(check)
    total = len(checks)
    if next(events, None) != f'FIFO END checked={total} mismatches={len(failures)}' or next(events, None) is not None:
        return invalid
    return dict(outcome='functional_fail' if failures else 'pass', reason='checker_completed',
                checkpoints=checks, signature=failures or None, tests_completed=total,
                comparisons_completed=total)
