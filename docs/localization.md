# Failure-conditioned localization pilot

The [localization experiment](../experiments/localization/README.md) replays a
saved SHA-256 case, captures its failing execution, exports explicitly selected
inputs, ranks source locations and evaluates predictions against a hidden label.
It is a development baseline, not a trained localizer or a general target adapter.

## Method

The curator driver verifies a saved case, reconstructs its mutation, and checks
original PASS, three consistent mutant failures and reverse-patch restored PASS.
It adds observation-only testbench instrumentation in a separate copy, verifies
that the checker signature is unchanged, and maps the checker observation to the
captured waveform. Ranking inputs derive from the buggy snapshot.

Three deterministic policies consume different inputs:

| Policy | Evidence used |
|---|---|
| Lexical overlap | Candidate RTL and normalized failure log |
| Backward distance | Above plus signal dependencies and checker anchor |
| Distance with activity tie-break | Above plus failing-run signal history |

Assignments at the same file/line/instance are grouped into one source location.
The structural policies filter to the backward cone, so candidate counts differ.
This historical comparison changes both policy and evidence; it is not a
controlled modality ablation of one fixed model.

## Recorded result

The October 19, 2026 replay used one previously known development case. These
are archived observations, not a new run with the current checkout:

| Policy | Candidates | True-location rank | Top-10 hit | Reciprocal rank |
|---|---:|---:|---|---:|
| Lexical overlap | 336 | 99 | No | 0.010101 |
| Backward distance | 322 | 136 | No | 0.007353 |
| Distance plus activity | 322 | 136 | No | 0.007353 |

The richer heuristics did not improve this example. One development case cannot
establish accuracy, generalization or debugging time saved. Counts and ranks may
change when candidate or graph rules change; do not present this table as current
benchmark performance.

## Limits and inference boundary

- The graph overapproximates signal dependencies, collapses arrays/loops, and
  does not model branch feasibility or cycle-accurate causality. Unsupported
  elaboration constructs are rejected rather than silently approximated.
- Checker anchoring and instrumentation are SHA-256-specific. Time units come
  from the compiled simulation scope and are checked against VCD resolution.
- Missing waveform signals, including an undumped memory in the recorded run,
  are explicit gaps. Activity is not proof of incorrect behavior.
- The driver needs curator artifacts, but a localizer must receive only its
  selected inference export. Fixed RTL, mutation patches, labels, operator/case
  metadata and acceptance records are not localization inputs.
- Separate ranker processes and JSON allowlists are not filesystem isolation.
  Tool-using models require an enforced access boundary before evaluation.

See the [experiment guide](../experiments/localization/README.md) for commands,
dependencies and output layout. Full development reports and case-specific
review dossiers are maintained in the separate agent repository; sealed run
artifacts remain in external evidence storage.
