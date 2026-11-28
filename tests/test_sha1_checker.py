"""The pinned SHA-1 bench prints three verdicts from two independent predicates."""
from pathlib import Path
import runpy
import unittest

adapter = runpy.run_path(str(Path(__file__).resolve().parents[1]/'targets/sha1/checker.py'))
classify = adapter['classify']
PASS = """-- Testbench for sha1 core started --
*** Toggle reset.
*** TC 1 single block test case started.
*** TC 1 successful.
*** TC 2 double block test case started.
*** TC 2 first block started.
*** TC 2 first block done.
*** TC 2 second block started.
*** TC 2 second block done.
*** TC 2 first block successful
*** TC 2 second block successful
*** All 02 test cases completed successfully
*** Simulation done.
"""


class SHA1CheckerTests(unittest.TestCase):
    def test_only_two_independent_checks(self):
        result = classify(PASS)
        self.assertEqual(result['outcome'], 'pass')
        self.assertEqual([c['id'] for c in result['checkpoints']], ['tc1', 'tc2_block1'])

    def test_repeated_predicate_can_print_correct_final_digest_on_failure(self):
        text = PASS.replace('*** TC 2 first block successful',
            '*** ERROR: TC 2 first block NOT successful\nExpected: 0x'+adapter['FIRST']+'\nGot: 0x'+'0'*40)
        text = text.replace('*** TC 2 second block successful',
            '*** ERROR: TC 2 second block NOT successful\nExpected: 0x'+adapter['FINAL']+'\nGot: 0x'+adapter['FINAL'])
        text = text.replace('All 02 test cases completed successfully', '01 test cases did not complete successfully.')
        result = classify(text)
        self.assertEqual(result['outcome'], 'functional_fail')
        self.assertEqual([row['id'] for row in result['signature']], ['tc2_block1'])

    def test_contradictions_or_incomplete_logs_are_withheld(self):
        for text in (PASS.replace('*** TC 2 first block successful','*** ERROR: TC 2 first block NOT successful'),
                     PASS.replace('*** TC 1 successful.', ''), PASS + '*** Simulation done.',
                     PASS.replace('*** All 02','*** All 03'), PASS+'FATAL: simulation failed'):
            with self.subTest(text=text):
                self.assertEqual(classify(text)['outcome'], 'infrastructure_error')
