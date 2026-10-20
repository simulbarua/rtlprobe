# Datasets Tried

Open source RTL designs previously run through the pipeline. Clone them under
the root `vendor/` directory; they are not stored in the repo.

Each clone is pinned to the exact commit we tested, so everyone runs the
same code. Run the updated commands below from the repository root. Results
describe historical runs, before the launcher/path update; they are not fresh
validation of the current environment. Historical evidence remains in its original
location; new runs default to `outputs/`.

## PicoRV32 (RISC-V CPU core)

* Repo: https://github.com/YosysHQ/picorv32
* Tested commit: ef203c2b0a3f (2026-09-07)
* Layout: whole design in one file, picorv32.v; testbenches next to it.

```
mkdir -p vendor
git clone https://github.com/YosysHQ/picorv32.git vendor/picorv32
git -C vendor/picorv32 checkout ef203c2b0a3fb793280f5114941416c425c5b461
./tooling/pipeline.sh vendor/picorv32/picorv32.v vendor/picorv32/testbench_ez.v picorv32
```

* Result: all stages PASS.
* Notes: testbench_ez.v runs a tiny built-in program and prints no pass or
  fail message. testbench.v is the thorough test but needs compiled RISC-V
  firmware (FINDINGS items 4 and 5).

## SHA256 (hash core)

* Repo: https://github.com/secworks/sha256
* Tested commit: 837c5cc396f0 (2025-12-15)
* Layout: 4 design files in src/rtl, testbenches in src/tb.

```
mkdir -p vendor
git clone https://github.com/secworks/sha256.git vendor/sha256
git -C vendor/sha256 checkout 837c5cc396f001d18f2c765721c585716eb439ae
./tooling/pipeline.sh vendor/sha256/src/rtl vendor/sha256/src/tb/tb_sha256.v sha256
```

* Result: all stages PASS (waveform NOT_PRODUCED); testbench prints
  "All 05 test cases completed successfully".
* Notes: needs the folder as input, not a single file (FINDINGS item 1).
  The testbench doesn't support +vcd, so no waveform (FINDINGS item 2).

## SERV (bit-serial RISC-V CPU)

* Repo: https://github.com/olofk/serv
* Tested commit: f200eb2ed7b6 (2026-08-25)
* Layout: core in rtl/, system wrapper in servant/ and servile/, testbench
  and helpers in bench/, prebuilt test programs in sw/.

```
mkdir -p vendor
git clone https://github.com/olofk/serv.git vendor/serv
git -C vendor/serv checkout f200eb2ed7b69ac1c6b8eddd47654522aeee5ce8
./tooling/pipeline.sh vendor/serv/rtl vendor/serv/bench/servant_tb.v serv_rf_top
```

* Result: lint, synthesis and AST PASS (4,233 cells); compile FAIL, so no
  simulation yet.
* Notes: the testbench needs files from several folders plus vlog_tb_utils,
  which isn't in the repo (FINDINGS items 6 to 9).

Running it through FuseSoC instead (works). Open a shell in the container
from the repository root, then run:

```
docker run -it --rm -v "$PWD":/workspace -w /workspace rtlprobe-tools
mkdir -p outputs/serv-fusesoc
cd outputs/serv-fusesoc
pip install --break-system-packages fusesoc
fusesoc library add serv /workspace/vendor/serv
fusesoc library add vlog_tb_utils https://github.com/fusesoc/vlog_tb_utils
fusesoc run --target=sim award-winning:serv:servant
```

* Historical result: simulation ran and printed "Hi, I'm Servant!" and
  "Test complete". With the updated working-directory recipe, FuseSoC's file list
  would be saved under outputs/serv-fusesoc/build/ (FINDINGS item 9).

## Adding a dataset

Add a section with the repo, tested commit, layout, the exact clone and
pipeline commands, the result, and any FINDINGS items it led to.
