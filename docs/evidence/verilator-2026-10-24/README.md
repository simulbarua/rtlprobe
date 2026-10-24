# Mac original-check evidence, October 24, 2026

This archive contains nine original-design PASS observations, their raw logs,
run commands, costs, and hashes. The final checker reparsed every selected log
and agreed with the recorded outcome. This is not qualification or gate-1
completion. Controls and restored runs remain pending the front end.

The rv_timer observations come from one original executable across the initial
run, the interrupt/TL continuation, and an identical-options same-CSR replay.
Two same-CSR attempts are retained separately: each exited zero but emitted
an internal timeout, an unexpected alert, and duplicate summaries/finish lines.
The checker rejected both as infrastructure_error. Do not discard that outcome
or treat the subsequent PASS as evidence of reproducible qualification.

Full source/build/controller artifacts remain at the absolute evidence paths in
the result summaries. No OpenTitan source tree is included here. A result_sha256
refers to the original full result, whose source hashes are summarized here by
source_sha256. The manifest in this directory binds these compact archive files.
Recorded and final checker hashes distinguish execution from later log-only
revalidation; a changed fingerprint requires fresh qualification.
