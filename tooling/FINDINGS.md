# Pipeline Findings: Dataset Dependencies

Running log of what we learn when running different datasets through
pipeline.sh. Each item lists what happened, why, and options. To review
with Simul before deciding what to implement and what to ignore.

Datasets tried so far: PicoRV32 (single file), SHA256 (secworks/sha256, multi file),
SERV (olofk/serv, multi folder).

## Key finding so far
The hard part is telling the pipeline which files make up a design and its
testbench, and it is different for every repo. PicoRV32 is one file, SHA256
is one folder, and SERV needs specific files from four folders (rtl, servant,
servile, bench) plus one file that isn't in the repo at all. Grabbing whole
folders breaks too, because folders can hold unrelated files (SERV's servant/
folder has about 25 FPGA board files). Some repos already list their exact
files (SERV's FuseSoC servant.core), so the pipeline could read that list
instead of guessing. Tested on Oct 11: FuseSoC ran SERV's simulation in
our container (item 9). Question for Simul: do the repos in his catalog
come with file lists like that? Details in items 1, 6, 7, 8 and 9.

## 1. Designs can be split across multiple files
Status: IMPLEMENTED (folder approach)

* What happened: SHA256 failed compile, lint and synthesis when given only
  sha256.v. Compile log: "Unknown module type: sha256_core".
* Why: sha256.v uses sha256_core, which uses sha256_w_mem and
  sha256_k_constants. Those live in other files. PicoRV32 hid this because
  the whole design is in one file.
* Done: the design argument can now be a file or a folder. With a folder,
  every .v file in it is used.
  Example: ./pipeline.sh sha256/src/rtl sha256/src/tb/tb_sha256.v sha256
* Follow up (not done): smart match, where the tools search a folder for
  missing modules by file name (-y for Icarus and Verilator, -libdir for
  Yosys). Only pulls in files the design uses, but depends on files being
  named after their modules.
* For Simul: does his dataset keep design files in their own folder, without
  unrelated .v files mixed in?

## 2. Waveforms depend on the testbench
Status: LOGGED (not implemented)

* What happened: SHA256 run gives "waveform: NOT_PRODUCED". PicoRV32 works.
* Why: the script passes +vcd to the simulator. PicoRV32's testbench checks
  for that flag ($test$plusargs("vcd")) and then calls $dumpfile and
  $dumpvars. SHA256's testbench has no dump code, so nothing is written.
  The script also expects the file name testbench.vcd, which is just
  PicoRV32's choice.
* Option: the script compiles its own small dump module alongside the design
  and testbench, so waveforms work for any testbench without editing it.
  Replaces the +vcd approach. Needs the testbench's top module name
  (testbench for PicoRV32, tb_sha256 for SHA256).
* For Simul: do we need waveforms for every run, or only when debugging?
  They get large for long simulations.

## 3. Results folder name comes from the design folder name
Status: IMPLEMENTED (Oct 11): runs are named after the top module

* What happened: the SHA256 run was saved as rtl__tb-tb_sha256__top-sha256__...
* Why: the name is built from the design argument, and for SHA256 that is
  the folder sha256/src/rtl.
* Done: runs are named after the top module (e.g. sha256__tb-tb_sha256__<time>),
  so different datasets never end up with the same generic name like rtl.

## 4. "simulation: PASS" means the simulator finished, not that tests passed
Status: LOGGED (discussed, not tried together yet)

* What happened: PicoRV32's testbench.v reported simulation PASS earlier,
  but sim.log shows "Unable to open firmware/firmware.hex". Nothing was
  actually tested.
* Why: the script only checks whether the simulator exited cleanly.
  Testbenches report results in their own words: PicoRV32 prints
  "ALL TESTS PASSED", SHA256 prints "completed successfully", and some
  testbenches (PicoRV32 testbench_ez) print no verdict at all.
* Direction: read what the testbench prints in sim.log and look for its own
  pass or fail message. Each testbench words it differently, so the pass and
  fail text has to be known per testbench:
  - PicoRV32 testbench.v: "ALL TESTS PASSED" / "ERROR!"
  - SHA256 tb_sha256.v: "completed successfully" / "errors detected"
  - PicoRV32 testbench_ez.v: prints no verdict, only the CPU's activity. Would
    need comparing its output against a saved known good run instead.
* For Simul: for bug injection we need a real pass or fail per run. When his
  dataset adds a testbench, we need to know what it prints on pass and fail.

## 5. PicoRV32's main testbench needs firmware
Status: IMPORTANT (logged, not tried together yet)

* What happened: see item 4.
* Why: a CPU core needs a program to run. PicoRV32's testbench.v loads test
  programs (firmware) written for the RISC-V instruction set. They must be
  compiled into firmware/firmware.hex first, which needs a RISC-V compiler,
  a tool our Docker image does not have yet.
* Why it matters: testbench.v is the thorough test (checks the RISC-V
  instructions one by one). Without firmware, PicoRV32 is only tested by
  testbench_ez's tiny program, so many planted bugs could go unnoticed.
* Same pattern likely for any CPU core in the dataset: the test is a program,
  and building that program needs a compiler for that CPU's instruction set.
* For Simul: which testbenches should count for PicoRV32? Are other CPU cores
  planned, and do they come with prebuilt firmware or only source?

## 6. Testbench helpers and designs spread across several folders (SERV)
Status: LOGGED (not implemented)

* What happened: ./pipeline.sh serv/rtl serv/bench/servant_tb.v serv_rf_top
  gave lint, synthesis and AST PASS (core synthesized to 4,233 cells) but
  compile FAIL: "Unknown module type" for servant_sim, uart_decoder and
  vlog_tb_utils.
* Why: the CPU core in rtl/ is self contained, so design-only stages pass.
  The testbench needs helper files in bench/ (servant_sim, uart_decoder), and
  servant_sim pulls in files from servant/ and servile/. One design folder
  plus one testbench file can't describe this.
* For Simul: how are his dataset designs laid out? Single folder, or design,
  system wrapper and testbench helpers in separate folders?

## 7. A folder can contain files that must not be included (SERV)
Status: LOGGED (not implemented)

* What happened: servant/ holds the 6 files the simulation needs plus about
  25 FPGA board specific files (clock generators, board tops, a Quartus .sv).
* Why it matters: "use every .v file in the folder" (our item 1 approach)
  would pull in board files that break a simulation compile. The folder
  approach only works when a folder holds exactly one design.

## 8. Some dependencies aren't in the repo at all (SERV)
Status: LOGGED (not implemented)

* What happened: vlog_tb_utils is not anywhere in the SERV repo.
* Why: it is a shared utility pulled in by FuseSoC, a hardware package and
  build manager (servant.core says: depend fusesoc:utils:vlog_tb_utils).
* Options: fetch such dependencies separately, or install FuseSoC in the
  Docker image and let it resolve them.
* Tested (Oct 11): FuseSoC fetched it from
  https://github.com/fusesoc/vlog_tb_utils with one `fusesoc library add`.
  The big shared library (fusesoc-cores) only has an older copy under a
  different name, so it is not enough on its own.

## 9. The repo may already list its own files (SERV)
Status: TESTED (works for SERV; not part of the pipeline yet)

* What happened: SERV ships FuseSoC .core files (serv.core, servile.core,
  servant.core). servant.core lists exactly which files the simulation needs
  (bench/servant_tb.v, bench/servant_sim.v, bench/uart_decoder.v, six files
  from servant/, plus servile and the core) and its external dependencies.
* Why it matters: when a repo has such a file list (FuseSoC .core, a
  Makefile, a file list .f), reading it is more reliable than guessing from
  folders. Could be the long term answer to items 1, 6 and 7.
* Also noted: SERV ships prebuilt test programs (sw/*.hex), so unlike
  PicoRV32 no RISC-V compiler is needed. The testbench loads hello_uart.hex
  from the working folder, and that program prints text over a UART rather
  than a pass or fail message (same issue as item 4).
* Tested (Oct 11), inside the rtlprobe-tools container:
  ```
  pip install --break-system-packages fusesoc
  fusesoc library add serv ./serv
  fusesoc library add vlog_tb_utils https://github.com/fusesoc/vlog_tb_utils
  fusesoc run --target=sim award-winning:serv:servant
  ```
  Result: compiled and simulated with our pinned Icarus 12.0, printed
  "Hi, I'm Servant!" and "Test complete", finished cleanly.
* FuseSoC writes the list it used to
  build/award-winning_serv_servant_1.4.0/sim-icarus/*.scr: 32 Verilog
  files (only the 5 needed servant/ files, no FPGA board files), plus the
  defines and parameters. It also records the testbench top module
  (servant_tb) and the test program (hello_uart.hex). This is exactly the
  information our pipeline was missing.
* Possible way to use it later: let FuseSoC produce the file list, then
  have our pipeline run its own stages (lint, synthesis, AST, logs) from
  that list. FuseSoC is not in the Docker image yet; it was installed by
  hand for this test.
* For Simul: do the repos in his catalog have FuseSoC .core files, Makefiles
  or file lists we could read?
