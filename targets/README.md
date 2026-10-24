# RTL target manifests and checker adapters

Each target has an explicit JSON manifest and a trusted local Python checker
adapter. These are hardware integration assets owned by RTLProbe; agents select
and consume them without embedding repository names in their runtime.

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
