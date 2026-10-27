# Failure-conditioned localization pilot

This experiment replays one saved SHA-256 case with the existing upstream
testbench and checker, captures a VCD, exports three inference bundles, runs
deterministic ranking heuristics, and evaluates predictions afterward.
It is separate from case admission and does not change dataset approvals.
It is not a trained model, a general target adapter, or a deployment workflow.

Read the [method, recorded results and limits](../../docs/localization.md).

From this repository root, using a Python environment with the pinned dataset
requirements and a real saved case directory:

```sh
python experiments/localization/run_sha256.py \
  --case /absolute/rtlprobe-data/outputs/sha256/cases/CASE_DIRECTORY \
  --out /absolute/evidence/localization/run-new

python -m unittest discover -s experiments/localization -p 'test_*.py' -v
```

Use a fresh output directory; an existing directory is rejected. Python needs
the repository's dataset dependencies, including PyVerilog and vcdvcd.
Native tools must be on PATH. The replay uses Icarus and patch; the environment
record also verifies the existing toolchain executables.

`run_sha256.py` is a curator-side experiment driver. It validates the case
manifest, reconstructs the saved mutation with the existing mapper, runs original
PASS / three failures / reverse-patch restored PASS, then adds observational
instrumentation to a separate testbench copy. It does not replace the testbench
or add a new correctness oracle. Synthesis remains available in historical case
evidence but is not rerun or supplied to these rankers.

`baseline.py` builds conservative RTL dependencies and ranks explicit JSON input.
Its standalone CLI accepts only an inference file and prediction destination:

```sh
python experiments/localization/baseline.py \
  /absolute/evidence/localization/run-new/inference/rtl_logs_structure_checker_trace.json \
  /absolute/predictions/rtlprobe-localization.json
```

The CLI is a reproducible data boundary, not an OS access-control sandbox.
Do not give a future model the experiment root or curator files.

The three policies are lexical token overlap, backward dependency distance, and
backward distance with signal activity as a tie-breaker. Source order breaks
remaining ties. AST assignment segmentation is shared across all modes; the
RTL/log mode receives no dependency edges. The richer mode includes the existing
checker source, but the current heuristic uses only its mapped failure anchor
and trace activity. This does not test a model's understanding of the checker.

Dependencies include named ports, branch/case controls, and sequential feedback.
Arrays and procedural loops are collapsed; branch feasibility and cycle-level
causality are not modeled. Functions, generate blocks, positional ports,
instance arrays, and parameter overrides are rejected. This parser is only
validated on the recorded SHA-256 example and focused fixtures.

Output layout:

```text
curator/                  source identity, target config, evaluation label
replay/                   original, buggy, restored, and instrumented sources
commands/                 exact argv, cwd, stdout/stderr, status and cost
outcomes/                 semantic checker verdicts
inference/                explicit label-free inputs for each baseline
predictions/              ranked source locations, observations and hypotheses
implementation/           experiment source and reused core source snapshots
structure.json            hierarchy/source-mapped dependency representation
trace.json                events from time zero through first failure, gaps
anchor.json               observed checker values and actual simulator time unit
instrumentation.patch     additive testbench observation edit
leakage-audit.json         input hashes, export checks, boundary limitations
summary.json              per-case metrics, evidence availability and costs
manifest.json             hashes of all sealed run artifacts
```

Treat scores, distances, and activity as heuristics, not probabilities.
Do not tune against the same case and report the outcome as held-out accuracy.
