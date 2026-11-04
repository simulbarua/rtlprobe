# Buggy evidence capture and alignment

`rtlprobe.evidence_capture` is an additive companion implementation. It does not
change case schemas, mutation execution, accepted bundles or acceptance receipts.
Capture uses only an explicitly bound buggy source set and the existing checker.
Original/fixed RTL, golden waveforms, mutation labels and operator/site selection
are not inputs to its source or waveform mappings.

## Available interfaces

- `build_inference_evidence(...)` assembles supplied buggy sources, VCD and logs
  offline. `validate_inference_evidence(payload)` rederives every nested result;
  unexpected fields or changed mappings are refused.
- `publish_companion(destination, payload, provenance=...)` atomically creates a
  new directory outside sealed bundles. `load_inference_evidence(directory)`
  verifies its exact file manifest, buggy snapshot binding, source/trace/checker
  derivation and observation artifacts. Private provenance never enters its
  returned seven-field inference dictionary.
- `capture_observation(config=..., buggy_root=..., destination=...,
  expected_hashes=..., execution_guard=..., runner_factory=Runner,
  require_complete=True)` is the bounded execution API for a later authorized
  launcher. `expected_hashes` must cover every configured RTL file and the
  unchanged existing testbench. The caller must verify those hashes against the
  selected case/validation manifest and use the current target configuration.
  The guard must return literal `True`; missing/no-op guards fail. It is called
  before copying, before every command and before publication.

There is no standalone live capture CLI. Offline verification and assembly are:

```sh
python -m rtlprobe.evidence_capture verify /absolute/new-companion
python -m rtlprobe.evidence_capture assemble /absolute/assembly-input.json /absolute/new-companion
```

Offline imports do not prove that a target executed or that an operator-supplied
snapshot is a validated buggy case. A valid manifest establishes content integrity;
case admission, trusted source binding and release of the execution hold are
separate caller requirements. This module never records human decisions.

## Observation and retention

The execution API supports the configured SHA-256 and ChaCha Icarus targets. It
uses the existing bounded `Runner` for an uninstrumented buggy compile/run and an
observed buggy compile/run. RTL and the original testbench copies stay byte
identical. A separate observed TB copy receives only timestamp/value display
statements and, for ChaCha, an observer-local comparison ordinal. Existing
comparisons, expected values, stimulus and finish behavior are retained. Both
logs are classified by the existing crypto checker and must produce identical
verdicts, checkpoint order and signatures.

Runtime invocation retains the qualified `vvp -N` behavior. A capture-only exec
wrapper applies POSIX `RLIMIT_FSIZE` before each vvp process, bounding each
waveform/stdout/stderr file in flight (at most 64 MiB, or one quarter of the
declared disk budget). Unsupported enforcement fails before capture. This is a
per-file limit; aggregate disk usage is checked before commands and projected
before companion publication, and is not a hard filesystem quota.

A separate observer dumps the whole static DUT hierarchy for the whole run. Each
supported static unpacked memory word is explicitly dumped; no memory, signal or
window is selected using an injection site. The raw VCD is preserved verbatim.
Waveforms containing declarations outside the declared DUT scope are refused.
Missing words/signals and unsupported dimensions remain explicit rather than
being replaced with zeros. Budgets cap source/VCD size and companion publication;
failed/partial capture work remains outside accepted bundles.

Only one static unpacked dimension is currently supported, with at most 4,096
explicit memory words in the default capture. Unsupported dimensions and
over-budget ranges are checked before expansion. They appear as declaration
missingness and trace `unavailable_signals` with a reason; `missing_signals`
retains the unresolved memory name. Multidimensional memory therefore makes the
graph/alignment/trace partial even if no memory words occur in an imported VCD.
Offline assembly preserves that partial status, and strict graph/waveform exports
refuse it. Older companion metadata must be regenerated under the current
derivation; existing sealed companions are not updated in place.

The source-only syntax artifact retains node kinds, byte spans and parent indices.
The conservative signal graph supports plain static named-port hierarchy, named
procedural blocks, assignments, conditions, parameters and collapsed procedural
loops/memories. Pure single-return static expression functions are checked for
state effects and conservatively connect arguments to caller outputs; this covers
the pinned ChaCha `l2b` byte permutation. It is not bit-accurate or cycle-causal
elaboration. Generate constructs, parameter overrides, instance arrays, stateful
functions and unresolved types/names produce explicit partial status.

## Time and checker alignment

Crypto adapters sample the existing comparison/snapshot sites. SHA-256's two
block digests are sampled where the unchanged testbench stores them; ChaCha uses
invocation ordinal because printed labels repeat. Task starts are also observed,
so passing checkpoint windows are explicit. No target run is implied by the
presence of these software adapters.

Time units come from the compiled Icarus testbench scope and VCD resolution.
Observed actual values must agree with the waveform at their mapped ticks and
with the unchanged checker's failure signature. Missing or inconsistent anchors
fail closed. No nanosecond unit is inferred when upstream leaves it unspecified;
settled VCD values cannot establish delta-cycle causality.

The trace records the observed active-low crypto reset and the window through the
first failing checker checkpoint, plus each passing checkpoint's task window.
The complete raw run remains in the companion; public condition exports must
apply their declared windows. Later failing segments are not silently added to a
first-failure condition. Missing reset, timebase, signal or anchor evidence is
reported as partial. Constant/function-source candidates retain mappings or
explicit missingness; an absent runtime value is not a zero-valued observation.

## Integration and validation limits

The common candidate universe is supplied by `rtlprobe.candidates`, with stable
source-bound identities. `evidence_structure.build_structure` provides graph and
alignment APIs to the sanitized exporter; the capture loader returns only
`buggy_sources`, `source_hashes`, `candidates`, `graph`, `alignment`, `trace` and
`checker`. Original/golden/label material is absent from this interface.

Automatic per-new-case invocation is not part of `batch.run` yet. A launcher must
bind a validated buggy case, enforce the current dependency/approval hold, call
capture and sanitized export, and verify target completeness before a case is
study-ready. Existing accepted cases receive separate companions only; their
sealed archives are not rewritten. Fixture tests mock all native execution.
Fresh target capture/signature/timebase validation and export-isolation tests are
required separately before claiming operational readiness or releasing a hold.
