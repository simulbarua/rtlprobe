# Dataset artifact contract

Contract ID **`rtlprobe-dataset-artifacts-1`**, version 1. The corresponding
[machine-readable catalog](contracts/dataset-artifacts-v1.json) names the
existing serialized formats and required retention layers. It is a collection
contract, not a runtime clearance, human acceptance or evaluation protocol.
Existing validators remain authoritative for their individual formats; the
catalog itself is not currently consumed by an admission API.

This version covers the SHA-256 and ChaCha Icarus adapters. Another qualified
target or approved operator does not automatically have capture/export support.
Verify its checker, source mapping, reset/time/memory behavior and provenance
before extending the contract. Preserve sealed historical records unchanged;
new companions, exports and metadata are additive and independently hash-bound.

## Required artifact layers

| Layer | Retain and bind | Access and validation |
|---|---|---|
| Validated case | Exact original/buggy/restored source snapshots; unchanged existing testbench/checker/collateral; raw compile/run stdout/stderr and verdicts; command records; source/config/revision/tool/implementation fingerprints; case/index/manifests; reviews and lineage. | Private curator archive. Verify existing lifecycle/index/seal/acceptance chains and saved validation. Acceptance alone is not evidence completeness. |
| Capture work | Actual plain and observed buggy compiles/runs; command argv/cwd/status/timing/log paths; raw logs; original TB and additive observed TB; compiled observed VVP from which the timebase was read; observer policies and budget outcomes. | Private, immutable retained work. Bind the actual output hashes and input/code/tool identity to the companion. Do not discard the work directory after publishing its companion. |
| Companion | `manifest.json` and exactly `inference.json`, `buggy.vcd`, `observer.v`, `observer-policy.json`, `ast.json`, `provenance.json`. `inference.json` has exactly buggy sources/hashes, candidates, graph, alignment, trace and checker. | Private complete capture archive; use `load_inference_evidence`. Curator metadata may remain in private provenance and is not returned by that loader. The companion is not itself a condition-specific inference export. |
| Condition exports | C0, C1, C2, C3, C4 and M for the same buggy snapshot, neutral ID and candidate universe, with independently bound manifests and fixed specification projection. | Evidence-only public-to-localizer boundary, outside curator/code roots. Use strict `export_evidence`/`verify_export` and cross-view rederivation. Directory permissions are not process isolation. |
| Private linkage and status | Case/index/review hashes → actual capture work/provenance → companion manifest → every condition manifest → frozen full/public spec identities. Retain all batch outcomes, partial attempts, review/feedback and completeness/missingness. | Private ledger; no curator case/operator IDs or labels in inference views. Recover every referenced root, including external companions and exports. |

The saved sealed case supplies historical validation evidence. A new companion
preserves the execution records and case authorship.
Actual current target qualification and scoped capture authorization remain
separate prerequisites, supplied by the caller. The raw VCD is retained in full
inside the private companion, together with raw buggy logs and unchanged oracle.

## Source and collection coordinates

These storage conventions describe the existing implementations; they choose no
primary localization score, metric, tie-breaking or filtering policy:

- Paths are canonical relative POSIX paths within the pinned upstream source
  snapshot. Bind coordinates to exact source SHA256; no patching, whitespace or
  newline normalization is allowed to change the coordinate reference.
- Lines and columns are one-based. Byte spans are zero-based, half-open
  `[start_byte, end_byte)`. End line/column describes the exclusive end position.
  Candidate syntax currently requires ASCII; non-ASCII/parse failures retain
  rejected/partial status and reasons, not an empty successful inventory.
- A `source-syntax-line-v2` candidate groups one path/module/anchor line and
  retains **every constituent `site_spans` entry**, syntax kind and mapping
  missingness. Its ID and inventory ID are source-bound. An assignment can cover
  an edit's line while not containing that exact edit token as a constituent
  span. Preserve and report the two facts independently; do not manufacture a
  span or equate line recall with exact-span recall.
- AST indices and `parent_index` are per source file. A stable AST reference
  includes the source hash and path, not an index alone. Graph instance/signal
  identities use the resolved static DUT hierarchy. Candidate-to-signal mapping
  is explicit; absent mapping is not an inactive or zero-valued signal.
- Capture reads ASCII source bytes without newline translation and checks the
  re-encoded sources against the sealed expected hashes. Candidate extraction
  accepts exact ASCII CRLF bytes; non-ASCII capture remains unsupported. The
  historical crypto slice uses LF; extractor support alone does not establish
  real target capture readiness for another source format.

Keep all source candidates identical across conditions. Private recall joins
may use injected locations after extraction, but neither truth nor a model's
success may choose the universe, captured signals or windows. The later study
must explicitly choose its line/span scoring and tie/filter policy.

## Signal, memory, reset and time evidence

The companion retains source syntax/AST (`ast.json` and graph AST), conservative
graph (`buggy-dependencies-1`), candidate alignment (`buggy-alignment-1`), candidate
inventory, full raw waveform and indexed trace (`buggy-trace-1`). Syntactic
coverage, conservative graph completeness, candidate-signal alignment, actual
waveform presence and measured RTL coverage are different quantities.

