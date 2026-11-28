"""Strict transcript adapter for the RTLProbe AES extended core testbench."""

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

PROTOCOL_PHASE = ('before_init|before_next|init_accepted|next_accepted|while_busy|completion|'
                  'before_busy_reset|reset_asserted|reset_held|after_reset')
PROTOCOL_ABORT = re.compile(rf'AES_EXT ABORT protocol ({PROTOCOL_PHASE}) ready=[01xz] valid=[01xz]')


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
    if next(stream, None) != 'AES_EXT START v1':
        return invalid

    checks, failures = [], []
    for name, expected in EXPECTED.items():
        if next(stream, None) != f'AES_EXT BEGIN {name}':
            return invalid
        event = next(stream, '')
        if event.startswith('AES_EXT ABORT'):
            if next(stream, None) is not None:
                return invalid
            if event in {'AES_EXT ABORT timeout 0', 'AES_EXT ABORT timeout 1'}:
                return dict(invalid, outcome='timeout_unclassified', reason='transaction_cycle_limit')
            protocol = PROTOCOL_ABORT.fullmatch(event)
            return dict(invalid, reason='protocol_'+protocol[1]) if protocol else invalid
        match = re.fullmatch(rf'AES_EXT RESULT {name} expected={expected} actual=([0-9a-fxXzZ]{{32}})', event)
        if match is None:
            return invalid
        actual = match[1].lower()
        if 'x' in actual or 'z' in actual:
            return dict(invalid, reason='unknown_block_result')
        checkpoint = dict(id=name, outcome='pass')
        if actual != expected:
            checkpoint.update(outcome='functional_fail', expected=expected, actual=actual)
            failures.append(checkpoint)
        checks.append(checkpoint)

    total = len(checks)
    if next(stream, None) != f'AES_EXT END checked={total} mismatches={len(failures)}' or next(stream, None) is not None:
        return invalid
    return dict(outcome='functional_fail' if failures else 'pass', reason='checker_completed',
                checkpoints=checks, signature=failures or None, tests_completed=total,
                comparisons_completed=total)
