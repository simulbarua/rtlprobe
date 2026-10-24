# Verilator backend implementation report — October 24, 2026

Status: implementation complete; nine admitted tests have original-PASS observations.
CRC32 and UART have sealed original-only proofs. rv_timer repeatability remains
unresolved after two infrastructure-error attempts. The requested clean
aggregate rv_timer original proof could not be sealed; successful observations
are reported without treating them as repeatable qualification. No commits, cases, or OpenTitan
control mutants.

## 1. Files changed and diffstat

This session owns the backend modules, target manifests/adapters, patch bundle,
fixtures/tests, backend documentation, and backend integration edits. A concurrent
operator session owns mutation/front-end/operator/candidate files. The shared
README and batch.py totals below include its changes; those edits were preserved.

```text
README.md | +64 -1
rtlprobe/batch.py | +13 -1
rtlprobe/evidence.py | +16 -4
rtlprobe/oracle.py | +6 -2
rtlprobe/pilot.py | +21 -15
rtlprobe/target.py | +57 -2
targets/README.md | +20 -0
tooling/README.md | +15 -0
docs/Verilator_Backend_Report_2026-10-24.md | +496 -0
docs/verilator-backends.md | +146 -0
rtlprobe/backends/__init__.py | +11 -0
rtlprobe/backends/common.py | +124 -0
rtlprobe/backends/icarus.py | +25 -0
rtlprobe/backends/proof.py | +48 -0
rtlprobe/backends/uvm_patchset.py | +85 -0
rtlprobe/backends/verilator_predv.py | +13 -0
rtlprobe/backends/verilator_uvm.py | +43 -0
targets/opentitan_crc32/checker.py | +35 -0
targets/opentitan_crc32/config.json | +203 -0
targets/opentitan_crc32/expected.json | +100 -0
targets/opentitan_rv_timer/config.json | +190 -0
targets/opentitan_uart/config.json | +131 -0
targets/opentitan_uvm/checker.py | +110 -0
tests/fixtures/verilator/crc-fail.log | +121 -0
tests/fixtures/verilator/crc-pass.log | +121 -0
tests/fixtures/verilator/intr_test.log | +80 -0
tests/fixtures/verilator/rv_timer_disabled.log | +75 -0
tests/fixtures/verilator/rv_timer_random_reset.log | +77 -0
tests/fixtures/verilator/same_csr_outstanding.log | +76 -0
tests/fixtures/verilator/sources.json | +58 -0
tests/fixtures/verilator/tl_errors.log | +76 -0
tests/fixtures/verilator/uart_smoke.log | +76 -0
tests/fixtures/verilator/uart_tx_rx.log | +91 -0
tests/fixtures/verilator/uvm-duplicate-finish.log | +113 -0
tests/fixtures/verilator/uvm-fail.log | +74 -0
tests/fixtures/verilator/uvm-pass.log | +75 -0
tests/fixtures/verilator/uvm-timeout.log | +32 -0
tests/fixtures/verilator/uvm-truncated.log | +4231 -0
tests/test_backends.py | +177 -0
tooling/verilator-uvm/Accellera-1800.2-2017-1.0.tar.gz | binary 603679 bytes
tooling/verilator-uvm/LICENSE.opentitan.txt | +202 -0
tooling/verilator-uvm/LICENSE.uvm.txt | +201 -0
tooling/verilator-uvm/NOTICE.uvm.txt | +85 -0
tooling/verilator-uvm/README.md | +49 -0
tooling/verilator-uvm/patches/alert_agent.sv.patch | +19 -0
tooling/verilator-uvm/patches/alert_agent_cov.sv.patch | +14 -0
tooling/verilator-uvm/patches/alert_if.sv.patch | +15 -0
tooling/verilator-uvm/patches/cip_base_env_cov.sv.patch | +38 -0
tooling/verilator-uvm/patches/cip_base_scoreboard.sv.patch | +87 -0
tooling/verilator-uvm/patches/cip_base_test.sv.patch | +11 -0
tooling/verilator-uvm/patches/cip_base_vseq.sv.patch | +38 -0
tooling/verilator-uvm/patches/clk_rst_if.sv.patch | +45 -0
tooling/verilator-uvm/patches/csr_aliasing_seq.sv.patch | +20 -0
tooling/verilator-uvm/patches/csr_utils_pkg.sv.patch | +69 -0
tooling/verilator-uvm/patches/dv_base_test.sv.patch | +11 -0
tooling/verilator-uvm/patches/manifest.json | +286 -0
tooling/verilator-uvm/patches/ot_uvm_compat.svh.patch | +11 -0
tooling/verilator-uvm/patches/prim_onehot_check_if.sv.patch | +14 -0
tooling/verilator-uvm/patches/sec_cm_base_if_proxy.sv.patch | +11 -0
tooling/verilator-uvm/patches/tl_agent_cov.sv.patch | +26 -0
tooling/verilator-uvm/patches/tl_device_seq.sv.patch | +57 -0
tooling/verilator-uvm/patches/tl_host_seq.sv.patch | +15 -0
tooling/verilator-uvm/patches/tl_host_single_seq.sv.patch | +15 -0
tooling/verilator-uvm/patches/tl_seq_item.sv.patch | +11 -0
tooling/verilator-uvm/patches/uart_base_vseq.sv.patch | +13 -0
tooling/verilator-uvm/patches/uvm_component.svh.patch | +11 -0
tooling/verilator-uvm/patches/uvm_hdl.svh.patch | +12 -0
tooling/verilator-uvm/patches/uvm_traversal.svh.patch | +13 -0
docs/evidence/verilator-2026-10-24/ | 67 files, +5015 lines (full file list in manifest.json)
```

