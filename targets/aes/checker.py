"""Classify the unmodified secworks AES core testbench transcript."""

import re

PLAINTEXT = (
    '6bc1bee22e409f96e93d7e117393172a', 'ae2d8a571e03ac9c9eb76fac45af8e51',
    '30c81c46a35ce411e5fbc1191a0a52ef', 'f69f2445df4f9b17ad2b417be66c3710',
    '00112233445566778899aabbccddeeff',
)
CIPHERTEXT = {
    128: ('3ad77bb40d7a3660a89ecaf32466ef97', 'f5d3d58503b9699de785895a96fdbaaf',
          '43b1cd7f598ece23881b00e3ed030688', '7b0c785e27e8ad3f8223207104725dd4',
          '69c4e0d86a7b0430d8cdb78070b4c55a'),
    256: ('f3eed1bdb5d2a03c064b5a7e3db181f8', '591ccb10d410ed26dc5ba74a31362870',
          'b6ed21b99ca6f4f9f153e7b1beafed1d', '23304b7a39f9f3ff067d8d8f9e24ecc7',
          '8ea2b7ca516745bfeafc49904b496089'),
}
START = '-= Testbench for aes core started =-'
END = '-= Testbench for aes core cmpleted =-'
RESET = '*** Toggle reset.'
KEY_READY = 'Key expansion done'
KEY_GROUPS = {128: range(1, 11), 256: range(16, 26)}


def expected_results(key_bits):
    ciphertext = CIPHERTEXT[key_bits]
    return (*ciphertext[:4], *PLAINTEXT[:4], ciphertext[4], PLAINTEXT[4])


def classify(stdout, stderr='', returncode=0, timed_out=False):
    invalid = dict(outcome='infrastructure_error', reason='incomplete_or_inconsistent_log',
                   checkpoints=[], signature=None)
    if timed_out:
        return dict(invalid, outcome='timeout_unclassified', reason='wall_clock_timeout')
    if returncode or stderr.strip():
        return dict(invalid, reason='simulator_error')
    events = []
    for line in map(str.strip, stdout.splitlines()):
        if line in (START, END, KEY_READY) or line.startswith(('***', 'ECB ', 'Expected:', 'Got:')):
            events.append(line)
        elif re.search(r'\b(?:error|fatal|warning)\b|\$stop', line, re.I):
            return dict(invalid, reason='unexpected_diagnostic')
    stream = iter(events)

    def need(message):
        if next(stream, None) != message:
            raise ValueError('Unexpected AES checker event')

    checks, failures = [], []
    try:
        need(START)
        need(RESET)
        for key_bits, tests in KEY_GROUPS.items():
            need(f'ECB {key_bits} bit key tests')
            for number, expected in zip(tests, expected_results(key_bits), strict=True):
                need(f'*** TC {number} ECB mode test started.')
                need(KEY_READY)
                check = dict(id=f'tc_{number:02x}', outcome='pass')
                verdict = next(stream, None)
                if verdict == f'*** ERROR: TC {number} NOT successful.':
                    need('Expected: 0x' + expected)
                    actual = re.fullmatch(r'Got:\s+0x([a-fA-F0-9]{32})', next(stream, ''))
                    if actual is None or actual[1].lower() == expected:
                        return invalid
                    check.update(outcome='functional_fail', expected=expected, actual=actual[1].lower())
                    failures.append(check)
                elif verdict != f'*** TC {number} successful.':
                    return invalid
                checks.append(check)
        total = len(checks)
        if failures:
            need(f'*** {total:02d} tests completed - {len(failures):02d} test cases did not complete successfully.')
        else:
            need(f'*** All {total:02d} test cases completed successfully')
        need(END)
        if next(stream, None) is not None:
            return invalid
    except ValueError:
        return invalid
    return dict(outcome='functional_fail' if failures else 'pass', reason='checker_completed',
                checkpoints=checks, signature=failures or None, tests_completed=total,
                comparisons_completed=total)
