# RTLProbe software tests

Put tests of RTLProbe itself here: configuration and path validation, checker
interpretation, exact mutation edits, evidence integrity, recovery, and pipeline
integration. Use small deterministic fixtures and temporary output directories.

Upstream RTL testbenches stay with their pinned source repositories under
`vendor/`; target configurations describe how to run them. Saved experiment
results belong in `outputs/` and are not substitutes for software tests.

Install the pinned dependencies in the runner environment, then run the regression
tests from the repository root:

```sh
.venv-dataset/bin/python -m unittest discover -s tests -v
```

Launcher tests use a Docker test double to verify the mounted root, working
directory, argument boundaries, and exit status without requiring Docker. They
do not establish that the container image builds or runs successfully.

Native stage smoke tests run when Icarus (`iverilog`/`vvp`), Verilator, and Yosys
are on PATH. They exercise default and explicit output paths using a small
software-test fixture in a temporary workspace. A Python timeout adapter is used
for portability; these tests do not qualify the container's GNU `timeout` or its
pinned tool versions, and the fixture is not a dataset target.

Capture-execution proof fixtures construct synthetic command/process/log records;
qualification safety tests mock compile, simulation and structural checks. These
tests verify refusal, restored identity, binding and publication sequencing without
qualifying a real target or attesting native execution. Per-command guard tests
mock child processes and verify that revocation preserves the completed outcome
and prevents the next launch. Physical target proof remains a separate operation.

An optional native Icarus capture fixture verifies explicit observation of an
unused register as unknown, DUT-interface reset selection with child aliases,
and unchanged fixture output/source bytes. It uses temporary synthetic RTL and
does not qualify SHA-256, ChaCha or another dataset target.

Scoped hook tests verify exact launch/query arguments and that after hooks see
already durable native outcomes. The qualifier's explicit destination remains
fresh and under the target qualification root; application policy lives in the
separate caller, not in the shared runner.
