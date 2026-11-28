"""Strict transcript adapter for the RTLProbe extended SHA-1 bench."""
import re

EXPECTED = {
    "tc1": "a9993e364706816aba3e25717850c26c9cd0d89d",
    "tc2_block1": "f4286818c37b27ae0408f581846771484a566572",
    "tc2_block2": "84983e441c3bd26ebaae4aa1f95129e5e54670f1",
    "empty": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
    "boundary55": "8ae2d46729cfe68ff927af5eec9c7d1b66d65ac2",
    "chain128": "3d2a6087b753ee344b2449332fcde215c5cf71af",
    "restart": "9a2a451f5dff77fb0733b36f32b5e640ff67a0f5"
}


def classify(stdout, stderr="", returncode=0, timed_out=False):
    invalid = dict(outcome="infrastructure_error", reason="incomplete_or_inconsistent_log",
                   checkpoints=[], signature=None)
    if timed_out:
        return dict(invalid, outcome="timeout_unclassified", reason="wall_clock_timeout")
    if returncode or stderr.strip():
        return dict(invalid, reason="simulator_error")
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if lines and re.fullmatch(r".+:\d+: \$finish called at \d+ \([^)]+\)", lines[-1]):
        lines.pop()
    if len(lines) != 2 * len(EXPECTED) + 1:
        return invalid
    checks = []
    for i, (name, expected) in enumerate(EXPECTED.items()):
        if lines[2*i] != "SHA1 BEGIN " + name:
            return invalid
        match = re.fullmatch(rf"SHA1 DIGEST {name} expected={expected} actual=([0-9a-fxz]{{40}})", lines[2*i+1])
        if not match:
            return invalid
        actual = match[1]
        checks.append(dict(id=name, outcome="pass") if actual == expected else
                      dict(id=name, outcome="functional_fail", expected=expected, actual=actual))
    failed = [check for check in checks if check["outcome"] == "functional_fail"]
    if lines[-1] != f"SHA1 DONE checks={len(checks)} failures={len(failed)}":
        return invalid
    return dict(outcome="functional_fail" if failed else "pass", reason="checker_completed",
                checkpoints=checks, signature=failed or None, tests_completed=6, comparisons_completed=len(checks))
