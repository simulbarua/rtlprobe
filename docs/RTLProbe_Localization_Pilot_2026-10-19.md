# RTLProbe implementation audit and localization pilot

> Evidence links below are written against `EVIDENCE_ROOT`, the sealed-evidence folder kept outside this repository (`<local root>/reference/evidence/`; see [execution-layout.md](execution-layout.md)). They are not clickable from a checkout by design.

Date: October 19, 2026, America/Los_Angeles.

The requested audit and one complete localization replay are finished. Existing
mutation validation is usable; the missing layer was failure-conditioned evidence
export, candidate extraction, ranking, and evaluation. An isolated experiment now
connects those steps. **The measured ranking result is negative:** all three
heuristics miss Top-10 on the one replayed development example.

This is implementation evidence, not a claim of model accuracy, engineering
time saved, or generalization.

## Authority and scope

The user's October 19 handoff prioritizes the December 3 prototype: localize an
already observed failure, preserve hidden mutation labels, report missing
evidence, and defer RAG, interactive agents, and dashboard extensions.
The handoff's evidence fields and collection mechanisms were recommendations to
audit, not claims of existing implementation.

The baseline and provenance notes identify `github/rtlprobe` as active code,
`github/rtlprobe-agents` as agent tooling, and `rtlprobe-data` as active data.
`workarea` remains historical. No agent workflow was moved back into core.

Netlists are omitted from this localization experiment. The existing approved
mutation runner's lint/synthesis gates and the broader capstone commitment were
not changed. There is no dataset expansion or new acceptance decision here.

## What existed before this change

The [case inventory](EVIDENCE_ROOT/localization-pilot-2026-10-19/existing-case-inventory.json)
contains 15 cases: 12 accepted and 3 pending review. None of these sealed case
directories contains a VCD or FST. The first SHA-256 case was inspected in detail,
alongside active implementation, schemas, target/checker assets, and the separate
raw tooling pipeline.

| Capability | Audited status before this experiment | Evidence and practical limit |
|---|---|---|
| Original PASS, mutation, replay, restoration | Implemented | `rtlprobe/batch.py`, `pilot.py`, saved source/executable/log hashes; three runs of one mutant |
| Pinned repository, source and tool provenance | Implemented | Target config, fingerprint, environment, command journal, snapshots and manifests |
| Failure identity and expected/actual values | Implemented for qualified targets | SHA-256 checker parses four comparisons; snapshots include existing TB |
| Undetected vs invalid vs infrastructure outcomes | Implemented with naming limitations | Mutant PASS is `unexposed`; compile failure is `invalid`; timeout detail is retained in command/verdict records, while outer case state can be `infrastructure_error` |
| Waveform capture for mutation cases | Missing | `pilot.simulate` invokes ordinary `vvp -N`; 0 traces in 15 case bundles |
| Raw waveform tooling | Partial, target-dependent | `tooling/run_pipeline.sh` tries PicoRV32's `+vcd` convention and moves `testbench.vcd`; this is not generic instrumentation or a qualified failure oracle |
| Failure simulation timestamp | Missing in parsed SHA-256 failures | Command `started_at` is wall-clock time, not failing simulation time; raw TB does not timestamp the comparison |
| Checker context | Partial | Source and comparison IDs/values are saved; no generalized checker-to-signal anchor extractor or transaction mapping |
| RTL structure and source mapping | Partial | Mutation mappers find narrow approved AST sites; raw tooling can dump an AST; neither is a localization dependency graph |
| Synthesized structure | Implemented artifact, unqualified mapping | Netlists exist; `source_mapping: not_qualified`, `functional_equivalence: not_checked` |
| Cross-module/sequential candidate extraction | Missing | No ranker/cone extractor in active core runtime |
| Label separation | Curator separation only | `case.json` includes proposal, original statement, ground truth and original/restored source references; its access field explicitly says no localization export exists |
| Learned localization and modality ablations | Missing | The Python planning agent proposes mutations; it is not a failure-conditioned localization model |
| Coverage-based suspiciousness | Missing | No measured per-test coverage in qualified case metadata; raw tooling's coverage folder contains a lint-log placeholder |
| RAG, interactive diagnosis, dashboard | Deferred/proposed | No evidence of an implemented prototype in the audited runtime |