## 2. Manifest schema and example

Backend selection defaults to `icarus`; explicit alternatives are
`verilator_predv` and `verilator_uvm`. Verilator manifests add build recipes and
admitted tests with explicit oracle kind, upstream run options, seed, sequence,
and completion checkpoints. Controls remain `pending: front end`; original-only
proofs cannot authorize generation. Full example:

```json
{
  "schema_version": "backend-1",
  "repository_url": "https://github.com/lowRISC/opentitan.git",
  "revision": "3a7f6947247254fcc2fd05143c18a2646f75c7ee",
  "vendor": "vendor/opentitan",
  "lineage": "opentitan",
  "split_group": "opentitan",
  "track": "synthesizable",
  "compile_flags": [],
  "parameters": {},
  "seed": 1,
  "collateral": [
    "LICENSE"
  ],
  "specification": {
    "status": "pending",
    "required_before_acceptance": true
  },
  "coverage": {
    "status": "unavailable",
    "reason": "Covergroup code guarded out in UVM portability patches; pre_dv has no measured coverage."
  },
  "control": {
    "pending": "front end",
    "intended_site": "hw/ip/rv_timer/rtl/timer_core.sv:39 >= to >; relational replacement after front end; trial M1 precedent only"
  },
  "limits": {
    "compile_seconds": 1200,
    "simulation_seconds": 2400,
    "synthesis_seconds": 120,
    "campaign_seconds": 14400,
    "cpu_seconds": 100000,
    "disk_bytes": 30000000000,
    "workers": 1,
    "max_candidates": 10,
    "fallback_tests": 0,
    "memory_bytes": 12884901888
  },
  "scope": "Original-only proof; no gate-1 qualification or cases until controls, restoration, structural gates and spec store are complete.",
  "design": "rv_timer",
  "design_id": "opentitan_rv_timer",
  "target_id": "opentitan_rv_timer",
  "case_prefix": "opentitan-rv_timer",
  "backend": "verilator_uvm",
  "top": "rv_timer",
  "test_top": "tb",
  "testbench": "hw/ip/rv_timer/dv/tb/tb.sv",
  "rtl": [
    "hw/ip/rv_timer/rtl/rv_timer.sv",
    "hw/ip/rv_timer/rtl/timer_core.sv"
  ],
  "defines": [
    "UVM_NO_DPI",
    "UVM",
    "UVM_ENABLE_DEPRECATED_API",
    "UVM_REGEX_NO_DPI",
    "UVM_REG_ADDR_WIDTH=32",
    "UVM_REG_DATA_WIDTH=32",
    "UVM_REG_BYTENABLE_WIDTH=4",
    "SIMULATION",
    "DUT_HIER=tb.dut",
    "DV_VERILATOR_UVM"
  ],
  "build": {
    "core": "lowrisc:dv:rv_timer_sim",
    "jobs": 8,
    "flags": [
      "-Wno-fatal",
      "-Wno-lint",
      "-Wno-style",
      "--timescale",
      "1ns/1ps",
      "--error-limit",
      "200"
    ],
    "optimization": "-O0",
    "verilator_git_sha": "0041d207c3dcede92f48b86e0c7e2b70626cd86c"
  },
  "checker": {
    "path": "targets/opentitan_uvm/checker.py"
  },
  "vcs_equivalence_gap": "Not established; covergroups and DPI/backdoor checks unavailable, wait wake-up and RAL read-back defects remain. Mixed RAL zero-read signatures require later curation hold.",
  "admitted_tests": [
    {
      "id": "rv_timer_random",
      "sequence": "rv_timer_random_vseq",
      "oracle_kind": "scoreboard",
      "seed": 1,
      "run_options": [
        "+UVM_NO_RELNOTES",
        "+UVM_VERBOSITY=UVM_LOW",
        "+cdc_instrumentation_enabled=1",
        "+test_timeout_ns=10000000000"
      ],
      "completion_pattern": "Running test iteration (\\d+)/(\\d+)"
    },
    {
      "id": "rv_timer_disabled",
      "sequence": "rv_timer_disabled_vseq",
      "oracle_kind": "scoreboard",
      "seed": 1,
      "run_options": [
        "+UVM_NO_RELNOTES",
        "+UVM_VERBOSITY=UVM_LOW",
        "+cdc_instrumentation_enabled=1",
        "+test_timeout_ns=10000000000"
      ],
      "completion_pattern": "Running test iteration (\\d+)/(\\d+)"
    },
    {
      "id": "rv_timer_random_reset",
      "sequence": "rv_timer_random_reset_vseq",
      "oracle_kind": "scoreboard",
      "seed": 1,
      "run_options": [
        "+UVM_NO_RELNOTES",
        "+UVM_VERBOSITY=UVM_LOW",
        "+cdc_instrumentation_enabled=1"
      ],
      "completion_pattern": "Running test iteration (\\d+)/(\\d+)"
    },
    {
      "id": "same_csr_outstanding",
      "sequence": "rv_timer_common_vseq",
      "oracle_kind": "sequence_tl_compare",
      "seed": 1,
      "run_options": [
        "+UVM_NO_RELNOTES",
        "+UVM_VERBOSITY=UVM_LOW",
        "+cdc_instrumentation_enabled=1",
        "+run_same_csr_outstanding",
        "+en_scb=0"
      ],
      "completion_pattern": "Running same CSR outstanding test iteration (\\d+)/(\\d+)"
    },
    {
      "id": "intr_test",
      "sequence": "rv_timer_common_vseq",
      "oracle_kind": "mixed_ral_read",
      "seed": 1,
      "run_options": [
        "+UVM_NO_RELNOTES",
        "+UVM_VERBOSITY=UVM_LOW",
        "+cdc_instrumentation_enabled=1",
        "+run_intr_test"
      ],
      "completion_pattern": "Running intr test iteration (\\d+)/(\\d+)"
    },
    {
      "id": "tl_errors",
      "sequence": "rv_timer_common_vseq",
      "oracle_kind": "scoreboard",
      "seed": 1,
      "run_options": [
        "+UVM_NO_RELNOTES",
        "+UVM_VERBOSITY=UVM_LOW",
        "+cdc_instrumentation_enabled=1",
        "+run_tl_errors"
      ],
      "completion_pattern": "Running run_tl_errors_vseq (\\d+)/(\\d+)"
    }
  ],
  "upstream_option_sources": [
    "hw/dv/tools/dvsim/common_sim_cfg.hjson",
    "hw/ip/rv_timer/dv/rv_timer_sim_cfg.hjson",
    "hw/dv/tools/dvsim/tests/csr_tests.hjson",
    "hw/dv/tools/dvsim/tests/intr_test.hjson",
    "hw/dv/tools/dvsim/tests/tl_access_tests.hjson"
  ],
  "excluded_tests": {
    "csr_*": "csr_rd_check / RAL read-back defect",
    "tl_intg_err": "RAL read-back defect",
    "sec_cm": "DPI unavailable",
    "rv_timer_max": "RAL read-back defect",
    "rv_timer_min": "constraint solver limits",
    "stress_all_with_rand_reset": "constraint solver limits",
    "csr_mem_rw_with_rand_reset": "clone/solver limitation",
    "rv_timer_cfg_update_on_fly": "exceeded 40 minutes at -O0",
    "alert_test": "exceeded 40 minutes at -O0",
    "stress_all": "not in bounded admitted set"
  },
  "test_id": "rv_timer_random",
  "test_metadata": {
    "checkpoints": [
      "uvm_checks"
    ],
    "checker": "Unchanged upstream checker; require explicit completion and consistent summary",
    "coverage": "unavailable"
  }
}

```

