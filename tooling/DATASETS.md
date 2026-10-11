# Datasets Tried

Open source RTL designs we have run through the pipeline. Clone them into
this folder (next to pipeline.sh); they are not stored in the repo.

Each clone is pinned to the exact commit we tested, so everyone runs the
same code. Run the commands from this folder.

## PicoRV32 (RISC-V CPU core)

* Repo: https://github.com/YosysHQ/picorv32
* Tested commit: ef203c2b0a3f (2026-09-07)
* Layout: whole design in one file, picorv32.v; testbenches next to it.

```
git clone https://github.com/YosysHQ/picorv32.git
git -C picorv32 checkout ef203c2b0a3fb793280f5114941416c425c5b461
./pipeline.sh picorv32/picorv32.v picorv32/testbench_ez.v picorv32
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
git clone https://github.com/secworks/sha256.git
git -C sha256 checkout 837c5cc396f001d18f2c765721c585716eb439ae
./pipeline.sh sha256/src/rtl sha256/src/tb/tb_sha256.v sha256
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
git clone https://github.com/olofk/serv.git
git -C serv checkout f200eb2ed7b69ac1c6b8eddd47654522aeee5ce8
./pipeline.sh serv/rtl serv/bench/servant_tb.v serv_rf_top
```

* Result: lint, synthesis and AST PASS (4,233 cells); compile FAIL, so no
  simulation yet.
* Notes: the testbench needs files from several folders plus vlog_tb_utils,
  which isn't in the repo (FINDINGS items 6 to 9). Next step: try running it
  through FuseSoC using the repo's own file list, servant.core.

## Adding a dataset

Add a section with the repo, tested commit, layout, the exact clone and
pipeline commands, the result, and any FINDINGS items it led to.
