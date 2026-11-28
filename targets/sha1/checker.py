"""Read the transcript of the unmodified secworks SHA-1 core testbench."""

import re

ABC = "a9993e364706816aba3e25717850c26c9cd0d89d"
FIRST = "f4286818c37b27ae0408f581846771484a566572"
FINAL = "84983e441c3bd26ebaae4aa1f95129e5e54670f1"


def classify(stdout, stderr="", returncode=0, timed_out=False):
    invalid = dict(outcome="infrastructure_error", reason="incomplete_or_inconsistent_log",
                   checkpoints=[], signature=None)
    if timed_out:
        return dict(invalid, outcome="timeout_unclassified", reason="wall_clock_timeout")
    if returncode or stderr.strip():
        return dict(invalid, reason="simulator_error")
    # Debug register dumps and Icarus's trailing $finish notice carry no verdict.
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(("***", "-- Testbench", "Expected:", "Got:")):
            events.append(line)
        elif re.search(r"\b(?:error|fatal|warning)\b", line, re.I):
            return dict(invalid, reason="unexpected_diagnostic")
    stream = iter(events)

    def need(message):
        if next(stream) != message:
            raise ValueError

    def checkpoint(name, ok, bad, expected, duplicate=False):
        message = next(stream)
        if message == ok:
            return dict(id=name, outcome="pass")
        if message != bad:
            raise ValueError
        need("Expected: 0x" + expected)
        actual = re.fullmatch(r"Got:\s+0x([0-9a-fA-FxXzZ]{40})", next(stream))
        if not actual or (not duplicate and actual[1].lower() == expected):
            raise ValueError
        return dict(id=name, outcome="functional_fail", expected=expected, actual=actual[1].lower())

    try:
        need("-- Testbench for sha1 core started --")
        need("*** Toggle reset.")
        need("*** TC 1 single block test case started.")
        abc = checkpoint("tc1", "*** TC 1 successful.", "*** ERROR: TC 1 NOT successful.", ABC)
        need("*** TC 2 double block test case started.")
        for part in ("first", "second"):
            for state in ("started", "done"):
                need(f"*** TC 2 {part} block {state}.")
        first = checkpoint("tc2_block1", "*** TC 2 first block successful",
                           "*** ERROR: TC 2 first block NOT successful", FIRST)
        # Both upstream branches test db_digest1 == expected1. The second
        # branch prints the final digest on failure but never compares it.
        duplicate = checkpoint(None, "*** TC 2 second block successful",
                               "*** ERROR: TC 2 second block NOT successful", FINAL, duplicate=True)
        if first["outcome"] != duplicate["outcome"]:
            return invalid
        checks = [abc, first]
        failures = [c for c in checks if c["outcome"] == "functional_fail"]
        need(f"*** {len(failures):02d} test cases did not complete successfully."
             if failures else "*** All 02 test cases completed successfully")
        need("*** Simulation done.")
        if next(stream, None) is not None:
            return invalid
    except (StopIteration, ValueError):
        return invalid
    return dict(outcome="functional_fail" if failures else "pass", reason="checker_completed",
                checkpoints=checks, signature=failures or None, tests_completed=2, comparisons_completed=2)