## 3. Tests

Command (from runner root):

```sh
.venv-operators/bin/python -m unittest discover -s tests -q
```

Most recent result:

```text
Ran 105 tests in 3.015s

OK
```

Additional read-only/pristine-copy checks:

```text
ICARUS_FUNCTION_AST_IDENTICAL compile_design simulate
PATCH_PRISTINE_AND_IDEMPOTENT rv_timer 18
PATCH_PRISTINE_AND_IDEMPOTENT uart 19
PATCH_BUNDLE_HASHES_OK 23
```

The 72 pre-existing tests passed unchanged. The full suite also includes the
concurrent operator session's tests. SHA-256 and ChaCha manifests/checkers are
unchanged. Icarus build/run function ASTs match their former implementations.
No claim of byte-identical fingerprints: backend/implementation changes must
invalidate qualifications.

## 4. Mac original-PASS and checker proof output

All nine admitted tests have a PASS observation with the upstream options in
section 2 and the UART/CRC32 manifests. No control or restored step was run.
`same_csr_outstanding` always retained `+en_scb=0`.

The rv_timer initial run returned infrastructure_error for same-CSR. Its other
three completed tests, a continuation for intr_test/tl_errors, and a same-source,
same-binary, same-seed replay supply the six PASS observations below. The
continuation reuses only the identical original executable; no different RTL
hash shares that binary. The replay used a 120-second diagnostic wall cap and
passed in 18.25 seconds. Its simulator run options were unchanged.

