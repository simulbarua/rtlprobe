"""Reject incomplete or contradictory upstream ChaCha checker evidence."""
from pathlib import Path
import runpy
import unittest

ADAPTER = runpy.run_path(str(Path(__file__).resolve().parents[1]/'targets/chacha/checker.py'))
CASES, classify = ADAPTER['CASES'], ADAPTER['classify']


def transcript(failed=()):
    lines = ['-- Testbench for chacha_core started --']
    for i, case in enumerate(CASES):
        label = case['printed_label']
        lines.append(f'*** TC {label} started.')
        if i in failed:
            lines.extend([f'*** ERROR: TC {label} not successful', 'Expected: 0x'+case['expected'],
                          'Got:      0x'+format(int(case['expected'],16)^1, '0128x')])
        else:
            lines.append(f'*** TC {label} successful')
    lines.append('*** chacha_core simulation done ***')
    lines.append(f'*** {len(failed):02d} test cases did not complete successfully.' if failed
                 else '*** All test cases completed successfully')
    return '\n'.join(lines)+'\n'


class ChaChaCheckerTests(unittest.TestCase):
    def test_complete_pass_and_unique_repeated_labels(self):
        result = classify(transcript())
        self.assertEqual(result['outcome'], 'pass')
        self.assertEqual(len(result['checkpoints']), 15)
        self.assertNotEqual(result['checkpoints'][6]['id'], result['checkpoints'][7]['id'])

    def test_failure_is_detected_despite_successful_process_exit(self):
        result = classify(transcript((3,4,5,7,13)))
        self.assertEqual(result['outcome'], 'functional_fail')
        self.assertEqual(result['signature'][0]['id'], 'case04_tc1_4')
        self.assertEqual(len(result['signature']), 5)

    def test_missing_duplicate_and_unknown_verdicts_cannot_pass(self):
        good = transcript()
        for text in (good.replace('*** chacha_core simulation done ***',''),
                     good.replace('*** TC 1-1 successful',''),
                     good.replace('*** TC 1-1 successful','*** TC 1-1 successful\n*** TC 1-1 successful'),
                     good.replace('*** TC 1-1 started.','*** TC 99-1 started.'),
                     good+'ERROR: unrelated simulator failure\n'):
            with self.subTest(text=text[-100:]):
                self.assertEqual(classify(text)['outcome'], 'infrastructure_error')

    def test_failure_details_must_match_existing_checker_expectations(self):
        text = transcript((3,)); expected = CASES[3]['expected']
        for changed in (text.replace('Expected: 0x'+expected, 'Expected: 0x'+'0'*128),
                        text.replace('Got:      0x'+format(int(expected,16)^1,'0128x'), 'Got:      0x'+expected),
                        text.replace('01 test cases','02 test cases')):
            self.assertEqual(classify(changed)['outcome'], 'infrastructure_error')

    def test_timeout_and_simulator_error_are_not_bug_detection(self):
        text = transcript((3,))
        self.assertEqual(classify(text,timed_out=True)['outcome'], 'timeout_unclassified')
        self.assertEqual(classify(text,returncode=1)['outcome'], 'infrastructure_error')
        self.assertEqual(classify(text,stderr='simulator diagnostic')['outcome'], 'infrastructure_error')

    def test_completion_before_last_verdict_is_incomplete(self):
        text = transcript().replace('*** chacha_core simulation done ***\n','')
        text = text.replace('*** TC 8-1 successful','*** chacha_core simulation done ***\n*** TC 8-1 successful')
        self.assertEqual(classify(text)['outcome'], 'infrastructure_error')


if __name__ == '__main__':
    unittest.main()