Wall-clock timeout, compile rejection, and an undetected mutant must not be treated
as successful bug localization examples. A baseline PASS is evidence about the
executed tests, not proof that the original design is correct.

## Small additions and replay

New experiment files are [baseline.py](../experiments/localization/baseline.py),
[run_sha256.py](../experiments/localization/run_sha256.py), and
[test_localization.py](../experiments/localization/test_localization.py).
The [experiment guide](../experiments/localization/README.md) documents invocation
and output layout. Core admission/approval code and its schemas were not edited.

Selected case: `sha256-ff21c95042a2062f`, pinned Secworks SHA-256 revision
`837c5cc396f001d18f2c765721c585716eb439ae`. This is an accepted, previously known
development case, chosen to exercise the pipeline. Its evaluation label is
`src/rtl/sha256_core.v:341`; no claim of blinded case selection is made.

The isolated replay verified the saved manifest, copied the original snapshot,
applied the approved mutation mapper, and required byte equality with the saved
buggy snapshot. Fresh execution produced:

| Step | Observed result |
|---|---|
| Original existing testbench | PASS |
| One mutant, three executions of the same binary | Three consistent functional FAIL signatures |
| Reverse patch and source identity check | Original bytes restored |
| Restored testbench execution | PASS |
| Instrumented rerun | Same complete checker verdict/signature as ordinary mutant execution |
| Timestamped digest vs VCD digest | Equal at the failure anchor |

The instrumented copy adds a display immediately before the existing first
comparison and a separate dump monitor. It changes neither stimulus nor expected
values and adds no replacement testbench. The full suite still runs; trace
extraction retains events from time zero through the first failed comparison.

**Timestamp finding:** upstream declares no timescale. Icarus compiled the TB
with unit/precision exponents `0, 0`; the VCD reports `1s`. The first comparison
occurs at tick 272. This is a simulator convention for this invocation, not an
assertion that the intended hardware latency is 272 seconds or 272 nanoseconds.
The export records the compiled scope's time unit and checks conversion against
the VCD.

The capture spans ticks 0–3176 and contains 126 signal references, consuming
1,319,880 bytes. The extracted window is 0–272. All 126 references map to graph
signals, including block-local temporaries and named submodule ports. One graph
signal is unavailable: `tb_sha256_core.dut.w_mem_inst.w_mem`, the unpacked memory
array. It is explicitly listed as missing. Of 322 cone candidates, 305 have
mapped LHS trace observations. This is not complete internal-state capture.

The graph follows data, branch/case controls, clock/reset dependencies, register
feedback, and named port connections through `k_constants_inst` and `w_mem_inst`.
It is a conservative signal graph: arrays and procedural loops are collapsed,
branch feasibility is not checked, and sequential edges do not encode a cycle
distance. Some syntax is deliberately rejected. This is not a general Verilog
elaborator or a precise dynamic causal slice.

## Actual inference inputs and leakage check

The production case bundle is unsafe to pass wholesale to a localizer. The new
experiment constructs three allowlisted JSON exports, with neutral filenames:

| Export | Contents | Size |
|---|---|---:|
| `rtl_logs.json` | Buggy RTL, normalized first mismatch, syntax-segmented candidates | 129,212 bytes |
| `rtl_logs_structure.json` | Above plus dependency graph and mapped checker output anchor | 310,167 bytes |
| `rtl_logs_structure_checker_trace.json` | Above plus original checker source and failing-run trace window | 679,391 bytes |

These are **actual inputs consumed by deterministic baseline processes**. No
learned/LLM localizer exists in this experiment and no model API was called.
The stronger input is not yet a practical LLM prompt: context selection and
token budgeting remain work.

Exported inputs contain no case ID, proposal ID, mutation patch, operator record,
ground truth, original/fixed RTL, original-source hash, acceptance receipt, or
golden waveform. Candidate regions use buggy RTL and the failing digest's
dependency cone; signal capture dumps the DUT independent of the mutation site.
The anchor is target-specific, manually mapped from the existing checker and its
named DUT connection. It is not an autonomous anchor extraction capability.