The following is verbatim output of the record-summary command over the saved
results, **not reconstructed CLI stdout presented as captured output**. Each
result hash names the original full result file. The final adapter reparsed all
nine raw logs and returned the same PASS outcomes. Raw logs, exact commands,
checker hashes and compact provenance are retained under
`docs/evidence/verilator-2026-10-24/`.

```text
ORIGINAL_OBSERVATION {"checker_proof": {"comparisons_completed": 98}, "executable_sha256": "0b79c9d954f22cf18acd1ed0403ae51915038ec222ad84d81d25a544c7e5d498", "oracle_kind": "upstream_expected_file_compare", "outcome": "pass", "result_sha256": "3c93bf131869077a15596e3acaf73b37b6a6e32905960ab5116a36d968ea313d", "run_wall_seconds": 0.18427825000253506, "source_sha256": "fdcd0036e5c8b3e5b1ca683fdc763e5ba9486c416ecb3dcd9944d5153f08303d", "target": "opentitan_crc32", "test": "prim_crc32"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 1]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "scoreboard", "outcome": "pass", "result_sha256": "4019aac184a41b240e76fc748535e6d54fdc6428ab7d18ca57eaab93fcf7c18d", "run_wall_seconds": 50.71624808300112, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "rv_timer_random"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 1]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "scoreboard", "outcome": "pass", "result_sha256": "357ed20b35ac2f042c120969bdd7f63571c08c4a3483dd6ed7a0b5314642daa0", "run_wall_seconds": 79.41014775000804, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "rv_timer_disabled"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 3], [2, 3], [3, 3]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "scoreboard", "outcome": "pass", "result_sha256": "9fdded16220e5a89be9df6250a9a49971dfc190a9b4d2b4ca027831a8084b387", "run_wall_seconds": 264.61879833399144, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "rv_timer_random_reset"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6], [6, 6]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "mixed_ral_read", "outcome": "pass", "result_sha256": "6ba56636ac553de6a3100762b251d9a2ba2cb1b5b4400f044dface0b208aeea7", "run_wall_seconds": 5.983191374994931, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "intr_test"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 2], [2, 2]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "scoreboard", "outcome": "pass", "result_sha256": "615fc5106e15658ee31d5c22b223cc59935f452b19fee1f3b9e949888e043e05", "run_wall_seconds": 184.90065962499648, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "tl_errors"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 2], [2, 2]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "sequence_tl_compare", "outcome": "pass", "result_sha256": "1e731162634161e6cf0a2b5da89f9e9948e6c6b66f8f04eecab3cba768c11093", "run_wall_seconds": 18.250010249990737, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "same_csr_outstanding"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 2], [2, 2]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "b8d0c28f357dd0245918fb61a19b0f1d982c5c775fe7b350299dc4e01e2cb20a", "oracle_kind": "mixed_ral_read", "outcome": "pass", "result_sha256": "9d63dca6ffed99290a3463f5027cce54c6d9d39c34c30a11b3dd06572a613733", "run_wall_seconds": 11.895331166000688, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_uart", "test": "uart_smoke"}
ORIGINAL_OBSERVATION {"checker_proof": {"finish": true, "iterations": [[1, 17], [2, 17], [3, 17], [4, 17], [5, 17], [6, 17], [7, 17], [8, 17], [9, 17], [10, 17], [11, 17], [12, 17], [13, 17], [14, 17], [15, 17], [16, 17], [17, 17]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "b8d0c28f357dd0245918fb61a19b0f1d982c5c775fe7b350299dc4e01e2cb20a", "oracle_kind": "mixed_ral_read", "outcome": "pass", "result_sha256": "8ea6dee4ac54bb8f1811022b8060023ad21f1336f9d07db25ae30ee87d705868", "run_wall_seconds": 1194.237609207994, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_uart", "test": "uart_tx_rx"}
```