The observer dumps the whole supported static DUT for the whole run, with every
supported static unpacked memory word. Current support is one unpacked dimension,
up to 4,096 explicit words by default. Multiple dimensions, unsupported ranges,
over-budget words and unsupported elaboration remain explicit partial evidence.
Named-port static hierarchy and checked pure expression functions have bounded
support; generated/parameterized/ambiguous/stateful contexts are not inferred
complete. Current crypto manifests declare measured RTL coverage unavailable;
do not insert zeros or claim coverage/Ochiai eligibility.

Keep integer VCD ticks and the recorded VCD resolution, plus the compiled
testbench's `time_unit_exponent` and `time_precision_exponent`. Map checker
samples using these values; no unit is guessed. The observed actual value must
agree with the unchanged checker and settled waveform value at the mapped tick.
Do not interpret indexed settled values as delta-cycle or physical causality.

For the current crypto adapters, record the unique observed active-low
`reset_n`, assertion/release ticks, the reset-through-first-failing-checkpoint
window, all checkpoint anchors and passing task windows. Repeated ChaCha labels
use the checked invocation order. Missing timebase/reset/windows or parity
produces partial/unavailable evidence or refusal. Retain raw full-run evidence;
the exported windows do not authorize adding later failures to a condition.

## Checker, specs and inference boundary

`buggy-checker-1` retains both raw buggy logs, unchanged TB/adapter source, verdict,
observational parity, anchors/windows and compiled timebase. Compare plain and
observed verdicts, checkpoint order and signature without changing the existing
oracle or stimulus. Capture diagnostics and exact supported memory-name warning
normalization must not erase the raw observed log.

Every condition contains identical `candidates.json`, public `checker.json`,
`common.json` and buggy `rtl/` bytes. The public checker projection includes
only its declared context, unchanged TB/adapter, plain buggy log and rederived
verdict. Observer diagnostics, time/signal anchors and private capture metadata
are withheld from that common projection.

| Condition | Additional evidence |
|---|---|
| C0 | Common evidence only. |
| C1 | Conservative graph and candidate-signal alignment. |
| C2 | Checked raw waveform windows and aligned trace. |
| C3 | Entire fixed public specification store. |
| C4 | C1, C2 and C3 evidence together. |
| M | Same graph, same selected raw waveform windows and fixed specs, without aligned structure/trace presentation. |

Retain the independently frozen **full** specification-store hash privately;
exports carry the fixed public-projection hash. Requirements/schema/section
bytes remain unchanged and are never selected using an injection location.
Bibliography is projected through an allowlist. Preserve citations, source
versions, claim classifications and redistribution policy; see the
[specification-store rules](../targets/SPEC_STORE.md).

Curator labels, edit/patch/operator IDs, case/review identities, original/restored
internal sources/traces and learning state stay out of condition inputs. Labels
and original/restored validation material remain private and recoverable, not
deleted. A future localizer must receive only its bound condition export through
the required isolated launch; creating files does not establish that isolation.

## Completeness, provenance and implementation limits

Record validation, human acceptance, artifact completeness, collection eligibility
and study eligibility independently. A schema/hash-valid import can be useful
offline evidence; it does **not** prove executed observational capture. A partial
companion or export can be retained for diagnosis but must not satisfy this
contract's full artifact-complete state. Six ready per-view manifests alone are
insufficient without the private actual-run and same-case linkage checks.

`load_inference_evidence` verifies the companion manifest and rederives its
payload/observer/AST/VCD, but does not semantically attest `provenance.json` or
reopen its referenced native command records. `offline-import-1` companions
therefore load by design. `rtlprobe.capture_execution.verify_capture_execution`
adds the private `capture-execution-1` sidecar at the capture root, beside the
unchanged companion directory. It requires an externally bound proof hash,
retained work and four ordered bounded command records, raw logs, actual-shaped
start/process records, observer/checker/timebase rederivation, exact sources,
current code/tools and resource outcomes. Symlinks, changed or extra work files,
partial captures and offline-import provenance refuse. See the
[capture guide](evidence-capture.md#retained-execution-proof).

Verifying a complete case export requires this proof in addition to the six
same-case exports. A trusted caller must bind the proof to the actual operation. These local files are not
cryptographic attestation of physical execution. This is stricter operational
admission, not a change to companion v1, coordinates or historical acceptance.
It does not implement a universal recovery or authorization validator.

Restore verification must cover every root referenced by the case, capture,
qualification, and export records.

For working APIs and limitations, see [capture](evidence-capture.md),
[sanitized exports](sanitized-exports.md), [execution layout](execution-layout.md)
and [target admission](../targets/README.md). Changing collection coordinates,
candidate generation, required modalities or supported targets requires a new
contract version and appropriate review; it must not silently reinterpret a
sealed artifact or adopt a study protocol.
