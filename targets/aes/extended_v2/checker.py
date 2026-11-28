"""Classify complete AES v2 transcripts and explicit terminal assertions."""

import re


EXPECTED = {
    'key128_encrypt_first': '3ad77bb40d7a3660a89ecaf32466ef97',
    'key128_reuse_decrypt': 'ae2d8a571e03ac9c9eb76fac45af8e51',
    'key128_reuse_encrypt': '43b1cd7f598ece23881b00e3ed030688',
    'key128_reuse_decrypt_again': '6bc1bee22e409f96e93d7e117393172a',
    'rekey_128_to_256': 'f3eed1bdb5d2a03c064b5a7e3db181f8',
    'key256_reuse_decrypt': 'ae2d8a571e03ac9c9eb76fac45af8e51',
    'key256_reuse_encrypt': 'b6ed21b99ca6f4f9f153e7b1beafed1d',
    'rekey_256_to_128': '00112233445566778899aabbccddeeff',
    'reset_during_key_expansion': 'f5d3d58503b9699de785895a96fdbaaf',
    'reset_during_block': '30c81c46a35ce411e5fbc1191a0a52ef',
}

CYCLE_LIMITS = {'key_expansion_cycle_limit', 'block_cycle_limit'}
PHASES = {
    'ready': {'before_init': '1', 'before_next': '1', 'init_accepted': '0',
              'next_accepted': '0', 'while_busy': '0', 'completion': '1', 'before_busy_reset': '0',
              'reset_asserted': '1', 'reset_held': '1', 'after_reset': '1'},
    'result_valid': {'init_accepted': '0', 'next_accepted': '0', 'while_busy': '0', 'completion': '01',
                     'before_busy_reset': '0', 'reset_asserted': '0', 'reset_held': '0', 'after_reset': '0'},
}
TERMINAL = re.compile(r'AES_EXT TERMINAL (\w+) (\w+) (ready|result_valid) expected=([01]) actual=([01xz])')


def classify(stdout, stderr='', returncode=0, timed_out=False):
    invalid = dict(outcome='infrastructure_error', reason='incomplete_or_inconsistent_log',
                   checkpoints=[], signature=None)
    if timed_out:
        return dict(invalid, outcome='timeout_unclassified', reason='wall_clock_timeout')
    if returncode or stderr.strip():
        return dict(invalid, reason='simulator_error')
    events = []
    for line in map(str.strip, stdout.splitlines()):
        if line.startswith('AES_EXT'):
            events.append(line)
        elif re.search(r'\b(?:error|fatal|warning)\b|\$stop', line, re.I):
            return dict(invalid, reason='unexpected_diagnostic')
    stream = iter(events)
    if next(stream, None) != 'AES_EXT START v2':
        return invalid

    checks, failures = [], []
    for name, expected in EXPECTED.items():
        if next(stream, None) != f'AES_EXT BEGIN {name}':
            return invalid
        event = next(stream, '')
        if terminal := TERMINAL.fullmatch(event):
            checkpoint, phase, signal, wanted, observed = terminal.groups()
            cycle_limit = phase in CYCLE_LIMITS
            allowed = ((signal, wanted, observed) == ('ready', '1', '0') if cycle_limit
                       else wanted in PHASES[signal].get(phase, []) and wanted != observed)
            if (checkpoint != name or not allowed
                    or next(stream, None) != f'AES_EXT STOP checked={len(checks)} mismatches={len(failures)}'
                    or next(stream, None) is not None):
                return invalid
            failure = dict(id=name, outcome='functional_fail', expected=wanted, actual=observed, signal=signal,
                           phase=phase, failure_kind='transaction_cycle_limit' if cycle_limit else 'protocol')
            return dict(outcome='functional_fail', reason='checker_terminal_failure', terminal_failure=True,
                        checkpoints=[*checks, failure], signature=[*failures, failure],
                        tests_completed=len(checks)+1, comparisons_completed=len(checks))
        result = re.fullmatch(rf'AES_EXT RESULT {name} expected={expected} actual=([0-9a-fxXzZ]{{32}})', event)
        if result is None:
            return invalid
        actual = result[1].lower()
        check = dict(id=name, outcome='pass')
        if actual != expected:
            kind = 'unknown_block_result' if 'x' in actual or 'z' in actual else 'block_mismatch'
            check.update(outcome='functional_fail', expected=expected, actual=actual, failure_kind=kind)
            failures.append(check)
        checks.append(check)

    total = len(checks)
    if next(stream, None) != f'AES_EXT END checked={total} mismatches={len(failures)}' or next(stream, None) is not None:
        return invalid
    return dict(outcome='functional_fail' if failures else 'pass', reason='checker_completed',
                checkpoints=checks, signature=failures or None, tests_completed=total, comparisons_completed=total)