Captured `qualify` stdout for CRC32, verbatim:

```text
ORIGINAL_PROOF {"checker_proof": {"comparisons_completed": 98}, "executable_sha256": "0b79c9d954f22cf18acd1ed0403ae51915038ec222ad84d81d25a544c7e5d498", "oracle_kind": "upstream_expected_file_compare", "outcome": "pass", "result_sha256": "3c93bf131869077a15596e3acaf73b37b6a6e32905960ab5116a36d968ea313d", "run_wall_seconds": 0.18427825000253506, "source_sha256": "fdcd0036e5c8b3e5b1ca683fdc763e5ba9486c416ecb3dcd9944d5153f08303d", "target": "opentitan_crc32", "test": "prim_crc32"}
ORIGINAL_PROOF_COMPLETE {"build_walltime_seconds": {"bld": 3.141, "command_wall_seconds": 3.2664329999970505, "cvt": 0.023, "elab": 0.001, "reported_total": 3.173}, "control": "pending front end", "evidence": "/private/tmp/rtlprobe-backend-uart-20261024/outputs/opentitan_crc32/original-proof/ed2b5b8f551e-20261024T224049858548Z", "fingerprint": "ed2b5b8f551e5dfabe68b5f05a6bd27e0d9c2759774fb7b19a359e2e2210ac89", "gate_1_complete": false, "manifest_sha256": "43e4e3fce0c076b35f38fc74760d903b8d44f38f55d2ddc383ef15f5a31deb84", "restored": "pending front end", "target": "opentitan_crc32"}
```

