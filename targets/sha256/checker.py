"""Strict adapter for the unchanged, pinned secworks core testbench."""

import re


def classify(stdout, stderr="", returncode=0, timed_out=False):
    """Require completion, all four checkpoints, and a consistent three-test summary."""
    result = {"outcome": "infrastructure_error", "reason": "incomplete_or_inconsistent_log",
              "signature": None, "checkpoints": []}
    if timed_out:
        return dict(result, outcome="timeout_unclassified", reason="wall_clock_timeout")
    if returncode != 0 or stderr.strip():
        return dict(result, reason="simulator_error")
    lines = [s.strip() for s in stdout.splitlines() if s.strip()]
    if lines.count("*** Simulation done.") != 1:
        return result
    starts = ["-- Testbench for sha256 core started --", "*** TC 1 single block test case started.",
              "*** TC 2 double block test case started.", "Running test for 9 block issue."]
    if any(lines.count(s) != 1 for s in starts):
        return result
    if [lines.index(s) for s in starts] != sorted(lines.index(s) for s in starts):
        return result
    known_errors = ("*** ERROR: TC 1 NOT successful.", "*** ERROR: TC 2 first block NOT successful",
                    "*** ERROR: TC 2 second block NOT successful")
    if any(re.search(r"error|fatal|warning", s, re.I) and s not in known_errors
           and not s.startswith(("Error! Got:", "Error! Expected:")) for s in lines):
        return dict(result, reason="unexpected_diagnostic")
    checkpoint_positions = []
    checks = [
        ("tc1", "*** TC 1 successful.", "*** ERROR: TC 1 NOT successful."),
        ("tc2_block1", "*** TC 2 first block successful", "*** ERROR: TC 2 first block NOT successful"),
        ("tc2_block2", "*** TC 2 second block successful", "*** ERROR: TC 2 second block NOT successful"),
        ("issue9", "Digest ok.", None),
    ]
    for name, good, bad in checks:
        bad_indices = ([i for i, s in enumerate(lines) if s.startswith("Error! Got:")]
                       if bad is None else [i for i, s in enumerate(lines) if s == bad])
        if lines.count(good) + len(bad_indices) != 1:
            return result
        checkpoint_positions.append(bad_indices[0] if bad_indices else lines.index(good))
        check = {"id": name, "outcome": "pass" if not bad_indices else "functional_fail"}
        if bad_indices:
            i = bad_indices[0]
            if bad is None:
                got = re.fullmatch(r"Error! Got:\s+0x([0-9a-fA-FxXzZ]{64})", lines[i])
                expected = re.fullmatch(r"Error! Expected:\s+0x([0-9a-fA-F]{64})", lines[i+1]) if i+1 < len(lines) else None
            else:
                expected = re.fullmatch(r"Expected:\s+0x([0-9a-fA-F]{64})", lines[i+1]) if i+1 < len(lines) else None
                got = re.fullmatch(r"Got:\s+0x([0-9a-fA-FxXzZ]{64})", lines[i+2]) if i+2 < len(lines) else None
            if not expected or not got or expected[1].lower() == got[1].lower():
                return result
            check.update(expected=expected[1].lower(), actual=got[1].lower())
        result["checkpoints"].append(check)
    failed = [c for c in result["checkpoints"] if c["outcome"] == "functional_fail"]
    ordinary_failures = sum(c["id"] != "issue9" for c in failed)
    issue_failures = sum(c["id"] == "issue9" for c in failed)
    for prefix, count in (("Expected:", ordinary_failures), ("Got:", ordinary_failures),
                          ("Error! Expected:", issue_failures), ("Error! Got:", issue_failures)):
        if sum(s.startswith(prefix) for s in lines) != count:
            return result
    failed_tests = len({"tc2" if c["id"].startswith("tc2") else c["id"] for c in failed})
    summaries = [s for s in lines if re.fullmatch(r"\*\*\* (?:All \d+ test cases completed successfully|\d+ test cases did not complete successfully\.)", s)]
    if len(summaries) != 1:
        return result
    wanted = (r"\*\*\* All 0?3 test cases completed successfully" if not failed else
              rf"\*\*\* 0?{failed_tests} test cases did not complete successfully\.")
    if not re.fullmatch(wanted, summaries[0]):
        return result
    if lines.index(summaries[0]) > lines.index("*** Simulation done."):
        return result
    if checkpoint_positions != sorted(checkpoint_positions) or checkpoint_positions[-1] > lines.index(summaries[0]):
        return result
    return dict(result, outcome="functional_fail" if failed else "pass", reason="checker_completed",
                signature=failed or None, tests_completed=3, comparisons_completed=4)
