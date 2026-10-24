# Verilator UVM portability bundle

OpenTitan revision: `3a7f6947247254fcc2fd05143c18a2646f75c7ee`.
UVM distribution: Accellera 1800.2-2017-1.0, copied byte-for-byte from the
read-only October 24 trial archive. Its SHA-256 is `60466406956e4a6f1101198b1b6459f829ba0bae72c8850b7dac24cd79ecc466`.
The upstream UVM LICENSE and NOTICE and OpenTitan LICENSE are retained here.

`patches/manifest.json` binds every diff to its upstream and patched SHA-256.
OpenTitan patch paths are relative to FuseSoC's exported `src/`, whose bytes
are checked against pristine pinned upstream files. The original locations are
listed below. No OpenTitan source tree is vendored.

Nineteen OpenTitan diffs (18 shared plus UART's enum-domain patch), three UVM
source diffs, and one new-file compatibility shim diff reproduce the trial.
The fourth documented UVM edit is the build configuration change enabling
`UVM_ENABLE_DEPRECATED_API`; it is not represented as a fictitious source edit.
The shim's upstream hash is the SHA-256 of empty bytes and is explicitly marked
as a new file; it is not attributed to a nonexistent upstream file.

Application validates all selected input and diff hashes before writing any
patch, preserves `.upstream` and `.patch` files beside each patched copy, checks
output hashes, and is idempotent. The original fetched checkout is never patched.
`uvm_reg.svh.orig` from the trial produced no diff and is not included.

| Diff | Pristine upstream location |
|---|---|
| `alert_agent.sv.patch` | `hw/dv/sv/alert_agent/alert_agent.sv` |
| `alert_agent_cov.sv.patch` | `hw/dv/sv/alert_agent/alert_agent_cov.sv` |
| `alert_if.sv.patch` | `hw/dv/sv/alert_agent/alert_if.sv` |
| `cip_base_env_cov.sv.patch` | `hw/dv/sv/cip_lib/cip_base_env_cov.sv` |
| `cip_base_scoreboard.sv.patch` | `hw/dv/sv/cip_lib/cip_base_scoreboard.sv` |
| `cip_base_test.sv.patch` | `hw/dv/sv/cip_lib/cip_base_test.sv` |
| `cip_base_vseq.sv.patch` | `hw/dv/sv/cip_lib/seq_lib/cip_base_vseq.sv` |
| `clk_rst_if.sv.patch` | `hw/dv/sv/common_ifs/clk_rst_if.sv` |
| `csr_aliasing_seq.sv.patch` | `hw/dv/sv/csr_utils/csr_aliasing_seq.sv` |
| `csr_utils_pkg.sv.patch` | `hw/dv/sv/csr_utils/csr_utils_pkg.sv` |
| `dv_base_test.sv.patch` | `hw/dv/sv/dv_lib/dv_base_test.sv` |
| `prim_onehot_check_if.sv.patch` | `hw/dv/sv/sec_cm/prim_onehot_check_if.sv` |
| `sec_cm_base_if_proxy.sv.patch` | `hw/dv/sv/sec_cm/sec_cm_base_if_proxy.sv` |
| `tl_agent_cov.sv.patch` | `hw/dv/sv/tl_agent/tl_agent_cov.sv` |
| `tl_device_seq.sv.patch` | `hw/dv/sv/tl_agent/seq_lib/tl_device_seq.sv` |
| `tl_host_seq.sv.patch` | `hw/dv/sv/tl_agent/seq_lib/tl_host_seq.sv` |
| `tl_host_single_seq.sv.patch` | `hw/dv/sv/tl_agent/seq_lib/tl_host_single_seq.sv` |
| `tl_seq_item.sv.patch` | `hw/dv/sv/tl_agent/tl_seq_item.sv` |
| `uart_base_vseq.sv.patch` | `hw/ip/uart/dv/env/seq_lib/uart_base_vseq.sv` |
| `uvm_component.svh.patch` | `Accellera 1800.2-2017-1.0/src/base/uvm_component.svh` |
| `uvm_hdl.svh.patch` | `Accellera 1800.2-2017-1.0/src/dpi/uvm_hdl.svh` |
| `uvm_traversal.svh.patch` | `Accellera 1800.2-2017-1.0/src/base/uvm_traversal.svh` |
| `ot_uvm_compat.svh.patch` | `new file (empty input); trial compatibility shim` |