Captured `qualify` stdout for UART, verbatim:

```text
ORIGINAL_PROOF {"checker_proof": {"finish": true, "iterations": [[1, 2], [2, 2]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "b8d0c28f357dd0245918fb61a19b0f1d982c5c775fe7b350299dc4e01e2cb20a", "oracle_kind": "mixed_ral_read", "outcome": "pass", "result_sha256": "9d63dca6ffed99290a3463f5027cce54c6d9d39c34c30a11b3dd06572a613733", "run_wall_seconds": 11.895331166000688, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_uart", "test": "uart_smoke"}
ORIGINAL_PROOF {"checker_proof": {"finish": true, "iterations": [[1, 17], [2, 17], [3, 17], [4, 17], [5, 17], [6, 17], [7, 17], [8, 17], [9, 17], [10, 17], [11, 17], [12, 17], [13, 17], [14, 17], [15, 17], [16, 17], [17, 17]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "b8d0c28f357dd0245918fb61a19b0f1d982c5c775fe7b350299dc4e01e2cb20a", "oracle_kind": "mixed_ral_read", "outcome": "pass", "result_sha256": "8ea6dee4ac54bb8f1811022b8060023ad21f1336f9d07db25ae30ee87d705868", "run_wall_seconds": 1194.237609207994, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_uart", "test": "uart_tx_rx"}
ORIGINAL_PROOF_COMPLETE {"build_walltime_seconds": {"bld": 23.738, "command_wall_seconds": 106.27123595800367, "cvt": 80.5, "elab": 0.836, "reported_total": 106.198}, "control": "pending front end", "evidence": "/private/tmp/rtlprobe-backend-uart-20261024/outputs/opentitan_uart/original-proof/d1e9c93b8ac7-20261024T224055789289Z", "fingerprint": "d1e9c93b8ac7df9093e97e54c5b544a83f82565f2d7e2c101ce036903b1cc4c8", "gate_1_complete": false, "manifest_sha256": "5eab5bb07035eecc143fdbb6e8e61ea00b875b2bafa8fae6924034ccb0edd39d", "restored": "pending front end", "target": "opentitan_uart"}
```

Captured rv_timer continuation/replay stdout, verbatim:

```text
ORIGINAL_PROOF {"checker_proof": {"finish": true, "iterations": [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6], [6, 6]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "mixed_ral_read", "outcome": "pass", "result_sha256": "6ba56636ac553de6a3100762b251d9a2ba2cb1b5b4400f044dface0b208aeea7", "run_wall_seconds": 5.983191374994931, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "intr_test"}
ORIGINAL_PROOF {"checker_proof": {"finish": true, "iterations": [[1, 2], [2, 2]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "oracle_kind": "scoreboard", "outcome": "pass", "result_sha256": "615fc5106e15658ee31d5c22b223cc59935f452b19fee1f3b9e949888e043e05", "run_wall_seconds": 184.90065962499648, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "target": "opentitan_rv_timer", "test": "tl_errors"}
ORIGINAL_CONTINUATION_COMPLETE {"evidence": "/private/tmp/rtlprobe-backend-rv-remaining-20261024", "gate_1_complete": false, "manifest_sha256": "3e45c5ec68cc0dd15b2d73c0b76d5f448b27adbfc976a7a178eb250d0cb3f39a"}
ORIGINAL_DIAGNOSTIC {"completion": {"finish": true, "iterations": [[1, 2], [2, 2]], "summary": true, "verdict": "TEST PASSED CHECKS"}, "evidence": "/private/tmp/rtlprobe-backend-same-csr-replay-20261024", "executable_sha256": "3e806b666c1376c4eae7125e684967165cf1671c37161430df3db4204802d9f8", "manifest_sha256": "93022169b9f0d4ed45e7e5491eee152e4745d985b9f1e25c335b044a1a22e26e", "outcome": "pass", "result_sha256": "1e731162634161e6cf0a2b5da89f9e9948e6c6b66f8f04eecab3cba768c11093", "run_wall_seconds": 18.250010249990737, "source_sha256": "3281b97c1a1b8b7631415ab57b34ddb7d5f095e9ef67cb38b9ed5d5386a10e57", "test": "same_csr_outstanding"}
```

