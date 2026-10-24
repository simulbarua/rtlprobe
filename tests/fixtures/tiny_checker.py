"""Strict checker for synthetic integration fixtures, never benchmark evidence."""
import re


def classify(stdout, stderr='', returncode=0, timed_out=False):
    result = dict(outcome='infrastructure_error', reason='incomplete_or_inconsistent_log', signature=None, checkpoints=[])
    if timed_out:
        return dict(result, outcome='timeout_unclassified', reason='wall_clock_timeout')
    if returncode != 0 or stderr.strip():
        return result
    lines = stdout.strip().splitlines()
    if lines and re.fullmatch(r'tb\.v:\d+: \$finish called at \d+ \(\d+[a-z]+\)', lines[-1]):
        lines.pop()
    if len(lines) != 4 or lines[0] != 'BEGIN' or lines[-1] != 'END':
        return result
    if lines[1] == 'CHECK PASS' and lines[2] == 'SUMMARY errors=0':
        return dict(result, outcome='pass', reason='checker_completed', checkpoints=[dict(id='sum', outcome='pass')])
    match = re.fullmatch(r'CHECK FAIL expected=([0-9a-f]{8}) actual=([0-9a-fxz]{8})', lines[1])
    if not match or match[1] == match[2] or lines[2] != 'SUMMARY errors=1':
        return result
    check = dict(id='sum', outcome='functional_fail', expected=match[1], actual=match[2])
    return dict(result, outcome='functional_fail', reason='checker_completed', checkpoints=[check], signature=[check])