All predictions are written by fresh processes before the evaluator loads the
curator label. The ranker reads only its explicit JSON path. Tests show that it
runs without a case bundle and that changing a neighboring label file leaves
rankings unchanged. Input hashes and forbidden-metadata checks are in
[leakage-audit.json](EVIDENCE_ROOT/localization-pilot-2026-10-19/run-06/leakage-audit.json).

Limits: process separation is not filesystem isolation; a future tool-using model
must not receive curator-directory access. The developer saw the label, so this
is exploratory development, not a preregistered blinded experiment. Public-source
memorization is also not ruled out for a future model.

## Measured ranking result

Policy definitions were saved in source:

1. RTL/logs: overlap between candidate-text identifiers and the normalized failure
   log, followed by source-order ties. This is a weak lexical baseline.
2. Structure: retain candidates whose LHS is reachable backward from the digest;
   rank by shortest signal dependency distance, then source order.
3. Checker/trace: same cone and distance, with LHS signal-change count as a
   tie-breaker. Full checker source is supplied, but this heuristic does not
   interpret its semantics beyond the anchor.

All modes use AST syntax segmentation for the same initial candidate universe.
Assignments starting at the same file/line/instance are grouped into one source
location, consistent with the line-level ground truth.
This comparison changes both available evidence and deterministic policy; it is
not a controlled ablation of one fixed learned model.

| Variant | Label included | Candidates | Label rank | Top-1 | Top-5 | Top-10 | MRR, n=1 |
|---|---|---:|---:|---:|---:|---:|---:|
| RTL + logs, lexical | Yes | 336 | 99 | 0 | 0 | 0 | 0.010101 |
| + structure, backward distance | Yes | 322 | 136 | 0 | 0 | 0 | 0.007353 |
| + checker/trace, activity tie-breaker | Yes | 322 | 136 | 0 | 0 | 0 | 0.007353 |

MRR equals reciprocal rank because there is one example. Rank fractions are
29.46% and 42.24% respectively; these are shortlist positions, not measured
engineer effort.

The structural cone spans three modules but removes only 14 of 336 candidates.
The injected statement is five dependency edges from the observed digest; its
LHS changes 65 times in the window. The distance heuristic prefers downstream
digest/register assignments, and activity cannot overcome that primary ordering.
The richer heuristic does **not** improve this case. No tuning to promote the
known answer was performed after observing this result.

Each ranked entry separates observed signal events from a generic causal
hypothesis and a proposed confirmation check. The experiment does not demonstrate
a useful diagnosis or calibrated confidence.

## Cost, commands, and verification

The final run took 2.998 seconds before source-copy/sealing overhead; recorded
subprocess wall time was 0.571 seconds and child CPU time 0.386 seconds. Structure
extraction took 1.280 seconds and trace extraction 0.027 seconds. The standalone
rankers made zero model calls, with zero model tokens/API cost. Interactive
development time/token cost is not included.

All commands, working directories, outputs, timeouts, statuses, environment
versions/hashes, source snapshots, instrumentation changes, and relevant
implementation files are preserved in the
[sealed final run](EVIDENCE_ROOT/localization-pilot-2026-10-19/run-06/summary.json).
The trace contains the entire run; window extraction reduces downstream data,
not the simulation's execution duration. Storage/runtime scaling and FST
comparison were not attempted.

Exact successful invocation, from `/Users/simulbarua/Work/ml_projects/RTLProbe`:

```sh
workarea/.venv-dataset/bin/python \
  github/rtlprobe/experiments/localization/run_sha256.py \
  --case rtlprobe-data/outputs/sha256/cases/sha256-ff21c95042a2062f-20261018T063551393932Z \
  --out localization-pilot-2026-10-19/run-06
```

Use a different nonexistent output directory to repeat it. Run-01 stopped on an
overly strict instrumentation guard while establishing the missing timescale;
run-02 stopped on Icarus option ordering. Their partial evidence remains
available. Run-03 completed. Run-04 completed after adding output time context
and fuller implementation provenance. Final review identified two assignments
on the same loop-header line; these are now grouped into one source location.
Run-05 and final run-06 use that correction and have identical inference bytes
and rankings. The correction reduced each candidate count by one and did not
change the injected line's rank.

Validation:

- 55 existing core tests passed in 14.907 seconds.
- 8 new tests passed: cross-module/control/sequential connectivity, block-local
  mapping, unique line candidates, unsupported constructs, label separation, evaluation misses,
  timestamp/value agreement with clipping, and standalone ranker independence.
