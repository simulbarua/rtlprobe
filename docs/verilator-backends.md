# Verilator execution and original-only proofs

The Python target schema is enforced by `rtlprobe/target.py`. The optional
`backend` field defaults to `icarus`; the other values are `verilator_predv` and
`verilator_uvm`. Each backend implements `build` and `run`. Fingerprints bind
the implementation and backend metadata as well as target inputs and tools.

## Manifest extension

Verilator manifests add `build`, `admitted_tests`, `lineage`, `design`, and a
pending `control` with an intended site. Each admitted UVM test records `id`,
`sequence`, `seed`, `oracle_kind`, `run_options`, and `completion_pattern` (the
upstream progress message with iteration/total captures). Oracle kinds are
`scoreboard`, `sequence_tl_compare`, or `mixed_ral_read`. CRC32 uses the separate
pre_dv oracle kind `upstream_expected_file_compare`.

For example, the admitted rv_timer `rv_timer_random` entry preserves:

```json
{
  "id": "rv_timer_random",
  "sequence": "rv_timer_random_vseq",
  "oracle_kind": "scoreboard",
  "seed": 1,
  "run_options": [
    "+UVM_NO_RELNOTES", "+UVM_VERBOSITY=UVM_LOW",
    "+cdc_instrumentation_enabled=1",
    "+test_timeout_ns=10000000000"
  ],
  "completion_pattern": "Running test iteration (\\d+)/(\\d+)"
}
```

Full runnable examples are `targets/opentitan_{crc32,rv_timer,uart}/config.json`.
Only explicit upstream defaults and per-test options are used. The
10-second simulation-time override is retained only where the upstream test
already declares it (rv_timer_random and rv_timer_disabled); other tests retain
their upstream default timeout. The independent wall-clock cap is 2,400 seconds.
No stimulus, seed sweep, checker modification, or converted bench is introduced.

`same_csr_outstanding` is excluded from the current rv_timer admitted-test list
because repeated original executions were not reliable. Archived observations
of that test do not authorize its use as a detector. Preserve upstream options
for each admitted test, including `+en_scb=0` wherever the upstream flow uses it.

## Build and reproduce

Use a Python environment containing the runner requirements. Fetch the target
using the runner's `fetch` action and an absolute manifest, with a separate
scratch data root. Configure the installed backend tools explicitly; the paths
below are examples to replace with actual host installations:

```sh
export RTLPROBE_VERILATOR_PREDV=/absolute/predv-prefix/bin/verilator
export RTLPROBE_VERILATOR_UVM=/absolute/uvm-prefix/bin/verilator
export RTLPROBE_VERILATOR_UVM_SOURCE=/absolute/pinned-verilator-source
export RTLPROBE_FUSESOC=/absolute/python-env/bin/fusesoc
export PATH="/absolute/python-env/bin:$PATH"
```

The UVM build's configured source revision is recorded in the target manifest;
install the matching tools and Python build dependencies for that backend.
These commands require no local trial directory or agent checkout.
Run the regular CLI `qualify` action with the scratch `--data-root` and selected
`--target-config`. Its pending-control branch executes every admitted test on a
fresh original binary, emits `ORIGINAL_PROOF` lines, and seals
`original-proof.json`. It deliberately creates no qualified `design.json`.
`check` and mutation generation reject pending controls. Gate 1 remains incomplete.

The pre_dv recipe uses the unchanged upstream SV bench, C++ driver and simulation
support directly, avoiding FuseSoC's unnecessary Linux libraries. UVM performs
FuseSoC setup-only with the generic primitive mapping, applies diffs to exported
copies, unpacks the pristine UVM archive, applies library diffs, then invokes
Verilator `--binary --timing` with `-CFLAGS -O0`. Original copies and diffs remain
beside each patched file. The compatibility macro is also a unified diff,
creating a new file from an explicitly hashed empty input. All patch inputs and outputs are SHA-256 checked;
wrong upstream bytes fail before any patch is written, and reapplication is
idempotent. Nineteen OpenTitan source diffs and three UVM source diffs are present.
The fourth documented UVM change is `UVM_ENABLE_DEPRECATED_API`, a build define.

## Provenance and checker contracts

Every build gets a new object directory. Replays of the same mutant may reuse
that one executable; any change to source hashes or binary bytes requires a new
build. Build records include Verilator's reported elab/cvt/bld timing and measured
command walltime. Results include run walltime, exact run options, test and oracle
identity, and source/executable hashes. Batch cost records have separate build
and simulation timing. If an older Verilator omits timing components they remain
null, never inferred.

Fingerprints include backend identity, Verilator banner/revision/binary hash,
UVM tree and library edit hashes, patch manifest/diff/shim hashes, FuseSoC/Edalize
versions, and the admitted-test-list hash. The Homebrew pre_dv bottle reports
`vUNKNOWN-built20260228`; its source Git SHA is unavailable, so its version and
wrapper/native-binary SHA-256 values identify that prefix. SDKROOT and compiler selections are
recorded. UVM snapshots include all pinned regular Git files so setup generators
and dependencies are hashed; unrelated symlink assets are omitted. No OpenTitan
source tree is committed or copied into the runner repository.

CRC32 requires exactly 100 hex output lines, selects the upstream 98-value
window, checks all 98 values, and requires `$finish`, shutdown, and 104 cycles.
It does not claim the two preamble values as checked values.

UVM requires exactly one PASS/FAIL banner, one complete report-server summary,
consistent ERROR/FATAL counts, and `$finish` in order. PASS additionally requires
the intended test start and every reported iteration through the declared final
iteration, using unchanged upstream log messages. This is completion proof with
source-identified checkers, not measured comparison or coverage counts.
Missing or contradictory evidence is infrastructure_error; a wall-clock timeout
is timeout_unclassified. Nonzero exit or unexpected stderr cannot be a PASS.

The first UVM_ERROR/UVM_FATAL is the functional signature; all parsed failures
are also recorded. Each records file, line, report id, simulation time, message,
source category (`scoreboard_check`, `sequence_tl_compare`,
`register_model_read_compare`, `other`), and expected/actual values when their
orientation is identifiable. Unknown values remain null; raw operands and lines
are retained. No promotion policy is implemented here. The curation follow-up
must hold register-model-read comparisons with actual zero as
`ral_read_zero_signature`.

## Remaining gates

Execute approved controls and restored PASS for pending-control targets; complete structural/mapping support and frozen specification stores before
case admission. The original-only path cannot satisfy those gates. Preserve the
full archived controller and evidence when checking older fingerprints.

Each new host requires native toolchain setup and complete target qualification;
Mac original-only proofs do not qualify a Linux host. Set backend build jobs to
fit the destination CPU/memory budget and run one UVM build at a time on a small
host. Curation must hold ambiguous tool-related detections; the known zero-read
hold is a separate pending implementation, not a guarantee of this backend.

## Resource limits and saved proof validity

The Verilator manifests request a 12 GiB per-process address-space ceiling.
Runner records explicitly identify whether it is enforced: Linux RLIMIT_AS is
supported; this Mac records it as unavailable. This is not a claim of a total
process-tree memory cap. Wall-clock process-group timeouts and campaign CPU/disk
accounting are inherited from the runner. Native BaruaLabs qualification must
validate its resource settings before production.

A saved proof binds its source, executable, checker, implementation and tool
fingerprints. Historical runs may refer to a frozen controller copy recorded
with their evidence. A later implementation or tool change requires fresh
qualification; editing a guide does not update an old proof. Per-test fields are
authoritative for Verilator seed/run selection; legacy top-level fields remain
for compatibility with existing manifests.
