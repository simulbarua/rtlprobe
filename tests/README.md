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
