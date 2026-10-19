# RTLProbe software tests

Put tests of RTLProbe itself here: configuration and path validation, checker
interpretation, exact mutation edits, evidence integrity, recovery, and pipeline
integration. Use small deterministic fixtures and temporary output directories.

Upstream RTL testbenches stay with their pinned source repositories under
`vendor/`; target configurations describe how to run them. Saved experiment
results belong in `outputs/` and are not substitutes for software tests.

This directory currently contains documentation only. Add runnable tests alongside
the implementation they validate; no test results are claimed by this scaffold.