The initial rv_timer CLI stdout file is empty. Its individual atomic result and
command records, plus simulator stdout/stderr, are intact; the record-summary
output above supplies the hashes/timing without claiming a captured CLI transcript.
The rv_timer continuation is not a sealed all-tests `qualify` success.

| Original build | elab (s) | cvt (s) | bld (s) | command wall (s) |
| --- | ---: | ---: | ---: | ---: |
| CRC32 | 0.001 | 0.023 | 3.141 | 3.266433 |
| rv_timer, primary observations | 0.866 | 60.240 | 22.255 | 84.524887 |
| UART | 0.836 | 80.500 | 23.738 | 106.271236 |

The first same-CSR attempt exited 0 after **826.6143066249933 seconds**, without
hitting the wall-clock cap. The adapter rejected its duplicate report summaries,
verdict banners and `$finish` records as `infrastructure_error`. Selected raw
lines, verbatim:

```text
UVM_FATAL @ 10047804935 ps: (cip_base_vseq.sv:915) [uvm_test_top.env.virtual_sequencer.rv_timer_common_vseq] timeout occurred!
TEST FAILED CHECKS
UVM_ERROR @ 10047804935 ps: (cip_base_vseq.sv:935) uvm_test_top.env.virtual_sequencer [uvm_test_top.env.virtual_sequencer.rv_timer_common_vseq] Alert fatal_fault fired unexpectedly.
TEST FAILED CHECKS
```

That attempt is retained in `same-csr-infrastructure-attempt-1/` and as a
regression fixture. Its stdout SHA-256 is
`4b40421ca272a3a2ac20e999c2e5d9e384169be3a69f07988a3154d6c43e7485`.
The fresh rerun, using the final adapter and a new build, also returned
`infrastructure_error` after **817.6214235420048 seconds**, exit 0, wall-clock
timeout false. It emitted the same two failure messages and duplicate completion
records. Its fingerprint is
`b92769fe41887e2f1f1a02f57831812b8043c7f5c1fae43a7aa904c518bbb681`. Its executable SHA-256 is
`a59b6a7770cc04a4410f4e406221e151cb16cda48ab8d157b5a6f2800e16b3d6`,
result SHA-256 is
`e903fb44faa097b0cd165c84119faf0e31ae13950496db008229595fc15aa0c5`,
and stdout SHA-256 is
`1f9be50a21546c7694d8b1f6e32320fdd05ab3073aec6901a03599c4c911e1d2`.
The fresh run's earlier random/disabled/random-reset tests passed; all its
completed records are retained under `same-csr-infrastructure-attempt-2/`.
Its CLI stdout file is also empty, so no captured CLI transcript is claimed.

The successful same-CSR replay used the original binary bytes with a different
executable path and working directory. The cause of the differing outcomes has
not been isolated. No additional HDL portability patch or altered upstream
option was introduced to force a PASS.


Fresh rerun build timing: `{"bld": 23.178, "command_wall_seconds": 83.43283749998955, "cvt": 58.27, "elab": 0.79, "reported_total": 83.322}`.
Its completed PASS walltimes: `{"rv_timer_disabled": 77.05260433300282, "rv_timer_random": 49.89180137500807, "rv_timer_random_reset": 270.07481116699637}`.

The compact archive was verified against its final manifest:

```text
FINAL_ARCHIVE_VERIFIED tests=9 pass_observations; additional_attempts=2 infrastructure_error
ARCHIVE_MANIFEST_SHA256 e7bb11e597c14ab82442d82db7fdbfb0c7087a509d51946ff36b4b1e57cd7439
```

## 5. Deviations and limitations

- A clean aggregate rv_timer original proof was not achieved. Nine admitted
  tests have PASS observations, but two same-CSR attempts were rejected. Further
  qualification requires resolving this discrepancy; no benchmark admission is
  implied by the successful replay.
