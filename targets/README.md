# RTL target manifests and checker adapters

Each target has an explicit JSON manifest and a trusted local Python checker
adapter. The runner loads both from the selected target configuration.

The manifest declares `target_id`, `case_prefix`, repository-lineage `split_group`,
`design_id`, `repository_url`, full pinned `revision`, data-relative `vendor`,
`top`, `test_top`, `test_id`, ordered `rtl`, existing `testbench`, `collateral`,
`compile_flags`, `defines`, `parameters`, `seed`, `track`, `limits`, `scope`,
`test_metadata` (checker description/checkpoints), `checker.path`, specification,
coverage status, and an AST-checkable negative `control` with an explicit approved
operator ID/version. Optional `dossier_notes` supplies target-specific scope notes.
See `sha256/config.json` for a real configured target.

Checker paths are relative to the main checkout, must stay within it, and name
trusted Python code exposing `classify(stdout, stderr, returncode, timed_out)`.
They return `outcome`, `reason`, `checkpoints`, and `signature`. Functional outcomes
require every declared checkpoint in order. Failed checkpoints form the signature
and carry `id`, `outcome`, `expected`, and `actual`. Incomplete/ambiguous simulator
output is an infrastructure error, never a detected bug. Adapters are fingerprinted
and frozen with qualification evidence; audit uses that frozen implementation.
Do not load arbitrary model-supplied or downloaded Python as a checker adapter.

Admission requires an existing usable testbench/checker, executed baseline PASS,
and detected separate checker control. Exclude/defer targets without a usable
existing checker. A source download or manifest is not qualification.

Current backend: deterministic unseeded Icarus compilation/simulation, Verilator
lint, and Yosys synthesis; empty defines/parameters. The two current operators have
narrow 32-bit AST preconditions. Unsupported sources/build systems need explicit
backend work; there is no claim of arbitrary-repository support or catalog discovery.
The tiny checker under `tests/fixtures/` is only a software regression fixture.

Use `scripts/rtlprobe.py --data-root /absolute/data --target-config /absolute/target.json qualify`.
There is no default target or data-root override. See [execution layout](../docs/execution-layout.md).

## secworks AES suites

[Upstream](aes/config.json) and [extended v1](aes/extended/config.json) use the
same pinned core revision and dataset split group. The extended bench is a
hash-bound runner asset with ten checkpoint windows for alternating encryption
and decryption under a reused key, rekeying from AES-128 to AES-256 and back to
a different AES-128 key, and resetting during key expansion and block processing.
Expected results use [NIST ECB examples](https://doi.org/10.6028/NIST.SP.800-38A)
and the [AES-128 example](https://doi.org/10.6028/NIST.FIPS.197-upd1).

A complete transcript with a known block mismatch produces a functional failure
signature. Protocol aborts and unknown results preserve their diagnostic reason as
incomplete evidence in v1, and cycle watchdogs are reported as timeouts. Trace
capture samples each completed result against `tb_aes_extended.dut.result`.

[Extended v2](aes/extended_v2/config.json) retains the same revision and checkpoint
sequence. Protocol violations and in-simulation cycle limits produce a named
terminal failure at the active checkpoint, with an expected and an observed value
for `ready` or `result_valid`. A block result containing `X` or `Z` produces a
comparison failure. Capture checks those values against the waveform. Simulator
process timeouts remain infrastructure outcomes.

Stage the extended manifest as `targets/aes/config.json` in a separate scoped
runner with its own data root. Use the [extended requirement mapping](aes/extended/requirements.jsonl)
as `targets/aes/spec/requirements.jsonl` in that runner. The upstream suite and
its qualification receipt continue to identify the initial 20-case baseline.
Measure incremental detection with a separately approved comparison before using
the extended suite for collection. Stage v2 in its own scoped runner and data
root so each suite resolves to its original evidence. The v2 manifest allows
900 seconds per operation and retains the individual command limits.

## OpenTitan original-only manifests

All three targets pin `3a7f6947247254fcc2fd05143c18a2646f75c7ee`, share lineage
`opentitan`, require pending specification stores, and have controls pending the
front end. IPs are designs within one lineage, not independent families. Shared
primitives and generated register RTL are not mutation candidates for the IPs.

| Target | Backend | Admitted tests and oracle |
|---|---|---|
| opentitan_crc32 | verilator_predv | prim_crc32: unchanged upstream expected-file comparison, 98 checkpoints |
| opentitan_rv_timer | verilator_uvm | rv_timer_random, rv_timer_disabled, rv_timer_random_reset, tl_errors: scoreboard; same_csr_outstanding: sequence_tl_compare; intr_test: conservatively mixed_ral_read |
| opentitan_uart | verilator_uvm | uart_smoke, uart_tx_rx: mixed_ral_read |

Each UVM test records its sequence, seed, upstream run options and existing
progress-log pattern. `same_csr_outstanding` retains `+en_scb=0`; no scoreboard is
enabled for it. `csr_rd_check` tests remain excluded. The manifests record the
other exclusions and the VCS-equivalence gap. A zero-valued register-model-read
failure signature must be held by the subsequent curation change; these manifests
and original-only proofs do not authorize promotion.