- Final run manifest verifies.
- All 4,535 protected files remain byte-identical across active data and the
  captured historical data/evidence roots. Dataset totals remain 12 accepted,
  3 pending.

See [verification.json](EVIDENCE_ROOT/localization-pilot-2026-10-19/verification.json)
and [new-test output](EVIDENCE_ROOT/localization-pilot-2026-10-19/localization-tests.log).
No commit, push, BaruaLabs execution, or live Hermes session occurred.

## Decisions, open questions, next actions

**Decisions:** Keep failure-conditioned localization as the prototype task.
Preserve the existing deterministic mutation runner and approval records. Use
explicit inference exports with labels consumed only by evaluation. Retain the
negative result. Keep netlist-based ranking optional for this pilot and preserve
the existing mutation admission gates. Do not scale generation on the strength
of this example.

**Open questions:** Which temporal evidence distinguishes faulty computations
from downstream symptoms? How should memory contents and statement activation be
captured? How can checker anchors be derived for another target without labels?
Will a fixed learned/rule-based localizer use checker semantics better than
distance/activity? Cross-module graph reachability is demonstrated, but a
cause-in-one-module/symptom-in-another localization benchmark is not.

**Next actions (proposals, not completed experiments):** Define and freeze the
next ranking policy and evidence budget before inspecting more labels; add a
target-specific memory observation option where required; apply the frozen policy
to additional existing cases with candidate inclusion and failures reported;
then add an independent design/bug-lineage holdout when qualified examples exist.
Do not use random mutation splits to claim cross-design generalization.

## Follow-up interpretation and proposed smallest change

The user requested explanation and a proposal before further code changes.
The following is a read-only analysis of run-06; the proposal is not implemented.

The lexical score of the injected line is zero. Among its 98 predecessors, one
has a positive lexical score and 97 are zero-score source-order ties. Rank 99
therefore does not demonstrate semantic understanding of the failure.

The structural rule gives all candidates at distances 0–4 priority over the
injected line at distance 5. There are exactly 135 such candidates, so its best
possible rank under that primary key is 136. It already ranks first in its
19-candidate distance-5 group. The trace rule counts 65 changes on its LHS but
only applies activity within a distance group. It changes 265 positions elsewhere
while leaving the injected line at 136. Waveforms did not worsen the target
rank; they did not repair the distance-first ordering.

The richer mode does not reason about the actual values or the expected digest,
interpret checker source, or follow time-indexed dependencies. Multiple
assignments to the same signal receive the same activity count even if their
branches execute at different times. Activity is neither statement execution
coverage nor an indication of incorrect behavior.

A diagnostic calculation, using the saved rankings without changing code,
retains the lexical order and applies only the existing cone filter: the target
would be 95/322. Thus the observed deterioration to 136 is due to ordering by
distance, not exclusion of the target by the cone. The four-position gain is
merely removal of earlier candidates, not evidence of better causal reasoning.

The digest-only cone also omits checker scheduling dependencies. The upstream
`single_block_test` calls `wait_ready`, whose loop reads `tb_ready`, before
comparing `tb_digest` with `expected`. The removed candidates include ready
assignments. Such logic can affect when a value is sampled; its exclusion is not
justified solely by absence from the digest's RTL fan-in.

**Proposed smallest change:** use a checker-aware cone as a relevance preference,
without treating shortest distance or raw activity as suspiciousness. For this
test, anchor the cone at the compared digest and the ready condition that governs
sampling. Retain all source candidates as a fallback; put cone members first
using the same existing lexical/source-order rule within both groups. Keep trace
values available as observations, but remove activity from ranking for this
baseline. This is a conservative relevance baseline, not a proposed solution to
causal localization.

**Decision for this turn:** ranking code and sealed evidence remain unchanged.
**Open question:** whether the corrected relevance policy helps other cases; it
does not establish what behavior is wrong. **Next action proposed:** freeze this
small policy, compare it with the existing rules on a fixed candidate universe,
then evaluate additional examples with hidden labels. A later, separate waveform
experiment should distinguish assignment/branch activation and register history
from mere signal changes, explicitly preserving unknown or missing evidence.