- Three UVM source diffs implement three library edits. The fourth documented
  edit is the `UVM_ENABLE_DEPRECATED_API` build define. The compatibility shim
  is a new-file unified diff with an explicit empty-input SHA-256.
- `intr_test` is conservatively `mixed_ral_read`, as requested. Each failure
  records its source and expected/actual values when identifiable. The curation
  hold policy is not implemented in this session.
- Successful aggregate original proof status is `original_pass_only`, never
  `qualified`; the rv_timer mixed-outcome observations are not an aggregate success. No control,
  restored execution, structural admission, case production, or promotion occurs.
- All proof source/build artifacts are in a separate temporary root, not the live
  data root. The pinned OpenTitan checkout was fetched through fetch-design.sh.
- The first setup attempt exposed loss of executable permission in the existing
  snapshot copier. Verilator snapshots now preserve modes; Icarus copying is
  unchanged. No new HDL portability edit was required.
- Preliminary runs were superseded after concurrent front-end edits invalidated
  a fingerprint and after the compatibility shim was packaged as a unified diff.
  Their logs remain available; they are not final proof evidence.
- Proofs use frozen controller copies under ignored outputs so concurrent
  checkout edits cannot change a running proof. The saved implementation and
  fingerprint identify that exact snapshot. The final adapter adds shared
  interrupt-cleanup RAL and TL-response failure mappings. Saved checker hashes
  distinguish original execution from log-only revalidation; no old proof is
  represented as fresh qualification under a changed fingerprint.
- The Homebrew pre_dv prefix reports `vUNKNOWN-built20260228`, so a full
  source Git SHA cannot be recovered from its banner. Its 5.046 version, wrapper
  SHA-256 and native binary SHA-256 are recorded. The UVM prefix has the full
  pinned Git SHA. No source SHA is invented for the Homebrew bottle.
- Native macOS address-space limits are not enforced; records explicitly say
  unavailable. Linux supports the configured per-process RLIMIT_AS limit.
  Wall-clock timeouts and existing campaign CPU/disk accounting remain enforced.
- UVM completion proof uses upstream iteration logs, report counts and finish;
  it does not invent comparison counts or claim measured coverage/VCS equivalence.

## 6. Follow-ups

1. After front-end/operator integration, select approved controls, execute control
   FAIL and restored PASS, and finish structural/mapping gates. Do not convert
   these original-only proofs into qualified dossiers manually.
2. Implement the curation `ral_read_zero_signature` hold for register-model read
   comparisons whose actual value is zero, including normalization of decimal
   and hexadecimal zero. Preserve other failure-source categories.
3. Curate and freeze independent OpenTitan specification stores before acceptance.
4. Update the agents launcher for backend selection, three targets, original-only
   proof status, admitted-test oracle/options, host tool prefixes, durable console
   capture, and hold routing.
5. Deploy native prefixes on BaruaLabs and repeat complete qualification there;
   use one UVM build at a time and appropriate jobs for four CPUs. Mac proof is
   not BaruaLabs gate-1 evidence.
6. Investigate the same-seed same-CSR reproducibility discrepancy before gate 1;
   retain the infrastructure-error log alongside any successful original proof.
7. The user or Claude adds the reviewed project change-log row. No project files
   outside the runner were edited, and no commit was made by this session.

Proposed change-log row for the user/Claude to add after review (not written to
the project log by this session):

| 2026-10-24 | implementation verified | Verilator backend abstraction, per-source fresh builds, fingerprints, hash-checked portability diffs, and three OpenTitan manifests implemented. All nine admitted tests have Mac original-PASS observations and checker evidence; same_csr_outstanding also has two infrastructure-error attempts, so rv_timer repeatability remains unresolved. Controls/restored steps remain pending; no cases or commits. 105 runner tests pass. | Codex (implementation); reviewer to confirm | Backend brief items 1–4a and amended decision 5c | rtlprobe/docs/Verilator_Backend_Report_2026-10-24.md; compact evidence archive; controls, curation hold, launcher and BaruaLabs follow-ups |
