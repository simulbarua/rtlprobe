"""Acceptance-oriented tests; no network or downloaded repository required."""

import copy
import tempfile
import unittest
from pathlib import Path

from rtlprobe.evidence import Runner, manifest, verify_manifest
from rtlprobe.mutation import apply, locate, safe_path
from rtlprobe.oracle import classify as dispatch

CHECKER = {"checker": {"path": "targets/sha256/checker.py"}}

def classify(*args, **kwargs):
    return dispatch(*args, config=CHECKER, **kwargs)
from rtlprobe.pilot import gates

PASS = """-- Testbench for sha256 core started --
*** TC 1 single block test case started.
*** TC 1 successful.
*** TC 2 double block test case started.
*** TC 2 first block successful
*** TC 2 second block successful
Running test for 9 block issue.
Digest ok.
*** All 03 test cases completed successfully
*** Simulation done.
"""
FAIL = PASS.replace("*** TC 1 successful.", "*** ERROR: TC 1 NOT successful.\nExpected: 0x"+"a"*64+"\nGot:      0x"+"b"*64).replace("All 03 test cases completed successfully", "01 test cases did not complete successfully.")
FIXTURE = b"module sample;\nreg [31 : 0] a, b, y;\nalways @* begin\n y = a + b;\nend\nendmodule\n"
OPERATOR = {"id": "unsigned32_root_add_to_sub", "version": "1.0", "status": "approved"}


class OracleTests(unittest.TestCase):
    def test_completed_pass(self):
        self.assertEqual(classify(PASS)["outcome"], "pass")

    def test_exit_zero_digest_failure(self):
        result = classify(FAIL)
        self.assertEqual(result["outcome"], "functional_fail")
        self.assertEqual(result["signature"][0]["id"], "tc1")

    def test_missing_or_contradictory_evidence(self):
        for text in (PASS.replace("*** Simulation done.", ""),
                     PASS.replace("*** TC 1 successful.", ""),
                     PASS.replace("All 03", "All 02"),
                     FAIL.replace("01 test", "02 test"),
                     PASS+"ERROR: unrelated simulator problem\n",
                     PASS+"*** TC 1 successful.\n",
                     PASS.replace("Running test for 9 block issue.", ""),
                     FAIL.replace("b"*64, "a"*64)):
            with self.subTest(text=text):
                self.assertEqual(classify(text)["outcome"], "infrastructure_error")

    def test_timeout_and_nonzero_are_not_functional(self):
        self.assertEqual(classify(FAIL, timed_out=True)["outcome"], "timeout_unclassified")
        self.assertEqual(classify(FAIL, returncode=1)["outcome"], "infrastructure_error")
        self.assertEqual(classify(PASS, stderr="failure")["outcome"], "infrastructure_error")


class MutationTests(unittest.TestCase):
    def setUp(self):
        self.target = locate(FIXTURE, 4, "y", "b", "y = a + b;")

    def test_exact_single_token_change(self):
        result = apply(FIXTURE, self.target, OPERATOR)
        self.assertEqual(result, FIXTURE.replace(b"a + b", b"a - b"))
        self.assertEqual(sum(a != b for a, b in zip(FIXTURE, result)), 1)

    def test_reject_stale_hash_and_span(self):
        with self.assertRaises(ValueError): apply(FIXTURE+b"\n", self.target, OPERATOR)
        target = dict(self.target, start_byte=0)
        with self.assertRaises(ValueError): apply(FIXTURE, target, OPERATOR)

    def test_reject_unapproved_operator(self):
        with self.assertRaises(ValueError): apply(FIXTURE, self.target, dict(OPERATOR, status="proposed"))

    def test_reject_comment_signed_and_wrong_width(self):
        for data, line in ((FIXTURE.replace(b" y =", b" // y ="), 4),
                           (FIXTURE.replace(b"reg [", b"reg signed ["), 4),
                           (FIXTURE.replace(b"31", b"15"), 4)):
            with self.subTest(data=data):
                with self.assertRaises(ValueError): locate(data, line, "y", "b", "y = a + b;")

    def test_reject_unsupported_expression(self):
        for expression in (b"a - b", b"a + (b & a)", b"a + 1"):
            data = FIXTURE.replace(b"a + b", expression)
            with self.assertRaises(ValueError): locate(data, 4, "y", "b", "y = "+expression.decode()+";")

    def test_reject_path_escape(self):
        for path in ("/tmp/source", "../source", "rtl/../../source", "rtl//source"):
            with self.assertRaises(ValueError): safe_path(path)


class EvidenceTests(unittest.TestCase):
    def test_tamper_and_extra_file_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/"log").write_text("original")
            manifest(path)
            verify_manifest(path)
            (path/"log").write_text("changed")
            with self.assertRaises(ValueError): verify_manifest(path)
            (path/"log").write_text("original")
            (path/"extra").write_text("new")
            with self.assertRaises(ValueError): verify_manifest(path)

    def test_only_three_consistent_failures(self):
        good = {"outcome": "pass"}
        bad = {"outcome": "functional_fail", "signature": [{"id": "tc1"}], "executable_sha256": "abc", "source_hashes": {"a": "b"}}
        runs = [copy.deepcopy(bad) for _ in range(3)]
        self.assertTrue(all(gates(good, runs, good, True).values()))
        self.assertFalse(all(gates(good, runs*2, good, True).values()))
        runs[2]["signature"] = [{"id": "other"}]
        self.assertFalse(all(gates(good, runs, good, True).values()))
        self.assertFalse(all(gates(good, [bad]*3, good, False).values()))

    def test_timeout_preserves_command_record(self):
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(tmp, {"campaign_seconds": 5, "cpu_seconds": 5, "disk_bytes": 100000})
            result = runner.run("timeout", [sys.executable, "-c", "import time; time.sleep(5)"], tmp, 0.1)
            self.assertTrue(result["timed_out"])
            self.assertTrue((Path(tmp)/"commands/timeout/run.json").exists())


if __name__ == "__main__":
    unittest.main()
